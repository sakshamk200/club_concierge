"""Account routes: register, login, current-user, and profile update.

Accounts live in ``public.app_users`` with salted PBKDF2 password hashes.
Sessions are stateless HMAC-signed bearer tokens verified per request.
"""

from __future__ import annotations

import logging
import secrets
from uuid import UUID

import asyncpg
import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.config import get_settings
from app.db.pool import ensure_pool
from app.db.users_repo import UsersRepository
from app.models.user import AppUser, UserPublic
from app.services.security import (
    hash_password,
    issue_token,
    verify_password,
    verify_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

_CAMPUSES = {"UBC", "SFU", "BCIT", "Douglas"}


class RegisterRequest(BaseModel):
    """New-account payload from the signup form."""

    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """Credentials from the login form."""

    email: EmailStr
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    """Session token plus the public account shape."""

    token: str
    user: UserPublic


class ProfileUpdate(BaseModel):
    """Editable profile fields."""

    name: str = Field(min_length=1, max_length=80)
    campus: str | None = None
    program: str | None = Field(default=None, max_length=120)
    interests: list[str] = Field(default_factory=list, max_length=20)


async def _repo() -> UsersRepository:
    return UsersRepository(await ensure_pool())


async def current_user(
    authorization: str = Header(default=""),
) -> AppUser:
    """Resolve the bearer token to an account or raise 401."""

    token = authorization.removeprefix("Bearer ").strip()
    user_id = verify_token(token) if token else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await (await _repo()).get_by_id(UUID(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return user


@router.post("/auth/register", response_model=AuthResponse)
async def register(payload: RegisterRequest) -> AuthResponse:
    """Create an account and sign the user in."""

    repo = await _repo()
    try:
        user = await repo.create(
            email=payload.email,
            name=payload.name,
            password_hash=hash_password(payload.password),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        )
    logger.debug("registered %s", user.email)
    return AuthResponse(token=issue_token(str(user.id)), user=user.public())


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest) -> AuthResponse:
    """Validate credentials and issue a session token."""

    user = await (await _repo()).get_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    logger.debug("login ok for %s", user.email)
    return AuthResponse(token=issue_token(str(user.id)), user=user.public())


class GoogleLoginRequest(BaseModel):
    """The ID-token credential returned by Google Identity Services."""

    credential: str = Field(min_length=1)


@router.post("/auth/google", response_model=AuthResponse)
async def google_login(payload: GoogleLoginRequest) -> AuthResponse:
    """Verify a Google ID token, then sign the matching account in / up."""

    # Verify the token with Google's tokeninfo endpoint (no extra deps needed).
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": payload.credential},
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google token")
        info = resp.json()
    except HTTPException:
        raise
    except Exception:
        logger.error("Google token verification failed", exc_info=True)
        raise HTTPException(status_code=502, detail="Could not verify with Google")

    settings = get_settings()
    if settings.google_client_id and info.get("aud") != settings.google_client_id:
        raise HTTPException(status_code=401, detail="Token audience mismatch")

    email = info.get("email")
    if not email or info.get("email_verified") in ("false", False):
        raise HTTPException(status_code=401, detail="Unverified Google email")
    name = info.get("name") or email.split("@")[0]

    repo = await _repo()
    user = await repo.get_by_email(email)
    if user is None:
        # New Google user: create with an unusable random password hash.
        user = await repo.create(
            email=email, name=name, password_hash=hash_password(secrets.token_hex(24))
        )
    logger.debug("google login for %s", email)
    return AuthResponse(token=issue_token(str(user.id)), user=user.public())


@router.get("/auth/me", response_model=UserPublic)
async def me(user: AppUser = Depends(current_user)) -> UserPublic:
    """Return the authenticated account."""

    return user.public()


@router.put("/auth/profile", response_model=UserPublic)
async def update_profile(
    payload: ProfileUpdate, user: AppUser = Depends(current_user)
) -> UserPublic:
    """Update the authenticated account's profile preferences."""

    campus = payload.campus if payload.campus in _CAMPUSES else None
    interests = [i.strip() for i in payload.interests if i.strip()][:20]
    updated = await (await _repo()).update_profile(
        user.id,
        name=payload.name,
        campus=campus,
        program=(payload.program or None),
        interests=interests,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return updated.public()
