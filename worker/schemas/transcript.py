"""Deterministic structured-output schemas for meeting transcript analysis.

These Pydantic models define the exact response contract the LLM is asked to
produce. By validating model output against these schemas (instead of parsing
unstructured text with regex), extraction becomes deterministic and failures
become loud instead of silent.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    """A single action item assigned during the meeting."""

    assignee: str = Field(
        ..., description="Person or team responsible for the action"
    )
    task: str = Field(..., description="Concrete task to be performed")
    deadline: Optional[str] = Field(
        default=None, description="Due date if stated (free text or ISO date)"
    )
    priority: str = Field(
        default="medium",
        description="Priority level: low, medium, high, urgent",
    )


class KeyDecision(BaseModel):
    """A decision made during the meeting."""

    decision: str = Field(..., description="The decision that was made")
    impact: Optional[str] = Field(
        default=None, description="Expected impact of the decision"
    )
    context: Optional[str] = Field(
        default=None, description="Background/context leading to the decision"
    )


class SpeakerSentiment(BaseModel):
    """Sentiment score for a single speaker."""

    speaker: str = Field(..., description="Speaker identifier or name")
    score: float = Field(
        ..., ge=-1.0, le=1.0, description="Sentiment score in [-1.0, 1.0]"
    )


class SentimentAnalysis(BaseModel):
    """Overall meeting sentiment plus per-speaker breakdown."""

    overall_score: float = Field(
        ..., ge=-1.0, le=1.0, description="Overall meeting sentiment in [-1.0, 1.0]"
    )
    speaker_sentiments: List[SpeakerSentiment] = Field(
        default_factory=list, description="Per-speaker sentiment scores"
    )


class MeetingAnalysisResponse(BaseModel):
    """Comprehensive payload wrapping all meeting analysis sections."""

    summary: str = Field(..., description="Short meeting summary")
    action_items: List[ActionItem] = Field(
        default_factory=list, description="Action items extracted from the meeting"
    )
    key_decisions: List[KeyDecision] = Field(
        default_factory=list, description="Key decisions made during the meeting"
    )
    sentiment: Optional[SentimentAnalysis] = Field(
        default=None, description="Meeting sentiment analysis"
    )

