"""High-level RAG pipeline: chunk -> index -> retrieve -> rerank.

Orchestrates the individual components (chunker, indexer, retriever,
reranker) into a single entry point so callers (e.g. the transcript
workflow) can index a transcript and later answer queries against the
full meeting history.
"""

from __future__ import annotations

import os
from typing import List, Optional

from dotenv import load_dotenv

from worker.rag.chunker import TranscriptChunk
from worker.rag.indexer import TranscriptIndexer
from worker.rag.reranker import CrossEncoderReranker
from worker.rag.retriever import HybridRetriever, RetrievalResult

load_dotenv()


class RagPipeline:
    """End-to-end async transcript RAG.

    Usage::

        rag = RagPipeline()
        rag.index("job-123", full_transcript)
        results = rag.query("What was the budget decision?", top_k=3)
    """

    def __init__(
        self,
        indexer: Optional[TranscriptIndexer] = None,
        retriever: Optional[HybridRetriever] = None,
        reranker: Optional[CrossEncoderReranker] = None,
        enable_rerank: Optional[bool] = None,
    ) -> None:
        self._indexer = indexer or TranscriptIndexer()
        self._retriever = retriever or HybridRetriever(
            embedding_provider=self._indexer._embedder,
            bm25_index=self._indexer._bm25,
        )
        self._reranker = reranker or (
            CrossEncoderReranker() if (enable_rerank if enable_rerank is not None else True) else None
        )

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index(
        self,
        source_id: str,
        text: str,
        meeting_title: Optional[str] = None,
        date: Optional[str] = None,
    ) -> int:
        """Index a full transcript. Returns the number of chunks indexed."""
        return self._indexer.index_transcript(
            source_id, text, meeting_title=meeting_title, date=date
        )

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Retrieve top-k chunks via dense+sparse RRF (no re-rank)."""
        return self._retriever.retrieve(query, top_k=top_k)

    def query(
        self,
        query: str,
        top_k: int = 5,
        rerank_top_n: Optional[int] = 3,
    ) -> List[RetrievalResult]:
        """Retrieve then re-rank. Returns final ordered chunks."""
        candidates = self.retrieve(query, top_k=top_k)
        if self._reranker is not None:
            return self._reranker.rerank(query, candidates, top_n=rerank_top_n)
        return candidates[:rerank_top_n] if rerank_top_n else candidates

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def indexed_chunk_count(self) -> int:
        """Number of chunks currently in the sparse BM25 index."""
        bm25 = self._indexer._bm25
        return len(bm25._corpus) if bm25 is not None else 0


def build_pipeline(
    enable_rerank: Optional[bool] = None,
    indexer: Optional[TranscriptIndexer] = None,
) -> RagPipeline:
    """Convenience factory for building a :class:`RagPipeline`.

    ``enable_rerank`` defaults to env var ``RAG_ENABLE_RERANK``; when unset,
    re-ranking is enabled (cross-encoder degrades gracefully if unavailable).
    """
    if enable_rerank is None:
        env = os.getenv("RAG_ENABLE_RERANK")
        enable_rerank = False if env and env.lower() in {"0", "false", "no"} else True
    return RagPipeline(indexer=indexer, enable_rerank=enable_rerank)
