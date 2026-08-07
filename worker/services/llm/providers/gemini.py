"""Google Gemini provider adapter."""

import os

from worker.services.llm.base import (
    LLMProvider,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


class GoogleGeminiProvider(LLMProvider):
    """Adapter for Google's Gemini models via the google-generativeai SDK."""

    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str = "gemini-1.5-flash"):
        self.model = model
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import google.generativeai as genai

            genai.configure(api_key=self._api_key)
            self._client = genai.GenerativeModel(self.model)
        return self._client

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        if not self._api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY is not configured")
        try:
            client = self._ensure_client()
            response = client.generate_content(prompt)
            return response.text
        except Exception as exc:  # noqa: BLE001 - translate SDK errors
            message = str(exc).lower()
            if "429" in message or "quota" in message or "rate" in message:
                raise ProviderRateLimitError(f"Gemini rate limited: {exc}") from exc
            raise ProviderUnavailableError(f"Gemini error: {exc}") from exc

