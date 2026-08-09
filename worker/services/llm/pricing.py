"""LLM pricing table and cost estimation.

Provides a simple, additive cost-accounting helper. Given a provider, model and
token counts, it returns an estimated USD cost. Unknown models fall back to a
configurable default (defaults to $0.00) so that cost accounting never raises
or breaks an LLM call.
"""

from __future__ import annotations

import os
from typing import Tuple

# (input_per_1M, output_per_1M) in USD, keyed by (provider, model).
# Values are approximate list prices; adjust as needed.
PRICING_TABLE: dict[Tuple[str, str], Tuple[float, float]] = {
    ("groq", "llama-3.1-8b-instant"): (0.05, 0.08),
    ("groq", "llama-3.3-70b-versatile"): (0.59, 0.79),
    ("groq", "mixtral-8x7b-32768"): (0.24, 0.24),
    ("openai", "gpt-4o-mini"): (0.15, 0.60),
    ("openai", "gpt-4o"): (2.50, 10.00),
    ("openai", "gpt-4"): (30.00, 60.00),
    ("anthropic", "claude-3-5-sonnet-latest"): (3.00, 15.00),
    ("anthropic", "claude-3-haiku"): (0.25, 1.25),
    ("gemini", "gemini-1.5-flash"): (0.075, 0.30),
    ("gemini", "gemini-1.5-pro"): (1.25, 5.00),
}

# Applied when a model is not found in the table (USD per 1M tokens).
DEFAULT_INPUT_PER_1M = float(os.getenv("LLM_DEFAULT_INPUT_PER_1M", "0.0"))
DEFAULT_OUTPUT_PER_1M = float(os.getenv("LLM_DEFAULT_OUTPUT_PER_1M", "0.0"))


def lookup_price(provider: str, model: str) -> Tuple[float, float]:
    """Return (input_per_1M, output_per_1M) for a provider/model.

    Unknown entries return the configured defaults (never raises).
    """
    key = (provider or "").lower(), (model or "").lower()
    return PRICING_TABLE.get(key, (DEFAULT_INPUT_PER_1M, DEFAULT_OUTPUT_PER_1M))


def estimate_cost_usd(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimate the cost in USD for a single LLM call.

    Handles negative/zero token counts gracefully (returns 0.0).
    """
    if prompt_tokens is None or completion_tokens is None:
        return 0.0
    prompt_tokens = max(int(prompt_tokens), 0)
    completion_tokens = max(int(completion_tokens), 0)
    input_per_1m, output_per_1m = lookup_price(provider, model)
    cost = (
        prompt_tokens / 1_000_000 * input_per_1m
        + completion_tokens / 1_000_000 * output_per_1m
    )
    return round(cost, 6)


def register_price(
    provider: str, model: str, input_per_1m: float, output_per_1m: float
) -> None:
    """Dynamically insert/override a pricing entry (additive)."""
    PRICING_TABLE[(provider.lower(), model.lower())] = (
        float(input_per_1m),
        float(output_per_1m),
    )
