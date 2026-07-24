"""POST /auth/signup, /auth/login, /auth/refresh, /auth/logout, GET /auth/me."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.backend.auth import service
from apps.backend.auth.db import get_db
from apps.backend.auth.deps import get_current_user
from apps.backend.auth.models import User
from apps.backend.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SignupRequest,
    TokenPair,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenPair, status_code=201)
async def signup(req: SignupRequest, db: Session = Depends(get_db)) -> TokenPair:
    return service.signup(
        db,
        name=req.name,
        email=req.email,
        password=req.password,
        role=req.role,
    )


@router.post("/login", response_model=TokenPair)
async def login(req: LoginRequest, db: Session = Depends(get_db)) -> TokenPair:
    return service.login(
        db,
        email=req.email,
        password=req.password,
        expected_role=req.role,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(req: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    return service.refresh(db, refresh_token=req.refresh_token)


@router.post("/logout", status_code=204)
async def logout(req: LogoutRequest, db: Session = Depends(get_db)) -> None:
    service.logout(db, refresh_token=req.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
