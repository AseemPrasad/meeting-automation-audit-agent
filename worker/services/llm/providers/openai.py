"""OpenAI provider adapter."""

import os
from typing import Type, TypeVar

from pydantic import BaseModel

from worker.services.llm.base import (
    LLMProvider,
    ProviderRateLimitError,
    ProviderUnavailableError,
    StructuredOutputError,
)

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider(LLMProvider):
    """Adapter for OpenAI's models via the openai SDK."""

    name = "openai"

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini"):
        self.model = model
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        if not self._api_key:
            raise ProviderUnavailableError("OPENAI_API_KEY is not configured")
        try:
            client = self._ensure_client()
            completion = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            return completion.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - translate SDK errors
            status = getattr(exc, "status_code", None)
            message = str(exc).lower()
            if status == 429 or "rate" in message or "429" in message:
                raise ProviderRateLimitError(f"OpenAI rate limited: {exc}") from exc
            raise ProviderUnavailableError(f"OpenAI error: {exc}") from exc

    def stream(self, prompt: str, temperature: float = 0.2, **kwargs):
        """Stream output token-by-token via the OpenAI SDK (stream=True)."""
        if not self._api_key:
            raise ProviderUnavailableError("OPENAI_API_KEY is not configured")
        try:
            client = self._ensure_client()
            stream = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None) or ""
                if text:
                    yield text
        except Exception as exc:  # noqa: BLE001 - translate SDK errors
            status = getattr(exc, "status_code", None)
            message = str(exc).lower()
            if status == 429 or "rate" in message or "429" in message:
                raise ProviderRateLimitError(f"OpenAI rate limited: {exc}") from exc
            raise ProviderUnavailableError(f"OpenAI error: {exc}") from exc

    def generate_structured(
        self, prompt: str, response_model: Type[T], temperature: float = 0.2
    ) -> T:
        """Native structured output via OpenAI's response_format JSON schema."""
        if not self._api_key:
            raise ProviderUnavailableError("OPENAI_API_KEY is not configured")
        try:
            client = self._ensure_client()
            completion = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": response_model.model_json_schema(),
                        "strict": True,
                    },
                },
            )
            raw = completion.choices[0].message.content or ""
            try:
                return response_model.model_validate_json(raw)
            except Exception as exc:  # noqa: BLE001 - validation failure
                raise StructuredOutputError(
                    f"OpenAI structured validation failed: {exc}"
                ) from exc
        except StructuredOutputError:
            # Fall back to the base text-based validation path.
            return super().generate_structured(prompt, response_model, temperature)
        except Exception as exc:  # noqa: BLE001 - translate SDK errors
            status = getattr(exc, "status_code", None)
            message = str(exc).lower()
            if status == 429 or "rate" in message or "429" in message:
                raise ProviderRateLimitError(f"OpenAI rate limited: {exc}") from exc
            raise ProviderUnavailableError(f"OpenAI error: {exc}") from exc
