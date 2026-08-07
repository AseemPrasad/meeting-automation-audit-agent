"""Tests for the deterministic transcript chunker (no external services)."""

from worker.rag.chunker import chunk_transcript


def test_empty_text_returns_no_chunks():
    assert chunk_transcript("", "job-1") == []


def test_short_text_yields_single_chunk():
    chunks = chunk_transcript("Alice: hello", "job-1", meeting_title="Sync")
    assert len(chunks) == 1
    assert chunks[0].source_id == "job-1"
    assert chunks[0].meeting_title == "Sync"


def test_long_text_yields_multiple_chunks_with_unique_ids():
    text = ("word " * 60)  # ~360 chars, above a small chunk_size
    chunks = chunk_transcript(text, "job-1", chunk_size=100, overlap=20)
    assert len(chunks) > 1
    ids = [c.chunk_id for c in chunks]
    assert len(set(ids)) == len(ids)  # unique ids
    assert all(c.chunk_id.startswith("job-1:") for c in chunks)


def test_chunks_preserve_offsets_and_metadata():
    text = ("data " * 40)
    chunks = chunk_transcript(
        text,
        "job-2",
        chunk_size=100,
        overlap=10,
        meeting_title="Retro",
        date="2024-01-01",
    )
    chunk = chunks[0]
    assert chunk.date == "2024-01-01"
    assert chunk.end_offset > chunk.start_offset


def test_chunk_text_is_non_empty():
    text = (
        "Speaker 1: We agreed to move to Q2.\n\n"
        "Speaker 2: The budget is approved.\n\n"
        "Speaker 1: Next steps are documented."
    )
    chunks = chunk_transcript(text, "job-3")
    assert all(c.text.strip() for c in chunks)

