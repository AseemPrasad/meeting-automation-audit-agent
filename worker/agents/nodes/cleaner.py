"""Cleaner node: pre-processes transcript formatting and speaker segmentation."""

from __future__ import annotations

import re

from worker.agents.state import AgentState
from worker.schemas.agent import CleanedTranscript, SpeakerSegment
from worker.services.llm.prompting import cleaner_prompt
from worker.services.llm.router import LLMRouter


def _heuristic_clean(transcript: str) -> CleanedTranscript:
    """Framework-free fallback: regex-based normalization + speaker parsing.

    Used when no LLM router is available or structured extraction fails, so the
    cleaner node never blocks the graph on a model outage.
    """
    # Collapse blank lines and strip leading/trailing whitespace per line.
    lines = [ln.strip() for ln in transcript.splitlines() if ln.strip()]
    cleaned_lines = []
    segments: list[SpeakerSegment] = []
    order = 0
    # Match "Speaker: text"
    speaker_re = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _-]{0,30}?)\s*:\s*(.+)$")
    for ln in lines:
        m = speaker_re.match(ln)
        if m:
            speaker, text = m.group(1).strip(), m.group(2).strip()
            cleaned_lines.append(f"{speaker}: {text}")
            segments.append(SpeakerSegment(speaker=speaker, text=text, order=order))
            order += 1
        else:
            cleaned_lines.append(ln)
    return CleanedTranscript(
        cleaned_text="\n".join(cleaned_lines),
        segments=segments,
    )


def clean(state: AgentState, router: LLMRouter | None = None) -> AgentState:
    """Run the cleaner node over ``state.transcript``.

    Uses the LLM gateway for structured speaker segmentation when available,
    else falls back to a deterministic regex cleaner. Mutates ``state.cleaned``.
    """
    if router is None:
        state.cleaned = _heuristic_clean(state.transcript)
        return state

    try:
        cleaned = router.generate_structured(
            cleaner_prompt(state.transcript), response_model=CleanedTranscript
        )
        state.cleaned = cleaned
    except Exception:
        # Fall back so the graph keeps progressing.
        state.cleaned = _heuristic_clean(state.transcript)
    return state
