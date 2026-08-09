"""LLM provider abstraction layer.

Defines the interface that all LLM provider adapters must implement, plus the
exception hierarchy used to translate provider-specific errors into a unified
set that the router can act upon (e.g. rate limits vs. hard outages).
"""

import json
import re
from abc import ABC, abstractmethod
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMProviderError(Exception):
    """Base exception for all LLM provider failures."""


class ProviderRateLimitError(LLMProviderError):
    """Raised when a provider returns HTTP 429 / rate limit exhaustion."""


class ProviderUnavailableError(LLMProviderError):
    """Raised on hard failures: outages, auth failures, timeouts, 5xx."""


class StructuredOutputError(LLMProviderError):
    """Raised when a provider output cannot be validated against a schema."""


class LLMProvider(ABC):
    """Interface every provider adapter must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier used in config, logs, and circuit tracking."""

    @abstractmethod
    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        """Run a single generation call and return the raw text output."""

    def stream(self, prompt: str, temperature: float = 0.2, **kwargs):
        """Stream text output as incremental chunks.

        Default implementation yields the entire result as a single chunk by
        delegating to :meth:`generate`. Providers that support token-by-token
        streaming should override this method. This is a concrete (non-abstract)
        method so existing providers keep working unchanged.
        """
        yield self.generate(prompt, temperature=temperature)

    def generate_structured(
        self, prompt: str, response_model: Type[T], temperature: float = 0.2
    ) -> T:
        """Generate output validated against a Pydantic schema.

        Default implementation: calls ``generate()`` and validates the raw
        text against ``response_model``. Providers that support native
        structured output / function calling should override this method.
        """
        raw = self.generate(prompt, temperature=temperature)
        try:
            # Prefer JSON extraction first (models often wrap JSON in fences).
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return response_model.model_validate_json(match.group(0))
            return response_model.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise StructuredOutputError(
                f"{self.name}: output failed schema validation: {exc}"
            ) from exc
