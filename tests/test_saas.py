"""Integration tests for B2B SaaS Metering, Organization Provisioning, and SOC2 Audit Ledger."""

import pytest
from worker.core.database import SessionLocal, init_db, Base, engine
from worker.saas.models.organization import Organization, AuditTrailEvent
from worker.saas.services.metering import MeteringService
from worker.saas.services.ledger import AuditLedgerService
from worker.saas.services.retention import RetentionPolicyService


@pytest.fixture(autouse=True)
def ensure_db_tables():
    """Ensure SaaS tables are registered and created in the DB."""
    Base.metadata.create_all(bind=engine)


def test_organization_provisioning_and_metering():
    db = SessionLocal()
    try:
        # 1. Provision Org with 2 hours quota (7200 seconds)
        org = Organization(
            name="Apex Wealth Partners",
            tier="ENTERPRISE",
            monthly_audio_quota_seconds=7200.0,
            consumed_audio_seconds=0.0
        )
        db.add(org)
        db.commit()
        db.refresh(org)

        assert org.id is not None
        assert org.tier == "ENTERPRISE"

        # 2. Check quota available for 30-min call (1800s)
        allowed, msg = MeteringService.check_quota_available(db, org.id, estimated_audio_seconds=1800.0)
        assert allowed is True

        # 3. Deduct usage
        usage_res = MeteringService.deduct_usage(db, org.id, actual_audio_seconds=1800.0, token_cost_usd=0.042)
        assert usage_res["consumed_audio_seconds"] == 1800.0
        assert usage_res["remaining_seconds"] == 5400.0
        assert usage_res["total_token_cost_usd"] == 0.042

        # 4. Attempt to consume more than remaining quota (e.g. 6000s)
        allowed_over, msg_over = MeteringService.check_quota_available(db, org.id, estimated_audio_seconds=6000.0)
        assert allowed_over is False
        assert "exceeded" in msg_over
    finally:
        db.close()


def test_soc2_audit_trail_logging():
    db = SessionLocal()
    try:
        org_id = "test-org-123"
        event = AuditLedgerService.record_event(
            db=db,
            org_id=org_id,
            action="REPORT_INSPECTED",
            resource_id="audit-job-999",
            user_id="user-compliance-officer",
            ip_address="192.168.1.50",
            metadata={"browser": "Chrome", "action_reason": "SEC annual examination"}
        )

        assert event.id is not None
        assert event.action == "REPORT_INSPECTED"

        # Retrieve org ledger
        ledger = AuditLedgerService.get_org_ledger(db, org_id)
        assert len(ledger) >= 1
        assert ledger[0].resource_id == "audit-job-999"
    finally:
        db.close()


def test_retention_policy_enforcement():
    db = SessionLocal()
    try:
        res = RetentionPolicyService.enforce_audio_retention(db=db, default_retention_days=30)
        assert res["status"] == "success"
        assert "audio_files_purged" in res
    finally:
        db.close()


def test_stripe_subscription_lifecycle_and_reset():
    import uuid
    test_cus_id = f"cus_test_{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        org = Organization(
            name="Stripe Test Org",
            tier="PILOT",
            stripe_customer_id=test_cus_id,
            monthly_audio_quota_seconds=3600.0,
            consumed_audio_seconds=3500.0
        )
        db.add(org)
        db.commit()

        # Simulate renewal payment success -> consumed usage should reset to 0
        success = MeteringService.handle_subscription_payment_succeeded(
            db=db,
            stripe_customer_id=test_cus_id,
            current_period_end_timestamp=1735689600
        )
        assert success is True
        db.refresh(org)
        assert org.consumed_audio_seconds == 0.0
        assert org.current_period_end is not None

        # Simulate subscription upgrade to Enterprise
        upgrade_ok = MeteringService.update_subscription_tier(
            db=db,
            stripe_customer_id=test_cus_id,
            new_tier="ENTERPRISE",
            monthly_quota_seconds=720000.0
        )
        assert upgrade_ok is True
        db.refresh(org)
        assert org.tier == "ENTERPRISE"
        assert org.monthly_audio_quota_seconds == 720000.0
    finally:
        db.close()



