"""Action extractor node: extracts action items, assignees, and target deadlines."""

from __future__ import annotations

from worker.agents.state import AgentState
from worker.schemas.agent import ActionItemsExtraction
from worker.services.llm.prompting import extractor_prompt
from worker.services.llm.router import LLMRouter


def extract_actions(state: AgentState, router: LLMRouter | None = None) -> AgentState:
    """Run the action-extractor node over the cleaned transcript.

    Reuses the existing ``ActionItem`` schema fields (assignee, task, deadline,
    priority) plus a ``confidence`` score. Mutates ``state.action_items``.
    """
    if router is None:
        # No LLM available -> no items (caller decides to pause for review).
        state.action_items = []
        return state

    cleaned_text = state.cleaned.cleaned_text if state.cleaned else state.transcript
    try:
        result = router.generate_structured(
            extractor_prompt(cleaned_text), response_model=ActionItemsExtraction
        )
        state.action_items = result.action_items
    except Exception:
        state.action_items = []
    return state
