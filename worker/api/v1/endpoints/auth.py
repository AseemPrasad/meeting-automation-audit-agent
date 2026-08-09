"""Authentication endpoints.

Provides tenant-scoped registration and login that issue JWTs, plus a ``/me``
endpoint for inspecting the current principal. These routes are additive and
do not alter the existing transcript/job endpoints.

- POST /api/v1/auth/register  -> create a user, return a JWT
- POST /api/v1/auth/login     -> verify credentials, return a JWT
- GET  /api/v1/auth/me        -> return the current principal (requires token)
"""

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status

from worker.core.database import SessionLocal
from worker.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
    Principal,
)
from worker.models.user import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterBody(BaseModel):
    email: str
    password: str
    tenant_id: str = "default"
    role: str = "member"


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterBody):
    """Register a new tenant-scoped user and return a JWT."""
    email = (body.email or "").strip().lower()
    if not email or not body.password:
        raise HTTPException(status_code=422, detail="Email and password required")

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Email already registered")

        user = User(
            email=email,
            tenant_id=body.tenant_id or "default",
            role=body.role if body.role in {"admin", "member", "viewer"} else "member",
            password_hash=hash_password(body.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    finally:
        db.close()

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@router.post("/login")
async def login(body: LoginBody):
    """Authenticate a user and return a JWT."""
    email = (body.email or "").strip().lower()
    if not email or not body.password:
        raise HTTPException(status_code=422, detail="Email and password required")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
    finally:
        db.close()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}


@router.get("/me")
async def me(principal: Principal = Depends(get_current_user)):
    """Return the current authenticated principal."""
    return {
        "user_id": principal.user_id,
        "tenant_id": principal.tenant_id,
        "role": principal.role,
        "email": principal.email,
    }
