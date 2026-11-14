"""Job model: persists state transitions and extraction payloads."""
import uuid
import json
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text

from worker.core.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(128), nullable=False, default="default", index=True)
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

    @property
    def result(self):
        """Dynamic hybrid property to read parsed JSON from result_payload."""
        if self.result_payload:
            try:
                return json.loads(self.result_payload)
            except Exception:
                return self.result_payload
        return None

    @result.setter
    def result(self, value):
        """Dynamic hybrid setter to serialize dict/list into result_payload."""
        if isinstance(value, (dict, list)):
            self.result_payload = json.dumps(value)
        else:
            self.result_payload = value

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Job id={self.id} status={self.status}>"
