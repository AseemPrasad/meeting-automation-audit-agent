"""Quality inspector node: validates extracted outputs against source text.

Uses deterministic substring/entity cross-checks plus an optional LLM pass to
detect hallucinations and compute an overall confidence. Low-confidence items
are surfaced as findings that can trigger human-in-the-loop review.
"""

from __future__ import annotations

import re

from worker.agents.state import AgentState
from worker.schemas.agent import QualityFinding, QualityReport
from worker.services.llm.prompting import inspector_prompt
from worker.services.llm.router import LLMRouter

# Threshold below which an item is flagged as low-confidence.
CONFIDENCE_THRESHOLD = 0.4


def _strip_text(text: str) -> str:
    """Normalize for substring matching: lowercase, strip punctuation."""
    return re.sub(r"[^a-z0-9 ]", " ", text.lower())


def _content_supported(content: str, source: str) -> bool:
    """Check whether the meaningful words of ``content`` appear in ``source``."""
    words = [
        w
        for w in _strip_text(content).split()
        if len(w) > 3 and w not in {"the", "that", "with", "this", "from", "will"}
    ]
    if not words:
        return True
    return any(w in _strip_text(source) for w in words)


def _deterministic_inspect(state: AgentState) -> QualityReport:
    """Framework-free cross-validation of extracted items against source text."""
    source = state.cleaned.cleaned_text if state.cleaned else state.transcript
    source_norm = _strip_text(source)
    findings: list[QualityFinding] = []
    confidence_sum = 0.0
    count = 0

    for idx, item in enumerate(state.action_items):
        supported = _content_supported(item.task, source_norm)
        if not supported:
            findings.append(
                QualityFinding(
                    item_index=idx,
                    item_type="action",
                    issue=f"Action task not found in source: '{item.task}'",
                    severity="warning",
                )
            )
        if item.confidence < CONFIDENCE_THRESHOLD:
            findings.append(
                QualityFinding(
                    item_index=idx,
                    item_type="action",
                    issue=f"Low-confidence action ({item.confidence:.2f})",
                    severity="info",
                )
            )
        confidence_sum += item.confidence
        count += 1

    for idx, dec in enumerate(state.decisions):
        supported = _content_supported(dec.decision, source_norm)
        if not supported:
            findings.append(
                QualityFinding(
                    item_index=idx,
                    item_type="decision",
                    issue=f"Decision not found in source: '{dec.decision}'",
                    severity="warning",
                )
            )
        if dec.confidence < CONFIDENCE_THRESHOLD:
            findings.append(
                QualityFinding(
                    item_index=idx,
                    item_type="decision",
                    issue=f"Low-confidence decision ({dec.confidence:.2f})",
                    severity="info",
                )
            )
        confidence_sum += dec.confidence
        count += 1

    overall = confidence_sum / count if count else 1.0
    return QualityReport(findings=findings, overall_confidence=max(0.0, min(overall, 1.0)))


def inspect(state: AgentState, router: LLMRouter | None = None) -> AgentState:
    """Run the quality-inspector node. Mutates ``state.quality``."""
    report = _deterministic_inspect(state)
    if router is not None and (state.action_items or state.decisions):
        try:
            cleaned_text = state.cleaned.cleaned_text if state.cleaned else state.transcript
            llm_report = router.generate_structured(
                inspector_prompt(
                    cleaned_text, state.action_items, state.decisions
                ),
                response_model=QualityReport,
            )
            # Merge: start from deterministic, add any findings the LLM flagged.
            existing = {(f.item_index, f.item_type) for f in report.findings}
            for f in llm_report.findings:
                if (f.item_index, f.item_type) not in existing:
                    report.findings.append(f)
            report.overall_confidence = min(
                report.overall_confidence, llm_report.overall_confidence
            )
        except Exception:
            pass
    state.quality = report
    return state
