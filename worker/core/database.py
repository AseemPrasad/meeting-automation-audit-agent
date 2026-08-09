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

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # SQLite requires this when used from multiple threads (FastAPI + worker)
    _connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db() -> None:
    """Create all tables (idempotent). Safe to call from web and worker."""
    from worker.models.job import Job  # noqa: F401  (register model with Base)
    from worker.models.cache import CacheEntry  # noqa: F401  (register model)
    from worker.models.user import User  # noqa: F401  (register model)

    Base.metadata.create_all(bind=engine)
