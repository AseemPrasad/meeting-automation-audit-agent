"""Dynamic LLM gateway configuration.

Reads provider selection and fallback chains from environment variables so
routing can be changed at runtime without code edits.
"""

import os
from dataclasses import dataclass, field

from worker.services.llm.circuit_breaker import CircuitBreaker
from worker.services.llm.providers.anthropic import AnthropicProvider
from worker.services.llm.providers.gemini import GoogleGeminiProvider
from worker.services.llm.providers.groq import GroqProvider
from worker.services.llm.providers.openai import OpenAIProvider


@dataclass
class LLMConfig:
    """Resolved LLM gateway configuration."""

    primary: str = "groq"
    fallbacks: list = field(default_factory=list)
    error_threshold: float = 0.5
    window_seconds: float = 60.0
    cooldown_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Build config from environment variables."""
        primary = os.getenv("LLM_PRIMARY", "groq").strip().lower()
        raw_fallbacks = os.getenv("LLM_FALLBACKS", "").strip()
        fallbacks = [
            item.strip().lower()
            for item in raw_fallbacks.split(",")
            if item.strip()
        ]
        return cls(
            primary=primary,
            fallbacks=fallbacks,
            error_threshold=float(
                os.getenv("LLM_CIRCUIT_ERROR_THRESHOLD", "0.5")
            ),
            window_seconds=float(
                os.getenv("LLM_CIRCUIT_WINDOW_SECONDS", "60")
            ),
            cooldown_seconds=float(
                os.getenv("LLM_CIRCUIT_COOLDOWN_SECONDS", "30")
            ),
        )

    def build_provider(self, name: str):
        """Instantiate a provider adapter by name.

        Returns None when the provider is not configured (missing API key)
        so the router can gracefully skip it.
        """
        factories = {
            "gemini": GoogleGeminiProvider,
            "anthropic": AnthropicProvider,
            "openai": OpenAIProvider,
            "groq": GroqProvider,
        }
        factory = factories.get(name)
        if factory is None:
            return None
        provider = factory()
        # If the provider reports no key, treat it as unconfigured.
        key_attr = {
            "gemini": "GEMINI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "groq": "GROQ_API_KEY",
        }.get(name)
        if key_attr and not os.getenv(key_attr):
            return None
        return provider

    def build_circuit_breaker(self) -> CircuitBreaker:
        """Create a circuit breaker using the configured policy."""
        return CircuitBreaker(
            error_threshold=self.error_threshold,
            window_seconds=self.window_seconds,
            cooldown_seconds=self.cooldown_seconds,
        )

