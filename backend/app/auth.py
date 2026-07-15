"""Clerk JWT verification and authenticated user dependency."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.config import settings
from app.db import User, get_db

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client() -> PyJWKClient:
    """
    Cached JWKS client for Clerk public keys.

    @returns PyJWKClient pointed at Clerk's JWKS endpoint
    """
    if not settings.clerk_jwks_url:
        raise RuntimeError("CLERK_JWKS_URL is not configured")
    return PyJWKClient(settings.clerk_jwks_url)


def _decode_clerk_token(token: str) -> dict:
    """
    Verify and decode a Clerk session JWT.

    @param token - Bearer token from Authorization header
    @returns Decoded JWT claims
    """
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        decode_kwargs: dict = {
            "algorithms": ["RS256"],
            "options": {"verify_aud": False},
            # Clerk iat can be a few seconds ahead of local clock — avoid false 401s
            "leeway": 60,
        }
        if settings.clerk_issuer:
            decode_kwargs["issuer"] = settings.clerk_issuer

        return jwt.decode(token, signing_key.key, **decode_kwargs)
    except jwt.PyJWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        ) from exc


def _extract_email(claims: dict) -> str:
    """Pull email from common Clerk JWT claim shapes."""
    if isinstance(claims.get("email"), str):
        return claims["email"]

    primary = claims.get("primary_email_address")
    if isinstance(primary, str):
        return primary

    emails = claims.get("email_addresses")
    if isinstance(emails, list) and emails:
        first = emails[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict) and isinstance(first.get("email_address"), str):
            return first["email_address"]

    return ""


def get_or_create_user(db: Session, clerk_user_id: str, email: str) -> User:
    """
    Fetch an existing user or create one from Clerk claims.

    @param db - Database session
    @param clerk_user_id - Clerk `sub` claim
    @param email - User email from JWT
    @returns Persisted User row
    """
    user = db.query(User).filter(User.clerk_user_id == clerk_user_id).one_or_none()
    if user:
        if email and user.email != email:
            user.email = email
            db.commit()
            db.refresh(user)
        return user

    user = User(clerk_user_id=clerk_user_id, email=email or "")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    FastAPI dependency that validates Clerk JWT and returns the DB user.

    When AUTH_DISABLED=true, returns a synthetic dev user for local testing.

    @param credentials - Authorization Bearer header
    @param db - Database session
    @returns Authenticated User
    """
    if not settings.auth_enabled:
        return get_or_create_user(db, "dev_user", "dev@localhost")

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide Authorization: Bearer <token>.",
        )

    if not settings.clerk_jwks_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on the server.",
        )

    claims = _decode_clerk_token(credentials.credentials)
    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim.",
        )

    return get_or_create_user(db, clerk_user_id, _extract_email(claims))
