"""Compliance auditor node: grades verified evidence against regulatory checklists."""

import hashlib
import json
import uuid
from typing import List, Dict, Any, Optional
from worker.audit.schemas.compliance import (
    EvidenceItem,
    ComplianceRequirementCheck,
    ComplianceSeverity,
    AuditReportResponse,
)
from worker.audit.services.templates import TEMPLATES, FINRA_REG_BI_TEMPLATE
from worker.audit.agents.verifier import verify_claims_against_transcript


def audit_transcript_compliance(
    raw_transcript: str,
    extracted_evidence: List[EvidenceItem],
    template_name: str = "FINRA_REG_BI",
    job_id: Optional[str] = None,
    audio_sha256: Optional[str] = None,
    org_id: Optional[str] = None
) -> AuditReportResponse:
    """
    Evaluates verified claims against specified compliance template.
    Generates a cryptographic tamper-evident audit report incorporating the source audio hash and org_id.
    """
    template = TEMPLATES.get(template_name, FINRA_REG_BI_TEMPLATE)
    
    # 1. Run adversarial verification on raw claims
    verified_claims, unsubstantiated = verify_claims_against_transcript(
        extracted_evidence, raw_transcript
    )

    requirements_results: List[ComplianceRequirementCheck] = []
    passed_count = 0

    transcript_lower = raw_transcript.lower()

    for rule in template:
        code = rule["code"]
        title = rule["title"]
        desc = rule["description"]

        # Match evidence to this rule with stop-word filtering
        STOP_WORDS = {"mandatory", "clear", "documented", "the", "and", "must", "with", "for", "have", "agreement"}
        title_terms = [t for t in title.lower().split() if t not in STOP_WORDS and len(t) > 2]
        desc_terms = [t for t in desc.lower().split() if t not in STOP_WORDS and len(t) > 3]

        matched_evidence = [
            item for item in verified_claims
            if any(term in item.claim.lower() for term in title_terms[:4])
            or any(term in item.verbatim_quote.lower() for term in desc_terms[:4])
        ]

        if not matched_evidence:
            # Fallback heuristic: check if substantive concepts exist in transcript
            matched_terms = [t for t in desc_terms if t in transcript_lower]
            if len(matched_terms) >= 2:
                # Disclosed in transcript
                passed = True
                findings = f"Requirement addressed in dialogue ({', '.join(matched_terms[:3])})."
            else:
                passed = False
                findings = f"Mandatory disclosure or discussion for '{title}' was missing or inconclusive."
        else:
            passed = True
            findings = f"Substantiated by {len(matched_evidence)} verified audio citation(s)."

        if passed:
            passed_count += 1

        requirements_results.append(
            ComplianceRequirementCheck(
                requirement_code=code,
                title=title,
                severity=ComplianceSeverity.HIGH,
                passed=passed,
                findings=findings,
                evidence=matched_evidence
            )
        )

    # 2. Calculate score
    total_reqs = len(template)
    score = (passed_count / total_reqs * 100.0) if total_reqs > 0 else 100.0
    
    if score >= 90.0:
        overall_status = "COMPLIANT"
    elif score >= 60.0:
        overall_status = "NEEDS_LEGAL_REVIEW"
    else:
        overall_status = "NON_COMPLIANT"

    summary_findings = (
        f"Audit completed under standard '{template_name}'. "
        f"Passed {passed_count} of {total_reqs} mandatory checks ({score:.1f}%). "
        f"Identified {len(unsubstantiated)} unsubstantiated/hallucinated claim(s)."
    )

    # 3. Create SHA-256 seal for tamper proofing (including raw audio binary hash and org_id with normalized line-endings)
    normalized_transcript = raw_transcript.replace("\r\n", "\n").strip()
    payload_to_hash = json.dumps({
        "org_id": org_id or "unassigned_tenant",
        "audio_sha256": audio_sha256 or "no_audio_hash_provided",
        "transcript": normalized_transcript,
        "score": score,
        "template": template_name,
        "findings": summary_findings
    }, sort_keys=True)
    sha256_hash = hashlib.sha256(payload_to_hash.encode("utf-8")).hexdigest()

    return AuditReportResponse(
        audit_id=str(uuid.uuid4()),
        job_id=job_id or str(uuid.uuid4()),
        compliance_score=round(score, 1),
        overall_status=overall_status,
        summary_findings=summary_findings,
        requirements_evaluated=requirements_results,
        unsubstantiated_or_hallucinated_claims=unsubstantiated,
        tamper_proof_sha256=sha256_hash
    )

