"""Provider-agnostic token usage extraction.

Different LLM SDKs expose token counts in different shaped objects. This module
extracts ``(prompt_tokens, completion_tokens)`` from any provider response by
duck-typing the common accessor patterns. It never raises: if the response
carries no usage information it returns ``(0, 0)`` so that cost accounting is
best-effort and never breaks the caller.
"""

from __future__ import annotations

from typing import Any, Tuple

# Common attribute names for prompt/input tokens across SDKs.
_PROMPT_ATTRS = ("prompt_tokens", "input_tokens", "promptTokenCount")
# Common attribute names for completion/output tokens across SDKs.
_COMPLETION_ATTRS = (
    "completion_tokens",
    "output_tokens",
    "candidatesTokenCount",
    "generated_tokens",
)


def _getattr_path(obj: Any, *attrs: str) -> Any:
    """Return the first attribute path that exists, else None."""
    for attr in attrs:
        current = obj
        ok = True
        for part in attr.split("."):
            if not hasattr(current, part):
                ok = False
                break
            current = getattr(current, part)
        if ok:
            return current
    return None


def extract_usage(response: Any) -> Tuple[int, int]:
    """Extract ``(prompt_tokens, completion_tokens)`` from a provider response.

    Supports:
      * OpenAI/Groq:  ``response.usage.prompt_tokens`` / ``completion_tokens``
      * Anthropic:    ``response.usage.input_tokens`` / ``output_tokens``
      * Gemini:       ``response.usage_metadata`` token counts (dict style)
    """
    if response is None:
        return 0, 0
    usage = getattr(response, "usage", None)
    if usage is None:
        usage = getattr(response, "usage_metadata", None)

    prompt_tokens = None
    completion_tokens = None

    # Duck-typing across attribute shapes.
    prompt_tokens = _getattr_path(
        usage, *_PROMPT_ATTRS, "prompt_token_count", "promptTokenCount"
    )
    completion_tokens = _getattr_path(
        usage, *_COMPLETION_ATTRS, "candidates_token_count"
    )

    # Fall back to dict-style access (Gemini usage_metadata etc.).
    if prompt_tokens is None and isinstance(usage, dict):
        prompt_tokens = usage.get(
            "prompt_tokens",
            usage.get("input_tokens", usage.get("promptTokenCount")),
        )
    if completion_tokens is None and isinstance(usage, dict):
        completion_tokens = usage.get(
            "completion_tokens",
            usage.get("output_tokens", usage.get("candidatesTokenCount")),
        )

    try:
        prompt_tokens = int(prompt_tokens) if prompt_tokens is not None else 0
    except (TypeError, ValueError):
        prompt_tokens = 0
    try:
        completion_tokens = (
            int(completion_tokens) if completion_tokens is not None else 0
        )
    except (TypeError, ValueError):
        completion_tokens = 0

    return prompt_tokens, completion_tokens
