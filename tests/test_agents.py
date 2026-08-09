"""Tests for the multi-agent DAG graph and its nodes.

Uses a fake LLM router (no external calls) to exercise the cleaner, extractor,
auditor, inspector, and the human-in-the-loop pause/resume flow.
"""

from worker.agents.graph import build_agent_graph
from worker.agents.state import AgentState
from worker.schemas.agent import (
    ActionItemsExtraction,
    AuditedDecision,
    CleanedTranscript,
    DecisionsExtraction,
    ExtractedActionItem,
    QualityReport,
)


class _StubRouter:
    """Router stub that returns scripted structured outputs per prompt."""

    def __init__(self, cleaner=None, extractor=None, auditor=None, inspector=None):
        self.cleaner = cleaner
        self.extractor = extractor
        self.auditor = auditor
        self.inspector = inspector
        self.calls = []

    def generate_structured(self, prompt, response_model, temperature=0.2):
        self.calls.append(response_model.__name__)
        if response_model is CleanedTranscript:
            return self.cleaner
        if response_model is ActionItemsExtraction:
            return self.extractor
        if response_model is DecisionsExtraction:
            return self.auditor
        if response_model is QualityReport:
            return self.inspector
        raise AssertionError(f"Unexpected model: {response_model}")


def _make_router():
    return _StubRouter(
        cleaner=CleanedTranscript(
            cleaned_text="Alice: Finalize budget.\nBob: Draft report.",
            segments=[],
        ),
        extractor=ActionItemsExtraction(
            action_items=[
                {
                    "assignee": "Alice",
                    "task": "Finalize budget",
                    "priority": "high",
                    "confidence": 0.9,
                }
            ]
        ),
        auditor=DecisionsExtraction(
            decisions=[
                {
                    "decision": "Approve Q3 budget",
                    "has_dissent": False,
                    "confidence": 0.85,
                }
            ]
        ),
        inspector=QualityReport(findings=[], overall_confidence=0.9),
    )


def test_graph_executes_all_nodes_in_order():
    router = _make_router()
    graph = build_agent_graph(router=router)
    state = AgentState(transcript="raw text", job_id="j1")
    result = graph.run(state)

    assert router.calls == [
        "CleanedTranscript",
        "ActionItemsExtraction",
        "DecisionsExtraction",
        "QualityReport",
    ]
    assert (
        result.cleaned_transcript.cleaned_text
        == "Alice: Finalize budget.\nBob: Draft report."
    )
    assert len(result.action_items) == 1
    assert result.action_items[0].task == "Finalize budget"
    assert len(result.decisions) == 1
    assert result.decisions[0].has_dissent is False
    assert result.needs_human_review is False


def test_graph_pauses_for_human_review_on_low_confidence():
    router = _make_router()
    # Make the action task unsupported by the source text so the deterministic
    # inspector emits a warning-severity finding (triggers review).
    router.extractor = ActionItemsExtraction(
        action_items=[
            {
                "assignee": "Alice",
                "task": "Purchase quantum computers",
                "priority": "high",
                "confidence": 0.9,
            }
        ]
    )
    router.inspector = QualityReport(findings=[], overall_confidence=0.9)
    graph = build_agent_graph(router=router)
    state = AgentState(transcript="raw text", job_id="j2")
    request = graph.run(state)

    assert request.review_items[0].severity == "warning"
    assert request.job_id == "j2"
    assert request.pending_state["needs_human_review"] is True


def test_resume_applies_human_verdicts():
    router = _make_router()
    graph = build_agent_graph(router=router)
    state = AgentState(transcript="raw", job_id="j3")
    # Pre-populate items + a review flag as if the graph had paused.
    state.action_items = [
        ExtractedActionItem(assignee="A", task="keep me", confidence=0.9),
        ExtractedActionItem(assignee="B", task="remove me", confidence=0.9),
    ]
    state.decisions = [
        AuditedDecision(decision="drop this", confidence=0.9)
    ]
    state.quality = QualityReport(findings=[], overall_confidence=1.0)
    state.needs_human_review = True

    result = graph.resume(
        state,
        verdicts={"remove me": "drop", "drop this": "reject", "keep me": "keep"},
    )
    assert result.reviewed is True
    assert [a.task for a in result.action_items] == ["keep me"]
    assert result.decisions == []


def test_cleaner_falls_back_to_heuristic_without_router():
    graph = build_agent_graph(router=None)
    state = AgentState(
        transcript="Alice: We need to finalize the budget.\nBob: I will draft.",
        job_id="j4",
    )
    result = graph.run(state)
    assert result.cleaned_transcript.segments
    assert result.cleaned_transcript.segments[0].speaker == "Alice"
    assert result.reviewed is False


def test_state_roundtrip():
    state = AgentState(transcript="hello", job_id="j5")
    state.needs_human_review = True
    restored = AgentState.from_dict(state.to_dict())
    assert restored.transcript == "hello"
    assert restored.job_id == "j5"
    assert restored.needs_human_review is True
