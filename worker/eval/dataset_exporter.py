"""Benchmark dataset exporter for low-scoring extractions.

When an evaluation identifies a low-quality extraction (low faithfulness or low
action-item recall), this module records the offending sample to an offline
dataset store so it can be used later for fine-tuning and benchmark regression
testing.

The exporter writes JSONL lines to a configurable output directory (default
``data/eval_benchmark.jsonl``). Each line is a self-contained record that
includes the transcript, the extracted analysis, the scores that triggered
flagging, the tenant, and a timestamp. This is fully additive and file-based,
so it needs no schema changes and touches nothing existing.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

# Default scoring thresholds under which a sample is flagged for export.
DEFAULT_FAITHFULNESS_THRESHOLD = 0.7
DEFAULT_RECALL_THRESHOLD = 0.7

# Default output path (relative to the project root). Overridable via env or
# the ``output_path`` argument.
DEFAULT_OUTPUT_PATH = os.environ.get(
    "EVAL_BENCHMARK_PATH", "data/eval_benchmark.jsonl"
)


def _now_iso() -> str:
    """Current UTC time as ISO-8601 string."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def should_flag(
    faithfulness: float,
    action_item_recall: float,
    *,
    faithfulness_threshold: float = DEFAULT_FAITHFULNESS_THRESHOLD,
    recall_threshold: float = DEFAULT_RECALL_THRESHOLD,
) -> bool:
    """Return True if a sample should be exported for the benchmark set.

    A sample is flagged when either the faithfulness or the action-item recall
    falls below its configured threshold. Pure and deterministic.
    """
    return (faithfulness < faithfulness_threshold) or (
        action_item_recall < recall_threshold
    )


def build_record(
    transcript: str,
    analysis: dict,
    scores: dict,
    *,
    tenant_id: Optional[str] = None,
) -> dict:
    """Build a single self-contained benchmark record dict.

    ``scores`` is expected to contain at least ``faithfulness`` and
    ``action_item_recall`` (keys emitted by ``metrics.aggregate_scores``).
    """
    return {
        "version": 1,
        "timestamp": _now_iso(),
        "tenant_id": tenant_id,
        "transcript": transcript,
        "analysis": analysis,
        "scores": scores,
        "flagged": bool(scores.get("flagged", False)),
    }


def append_record(
    record: dict,
    output_path: Optional[str] = None,
) -> str:
    """Append a single record as a JSON line to the benchmark dataset.

    Creates the parent directory if needed. Returns the path written to.
    """
    path = Path(output_path or DEFAULT_OUTPUT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return str(path)


def record_evaluation(
    transcript: str,
    analysis: dict,
    scores: dict,
    *,
    tenant_id: Optional[str] = None,
    output_path: Optional[str] = None,
    force: bool = False,
) -> Optional[str]:
    """Log a completed extraction to the benchmark set if it scores low.

    Returns the path written (str) if the sample was flagged and persisted,
    or ``None`` if it was not flagged (or forced export wrote nothing because
    ``force=True`` always writes). ``force=True`` writes regardless of score.
    """
    faithfulness = float(scores.get("faithfulness", 1.0))
    recall = float(scores.get("action_item_recall", 1.0))
    flagged = force or should_flag(faithfulness, recall)

    if not flagged:
        return None

    payload_scores = dict(scores)
    payload_scores["flagged"] = True
    record = build_record(
        transcript, analysis, payload_scores, tenant_id=tenant_id
    )
    return append_record(record, output_path=output_path)
