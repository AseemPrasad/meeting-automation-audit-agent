"""Cross-encoder re-ranking of retrieved chunks.

Uses a sentence-transformers cross-encoder (e.g. ``ms-marco-MiniLM-L-6-v2``)
to score ``(query, chunk)`` pairs more accurately than bi-encoder cosine
similarity. If the cross-encoder is unavailable, the module degrades
gracefully and returns candidates in their original order.
"""

from __future__ import annotations

import os
from typing import List, Optional

from dotenv import load_dotenv

from worker.rag.chunker import TranscriptChunk
from worker.rag.retriever import RetrievalResult

load_dotenv()

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    """Re-rank candidate chunks with a cross-encoder.

    Usage::

        reranker = CrossEncoderReranker()
        reranked = reranker.rerank(query, candidates, top_n=3)
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        self._model_name = model_name or os.getenv(
            "CROSS_ENCODER_MODEL", _DEFAULT_MODEL
        )
        self._model = None
        self._available = True

    def _load_model(self):
        """Lazily load the cross-encoder; fall back to unavailable on failure."""
        if self._model is not None or not self._available:
            return
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
        except Exception:
            # Cross-encoder not installed/downloadable -> no-op rerank.
            self._available = False
            self._model = None

    def rerank(
        self,
        query: str,
        candidates: List[RetrievalResult],
        top_n: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """Score and re-rank candidates by cross-encoder relevance.

        Returns the top ``top_n`` results. If the cross-encoder is unavailable,
        returns candidates unchanged (preserving the fused RRF order).
        """
        if not candidates:
            return []

        self._load_model()
        if self._model is None:
            return candidates[:top_n] if top_n else candidates

        # Build (query, chunk_text) pairs and score them.
        pairs = [(query, c.chunk.text) for c in candidates]
        try:
            scores = self._model.predict(pairs)
        except Exception:
            return candidates[:top_n] if top_n else candidates

        ranked = sorted(
            zip(candidates, scores), key=lambda x: x[1], reverse=True
        )
        results = [c for c, _ in ranked]
        return results[:top_n] if top_n else results


def rerank_results(
    query: str,
    candidates: List[RetrievalResult],
    top_n: Optional[int] = None,
    model_name: Optional[str] = None,
) -> List[RetrievalResult]:
    """Convenience function: build a reranker and re-rank candidates."""
    return CrossEncoderReranker(model_name=model_name).rerank(
        query, candidates, top_n=top_n
    )
