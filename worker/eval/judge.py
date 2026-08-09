"""LLM-as-a-Judge engine for verifying extracted claims against a transcript.

This module wraps the existing ``LLMRouter`` (with its failover + circuit
breaker semantics) to act as a judge. Given a transcript and a set of extracted
action items / claims, it asks the judge model to verify whether each claim is
directly supported by the source text, and returns a per-claim verdict plus a
``0.0 - 1.0`` faithfulness score.

Design notes:
- Deterministic metrics (``worker.eval.metrics.compute_faithfulness``) provide
  the offline baseline; this judge is the semantic refinement offered when an
  LLM is available.
- If the judge model is unavailable (no providers configured, all fail), the
  engine degrades gracefully to the lexical baseline rather than raising.
"""

from __future__ import annotations

import json
from typing import List, Optional

from pydantic import BaseModel, Field

from worker.services.llm.router import LLMRouter
from worker.eval.metrics import compute_faithfulness


class ClaimVerdict(BaseModel):
    """A single judge verdict for one extracted claim/action item."""

    claim: str = Field(..., description="The claim being verified")
    supported: bool = Field(
        ...,
        description="True if the claim is directly supported by the transcript",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Judge confidence in the verdict (0.0 to 1.0)",
    )
    rationale: str = Field(
        default="", description="Short explanation from the judge"
    )


class JudgeReport(BaseModel):
    """Structured output the judge model is asked to produce."""

    verdicts: List[ClaimVerdict] = Field(
        default_factory=list, description="Per-claim verification verdicts"
    )


# Prompt template. The judge is instructed to verify each claim strictly
# against the transcript and return ONLY valid JSON.
_JUDGE_PROMPT = """\
You are a strict factuality judge. Your task is to verify whether each extracted
action item / claim is DIRECTLY SUPPORTED by the meeting transcript below.

Rules:
- A claim is supported only if the transcript explicitly states or clearly
  entails it. Do not infer, guess, or import outside knowledge.
- If any part of a claim is not backed by the transcript, mark it unsupported.
- Provide a confidence in [0.0, 1.0] and a one-sentence rationale per claim.

Respond ONLY with valid JSON in this exact shape:
{{
  "verdicts": [
    {{"claim": "...", "supported": true|false,
      "confidence": 0.0, "rationale": "..."}}
  ]
}}

Transcript:
{transcript}

Claims to verify:
{claims}
"""


def _build_claims_payload(claims: List[str]) -> str:
    """Format the claims list into a numbered block for the prompt."""
    return "\n".join(f"- {c}" for c in claims if c and str(c).strip())


def judge_faithfulness(
    claims: List[str],
    transcript: str,
    router: Optional[LLMRouter] = None,
    *,
    temperature: float = 0.0,
) -> dict:
    """Verify claims against the transcript using LLM-as-a-Judge.

    Returns a dict with:
    - ``verdicts``: per-claim ``ClaimVerdict`` results (as dicts)
    - ``faithfulness``: the ``0.0 - 1.0`` faithfulness score (fraction of
      claims the judge marked supported)
    - ``judge_used``: ``True`` if the judge model produced verdicts, else
      ``False`` (meaning the score fell back to the lexical baseline).

    If no router is provided or the judge call fails, falls back to the
    deterministic lexical ``compute_faithfulness`` so the pipeline never
    crashes when the LLM is unavailable.
    """
    claims = [c for c in claims if c and str(c).strip()]

    if router is not None and claims and transcript.strip():
        prompt = _JUDGE_PROMPT.format(
            transcript=transcript, claims=_build_claims_payload(claims)
        )
        try:
            report = router.generate_structured(
                prompt, response_model=JudgeReport, temperature=temperature
            )
            verdicts = [v.model_dump() for v in report.verdicts]
            supported = sum(1 for v in report.verdicts if v.supported)
            faithfulness = supported / len(report.verdicts) if report.verdicts else 1.0
            return {
                "verdicts": verdicts,
                "faithfulness": round(faithfulness, 4),
                "judge_used": True,
            }
        except Exception:
            # Fall through to lexical baseline on any judge failure.
            pass

    # Lexical baseline fallback (deterministic, offline).
    faithfulness = compute_faithfulness(claims, transcript)
    verdicts = [
        {
            "claim": c,
            "supported": True,
            "confidence": faithfulness,
            "rationale": "lexical baseline fallback",
        }
        for c in claims
    ]
    return {
        "verdicts": verdicts,
        "faithfulness": round(faithfulness, 4),
        "judge_used": False,
    }


def parse_judge_json(raw: str) -> Optional[dict]:
    """Best-effort parse of a raw judge response into a dict.

    Handles models that wrap JSON in code fences or emit prose around it.
    Returns ``None`` if no valid JSON object can be found.
    """
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fall back to extracting the first {...} block.
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None
