"""Job model: persists state transitions and extraction payloads."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text

from worker.core.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # PENDING -> PROCESSING -> COMPLETED | FAILED
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    input_payload = Column(Text, nullable=True)
    result_payload = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Job id={self.id} status={self.status}>"

