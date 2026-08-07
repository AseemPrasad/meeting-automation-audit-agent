"""Tests for the end-to-end RAG pipeline (chunk -> index -> retrieve -> rerank).

Uses a fake embedder to avoid the sentence-transformers dependency.

Note: BM25 needs a corpus of >= 3 documents to produce strictly positive
IDF scores (with fewer docs the IDF formula saturates to zero), so each
indexing test seeds at least three distinct documents.
"""

from worker.rag.indexer import BM25Index, TranscriptIndexer
from worker.rag.pipeline import RagPipeline
from worker.rag.reranker import CrossEncoderReranker
from worker.rag.retriever import HybridRetriever


class _FakeEmbedder:
    name = "fake"
    dimensions = 8

    def embed(self, text):
        return [float(ord(c)) % 10 for c in text[: self.dimensions]] or [0.0] * self.dimensions

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


def _make_rag(enable_rerank=False):
    bm25 = BM25Index()
    embedder = _FakeEmbedder()
    indexer = TranscriptIndexer(embedding_provider=embedder, bm25_index=bm25)
    retriever = HybridRetriever(
        embedding_provider=embedder,
        bm25_index=bm25,
        qdrant_client=None,
    )
    reranker = CrossEncoderReranker() if enable_rerank else None
    return RagPipeline(indexer=indexer, retriever=retriever, reranker=reranker)


_CORPUS = [
    "The team approved the Q3 budget allocation for the marketing campaign.",
    "Engineering set the release date for the new API integration product.",
    "Legal reviewed the software vendor contract and signed off on it.",
    "Sarah scheduled the customer feedback session for this Thursday morning.",
]


def test_pipeline_index_and_retrieve():
    rag = _make_rag()
    rag.index("job-001", _CORPUS[0])
    rag.index("job-002", _CORPUS[1])
    rag.index("job-003", _CORPUS[2])

    assert rag.indexed_chunk_count > 0

    results = rag.query("budget allocation", top_k=3, rerank_top_n=None)
    assert results
    assert "budget" in results[0].chunk.text


def test_pipeline_empty_text():
    rag = _make_rag()
    n = rag.index("job-004", "")
    assert n == 0


def test_pipeline_no_match():
    rag = _make_rag()
    rag.index("job-005", _CORPUS[0])
    rag.index("job-006", _CORPUS[1])
    rag.index("job-007", _CORPUS[2])
    results = rag.query("quantum computing wormhole", top_k=5)
    assert results == []


def test_pipeline_rerank_degrades_gracefully():
    rag = _make_rag(enable_rerank=True)
    rag.index("job-008", _CORPUS[0])
    rag.index("job-009", _CORPUS[1])
    rag.index("job-010", _CORPUS[2])
    results = rag.query("budget", top_k=2)
    assert results

