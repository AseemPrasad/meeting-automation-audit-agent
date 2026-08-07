"""Hybrid dense/sparse RAG engine for transcript history retrieval.

Public API:
    - ``RagPipeline`` / ``build_pipeline``: end-to-end orchestrator
    - ``chunk_transcript`` / ``TranscriptChunk``: chunking primitives
    - ``TranscriptIndexer`` / ``BM25Index``: indexing
    - ``HybridRetriever`` / ``RetrievalResult``: retrieval (RRF fusion)
    - ``CrossEncoderReranker``: re-ranking
"""

from worker.rag.chunker import TranscriptChunk, chunk_transcript
from worker.rag.indexer import BM25Index, TranscriptIndexer
from worker.rag.pipeline import RagPipeline, build_pipeline
from worker.rag.reranker import CrossEncoderReranker
from worker.rag.retriever import HybridRetriever, RetrievalResult

__all__ = [
    "TranscriptChunk",
    "chunk_transcript",
    "BM25Index",
    "TranscriptIndexer",
    "HybridRetriever",
    "RetrievalResult",
    "CrossEncoderReranker",
    "RagPipeline",
    "build_pipeline",
]
