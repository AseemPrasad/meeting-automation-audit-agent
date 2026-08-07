"""Tests for the transcript indexer using a fake embedding provider.

No live Qdrant or rank_bm25 required — the BM25 index is tested in isolation
and the dense indexer degrades gracefully without Qdrant.
"""

import pytest

from worker.rag.chunker import TranscriptChunk
from worker.rag.indexer import BM25Index, TranscriptIndexer


class FakeEmbedder:
    """Minimal fake VectorProvider for tests."""

    name = "fake"
    dimensions = 8

    def embed(self, text: str):
        # Deterministic pseudo-embedding so tests don't need a real model.
        return [float(ord(c)) % 10 for c in text[: self.dimensions]] or [0.0] * self.dimensions

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


def _mk_chunk(chunk_id, text):
    return TranscriptChunk(chunk_id=chunk_id, text=text, source_id="src")


def test_bm25_ranked_search_returns_expected():
    # Use a corpus large enough that BM25's idf is non-zero (>=3 docs).
    index = BM25Index()
    index.add([
        _mk_chunk("a", "The budget was approved for Q3 and the team is happy"),
        _mk_chunk("b", "We discussed the marketing roadmap for next year"),
        _mk_chunk("c", "The budget includes hiring two new engineers"),
        _mk_chunk("d", "Customer feedback on the roadmap was positive"),
        _mk_chunk("e", "Legal reviewed the vendor contract this week"),
    ])
    results = index.search("budget approved", top_k=1)
    assert results
    top, _ = results[0]
    assert "budget" in top.text


def test_bm25_empty_corpus_returns_empty():
    index = BM25Index()
    assert index.search("anything", top_k=5) == []


def test_indexer_indexes_chunks_without_qdrant():
    # No QDRANT_URL configured -> _qdrant_client returns None -> sparse-only path.
    indexer = TranscriptIndexer(embedding_provider=FakeEmbedder())
    n = indexer.index_transcript(
        "job-1",
        "Alice: approved budget. Bob: next steps for Q3.",
        meeting_title="Budget Sync",
    )
    assert n > 0
    assert indexer.has_sparse
    assert not indexer.has_dense


def test_indexer_empty_transcript_indexes_zero():
    indexer = TranscriptIndexer(embedding_provider=FakeEmbedder())
    assert indexer.index_transcript("job-2", "") == 0

