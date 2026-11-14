"""SaaS Data Models: Organizations, Subscriptions, Metering Quotas, and SOC2 Audit Logs."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from worker.core.database import Base


class Organization(Base):
    """B2B Customer Account (Wealth Management Firm, Insurance Provider, Enterprise)."""
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    tier = Column(String(50), default="GROWTH")  # PILOT, GROWTH, ENTERPRISE
    
    # Metering & Audio Quotas (in seconds)
    monthly_audio_quota_seconds = Column(Float, default=180000.0)  # 50 hours default
    consumed_audio_seconds = Column(Float, default=0.0)
    total_token_cost_usd = Column(Float, default=0.0)
    
    # Retention & Compliance Policy
    raw_audio_retention_days = Column(Integer, default=30)  # Purge raw audio after 30 days
    certificate_retention_years = Column(Integer, default=7)  # Retain SHA-256 certs for 7 yrs
    
    # Stripe Billing & Subscription Lifecycle
    stripe_customer_id = Column(String(255), index=True, nullable=True)
    stripe_subscription_id = Column(String(255), index=True, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class OrgMembership(Base):
    """User membership and role assignment within an organization."""
    __tablename__ = "org_memberships"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    role = Column(String(50), default="AUDITOR")  # ORG_OWNER, COMPLIANCE_DIRECTOR, AUDITOR, MEMBER
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AuditTrailEvent(Base):
    """Immutable SOC2 / HIPAA access ledger for who inspected or modified audit evidence."""
    __tablename__ = "audit_trail_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(36), index=True, nullable=False)
    user_id = Column(String(36), index=True, nullable=True)
    action = Column(String(100), nullable=False)  # AUDIO_UPLOADED, REPORT_INSPECTED, CLAIM_FLAGGED, CERTIFICATE_EXPORTED
    resource_id = Column(String(255), nullable=False)
    ip_address = Column(String(45), default="127.0.0.1")
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

