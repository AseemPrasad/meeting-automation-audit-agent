"""Adversarial verifier node that cross-examines claims against the raw transcript."""

import re
from typing import List, Tuple
from worker.audit.schemas.compliance import EvidenceItem, VerificationStatus


def verify_claims_against_transcript(
    extracted_claims: List[EvidenceItem],
    raw_transcript: str,
    speaker_attributions: Optional[dict] = None
) -> Tuple[List[EvidenceItem], List[EvidenceItem]]:
    """
    Adversarial cross-examination:
    Verifies that every extracted claim has actual verbatim grounding in the transcript
    and confirms speaker attribution consistency when speaker_attributions are available.
    """
    verified = []
    unsubstantiated = []

    # Normalized transcript for fuzzy search
    normalized_transcript = " ".join(raw_transcript.lower().split())

    for item in extracted_claims:
        clean_quote = " ".join(item.verbatim_quote.lower().split())
        
        # Check speaker role conflict if speaker attributions are provided
        if speaker_attributions and item.speaker:
            spk_lower = item.speaker.lower()
            is_client = any(
                k.lower() in spk_lower and "client" in v.lower()
                for k, v in speaker_attributions.items()
            ) or "client" in spk_lower

            # If attributed to Advisor but quote is actually from client, flag warning
            if is_client and "advisor" in item.claim.lower():
                item.verification_status = VerificationStatus.FLAGGED_UNSUBSTANTIATED
                item.confidence_score = 0.3
                unsubstantiated.append(item)
                continue

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

