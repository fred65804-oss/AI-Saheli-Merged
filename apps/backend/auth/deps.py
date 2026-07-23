"""FastAPI dependencies: DB session + the current-user guard."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from apps.backend.auth import security
from apps.backend.auth.db import get_db
from apps.backend.auth.models import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    try:
        payload = security.decode_token(creds.credentials, expected_type="access")
    except Exception as e:
        raise unauthorized from e

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if user is None or not user.is_active:
        raise unauthorized
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required.")
    return user
