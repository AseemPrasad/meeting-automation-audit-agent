"""Transcript chunking for RAG indexing.

Split meeting transcript text into deterministic, overlapping chunks suitable
for both dense (embedding) and sparse (BM25) indexing. Chunks preserve source
metadata (job id, meeting title, date) so retrievals can be traced back to the
original meeting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TranscriptChunk:
    """A single retrievable piece of a transcript."""

    chunk_id: str
    text: str
    source_id: str  # typically the job_id / meeting id
    meeting_title: Optional[str] = None
    date: Optional[str] = None
    start_offset: int = 0
    end_offset: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serializable representation for vector-store payloads."""
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "source_id": self.source_id,
            "meeting_title": self.meeting_title,
            "date": self.date,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            **self.metadata,
        }


# Heuristic to split a transcript into "speaker turns" or paragraphs.
_TURN_SPLIT_RE = re.compile(r"(?:\n\s*\n)|(?:\n?\s*(?:\[?\w+[\w\s]*\]?:|Speaker\s*\d+:))", re.IGNORECASE)


def _default_splitter(text: str) -> List[str]:
    """Split text into rough segments (paragraphs / speaker turns)."""
    segments = [s.strip() for s in _TURN_SPLIT_RE.split(text) if s and s.strip()]
    if not segments:
        segments = [text]
    return segments


def chunk_transcript(
    text: str,
    source_id: str,
    chunk_size: int = 500,
    overlap: int = 50,
    meeting_title: Optional[str] = None,
    date: Optional[str] = None,
    splitter=None,
) -> List[TranscriptChunk]:
    """Chunk ``text`` into overlapping ``TranscriptChunk`` objects.

    Args:
        text: Full transcript text.
        source_id: Identifier of the source meeting (job id).
        chunk_size: Target chunk length in characters.
        overlap: Character overlap between consecutive chunks.
        meeting_title: Optional title stored in chunk metadata.
        date: Optional meeting date stored in chunk metadata.
        splitter: Optional callable returning raw segments from ``text``.
    """
    if not text or not text.strip():
        return []

    splitter = splitter or _default_splitter
    raw_segments = splitter(text)

    # Merge small segments until they reach chunk_size, then slice with overlap.
    chunks: List[TranscriptChunk] = []
    buffer = ""
    running_offset = 0

    for segment in raw_segments:
        buffer += (" " if buffer else "") + segment
        while len(buffer) >= chunk_size:
            piece = buffer[:chunk_size]
            start = _first_whitespace_offset(buffer, chunk_size)
            piece = buffer[:start] if start > 0 else piece
            chunks.append(
                _make_chunk(
                    piece, source_id, meeting_title, date, running_offset, chunks
                )
            )
            running_offset += len(piece) - overlap
            buffer = buffer[len(piece) - overlap:] if len(piece) > overlap else buffer[len(piece):]

    if buffer.strip():
        chunks.append(
            _make_chunk(
                buffer, source_id, meeting_title, date, running_offset, chunks
            )
        )

    return chunks


def _first_whitespace_offset(text: str, limit: int) -> int:
    """Find the last whitespace <= limit so chunks break at word boundaries."""
    window = text[:limit]
    idx = window.rfind(" ")
    return idx + 1 if idx > 0 else 0


def _make_chunk(
    piece: str,
    source_id: str,
    meeting_title: Optional[str],
    date: Optional[str],
    start_offset: int,
    existing: List[TranscriptChunk],
) -> TranscriptChunk:
    """Build a TranscriptChunk with a stable, unique chunk_id."""
    chunk_id = f"{source_id}:{len(existing)}"
    return TranscriptChunk(
        chunk_id=chunk_id,
        text=piece.strip(),
        source_id=source_id,
        meeting_title=meeting_title,
        date=date,
        start_offset=start_offset,
        end_offset=start_offset + len(piece),
    )
