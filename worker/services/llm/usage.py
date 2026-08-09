"""Provider-agnostic token usage extraction.

Different LLM SDKs expose token counts in different shaped objects. This module
extracts ``(prompt_tokens, completion_tokens)`` from any provider response by
duck-typing the common accessor patterns. It never raises: if the response
carries no usage information it returns ``(0, 0)`` so that cost accounting is
best-effort and never breaks the caller.

It also provides a simple heuristic token estimator (``estimate_tokens``) for
paths where the provider discards raw usage information (e.g. the router only
receives the generated text string).
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


def _to_int(value) -> int:
    """Coerce a value to int, returning 0 on failure."""
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


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

    return _to_int(prompt_tokens), _to_int(completion_tokens)


def estimate_tokens(text) -> int:
    """Heuristic token estimate (~4 chars per token) for cost accounting.

    Used when a provider discards raw usage info (the router only receives the
    generated text). Approximation only; never raises.
    """
    if text is None:
        return 0
    try:
        return max(int(len(str(text)) / 4), 0)
    except Exception:  # noqa: BLE001 - never break on estimation
        return 0
