"""API endpoints for enterprise SaaS management, tenant quotas, and SOC2 audit ledger."""

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from typing import Optional
from sqlalchemy.orm import Session
from worker.core.database import get_db
from worker.saas.models.organization import Organization, OrgMembership
from worker.saas.services.metering import MeteringService
from worker.saas.services.ledger import AuditLedgerService
from worker.saas.services.retention import RetentionPolicyService

router = APIRouter(prefix="/api/v2/saas", tags=["B2B SaaS Enterprise Management"])


@router.post("/organizations")
def create_organization(
    name: str,
    tier: str = "GROWTH",
    monthly_hours_quota: float = 50.0,
    db: Session = Depends(get_db)
):
    """Provisions a new B2B client organization with allocated audio quota."""
    quota_seconds = monthly_hours_quota * 3600.0
    new_org = Organization(
        name=name,
        tier=tier,
        monthly_audio_quota_seconds=quota_seconds
    )
    db.add(new_org)
    db.commit()
    db.refresh(new_org)

    # Log provision event
    AuditLedgerService.record_event(
        db=db,
        org_id=new_org.id,
        action="ORG_PROVISIONED",
        resource_id=new_org.id,
        metadata={"name": name, "tier": tier, "quota_hours": monthly_hours_quota}
    )

    return {
        "org_id": new_org.id,
        "name": new_org.name,
        "tier": new_org.tier,
        "monthly_quota_hours": monthly_hours_quota,
        "created_at": new_org.created_at
    }


@router.get("/organizations")
def list_organizations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists enterprise organizations with standard pagination."""
    total_count = db.query(Organization).count()
    orgs = db.query(Organization).order_by(Organization.created_at.desc()).offset(skip).limit(limit).all()
    return {
        "total_count": total_count,
        "skip": skip,
        "limit": limit,
        "organizations": [
            {
                "org_id": o.id,
                "name": o.name,
                "tier": o.tier,
                "quota_hours": round(o.monthly_audio_quota_seconds / 3600.0, 1),
                "consumed_hours": round(o.consumed_audio_seconds / 3600.0, 2),
                "created_at": o.created_at
            }
            for o in orgs
        ]
    }


@router.get("/organizations/{org_id}/usage")
def get_org_usage_and_metering(
    org_id: str,
    db: Session = Depends(get_db)
):
    """Returns real-time audio consumption, remaining quota, and LLM token costs."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    remaining_sec = max(0.0, org.monthly_audio_quota_seconds - org.consumed_audio_seconds)
    percent_used = (org.consumed_audio_seconds / org.monthly_audio_quota_seconds * 100.0) if org.monthly_audio_quota_seconds > 0 else 0.0

    return {
        "org_id": org.id,
        "name": org.name,
        "tier": org.tier,
        "quota_hours": round(org.monthly_audio_quota_seconds / 3600.0, 1),
        "consumed_hours": round(org.consumed_audio_seconds / 3600.0, 2),
        "remaining_hours": round(remaining_sec / 3600.0, 2),
        "percent_used": round(percent_used, 1),
        "total_token_cost_usd": round(org.total_token_cost_usd, 4),
        "retention_policy_days": org.raw_audio_retention_days
    }


@router.get("/organizations/{org_id}/audit-ledger")
def get_soc2_audit_ledger(
    org_id: str,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db)
):
    """Retrieves immutable SOC2 / HIPAA access logs for who viewed or modified evidence."""
    events = AuditLedgerService.get_org_ledger(db=db, org_id=org_id, limit=limit)
    return {
        "org_id": org_id,
        "total_records": len(events),
        "events": [
            {
                "event_id": e.id,
                "action": e.action,
                "resource_id": e.resource_id,
                "user_id": e.user_id,
                "ip_address": e.ip_address,
                "timestamp": e.timestamp
            }
            for e in events
        ]
    }


@router.post("/retention/prune-media")
def trigger_privacy_retention_prune(
    retention_days: int = 30,
    db: Session = Depends(get_db)
):
    """Triggers automated destruction of expired raw audio files while preserving compliance certificates."""
    result = RetentionPolicyService.enforce_audio_retention(db=db, default_retention_days=retention_days)
    return result

