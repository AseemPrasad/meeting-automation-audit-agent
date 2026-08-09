"""Core numerical quality metrics for meeting-analysis evaluation.

All functions here are pure and deterministic (no LLM calls), making them
trivially testable offline. They compute scores in the ``0.0 - 1.0`` range:

- ``compute_faithfulness``: the Faithfulness / Hallucination Index. Verifies
  that each extracted claim/action item is directly supported by the source
  transcript. Higher = more faithful (fewer hallucinations).
- ``compute_action_item_recall``: extraction completeness against a ground
  truth benchmark. Measures how many of the expected action items were
  actually extracted.

The LLM-as-a-Judge refinement lives in ``judge.py``; these functions provide
the deterministic baseline and the final aggregated numbers.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

# A claim is "supported" if a meaningful fraction of its significant tokens
# appear in the transcript. Tokens are lowercased and stripped of punctuation.
_TOKEN_RE = re.compile(r"[a-z0-9']+")

# Fraction of claim tokens that must appear in the transcript for the claim to
# be considered directly supported. Tunable per deployment.
_SUPPORT_THRESHOLD = 0.6


def _tokenize(text: str) -> set:
    """Return the set of significant lowercased tokens in ``text``."""
    return set(_TOKEN_RE.findall(text.lower()))


def _significant_tokens(text: str) -> set:
    """Tokens minus an English stopword list (kept small and dependency-free)."""
    stopwords = {
        "the", "a", "an", "and", "or", "but", "if", "then", "else", "of",
        "to", "in", "on", "for", "with", "at", "by", "from", "as", "is",
        "are", "was", "were", "be", "been", "being", "it", "this", "that",
        "these", "those", "we", "you", "they", "he", "she", "i", "will",
        "would", "can", "could", "should", "shall", "do", "does", "did",
        "have", "has", "had", "not", "no", "yes", "so", "very", "just",
        "about", "into", "over", "after", "before", "between", "also",
        "more", "most", "some", "any", "each", "all", "both", "our", "them",
    }
    return _tokenize(text) - stopwords


def _claim_supported(claim: str, transcript_tokens: set) -> bool:
    """Return True if ``claim`` is directly supported by the transcript.

    A claim is supported if at least ``_SUPPORT_THRESHOLD`` of its significant
    tokens are present in the transcript token set. This is a strict lexical
    containment check; the judge (``judge.py``) can refine it semantically.
    """
    claim_tokens = _significant_tokens(claim)
    if not claim_tokens:
        # Empty claims are vacuously supported (nothing to hallucinate).
        return True
    overlap = len(claim_tokens & transcript_tokens)
    return (overlap / len(claim_tokens)) >= _SUPPORT_THRESHOLD


def compute_faithfulness(
    claims: Iterable[str], transcript: str
) -> float:
    """Compute the Faithfulness / Hallucination Index in ``0.0 - 1.0``.

    The score is the fraction of claims that are directly supported by the
    transcript. ``1.0`` means every claim is supported (no hallucination);
    lower values indicate a higher rate of hallucinated/unverifiable content.
    """
    claims = [c for c in claims if c and str(c).strip()]
    if not claims:
        # No claims to verify -> vacuously faithful.
        return 1.0
    transcript_tokens = _significant_tokens(transcript)
    supported = sum(
        1 for c in claims if _claim_supported(str(c), transcript_tokens)
    )
    return supported / len(claims)


def token_set_similarity(a: str, b: str) -> float:
    """Jaccard similarity between the significant tokens of two strings."""
    tok_a = _significant_tokens(a)
    tok_b = _significant_tokens(b)
    if not tok_a and not tok_b:
        return 1.0
    if not tok_a or not tok_b:
        return 0.0
    inter = len(tok_a & tok_b)
    union = len(tok_a | tok_b)
    return inter / union


def compute_action_item_recall(
    extracted_tasks: Sequence[str],
    ground_truth_tasks: Sequence[str],
    similarity_threshold: float = 0.4,
) -> float:
    """Compute Action Item Recall in ``0.0 - 1.0`` against a ground-truth set.

    For each ground-truth task, it is considered "recalled" if it matches at
    least one extracted task with token-set (Jaccard) similarity at or above
    ``similarity_threshold``. The score is the fraction of ground-truth tasks
    recalled. ``1.0`` means all expected action items were extracted.
    """
    extracted = [str(t) for t in extracted_tasks if t and str(t).strip()]
    ground_truth = [str(t) for t in ground_truth_tasks if t and str(t).strip()]
    if not ground_truth:
        # Nothing expected -> trivially complete.
        return 1.0
    if not extracted:
        return 0.0

    recalled = 0
    for gt in ground_truth:
        best = max(
            (token_set_similarity(gt, ex) for ex in extracted), default=0.0
        )
        if best >= similarity_threshold:
            recalled += 1
    return recalled / len(ground_truth)


def aggregate_scores(
    faithfulness: float,
    action_item_recall: float,
    *,
    faithfulness_weight: float = 0.5,
) -> dict:
    """Combine the two metrics into a single report dict.

    Returns a dict with the individual metrics plus a weighted overall quality
    score (default 50/50). Pure and deterministic.
    """
    overall = (
        faithfulness_weight * faithfulness
        + (1.0 - faithfulness_weight) * action_item_recall
    )
    return {
        "faithfulness": round(faithfulness, 4),
        "action_item_recall": round(action_item_recall, 4),
        "overall_quality": round(overall, 4),
    }
