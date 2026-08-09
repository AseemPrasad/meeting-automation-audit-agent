"""Framework-free DAG execution engine with human-in-the-loop interruption.

Executes the agent graph in topological order:

    clean -> [ extract_actions, audit_decisions ] -> inspect -> review

If the quality inspector flags low-confidence extractions, the graph pauses and
returns a ``HumanReviewRequest`` so an operator can verify before final
persistence. ``resume()`` applies the human verdicts and completes the run.
"""

from __future__ import annotations

from typing import Optional

from worker.agents.nodes.auditor import audit_decisions
from worker.agents.nodes.cleaner import clean
from worker.agents.nodes.extractor import extract_actions
from worker.agents.nodes.inspector import inspect
from worker.agents.state import AgentState
from worker.schemas.agent import AgentGraphResult, CleanedTranscript, HumanReviewRequest
from worker.services.llm.router import LLMRouter

# Any error/warning finding triggers a review pause.
REVIEW_SEVERITIES = {"error", "warning"}


class AgentGraph:
    """Acyclic state machine orchestrating the agent nodes."""

    def __init__(self, router: Optional[LLMRouter] = None):
        self.router = router

    def run(self, state: AgentState) -> HumanReviewRequest | AgentGraphResult:
        """Execute the full DAG. Returns a pause request or the final result."""
        clean(state, self.router)
        extract_actions(state, self.router)
        audit_decisions(state, self.router)
        inspect(state, self.router)

        # Decide whether to pause for human review.
        review_items = [
            f
            for f in (state.quality.findings if state.quality else [])
            if f.severity in REVIEW_SEVERITIES
        ]
        if review_items:
            state.needs_human_review = True
            return HumanReviewRequest(
                job_id=state.job_id,
                review_items=review_items,
                pending_state=state.to_dict(),
            )

        return self._finalize(state)

    def resume(
        self, state: AgentState, verdicts: dict[str, str]
    ) -> AgentGraphResult:
        """Apply human verdicts (e.g. 'keep'/'drop') and finalize the state."""
        state.reviewed = True
        state.human_verdicts = verdicts
        # Drop items the human marked for removal.
        drop = {
            k for k, v in verdicts.items() if v.lower() in {"drop", "remove", "reject"}
        }
        if drop:
            state.action_items = [
                it
                for it in state.action_items
                if it.task not in drop and str(it.task) not in drop
            ]
            state.decisions = [
                d
                for d in state.decisions
                if d.decision not in drop and str(d.decision) not in drop
            ]
        return self._finalize(state, reviewed=True)

    @staticmethod
    def _finalize(state: AgentState, reviewed: bool = False) -> AgentGraphResult:
        return AgentGraphResult(
            cleaned_transcript=(
                state.cleaned
                if state.cleaned
                else CleanedTranscript(cleaned_text=state.transcript)
            ),
            action_items=state.action_items,
            decisions=state.decisions,
            quality=state.quality,
            needs_human_review=state.needs_human_review,
            reviewed=reviewed or state.reviewed,
        )


def build_agent_graph(router: Optional[LLMRouter] = None) -> AgentGraph:
    """Factory for the agent graph (dependency-injectable for tests)."""
    return AgentGraph(router=router)
