"""Hybrid retriever: dense (Qdrant) + sparse (BM25) fused with RRF.

Reciprocal Rank Fusion (RRF) combines ranked candidate lists from both
retrievers:  ``score = sum(1 / (k + rank_i))``. This is robust to
uncalibrated score scales across different retrieval methods.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

from worker.rag.chunker import TranscriptChunk
from worker.rag.indexer import BM25Index, _QDRANT_COLLECTION
from worker.services.embeddings.vector_provider import (
    VectorProvider,
    build_embedding_provider,
)

load_dotenv()


@dataclass
class RetrievalResult:
    """A single fused/ranked retrieval candidate."""

    chunk: TranscriptChunk
    score: float = 0.0
    sources: List[str] = field(default_factory=list)  # which retrievers matched

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id


def reciprocal_rank_fusion(
    ranked_lists: List[List[Tuple[str, float]]],
    k: int = 60,
) -> Dict[str, float]:
    """Fuse multiple ranked lists of (doc_id, score) into one RRF score map.

    Args:
        ranked_lists: Each list is ordered by relevance (best first). Scores
            from individual retrievers are ignored — only ranks matter.
        k: RRF constant (typically 60).
    """
    fused: Dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (doc_id, _score) in enumerate(ranked):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return fused


def _qdrant_search(
    client,
    embedder: VectorProvider,
    query: str,
    top_k: int,
) -> List[Tuple[str, float]]:
    """Search the Qdrant collection by query embedding."""
    if client is None:
        return []
    try:
        query_vec = embedder.embed(query)
        hits = client.search(
            collection_name=_QDRANT_COLLECTION,
            query_vector=query_vec,
            limit=top_k,
            with_payload=True,
        )
        results = []
        for hit in hits:
            doc_id = hit.payload.get("chunk_id") or hit.id
            results.append((doc_id, float(hit.score)))
        return results
    except Exception:
        # Qdrant unreachable -> gracefully degrade to sparse-only results.
        return []


class HybridRetriever:
    """Combine dense + sparse retrievers and fuse with RRF.

    Usage::

        retriever = HybridRetriever()
        results = retriever.retrieve("Q3 budget decision", top_k=5)
    """

    def __init__(
        self,
        embedding_provider: Optional[VectorProvider] = None,
        bm25_index: Optional[BM25Index] = None,
        qdrant_client=None,
        rrf_k: int = 60,
    ) -> None:
        self._embedder = embedding_provider or build_embedding_provider()
        self._bm25 = bm25_index or BM25Index()
        self._qdrant = qdrant_client or self._resolve_qdrant()
        self._rrf_k = rrf_k

    @staticmethod
    def _resolve_qdrant():
        """Return a configured Qdrant client or None."""
        url = os.getenv("QDRANT_URL", "http://localhost:6333")
        try:
            from qdrant_client import QdrantClient

            return QdrantClient(url=url)
        except ImportError:
            return None

    def sparse_search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """BM25 keyword retrieval -> [(chunk_id, score)]."""
        return [(c.chunk_id, s) for c, s in self._bm25.search(query, top_k=top_k)]

    def dense_search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """Qdrant vector similarity -> [(chunk_id, score)]."""
        return _qdrant_search(self._qdrant, self._embedder, query, top_k)

    def hybrid_search(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Run both retrievers, fuse with RRF, return top-k fused results."""
        dense = self.dense_search(query, top_k=top_k)
        sparse = self.sparse_search(query, top_k=top_k)

        fused = reciprocal_rank_fusion([dense, sparse], k=self._rrf_k)

        # Rank fused doc ids by RRF score (descending).
        ranked_ids = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]

        # Attach chunk objects. Fall back to a lightweight placeholder chunk
        # if the BM25 index doesn't hold the doc (e.g. Qdrant-only match).
        results: List[RetrievalResult] = []
        chunk_by_id = {c.chunk_id: c for c in self._bm25._chunk_map}
        for doc_id, rrf_score in ranked_ids:
            chunk = chunk_by_id.get(doc_id)
            if chunk is None:
                chunk = TranscriptChunk(chunk_id=doc_id, text="", source_id="")
            sources = []
            if any(doc_id == did for did, _ in dense):
                sources.append("dense")
            if any(doc_id == did for did, _ in sparse):
                sources.append("sparse")
            results.append(
                RetrievalResult(chunk=chunk, score=rrf_score, sources=sources)
            )
        return results

    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Convenience alias for :meth:`hybrid_search`."""
        return self.hybrid_search(query, top_k=top_k)
