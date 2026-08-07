"""LLM provider abstraction layer.

Defines the interface that all LLM provider adapters must implement, plus the
exception hierarchy used to translate provider-specific errors into a unified
set that the router can act upon (e.g. rate limits vs. hard outages).
"""

from abc import ABC, abstractmethod


class LLMProviderError(Exception):
    """Base exception for all LLM provider failures."""


class ProviderRateLimitError(LLMProviderError):
    """Raised when a provider returns HTTP 429 / rate limit exhaustion."""


class ProviderUnavailableError(LLMProviderError):
    """Raised on hard failures: outages, auth failures, timeouts, 5xx."""


class LLMProvider(ABC):
    """Interface every provider adapter must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier used in config, logs, and circuit tracking."""

    @abstractmethod
    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        """Run a single generation call and return the raw text output."""

