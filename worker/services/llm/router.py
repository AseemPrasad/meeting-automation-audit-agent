"""LLM router with fallback chains and circuit breaker enforcement.

Routes each generation request through the primary provider first, then
automatically fails over to configured fallbacks on hard failures or
persistent rate limits (429s). Providers whose circuit is OPEN are skipped.
"""

from typing import List, Tuple

from worker.services.llm.base import (
    LLMProvider,
    LLMProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from worker.services.llm.circuit_breaker import CircuitBreaker
from worker.services.llm.config import LLMConfig


class LLMRouter:
    """Routes requests across providers with circuit breakers and failover."""

    def __init__(self, config: LLMConfig):
        self.config = config
        # Ordered list of (provider, circuit_breaker) pairs: primary first.
        self._chain: List[Tuple[LLMProvider, CircuitBreaker]] = []
        self._build_chain()

    def _build_chain(self) -> None:
        """Assemble the provider chain from config, skipping unconfigured ones."""
        names = [self.config.primary] + [
            f for f in self.config.fallbacks if f != self.config.primary
        ]
        seen = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            provider = self.config.build_provider(name)
            if provider is None:
                continue
            self._chain.append((provider, self.config.build_circuit_breaker()))

    @property
    def chain_names(self) -> list:
        """Names of providers currently in the chain (for logging/debugging)."""
        return [p.name for p, _ in self._chain]

    @property
    def circuit_states(self) -> dict:
        """Current circuit breaker state per provider (for observability)."""
        return {p.name: c.state for p, c in self._chain}

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        """Run the prompt through the provider chain with failover."""
        if not self._chain:
            raise ProviderUnavailableError(
                "No LLM providers are configured (set at least one API key)"
            )

        errors = []
        for provider, breaker in self._chain:
            if not breaker.allow_request():
                errors.append(
                    f"{provider.name}: circuit OPEN (skipped)"
                )
                continue

            try:
                result = provider.generate(prompt, temperature=temperature)
                breaker.record_success()
                return result
            except ProviderRateLimitError as exc:
                breaker.record_failure()
                errors.append(f"{provider.name}: rate limited -> {exc}")
                # Fall through to next provider for persistent 429s.
            except ProviderUnavailableError as exc:
                breaker.record_failure()
                errors.append(f"{provider.name}: unavailable -> {exc}")
                # Fall through to next provider.
            except LLMProviderError as exc:
                breaker.record_failure()
                errors.append(f"{provider.name}: error -> {exc}")
            except Exception as exc:  # noqa: BLE001 - unexpected errors
                breaker.record_failure()
                errors.append(f"{provider.name}: unexpected -> {exc}")

        raise ProviderUnavailableError(
            "All LLM providers failed. Details: " + " | ".join(errors)
        )

    @classmethod
    def from_env(cls) -> "LLMRouter":
        """Build a router from environment configuration."""
        return cls(LLMConfig.from_env())

