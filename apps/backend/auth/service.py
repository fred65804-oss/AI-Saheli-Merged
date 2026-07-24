"""Auth business logic: signup, login, and refresh-token rotation.

Kept separate from the router so the HTTP layer stays thin (parse request →
call service → map result/exception to a response).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from apps.backend.auth import security
from apps.backend.auth.models import RefreshToken, User
from apps.backend.auth.schemas import TokenPair
from apps.backend.config import get_settings


def _issue_pair(db: Session, user: User, family_id: str | None = None) -> TokenPair:
    access = security.create_access_token(user.id)
    refresh, jti, family, expires_at = security.create_refresh_token(user.id, family_id)
    db.add(
        RefreshToken(
            jti=jti,
            user_id=user.id,
            family_id=family,
            expires_at=expires_at,
        )
    )
    db.commit()
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=get_settings().access_token_expire_minutes * 60,
        user=user,
    )


def signup(
    db: Session,
    *,
    name: str,
    email: str,
    password: str,
    role: str = "citizen",
) -> TokenPair:
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(
        name=name,
        email=email,
        hashed_password=security.hash_password(password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_pair(db, user)


def login(
    db: Session,
    *,
    email: str,
    password: str,
    expected_role: str | None = None,
) -> TokenPair:
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    # Same error for "no such user" and "wrong password" — don't leak which
    # half was wrong (avoids account enumeration via the login form).
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if user is None or not security.verify_password(password, user.hashed_password):
        raise invalid
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled.")
    if expected_role is not None and user.role != expected_role:
        label = "Administrator" if user.role == "admin" else "Citizen"
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"This account is registered as {label}. Select the matching role to sign in.",
        )
    return _issue_pair(db, user)


def refresh(db: Session, *, refresh_token: str) -> TokenPair:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token.")
    try:
        payload = security.decode_token(refresh_token, expected_type="refresh")
    except Exception as e:
        raise unauthorized from e

    jti = payload.get("jti")
    user_id = payload.get("sub")
    family_id = payload.get("family")
    row = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()

    if row is None:
        raise unauthorized

    if row.revoked:
        # This jti was already rotated away (or explicitly logged out) and is
        # being replayed — treat as theft and kill every token in the family
        # so a stolen refresh token can't keep minting new sessions.
        db.query(RefreshToken).filter(
            RefreshToken.family_id == row.family_id, RefreshToken.revoked == False  # noqa: E712
        ).update({"revoked": True})
        db.commit()
        raise unauthorized

    if row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise unauthorized

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise unauthorized

    row.revoked = True
    db.commit()
    return _issue_pair(db, user, family_id=family_id)


def logout(db: Session, *, refresh_token: str) -> None:
    """Best-effort revoke — an already-invalid token is not an error, logout
    should always succeed from the client's point of view."""
    try:
        payload = security.decode_token(refresh_token, expected_type="refresh")
    except Exception:
        return
    row = db.query(RefreshToken).filter(RefreshToken.jti == payload.get("jti")).first()
    if row is not None and not row.revoked:
        row.revoked = True
        db.commit()
