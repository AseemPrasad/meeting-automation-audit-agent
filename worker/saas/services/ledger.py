"""Immutable SOC2 / HIPAA access ledger logging for evidentiary records."""

import json
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from worker.saas.models.organization import AuditTrailEvent


class AuditLedgerService:
    """Records immutable audit access and modification logs for compliance defensibility."""

    @staticmethod
    def record_event(
        db: Session,
        org_id: str,
        action: str,
        resource_id: str,
        user_id: Optional[str] = None,
        ip_address: str = "127.0.0.1",
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditTrailEvent:
        """Appends an immutable event log to the SOC2 ledger."""
        event = AuditTrailEvent(
            org_id=org_id,
            user_id=user_id,
            action=action,
            resource_id=resource_id,
            ip_address=ip_address,
            details=json.dumps(metadata or {})
        )
        db.add(event)
        db.commit()
        return event

    @staticmethod
    def get_org_ledger(
        db: Session,
        org_id: str,
        limit: int = 100
    ):
        """Fetches the event ledger for compliance exports or audits."""
        return db.query(AuditTrailEvent).filter(
            AuditTrailEvent.org_id == org_id
        ).order_by(AuditTrailEvent.timestamp.desc()).limit(limit).all()

