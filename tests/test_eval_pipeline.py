"""Tests for the evaluation pipeline (metrics, judge, exporter, orchestrator).

All tests are deterministic and make no external calls. The judge is exercised
through a fake router and the fallback path (``router=None``).
"""

import json

import pytest

from worker.eval.metrics import (
    compute_faithfulness,
    compute_action_item_recall,
    aggregate_scores,
    token_set_similarity,
)
from worker.eval.judge import judge_faithfulness, parse_judge_json
from worker.eval.dataset_exporter import (
    should_flag,
    build_record,
    record_evaluation,
)
from worker.eval.pipeline import evaluate


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------
def test_faithfulness_supported_claim():
    """A claim fully present in the transcript scores 1.0."""
    score = compute_faithfulness(
        ["ship the product in march"], "we will ship the product in march"
    )
    assert score == 1.0


def test_faithfulness_hallucinated_claim():
    """A claim with no support in the transcript scores 0.0."""
    score = compute_faithfulness(
        ["team won the lottery in june"], "we will ship the product in march"
    )
    assert score == 0.0


def test_faithfulness_empty_claims_vacuous():
    """No claims to verify is vacuously faithful (1.0)."""
    assert compute_faithfulness([], "any transcript") == 1.0


def test_action_item_recall_full():
    assert compute_action_item_recall(["send report"], ["send report"]) == 1.0


def test_action_item_recall_none():
    assert compute_action_item_recall(["build rocket"], ["send report"]) == 0.0


def test_action_item_recall_partial_similarity():
    """Partial matches above the threshold count as recalled."""
    score = compute_action_item_recall(
        ["send weekly report"], ["send the report"], similarity_threshold=0.4
    )
    assert 0.0 < score <= 1.0


def test_aggregate_scores_default_weight():
    report = aggregate_scores(1.0, 0.5)
    assert report["faithfulness"] == 1.0
    assert report["action_item_recall"] == 0.5
    assert report["overall_quality"] == 0.75


def test_token_set_similarity_identical():
    assert token_set_similarity("send report", "send report") == 1.0


# ---------------------------------------------------------------------------
# judge
# ---------------------------------------------------------------------------
def test_judge_falls_back_without_router():
    """Without a router, judge degrades to the lexical baseline."""
    out = judge_faithfulness(["ship product in march"], "we will ship product")
    assert out["judge_used"] is False
    assert "faithfulness" in out and "verdicts" in out


class _VerdictRouter:
    def __init__(self, verdicts):
        self._verdicts = verdicts

    def generate_structured(self, prompt, response_model, temperature=0.0):
        return response_model(verdicts=self._verdicts)


def test_judge_uses_router_when_provided():
    """A provided router's verdicts drive the faithfulness score."""
    router = _VerdictRouter(
        [
            {"claim": "ship in march", "supported": True, "confidence": 0.9},
            {"claim": "win lottery", "supported": False, "confidence": 0.8},
        ]
    )
    out = judge_faithfulness(
        ["ship in march", "win lottery"], "we ship in march", router
    )
    assert out["judge_used"] is True
    assert out["faithfulness"] == 0.5
    assert len(out["verdicts"]) == 2


def test_judge_router_exception_falls_back():
    """A router that raises falls back to the lexical baseline, no crash."""

    class _BrokenRouter:
        def generate_structured(self, prompt, response_model, temperature=0.0):
            raise RuntimeError("boom")

    out = judge_faithfulness(
        ["ship in march"], "we ship in march", _BrokenRouter()
    )
    assert out["judge_used"] is False


def test_parse_judge_json_with_fences():
    raw = '```json\n{"verdicts": [{"claim": "x", "supported": true}]}\n```'
    parsed = parse_judge_json(raw)
    assert parsed is not None
    assert parsed["verdicts"][0]["supported"] is True


def test_parse_judge_json_invalid_returns_none():
    assert parse_judge_json("not json") is None


# ---------------------------------------------------------------------------
# dataset exporter
# ---------------------------------------------------------------------------
def test_should_flag_low_score():
    assert should_flag(0.5, 0.9) is True


def test_should_flag_high_score():
    assert should_flag(0.9, 0.9) is False


def test_build_record_shape():
    rec = build_record("t", {"tasks": []}, {"faithfulness": 0.5}, tenant_id="t1")
    assert rec["tenant_id"] == "t1"
    assert rec["transcript"] == "t"
    assert "timestamp" in rec and "version" in rec


def test_record_evaluation_flagged_writes(tmp_path):
    out = tmp_path / "bench.jsonl"
    path = record_evaluation(
        "transcript",
        {"tasks": []},
        {"faithfulness": 0.5, "action_item_recall": 0.9},
        tenant_id="t1",
        output_path=str(out),
    )
    assert path is not None
    assert out.exists()
    line = json.loads(out.read_text().strip())
    assert line["flagged"] is True


def test_record_evaluation_not_flagged_returns_none(tmp_path):
    out = tmp_path / "bench.jsonl"
    path = record_evaluation(
        "transcript",
        {"tasks": []},
        {"faithfulness": 0.9, "action_item_recall": 0.9},
        output_path=str(out),
    )
    assert path is None


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------
def test_pipeline_good_analysis_not_exported(tmp_path):
    report = evaluate(
        "we will ship the product in march and send the report",
        {"tasks": ["ship product in march", "send report"], "decisions": []},
        ground_truth_tasks=["ship the product", "send the report"],
        tenant_id="t1",
        export_path=str(tmp_path / "bench.jsonl"),
    )
    assert report["faithfulness"] >= 0.9
    assert report["action_item_recall"] >= 0.9
    assert report["exported"] is None


def test_pipeline_hallucinated_analysis_exported(tmp_path):
    report = evaluate(
        "we discussed the budget for next quarter",
        {"tasks": ["team won the lottery in june"], "decisions": []},
        ground_truth_tasks=["review budget"],
        tenant_id="t1",
        export_path=str(tmp_path / "bench.jsonl"),
    )
    assert report["faithfulness"] <= 0.1
    assert report["exported"] is not None


def test_pipeline_uses_router_when_provided(tmp_path):
    class _Router:
        def generate_structured(self, prompt, response_model, temperature=0.0):
            return response_model(
                verdicts=[
                    {
                        "claim": "ship in march",
                        "supported": True,
                        "confidence": 0.9,
                    }
                ]
            )

    report = evaluate(
        "we ship in march",
        {"tasks": ["ship in march"], "decisions": []},
        router=_Router(),
        export_path=str(tmp_path / "bench.jsonl"),
    )
    assert report["judge_used"] is True
    assert report["faithfulness"] == 1.0
