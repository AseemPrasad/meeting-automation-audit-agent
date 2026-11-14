"""AuditAgent schemas for regulatory compliance, contract obligations, and evidentiary verification."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FLAGGED_UNSUBSTANTIATED = "FLAGGED_UNSUBSTANTIATED"
    OMITTED = "OMITTED"
    PARTIAL = "PARTIAL"


class ComplianceSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceItem(BaseModel):
    """An evidentiary item tied to verbatim transcript support and exact audio timestamps."""
    claim: str = Field(..., description="The factual commitment, warranty, disclosure, or agreement claim made.")
    verbatim_quote: str = Field(..., description="Exact word-for-word excerpt from the transcript.")
    speaker: str = Field(default="Unknown", description="Speaker identity or legal role (e.g. Advisor, Client, Vendor).")
    start_timestamp: float = Field(..., description="Audio offset start time in seconds.")
    end_timestamp: float = Field(..., description="Audio offset end time in seconds.")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Verification confidence from the inspector.")
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.VERIFIED,
        description="Whether the claim is substantiated by verbatim audio or flagged as hallucination."
    )


class ComplianceRequirementCheck(BaseModel):
    """Evaluation of a specific regulatory mandate, SLA, or contractual disclosure."""
    requirement_code: str = Field(..., description="Identifier (e.g., SEC_REG_BI_01, SLA_UPTIME_WARRANTY, HIPAA_CONSENT).")
    title: str = Field(..., description="Human-readable requirement title.")
    severity: ComplianceSeverity = Field(default=ComplianceSeverity.HIGH)
    passed: bool = Field(..., description="True if requirement is fully met and substantiated.")
    findings: str = Field(..., description="Explanation of compliance adherence or failure reasoning.")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Verbatim citations proving compliance.")


class AuditReportResponse(BaseModel):
    """Comprehensive, tamper-evident audit report ready for regulatory or legal submission."""
    audit_id: str = Field(..., description="Unique audit identifier.")
    job_id: str = Field(..., description="Associated ingestion job identifier.")
    compliance_score: float = Field(..., ge=0.0, le=100.0, description="Overall compliance score percentage (0-100).")
    overall_status: str = Field(..., description="COMPLIANT, NON_COMPLIANT, or NEEDS_LEGAL_REVIEW.")
    summary_findings: str = Field(..., description="Executive compliance and risk assessment overview.")
    requirements_evaluated: List[ComplianceRequirementCheck] = Field(default_factory=list)
    unsubstantiated_or_hallucinated_claims: List[EvidenceItem] = Field(
        default_factory=list,
        description="Claims that were made or extracted but could NOT be proven against verbatim audio."
    )
    tamper_proof_sha256: str = Field(..., description="Cryptographic SHA-256 hash sealing transcript + audit result.")

