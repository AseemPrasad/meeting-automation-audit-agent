"""Credit metering service: Enforces audio-hour quotas and tracks LLM token spend per tenant."""

from typing import Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from worker.saas.models.organization import Organization


class MeteringService:
    """Manages audio quota allocation and credit deductions for enterprise B2B tenants."""

    @staticmethod
    def check_quota_available(
        db: Session,
        org_id: str,
        estimated_audio_seconds: float = 3600.0
    ) -> Tuple[bool, str]:
        """
        Verifies if the organization has sufficient audio quota remaining.
        Returns: (is_allowed, reason_message)
        """
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            # If org does not exist (dev mode or unmetered tier), permit execution
            return True, "Unmetered access (default/dev tier)"

        remaining = org.monthly_audio_quota_seconds - org.consumed_audio_seconds
        if remaining < estimated_audio_seconds:
            return False, f"Monthly audio quota exceeded. Remaining: {remaining:.1f}s, Required: {estimated_audio_seconds:.1f}s"

        return True, "Quota verified"

    @staticmethod
    def deduct_usage(
        db: Session,
        org_id: str,
        actual_audio_seconds: float,
        token_cost_usd: float = 0.0
    ) -> Dict[str, Any]:
        """Atomically deducts consumed audio seconds and records LLM inference cost to prevent race conditions."""
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            return {"status": "unmetered"}

        # Atomic SQL-level increment preventing lost-update race conditions
        db.query(Organization).filter(Organization.id == org_id).update({
            Organization.consumed_audio_seconds: Organization.consumed_audio_seconds + actual_audio_seconds,
            Organization.total_token_cost_usd: Organization.total_token_cost_usd + token_cost_usd
        })
        db.commit()
        db.refresh(org)

        remaining = max(0.0, org.monthly_audio_quota_seconds - org.consumed_audio_seconds)
        percent_used = (org.consumed_audio_seconds / org.monthly_audio_quota_seconds * 100.0) if org.monthly_audio_quota_seconds > 0 else 100.0

        return {
            "org_id": org_id,
            "consumed_audio_seconds": round(org.consumed_audio_seconds, 1),
            "remaining_seconds": round(remaining, 1),
            "percent_consumed": round(percent_used, 1),
            "total_token_cost_usd": round(org.total_token_cost_usd, 4)
        }

    @staticmethod
    def handle_subscription_payment_succeeded(
        db: Session,
        stripe_customer_id: str,
        current_period_end_timestamp: Optional[int] = None
    ) -> bool:
        """Resets consumed quota when an invoice/subscription renewal payment succeeds."""
        from datetime import datetime, timezone
        org = db.query(Organization).filter(Organization.stripe_customer_id == stripe_customer_id).first()
        if not org:
            return False

        org.consumed_audio_seconds = 0.0
        if current_period_end_timestamp:
            org.current_period_end = datetime.fromtimestamp(current_period_end_timestamp, tz=timezone.utc)
        db.commit()
        return True

    @staticmethod
    def update_subscription_tier(
        db: Session,
        stripe_customer_id: str,
        new_tier: str,
        monthly_quota_seconds: Optional[float] = None
    ) -> bool:
        """Updates plan tier and monthly quota upon subscription change/downgrade."""
        org = db.query(Organization).filter(Organization.stripe_customer_id == stripe_customer_id).first()
        if not org:
            return False

        org.tier = new_tier.upper()
        if monthly_quota_seconds is not None:
            org.monthly_audio_quota_seconds = monthly_quota_seconds
        db.commit()
        return True


