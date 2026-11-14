"""Unit and integration tests for AuditAgent (High-Stakes Compliance & Contract Auditor)."""

import pytest
from worker.audit.schemas.compliance import (
    EvidenceItem,
    VerificationStatus,
    ComplianceSeverity,
    AuditReportResponse,
)
from worker.audit.agents.verifier import verify_claims_against_transcript
from worker.audit.agents.auditor import audit_transcript_compliance
from worker.audit.services.templates import TEMPLATES
from worker.audit.services.audio import get_audio_file_size_mb, split_audio_if_needed


def test_audit_schemas_serialization():
    evidence = EvidenceItem(
        claim="Advisor disclosed 1.5% fee structure",
        verbatim_quote="Our annual advisory fee is 1.5% of assets under management",
        speaker="Advisor",
        start_timestamp=12.5,
        end_timestamp=18.0,
        confidence_score=0.98,
        verification_status=VerificationStatus.VERIFIED
    )
    assert evidence.speaker == "Advisor"
    assert evidence.verification_status == VerificationStatus.VERIFIED

    dumped = evidence.model_dump()
    assert dumped["start_timestamp"] == 12.5
    assert dumped["claim"] == "Advisor disclosed 1.5% fee structure"


def test_adversarial_verifier_accepts_grounded_claim():
    transcript = (
        "Good morning Mr. Smith. Before we begin, please note that past performance "
        "does not guarantee future results, and all market investments carry principal risk."
    )
    claim = EvidenceItem(
        claim="Advisor provided investment risk disclosure",
        verbatim_quote="past performance does not guarantee future results",
        speaker="Advisor",
        start_timestamp=5.0,
        end_timestamp=10.0
    )

    verified, unsubstantiated = verify_claims_against_transcript([claim], transcript)
    assert len(verified) == 1
    assert len(unsubstantiated) == 0
    assert verified[0].verification_status == VerificationStatus.VERIFIED


def test_adversarial_verifier_flags_hallucinated_claim():
    transcript = "The client asked about tech stocks, but we did not discuss any guarantees."
    hallucinated_claim = EvidenceItem(
        claim="Advisor guaranteed 20% annual returns",
        verbatim_quote="We guarantee you will earn a 20% return this year",
        speaker="Advisor",
        start_timestamp=30.0,
        end_timestamp=35.0
    )

    verified, unsubstantiated = verify_claims_against_transcript([hallucinated_claim], transcript)
    assert len(verified) == 0
    assert len(unsubstantiated) == 1
    assert unsubstantiated[0].verification_status == VerificationStatus.FLAGGED_UNSUBSTANTIATED


def test_audit_transcript_compliance_scoring_and_sha256():
    transcript = (
        "Today we are reviewing your portfolio. First, the fee structure: our annual advisory fee is 1%. "
        "Second, regarding investment risk, past performance does not guarantee future results. "
        "The client confirmed their risk tolerance is moderate."
    )
    extracted = [
        EvidenceItem(
            claim="Fee schedule disclosed as 1%",
            verbatim_quote="our annual advisory fee is 1%",
            start_timestamp=2.0,
            end_timestamp=6.0
        ),
        EvidenceItem(
            claim="Market risk disclosure communicated",
            verbatim_quote="past performance does not guarantee future results",
            start_timestamp=7.0,
            end_timestamp=12.0
        )
    ]

    report = audit_transcript_compliance(
        raw_transcript=transcript,
        extracted_evidence=extracted,
        template_name="FINRA_REG_BI"
    )

    assert isinstance(report, AuditReportResponse)
    assert report.compliance_score >= 50.0
    assert report.tamper_proof_sha256 is not None
    assert len(report.tamper_proof_sha256) == 64  # Valid SHA-256 length


def test_templates_registry():
    assert "FINRA_REG_BI" in TEMPLATES
    assert "COMMERCIAL_SLA" in TEMPLATES
    assert len(TEMPLATES["FINRA_REG_BI"]) >= 3


def test_audio_splitter_handles_small_file(tmp_path):
    small_file = tmp_path / "test.mp3"
    small_file.write_text("dummy audio data")
    
    chunks = split_audio_if_needed(str(small_file), max_chunk_mb=24.0)
    assert len(chunks) == 1
    assert chunks[0][0] == str(small_file)
    assert chunks[0][1] == 0.0

