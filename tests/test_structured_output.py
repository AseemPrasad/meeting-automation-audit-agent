"""Tests for deterministic structured output via Pydantic schemas.

Covers the base provider validation path, the router's structured failover,
and the workflow's projection back to the legacy {summary, tasks, decisions}
contract. No external calls are made.
"""

import json

import pytest

from worker.schemas.transcript import MeetingAnalysisResponse
from worker.services.llm.base import (
    LLMProvider,
    ProviderUnavailableError,
    StructuredOutputError,
)
from worker.services.llm.router import LLMRouter
from worker.workflows.transcript_workflow import _extract_tasks_decisions


class _FakeProvider(LLMProvider):
    """Provider that returns scripted JSON strings for structured output."""

    def __init__(self, name, raw):
        self._name = name
        self.raw = raw
        self.calls = 0

    @property
    def name(self):
        return self._name

    def generate(self, prompt, temperature=0.2):
        self.calls += 1
        return self.raw


def _make_router(raw):
    from worker.services.llm.circuit_breaker import CircuitBreaker

    router = object.__new__(LLMRouter)
    object.__setattr__(router, "config", None)
    provider = _FakeProvider("fake", raw)
    object.__setattr__(
        router, "_chain", [(provider, CircuitBreaker(error_threshold=0.5))]
    )
    return router, provider


def test_base_structured_validates_json():
    """A valid JSON doc is parsed into the Pydantic model (no regex)."""
    provider = _FakeProvider(
        "fake",
        json.dumps(
            {
                "summary": "We picked a vendor.",
                "action_items": [
                    {"assignee": "Alice", "task": "Draft the SOW"}
                ],
                "key_decisions": [
                    {"decision": "Use vendor X", "impact": "Faster rollout"}
                ],
            }
        ),
    )
    result = provider.generate_structured(
        "prompt", response_model=MeetingAnalysisResponse
    )
    assert result.summary == "We picked a vendor."
    assert result.action_items[0].task == "Draft the SOW"
    assert result.key_decisions[0].decision == "Use vendor X"


def test_base_structured_raises_on_invalid():
    """Malformed output raises StructuredOutputError instead of silent parse."""
    provider = _FakeProvider("fake", "not json at all")
    with pytest.raises(StructuredOutputError):
        provider.generate_structured("p", response_model=MeetingAnalysisResponse)


def test_router_structured_return_value():
    """Router returns the validated model through the chain."""
    router, _ = _make_router(
        json.dumps(
            {
                "summary": "s",
                "action_items": [],
                "key_decisions": [],
            }
        )
    )
    result = router.generate_structured("p", response_model=MeetingAnalysisResponse)
    assert isinstance(result, MeetingAnalysisResponse)
    assert result.summary == "s"


def test_router_structured_empty_chain_raises():
    router = object.__new__(LLMRouter)
    object.__setattr__(router, "_chain", [])
    object.__setattr__(router, "config", None)
    with pytest.raises(ProviderUnavailableError):
        router.generate_structured("p", response_model=MeetingAnalysisResponse)


def test_workflow_projects_schema_to_legacy_contract(monkeypatch):
    """Workflow projects action_items/decisions back to flatten lists."""
    from worker.workflows import transcript_workflow as wf

    captured = {}

    class _FakeRouter:
        def generate_structured(self, prompt, response_model, temperature=0.2):
            captured["prompt"] = prompt
            return MeetingAnalysisResponse(
                summary="Meeting summary",
                action_items=[
                    {"assignee": "Bob", "task": "Send the report"}
                ],
                key_decisions=[
                    {"decision": "Ship in March", "impact": "On time"}
                ],
            )

    monkeypatch.setattr(wf, "llm_router", _FakeRouter())
    result = _extract_tasks_decisions(None, "some transcript text")

    assert result["summary"] == "Meeting summary"
    assert result["tasks"] == ["Send the report"]
    assert result["decisions"] == ["Ship in March"]
    assert "Transcript:" in captured["prompt"]
