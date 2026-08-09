"""Evaluation pipeline orchestrator.

Ties together the pieces of the evaluation layer:

- ``metrics`` provides the deterministic numerical scores.
- ``judge`` provides the optional LLM-as-a-Judge faithfulness refinement.
- ``dataset_exporter`` persists low-scoring extractions for the benchmark set.

The public entry point ``evaluate`` accepts a transcript and a completed
analysis (with ``tasks`` and ``decisions``), optionally a set of
ground-truth action items for recall, and an optional ``LLMRouter`` for the
judge. It returns a dict with the computed scores, per-task verdicts, and a
flag indicating whether the sample was exported for benchmarking.

This module is fully additive and never raises on a bad sample: judge/exporter
failures degrade gracefully to deterministic behavior.
"""

from __future__ import annotations

from typing import List, Optional

from worker.eval.metrics import (
    compute_action_item_recall,
    compute_faithfulness,
    aggregate_scores,
)
from worker.eval.judge import judge_faithfulness
from worker.eval.dataset_exporter import record_evaluation
from worker.services.llm.router import LLMRouter


def _extract_claims(analysis: dict) -> List[str]:
    """Flatten tasks + decisions from an analysis dict into a claim list."""
    claims: List[str] = []
    for key in ("tasks", "decisions", "action_items"):
        items = analysis.get(key) or []
        claims.extend(
            str(i) for i in items if i and str(i).strip()
        )
    return claims


def evaluate(
    transcript: str,
    analysis: dict,
    *,
    ground_truth_tasks: Optional[List[str]] = None,
    router: Optional[LLMRouter] = None,
    tenant_id: Optional[str] = None,
    export_path: Optional[str] = None,
    faithfulness_weight: float = 0.5,
) -> dict:
    """Run the full evaluation on a completed extraction.

    Returns a dict containing:
    - ``faithfulness``: ``0.0 - 1.0`` (judge if available, else lexical)
    - ``action_item_recall``: ``0.0 - 1.0`` (vs. ground truth if provided)
    - ``overall_quality``: weighted combination
    - ``judge_used``: whether the LLM judge produced the faithfulness score
    - ``verdicts``: per-claim judge verdicts (list of dicts)
    - ``exported``: path written to the benchmark set, or ``None``
    """
    claims = _extract_claims(analysis)

    # 1. Faithfulness (LLM judge if router is provided, else lexical).
    judge_result = judge_faithfulness(
        claims, transcript, router, temperature=0.0
    )
    faithfulness = judge_result["faithfulness"]
    verdicts = judge_result["verdicts"]
    judge_used = judge_result["judge_used"]

    # 2. Action-item recall (only meaningful when ground truth is available).
    recall = compute_action_item_recall(
        claims, ground_truth_tasks or []
    )

    # 3. Aggregate into a single report.
    report = aggregate_scores(
        faithfulness, recall, faithfulness_weight=faithfulness_weight
    )
    report["judge_used"] = judge_used
    report["verdicts"] = verdicts

    # 4. Export low-scoring samples for the offline benchmark set.
    try:
        exported = record_evaluation(
            transcript,
            analysis,
            report,
            tenant_id=tenant_id,
            output_path=export_path,
        )
    except Exception:
        exported = None
    report["exported"] = exported

    return report
