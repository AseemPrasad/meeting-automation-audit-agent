"""Anthropic Claude provider adapter."""

import os

from worker.services.llm.base import (
    LLMProvider,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


class AnthropicProvider(LLMProvider):
    """Adapter for Anthropic's Claude models via the anthropic SDK."""

    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str = "claude-3-5-sonnet"):
        self.model = model
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self._api_key)
        return self._client

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        if not self._api_key:
            raise ProviderUnavailableError("ANTHROPIC_API_KEY is not configured")
        try:
            client = self._ensure_client()
            message = client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(block.text for block in message.content)
        except Exception as exc:  # noqa: BLE001 - translate SDK errors
            status = getattr(exc, "status_code", None)
            message = str(exc).lower()
            if status == 429 or "rate" in message or "429" in message:
                raise ProviderRateLimitError(f"Anthropic rate limited: {exc}") from exc
            raise ProviderUnavailableError(f"Anthropic error: {exc}") from exc

