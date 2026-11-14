"""Adversarial verifier node that cross-examines claims against the raw transcript."""

import re
from typing import List, Tuple
from worker.audit.schemas.compliance import EvidenceItem, VerificationStatus


def verify_claims_against_transcript(
    extracted_claims: List[EvidenceItem],
    raw_transcript: str
) -> Tuple[List[EvidenceItem], List[EvidenceItem]]:
    """
    Adversarial cross-examination:
    Verifies that every extracted claim has actual verbatim grounding in the transcript.
    If the verbatim quote cannot be matched or is suspiciously absent, it is flagged as
    FLAGGED_UNSUBSTANTIATED and segregated.
    
    Returns:
        (verified_claims, unsubstantiated_claims)
    """
    verified = []
    unsubstantiated = []

    # Normalized transcript for fuzzy search
    normalized_transcript = " ".join(raw_transcript.lower().split())

    for item in extracted_claims:
        clean_quote = " ".join(item.verbatim_quote.lower().split())
        
        # Exact quote or robust substring match (at least 70% of quote present)
        if clean_quote and clean_quote in normalized_transcript:
            item.verification_status = VerificationStatus.VERIFIED
            item.confidence_score = 1.0
            verified.append(item)
        else:
            # Check for high token overlap
            quote_tokens = set(clean_quote.split())
            if len(quote_tokens) > 4:
                # Find best token containment in sliding window
                matches = sum(1 for tok in quote_tokens if tok in normalized_transcript)
                overlap_ratio = matches / len(quote_tokens)
                if overlap_ratio >= 0.85:
                    item.verification_status = VerificationStatus.VERIFIED
                    item.confidence_score = round(overlap_ratio, 2)
                    verified.append(item)
                    continue

            # If not backed by verbatim evidence, flag as hallucination/unsubstantiated
            item.verification_status = VerificationStatus.FLAGGED_UNSUBSTANTIATED
            item.confidence_score = 0.2
            unsubstantiated.append(item)

    return verified, unsubstantiated

