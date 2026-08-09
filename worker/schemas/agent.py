"""Deterministic structured-output schemas for the multi-agent graph.

Each node in the DAG produces and consumes these typed contracts. The nodes
validate LLM output against these Pydantic models (via ``LLMRouter``), which
makes extraction deterministic and failures loud instead of silent.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SpeakerSegment(BaseModel):
    """A single cleaned speaker segment."""

    speaker: str = Field(..., description="Normalized speaker name or label")
    text: str = Field(..., description="Normalized utterance text")
    order: int = Field(..., description="Zero-based position in the transcript")


class CleanedTranscript(BaseModel):
    """Output of the cleaner node."""

    cleaned_text: str = Field(
        ..., description="Normalized, formatting-fixed transcript text"
    )
    segments: List[SpeakerSegment] = Field(
        default_factory=list, description="Segmented speaker utterances"
    )


class ExtractedActionItem(BaseModel):
    """Output of the extractor node: an action item with confidence."""

    assignee: str = Field(..., description="Person or team responsible")
    task: str = Field(..., description="Concrete task to be performed")
    deadline: Optional[str] = Field(
        default=None, description="Due date if stated (free text or ISO date)"
    )
    priority: str = Field(
        default="medium",
        description="Priority level: low, medium, high, urgent",
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Extraction confidence in [0,1]"
    )


class ActionItemsExtraction(BaseModel):
    """Output of the action extractor node."""

    action_items: List[ExtractedActionItem] = Field(
        default_factory=list, description="Action items extracted from the meeting"
    )


class AuditedDecision(BaseModel):
    """Output of the auditor node: a decision with dissent flag."""

    decision: str = Field(..., description="The decision that was made")
    impact: Optional[str] = Field(
        default=None, description="Expected impact of the decision"
    )
    context: Optional[str] = Field(
        default=None, description="Background/context leading to the decision"
    )
    has_dissent: bool = Field(
        default=False, description="Whether there was explicit dissent"
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Audit confidence in [0,1]"
    )


class DecisionsExtraction(BaseModel):
    """Output of the decision auditor node."""

    decisions: List[AuditedDecision] = Field(
        default_factory=list, description="Key decisions made during the meeting"
    )


class QualityFinding(BaseModel):
    """A single quality inspection finding."""

    item_index: int = Field(..., description="Index into the source item list")
    item_type: str = Field(..., description="Either 'action' or 'decision'")
    issue: str = Field(..., description="Human-readable description of the issue")
    severity: str = Field(
        default="warning", description="Severity: info, warning, error"
    )


class QualityReport(BaseModel):
    """Output of the quality inspector node."""

    findings: List[QualityFinding] = Field(
        default_factory=list,
        description="Hallucination / omission / low-confidence findings",
    )
    overall_confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Overall confidence in [0,1]"
    )


class HumanReviewRequest(BaseModel):
    """Payload returned when the graph pauses for human verification."""

    job_id: str = Field(..., description="Job identifier the graph is processing")
    review_items: List[QualityFinding] = Field(
        default_factory=list,
        description="Low-confidence extractions awaiting human verdict",
    )
    pending_state: dict = Field(
        default_factory=dict,
        description="Serialized AgentState snapshot to resume from",
    )


class AgentGraphResult(BaseModel):
    """Composite output of the full agent graph run."""

    cleaned_transcript: CleanedTranscript
    action_items: List[ExtractedActionItem] = Field(default_factory=list)
    decisions: List[AuditedDecision] = Field(default_factory=list)
    quality: QualityReport = Field(default_factory=QualityReport)
    needs_human_review: bool = Field(default=False)
    reviewed: bool = Field(default=False)
