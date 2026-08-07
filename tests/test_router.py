"""Tests for the LLM router fallback behavior (no external calls)."""

import pytest

from worker.services.llm.base import (
    LLMProvider,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from worker.services.llm.circuit_breaker import CircuitBreaker
from worker.services.llm.router import LLMRouter


class _FakeProvider(LLMProvider):
    """Synthetic provider returning scripted outcomes."""

    def __init__(self, name, outcomes):
        self._name = name
        self._outcomes = list(outcomes)
        self.calls = 0

    @property
    def name(self):
        return self._name

    def generate(self, prompt, temperature=0.2):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if outcome == "ok":
            return f"{self._name}-result"
        if outcome == "rate":
            raise ProviderRateLimitError(f"{self._name} 429")
        raise ProviderUnavailableError(f"{self._name} down")


def _make_router(primary_outcomes, fallback_outcomes):
    """Build a router with a scripted primary and fallback provider."""
    router = object.__new__(LLMRouter)
    router.config = None
    primary = _FakeProvider("primary", primary_outcomes)
    fallback = _FakeProvider("fallback", fallback_outcomes)
    object.__setattr__(
        router,
        "_chain",
        [
            (primary, CircuitBreaker(error_threshold=0.5)),
            (fallback, CircuitBreaker(error_threshold=0.5)),
        ],
    )
    return router, primary, fallback


def test_fails_over_to_fallback_on_rate_limit():
    router, primary, fallback = _make_router(["rate"], ["ok"])
    result = router.generate("hi")
    assert result == "fallback-result"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_fails_over_on_unavailable_primary():
    router, primary, fallback = _make_router(["down"], ["ok"])
    result = router.generate("hi")
    assert result == "fallback-result"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_raises_when_all_providers_fail():
    router, _, _ = _make_router(["down"], ["rate"])
    with pytest.raises(ProviderUnavailableError):
        router.generate("hi")


def test_empty_chain_raises():
    router = object.__new__(LLMRouter)
    object.__setattr__(router, "_chain", [])
    object.__setattr__(router, "config", None)
    with pytest.raises(ProviderUnavailableError):
        router.generate("hi")


def test_router_factory_builds_configured_providers(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    router = LLMRouter.from_env()
    # Should include groq (configured) and skip unconfigured providers.
    assert "groq" in router.chain_names

