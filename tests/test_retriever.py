"""Tests for the hybrid retriever + RRF fusion.

Uses a BM25 index with a fake embedder and no live Qdrant, so these run
offline.
"""

from worker.rag.chunker import TranscriptChunk
from worker.rag.indexer import BM25Index
from worker.rag.retriever import (
    HybridRetriever,
    reciprocal_rank_fusion,
)


def _mk_chunk(chunk_id, text):
    return TranscriptChunk(chunk_id=chunk_id, text=text, source_id="src")


class FakeEmbedder:
    name = "fake"
    dimensions = 8

    def embed(self, text: str):
        return [float(ord(c)) % 10 for c in text[: self.dimensions]] or [0.0] * self.dimensions

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


def test_rrf_combines_rankings():
    # doc "a" appears in both lists -> higher fused score.
    # Each item is a (doc_id, score) tuple; only ranks matter.
    fused = reciprocal_rank_fusion(
        [[("a", 1.0), ("b", 0.9)], [("a", 0.8), ("c", 0.7)]],
        k=60,
    )
    assert fused["a"] > fused["b"]
    assert fused["a"] > fused["c"]


def test_rrf_empty_lists():
    assert reciprocal_rank_fusion([[], []]) == {}


def test_hybrid_search_returns_fused_results():
    bm25 = BM25Index()
    bm25.add([
        _mk_chunk("a", "The budget was approved for Q3 and the team is happy"),
        _mk_chunk("b", "We discussed the marketing roadmap for next year"),
        _mk_chunk("c", "The budget includes hiring two new engineers"),
        _mk_chunk("d", "Customer feedback on the roadmap was positive"),
        _mk_chunk("e", "Legal reviewed the vendor contract this week"),
    ])

    retriever = HybridRetriever(
        embedding_provider=FakeEmbedder(),
        bm25_index=bm25,
        qdrant_client=None,  # force sparse-only path
    )
    results = retriever.retrieve("budget approved", top_k=3)
    assert results
    assert results[0].chunk_id in {"a", "c"}


def test_hybrid_search_sparse_only_when_no_qdrant():
    bm25 = BM25Index()
    bm25.add([
        _mk_chunk("a", "Q3 budget planning session with the finance team"),
        _mk_chunk("b", "Marketing reviewed the creative assets today"),
        _mk_chunk("c", "Engineering set the release date for the API"),
    ])

    retriever = HybridRetriever(
        embedding_provider=FakeEmbedder(),
        bm25_index=bm25,
        qdrant_client=None,
    )
    results = retriever.retrieve("budget", top_k=5)
    assert results
    assert "sparse" in results[0].sources

