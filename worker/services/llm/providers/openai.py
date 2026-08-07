"""OpenAI provider adapter."""

import os

from worker.services.llm.base import (
    LLMProvider,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


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

