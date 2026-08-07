"""Tests for the cross-encoder reranker.

The real cross-encoder may not be installed, so we test both the
graceful-degradation path (returns original order) and the re-ranking
logic using a stub model injected via monkeypatching.
"""

from worker.rag.chunker import TranscriptChunk
from worker.rag.retriever import RetrievalResult
from worker.rag.reranker import CrossEncoderReranker


def _mk_retrieval(chunk_id, text, score=1.0):
    chunk = TranscriptChunk(chunk_id=chunk_id, text=text, source_id="src")
    return RetrievalResult(chunk=chunk, score=score)


def test_rerank_empty_candidates():
    r = CrossEncoderReranker()
    assert r.rerank("q", []) == []


def test_rerank_degrades_when_model_unavailable(monkeypatch):
    r = CrossEncoderReranker()
    # Force model load to fail -> should return candidates unchanged.
    monkeypatch.setattr(
        r, "_load_model", lambda: setattr(r, "_model", None)
    )
    candidates = [
        _mk_retrieval("a", "budget approved"),
        _mk_retrieval("b", "roadmap discussion"),
    ]
    out = r.rerank("budget", candidates, top_n=1)
    assert len(out) == 1
    assert out[0].chunk_id == "a"  # original order preserved


def test_rerank_orders_by_score(monkeypatch):
    r = CrossEncoderReranker()
    # Provide a fake model whose predict returns scores.
    class FakeModel:
        def predict(self, pairs):
            # Higher score for pairs containing "budget".
            return [1.0 if "budget" in p[1] else 0.0 for p in pairs]

    r._model = FakeModel()
    candidates = [
        _mk_retrieval("a", "roadmap discussion"),
        _mk_retrieval("b", "budget approved for Q3"),
    ]
    out = r.rerank("budget", candidates, top_n=2)
    # "b" (budget) should rank first.
    assert out[0].chunk_id == "b"
