"""Security utilities: JWT auth, password hashing, and RBAC dependencies.

This module provides the building blocks for authenticating requests and
enforcing role-based access control (Admin / Member / Viewer) with an
Organization (tenant) context. It is intentionally self-contained and
additive: nothing here changes existing routes or middleware behavior.

The ``get_current_user`` FastAPI dependency decodes the ``Authorization:
Bearer <token>`` header and returns a :class:`Principal` describing the caller.
Route handlers can then read ``principal.tenant_id`` to scope their queries and
use :func:`require_role` to restrict access by role.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

load_dotenv()

# --- Role constants ---------------------------------------------------------
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"
ROLE_VIEWER = "viewer"
VALID_ROLES = {ROLE_ADMIN, ROLE_MEMBER, ROLE_VIEWER}

# --- JWT configuration ------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "60"))

# --- Password hashing -------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    """Authenticated caller identity: user, tenant, and role."""

    user_id: str
    tenant_id: str
    role: str
    email: Optional[str] = None


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:  # noqa: BLE001 - malformed hash should not crash
        return False


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    email: Optional[str] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    """Create a signed JWT containing user, tenant, and role claims."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(
        minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "email": email,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises ``jwt.PyJWTError`` on failure."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Principal:
    """FastAPI dependency: parse the Bearer token and return a Principal.

    Raises 401 when the token is missing or invalid.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    role = claims.get("role", ROLE_VIEWER)
    if role not in VALID_ROLES:
        role = ROLE_VIEWER

    return Principal(
        user_id=claims.get("sub", ""),
        tenant_id=claims.get("tenant_id", ""),
        role=role,
        email=claims.get("email"),
    )


def require_role(*roles: str):
    """Build a FastAPI dependency that enforces one of the given roles."""

    def _checker(principal: Principal = Depends(get_current_user)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return principal

    return _checker
