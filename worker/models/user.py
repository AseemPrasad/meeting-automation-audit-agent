"""User model: tenant-scoped identity with hashed password and role."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String

from worker.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(128), nullable=False, default="default", index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    # bcrypt hash (never store plaintext).
    password_hash = Column(String(255), nullable=False)
    # admin | member | viewer
    role = Column(String(20), nullable=False, default="member")
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} tenant={self.tenant_id} role={self.role}>"
