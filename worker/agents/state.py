"""AgentState: the typed state that flows through the agent DAG.

Holds the raw transcript, per-node outputs, confidence scores, and the
human-in-the-loop flag. Mutated by nodes in place as the graph executes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from worker.schemas.agent import (
    AuditedDecision,
    CleanedTranscript,
    ExtractedActionItem,
    QualityReport,
)


@dataclass
class AgentState:
    """Mutable state passed through the graph nodes."""

    transcript: str
    job_id: str = ""
    cleaned: Optional[CleanedTranscript] = None
    action_items: List[ExtractedActionItem] = field(default_factory=list)
    decisions: List[AuditedDecision] = field(default_factory=list)
    quality: Optional[QualityReport] = None
    # Confidence thresholds / flags
    needs_human_review: bool = False
    reviewed: bool = False
    # Human-supplied verdicts, keyed by finding description
    human_verdicts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict (for persistence / resume)."""
        return {
            "transcript": self.transcript,
            "job_id": self.job_id,
            "cleaned": self.cleaned.model_dump() if self.cleaned else None,
            "action_items": [a.model_dump() for a in self.action_items],
            "decisions": [d.model_dump() for d in self.decisions],
            "quality": self.quality.model_dump() if self.quality else None,
            "needs_human_review": self.needs_human_review,
            "reviewed": self.reviewed,
            "human_verdicts": self.human_verdicts,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        """Rehydrate a state from a serialized dict (for resume)."""
        state = cls(
            transcript=data.get("transcript", ""),
            job_id=data.get("job_id", ""),
            action_items=[
                ExtractedActionItem(**a) for a in data.get("action_items", [])
            ],
            decisions=[AuditedDecision(**d) for d in data.get("decisions", [])],
            needs_human_review=data.get("needs_human_review", False),
            reviewed=data.get("reviewed", False),
            human_verdicts=data.get("human_verdicts", {}),
        )
        if data.get("cleaned"):
            state.cleaned = CleanedTranscript(**data["cleaned"])
        if data.get("quality"):
            state.quality = QualityReport(**data["quality"])
        return state
