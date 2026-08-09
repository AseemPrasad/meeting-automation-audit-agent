"""Evaluation pipeline for measuring extraction quality and hallucination.

This package provides an LLM-as-a-Judge evaluation layer that computes
numerical quality metrics (faithfulness / hallucination index and action-item
recall) for completed meeting analyses, and exports low-scoring extractions
for offline benchmark regression and future fine-tuning.

It is fully additive: it reuses the existing ``LLMRouter`` for the judge model
and touches none of the existing application code paths.

Submodules are imported lazily so the package can be introduced incrementally
and individual modules remain importable on their own.
"""

# Re-export the two deterministic metrics (pure, dependency-light).
from worker.eval.metrics import compute_faithfulness, compute_action_item_recall

__all__ = [
    "compute_faithfulness",
    "compute_action_item_recall",
]


def __getattr__(name):
    """Lazily import heavier submodules (judge, exporter, pipeline) on demand.

    This keeps ``import worker.eval`` cheap and avoids import-time side effects
    (e.g., constructing the LLM router) until a feature is actually used.
    """
    if name == "record_evaluation":
        from worker.eval.dataset_exporter import record_evaluation
        return record_evaluation
    if name == "should_flag":
        from worker.eval.dataset_exporter import should_flag
        return should_flag
    if name == "evaluate":
        # Importing the pipeline also pulls in the judge + exporter.
        from worker.eval.pipeline import evaluate
        return evaluate
    raise AttributeError(f"module 'worker.eval' has no attribute {name!r}")
