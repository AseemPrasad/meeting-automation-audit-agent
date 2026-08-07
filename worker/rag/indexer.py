"""Indexer for hybrid dense/sparse transcript retrieval.

Dense index: Qdrant vector collection (embeddings via the existing VectorProvider).
Sparse index: in-memory BM25 term index (rank_bm25).

Indexing is optional and idempotent — missing Qdrant or BM25 state degrades
gracefully to the other index.
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from dotenv import load_dotenv

from worker.rag.chunker import TranscriptChunk, chunk_transcript
from worker.services.embeddings.vector_provider import (
    VectorProvider,
    build_embedding_provider,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Qdrant client (lazy, optional)
# ---------------------------------------------------------------------------

_QDRANT_COLLECTION = "transcripts"


def _qdrant_client():
    """Return a Qdrant client or None if Qdrant is not configured."""
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import Distance, VectorParams

        return QdrantClient(url=url)
    except ImportError:
        return None


def _ensure_collection(client, dims: int) -> None:
    """Create the Qdrant collection if it does not exist (idempotent)."""
    from qdrant_client.http.exceptions import UnexpectedResponse

    try:
        client.get_collection(_QDRANT_COLLECTION)
    except UnexpectedResponse:
        client.create_collection(
            collection_name=_QDRANT_COLLECTION,
            vectors_config=VectorParams(size=dims, distance=Distance.COSINE),
        )


# ---------------------------------------------------------------------------
# BM25 index (in-memory, built on the fly)
# ---------------------------------------------------------------------------

class BM25Index:
    """In-memory BM25 sparse index over a corpus of chunks."""

    def __init__(self) -> None:
        self._corpus: List[str] = []
        self._chunk_map: List[TranscriptChunk] = []
        self._bm25 = None

    def add(self, chunks: List[TranscriptChunk]) -> None:
        """Add chunks to the BM25 index (idempotent)."""
        self._corpus.extend(c.text for c in chunks)
        self._chunk_map.extend(chunks)
        self._rebuild()

    def _rebuild(self) -> None:
        """Rebuild the BM25 model from the current corpus."""
        from rank_bm25 import BM25Okapi

        tokenized = [doc.lower().split() for doc in self._corpus]
        self._bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[TranscriptChunk, float]]:
        """Return (chunk, score) pairs for the top-k BM25 results."""
        if self._bm25 is None or not self._corpus:
            return []
        tokenized_query = query.lower().split()
        scores = self._bm25.get_scores(tokenized_query)
        ranked = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )[:top_k]
        return [(self._chunk_map[idx], float(score)) for idx, score in ranked if score > 0]


# ---------------------------------------------------------------------------
# Transcript indexer (orchestrator)
# ---------------------------------------------------------------------------

class TranscriptIndexer:
    """Index transcripts into dense (Qdrant) and sparse (BM25) stores.

    Typical usage::

        indexer = TranscriptIndexer()
        indexer.index_transcript("job-123", full_transcript_text)
    """

    def __init__(
        self,
        embedding_provider: Optional[VectorProvider] = None,
        bm25_index: Optional[BM25Index] = None,
    ) -> None:
        self._embedder = embedding_provider or build_embedding_provider()
        self._qdrant = _qdrant_client()
        self._bm25 = bm25_index or BM25Index()

        if self._qdrant is not None:
            _ensure_collection(self._qdrant, self._embedder.dimensions)

    def index_transcript(
        self,
        source_id: str,
        text: str,
        meeting_title: Optional[str] = None,
        date: Optional[str] = None,
    ) -> int:
        """Chunk, embed, and index a transcript. Returns the number of chunks indexed."""
        chunks = chunk_transcript(
            text,
            source_id=source_id,
            meeting_title=meeting_title,
            date=date,
        )
        if not chunks:
            return 0

        # 1. Dense: embed and upsert to Qdrant
        if self._qdrant is not None:
            vectors = self._embedder.embed_batch([c.text for c in chunks])
            points = [
                {
                    "id": hash(c.chunk_id) % (2**63),
                    "vector": vec,
                    "payload": c.to_dict(),
                }
                for c, vec in zip(chunks, vectors)
            ]
            self._qdrant.upsert(
                collection_name=_QDRANT_COLLECTION,
                points=points,
            )

        # 2. Sparse: add to BM25 index
        self._bm25.add(chunks)

        return len(chunks)

    @property
    def has_dense(self) -> bool:
        """True if Qdrant is available."""
        return self._qdrant is not None

    @property
    def has_sparse(self) -> bool:
        """True if BM25 has indexed at least one document."""
        return self._bm25 is not None and len(self._bm25._corpus) > 0
