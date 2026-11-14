"""SQLAlchemy engine/session for relational job-state persistence.

Defaults to SQLite (zero external setup); can be switched to PostgreSQL by
setting the DATABASE_URL environment variable.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobs.db")
DATABASE_READ_REPLICA_URL = os.getenv("DATABASE_READ_REPLICA_URL")

_connect_args = {}
_engine_kwargs = {}

if DATABASE_URL.startswith("sqlite"):
    # SQLite requires this when used from multiple threads (FastAPI + worker)
    _connect_args["check_same_thread"] = False
else:
    # Production PostgreSQL connection pooling to survive failovers and TCP timeouts
    _engine_kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "20"))
    _engine_kwargs["max_overflow"] = int(os.getenv("DB_MAX_OVERFLOW", "30"))
    _engine_kwargs["pool_recycle"] = int(os.getenv("DB_POOL_RECYCLE", "1800"))
    _engine_kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)

# Read replica engine (falls back to primary engine if no replica configured)
if DATABASE_READ_REPLICA_URL:
    read_engine = create_engine(DATABASE_READ_REPLICA_URL, connect_args=_connect_args, **_engine_kwargs)
else:
    read_engine = engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
ReadSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=read_engine)

Base = declarative_base()


def get_db():
    """FastAPI transactional database dependency for write & transactional operations."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_read_db():
    """FastAPI read-only database dependency routing traffic to read replicas."""
    db = ReadSessionLocal()
    try:
        yield db
    finally:
        db.close()



def init_db() -> None:
    """Create all tables (idempotent). Safe to call from web and worker."""
    from worker.models.job import Job  # noqa: F401  (register model with Base)
    from worker.models.cache import CacheEntry  # noqa: F401  (register model)
    from worker.models.user import User  # noqa: F401  (register model)
    from worker.saas.models.organization import (  # noqa: F401 (register SaaS models)
        Organization,
        OrgMembership,
        AuditTrailEvent,
    )

    Base.metadata.create_all(bind=engine)
