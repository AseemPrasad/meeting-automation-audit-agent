"""Tests for the LLM pricing and usage instrumentation modules."""

from types import SimpleNamespace

from worker.services.llm.pricing import (
    estimate_cost_usd,
    lookup_price,
    register_price,
)
from worker.services.llm.usage import estimate_tokens, extract_usage


class TestPricing:
    def test_known_model_cost(self):
        cost = estimate_cost_usd("groq", "llama-3.1-8b-instant", 1_000_000, 1_000_000)
        # 0.05 + 0.08 = 0.13
        assert abs(cost - 0.13) < 1e-6

    def test_unknown_model_returns_zero(self):
        assert estimate_cost_usd("nope", "nope", 1000, 500) == 0.0

    def test_none_tokens_returns_zero(self):
        assert estimate_cost_usd("groq", "x", None, 500) == 0.0

    def test_zero_tokens_returns_zero(self):
        assert estimate_cost_usd("groq", "llama-3.1-8b-instant", 0, 0) == 0.0

    def test_register_price_overrides(self):
        register_price("test", "m", 1.0, 2.0)
        assert lookup_price("test", "m") == (1.0, 2.0)


class TestUsageExtraction:
    def test_openai_groq_shape(self):
        resp = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20)
        )
        assert extract_usage(resp) == (10, 20)

    def test_anthropic_shape(self):
        resp = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=10, output_tokens=20)
        )
        assert extract_usage(resp) == (10, 20)

    def test_gemini_dict_shape(self):
        resp = SimpleNamespace(
            usage_metadata={"promptTokenCount": 10, "candidatesTokenCount": 20}
        )
        assert extract_usage(resp) == (10, 20)

    def test_none_response(self):
        assert extract_usage(None) == (0, 0)

    def test_no_usage(self):
        assert extract_usage(SimpleNamespace(foo=1)) == (0, 0)


class TestTokenEstimate:
    def test_estimate(self):
        assert estimate_tokens("abcd abcd abcd abcd") > 0

    def test_estimate_none(self):
        assert estimate_tokens(None) == 0
