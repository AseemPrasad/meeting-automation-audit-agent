"""Tests for the security layer: JWT auth, RBAC, rate limiting, tenant scoping."""

import os
import tempfile

import pytest
from fastapi import HTTPException

# Point the DB to a throwaway file before importing worker modules.
_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

from worker.core.security import (  # noqa: E402
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
    get_current_user,
    require_role,
    Principal,
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_VIEWER,
)
from worker.middleware.rate_limit import _MemoryBucket  # noqa: E402


# --- JWT + password hashing ------------------------------------------------
def test_password_hash_roundtrip():
    hashed = hash_password("s3cret")
    assert hashed != "s3cret"
    assert verify_password("s3cret", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_jwt_roundtrip():
    token = create_access_token(
        user_id="u1", tenant_id="tenant-a", role=ROLE_ADMIN, email="a@b.c"
    )
    claims = decode_token(token)
    assert claims["sub"] == "u1"
    assert claims["tenant_id"] == "tenant-a"
    assert claims["role"] == ROLE_ADMIN
    assert claims["email"] == "a@b.c"
    assert "exp" in claims


# --- get_current_user dependency ------------------------------------------
class _FakeCreds:
    def __init__(self, scheme, credentials):
        self.scheme = scheme
        self.credentials = credentials


def test_get_current_user_valid():
    token = create_access_token("u1", "tenant-a", ROLE_MEMBER, "m@x.io")
    principal = get_current_user(_FakeCreds("Bearer", token))
    assert isinstance(principal, Principal)
    assert principal.user_id == "u1"
    assert principal.tenant_id == "tenant-a"
    assert principal.role == ROLE_MEMBER


def test_get_current_user_missing_raises():
    with pytest.raises(HTTPException) as exc:
        get_current_user(None)
    assert exc.value.status_code == 401


def test_get_current_user_invalid_token_raises():
    with pytest.raises(HTTPException) as exc:
        get_current_user(_FakeCreds("Bearer", "not.a.jwt"))
    assert exc.value.status_code == 401


def test_get_current_user_wrong_scheme_raises():
    with pytest.raises(HTTPException) as exc:
        get_current_user(_FakeCreds("Basic", "abc"))
    assert exc.value.status_code == 401


# --- RBAC -----------------------------------------------------------------
def test_require_role_allows_matching():
    token = create_access_token("u1", "tenant-a", ROLE_ADMIN)
    principal = get_current_user(_FakeCreds("Bearer", token))
    checker = require_role(ROLE_ADMIN)
    assert checker(principal).role == ROLE_ADMIN


def test_require_role_denies_insufficient():
    token = create_access_token("u1", "tenant-a", ROLE_VIEWER)
    principal = get_current_user(_FakeCreds("Bearer", token))
    checker = require_role(ROLE_ADMIN)
    with pytest.raises(HTTPException) as exc:
        checker(principal)
    assert exc.value.status_code == 403


# --- Rate limiter (in-memory fallback) ------------------------------------
def test_memory_bucket_enforces_limit():
    bucket = _MemoryBucket(limit=2, window=60)
    assert bucket.allow("key") is True
    assert bucket.allow("key") is True
    assert bucket.allow("key") is False
    # A different key is unaffected (per-tenant isolation)
    assert bucket.allow("other") is True


# --- Tenant scoping on job queries ----------------------------------------
def test_job_tenant_scoping():
    from worker.core.database import SessionLocal, init_db
    from worker.models.job import Job

    init_db()
    db = SessionLocal()
    try:
        db.add(Job(id="job-a", tenant_id="tenant-1", status="PENDING"))
        db.add(Job(id="job-b", tenant_id="tenant-2", status="PENDING"))
        db.commit()

        # Tenant 1 sees only its own job
        theirs = (
            db.query(Job)
            .filter(Job.id == "job-a", Job.tenant_id == "tenant-1")
            .first()
        )
        other = (
            db.query(Job)
            .filter(Job.id == "job-b", Job.tenant_id == "tenant-1")
            .first()
        )
        assert theirs is not None
        assert other is None
    finally:
        db.close()


def teardown_module():
    from worker.core.database import engine

    engine.dispose()
    try:
        os.unlink(_db_path)
    except PermissionError:  # pragma: no cover - Windows occasionally locks the file
        pass
