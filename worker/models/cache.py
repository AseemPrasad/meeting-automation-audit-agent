"""Cache metadata model for observability of the semantic cache layer.

The vector payload itself lives in Redis; this relational table tracks which
texts were cached, by which tenant, and when they expire so operators can
inspect and audit cache usage.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from worker.core.database import Base


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(128), nullable=False, default="default", index=True)
    # Stable hash of the cached text (for exact-hit inspection).
    text_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at = Column(DateTime, nullable=True, index=True)
    # Hit/miss counters for observability.
    hits = Column(Integer, nullable=False, default=0)
    misses = Column(Integer, nullable=False, default=0)
    # Optional: cached payload size in bytes for cost tracking.
    payload_bytes = Column(BigInteger, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<CacheEntry id={self.id} tenant={self.tenant_id}>"

