"""Password hashing and JWT issuance/verification.

Uses ``bcrypt`` directly (not passlib — passlib 1.7.4's bcrypt backend probes
a ``__about__.__version__`` attribute that bcrypt>=4.1 removed, which raises
on every hash/verify call). Access and refresh tokens are both JWTs signed
with the same HS256 secret, distinguished by a ``type`` claim so an access
token can't be replayed as a refresh token or vice versa.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import bcrypt
import jwt

from apps.backend.config import get_settings

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash (shouldn't happen for rows we wrote ourselves) —
        # treat as a failed verification rather than a 500.
        return False


def _encode(payload: dict, expires_delta: timedelta) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    to_encode = {**payload, "iat": now, "exp": now + expires_delta}
    return jwt.encode(to_encode, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    s = get_settings()
    return _encode(
        {"sub": user_id, "type": "access"},
        timedelta(minutes=s.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str, family_id: str | None = None) -> tuple[str, str, str, datetime]:
    """Returns ``(token, jti, family_id, expires_at)``.

    ``family_id`` links every token descended from one login together so a
    reuse-detected theft can revoke the whole chain, not just the one token.
    Pass the prior token's family_id when rotating; omit it on a fresh login
    to start a new family.
    """
    s = get_settings()
    jti = str(uuid.uuid4())
    family = family_id or str(uuid.uuid4())
    expires_delta = timedelta(days=s.refresh_token_expire_days)
    expires_at = datetime.now(timezone.utc) + expires_delta
    token = _encode(
        {"sub": user_id, "type": "refresh", "jti": jti, "family": family},
        expires_delta,
    )
    return token, jti, family, expires_at


def decode_token(token: str, expected_type: TokenType) -> dict:
    """Decode + validate a JWT. Raises jwt.PyJWTError (or ValueError on a
    type mismatch) on anything invalid — callers turn that into a 401."""
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise ValueError(f"expected a {expected_type} token")
    return payload
