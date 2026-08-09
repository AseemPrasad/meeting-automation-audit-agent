"""LLM router with fallback chains and circuit breaker enforcement.

Routes each generation request through the primary provider first, then
automatically fails over to configured fallbacks on hard failures or
persistent rate limits (429s). Providers whose circuit is OPEN are skipped.

In addition to failover, the router records best-effort usage/cost metadata
for the most recent successful call (``last_usage``) for observability. This
is purely additive and never changes the return type or blocking behavior of
the public ``generate*`` methods.
"""

from typing import List, Tuple, Type, TypeVar

from pydantic import BaseModel

from worker.services.llm.base import (
    LLMProvider,
    LLMProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from worker.services.llm.circuit_breaker import CircuitBreaker
from worker.services.llm.config import LLMConfig
from worker.services.llm.pricing import estimate_cost_usd
from worker.services.llm.usage import estimate_tokens

T = TypeVar("T", bound=BaseModel)


class LLMRouter:
    """Routes requests across providers with circuit breakers and failover."""

    def __init__(self, config: LLMConfig):
        self.config = config
        # Ordered list of (provider, circuit_breaker) pairs: primary first.
        self._chain: List[Tuple[LLMProvider, CircuitBreaker]] = []
        self._build_chain()
        # Last completed call's usage/cost (best-effort observability).
        self.last_usage = {
            "provider": None,
            "model": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
        }

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

    def _record_usage(self, provider: LLMProvider, prompt: str, result) -> None:
        """Best-effort record of estimated usage/cost for the last call.

        Providers return plain text (discarding raw token counts), so token
        counts are estimated heuristically. Never raises.
        """
        try:
            prompt_tokens = estimate_tokens(prompt)
            completion_tokens = estimate_tokens(result)
            model = getattr(provider, "model", None) or provider.name
            self.last_usage = {
                "provider": provider.name,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": estimate_cost_usd(
                    provider.name, model, prompt_tokens, completion_tokens
                ),
            }
        except Exception:  # noqa: BLE001 - observability must never break calls
            pass

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
                self._record_usage(provider, prompt, result)
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

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        temperature: float = 0.2,
    ) -> T:
        """Run the prompt through the provider chain and validate output.

        Uses each provider's native structured-output support when available,
        otherwise falls back to text generation + schema validation. Applies
        the same circuit-breaker failover semantics as ``generate()``.
        """
        if not self._chain:
            raise ProviderUnavailableError(
                "No LLM providers are configured (set at least one API key)"
            )

        errors = []
        for provider, breaker in self._chain:
            if not breaker.allow_request():
                errors.append(f"{provider.name}: circuit OPEN (skipped)")
                continue

            try:
                result = provider.generate_structured(
                    prompt, response_model, temperature=temperature
                )
                breaker.record_success()
                self._record_usage(provider, prompt, result)
                return result
            except ProviderRateLimitError as exc:
                breaker.record_failure()
                errors.append(f"{provider.name}: rate limited -> {exc}")
            except ProviderUnavailableError as exc:
                breaker.record_failure()
                errors.append(f"{provider.name}: unavailable -> {exc}")
            except LLMProviderError as exc:
                breaker.record_failure()
                errors.append(f"{provider.name}: error -> {exc}")
            except Exception as exc:  # noqa: BLE001 - unexpected errors
                breaker.record_failure()
                errors.append(f"{provider.name}: unexpected -> {exc}")

        raise ProviderUnavailableError(
            "All LLM providers failed (structured). Details: " + " | ".join(errors)
        )

    @classmethod
    def from_env(cls) -> "LLMRouter":
        """Build a router from environment configuration."""
        return cls(LLMConfig.from_env())
