"""Groq provider adapter (compatibility with the existing pipeline).

Wraps the exact call currently used in the app (llama-3.1-8b-instant via the
Groq SDK) so the router can serve as a drop-in replacement without changing
the existing behavior when no other provider keys are configured.
"""

import os

from worker.services.llm.base import (
    LLMProvider,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


class GroqProvider(LLMProvider):
    """Adapter for Groq's hosted models via the groq SDK."""

    name = "groq"

    def __init__(self, api_key: str | None = None, model: str = "llama-3.1-8b-instant"):
        self.model = model
        self._api_key = api_key or os.getenv("GROQ_API_KEY")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from groq import Groq

            self._client = Groq(api_key=self._api_key)
        return self._client

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        if not self._api_key:
            raise ProviderUnavailableError("GROQ_API_KEY is not configured")
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
                raise ProviderRateLimitError(f"Groq rate limited: {exc}") from exc
            raise ProviderUnavailableError(f"Groq error: {exc}") from exc

