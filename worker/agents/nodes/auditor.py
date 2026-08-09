"""Decision auditor node: identifies explicit decisions and dissent points."""

from __future__ import annotations

from worker.agents.state import AgentState
from worker.schemas.agent import DecisionsExtraction
from worker.services.llm.prompting import auditor_prompt
from worker.services.llm.router import LLMRouter


def audit_decisions(state: AgentState, router: LLMRouter | None = None) -> AgentState:
    """Run the decision-auditor node over the cleaned transcript.

    Reuses the existing ``KeyDecision`` fields (decision, impact, context) plus
    ``has_dissent`` and ``confidence``. Mutates ``state.decisions``.
    """
    if router is None:
        state.decisions = []
        return state

    cleaned_text = state.cleaned.cleaned_text if state.cleaned else state.transcript
    try:
        result = router.generate_structured(
            auditor_prompt(cleaned_text), response_model=DecisionsExtraction
        )
        state.decisions = result.decisions
    except Exception:
        state.decisions = []
    return state
