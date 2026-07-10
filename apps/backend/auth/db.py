"""SQLite engine + session factory for the auth store.

Separate from the orchestrator's Qdrant/JSONL storage — auth is the one part
of this app with real relational, ACID-sensitive state (a user's password
hash, which refresh tokens are still valid). SQLite is the whole DB: a single
file under data/, zero external services to stand up for a demo.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from apps.backend.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = get_settings().auth_database_url
    if url.startswith("sqlite:///./"):
        # Resolve relative sqlite paths against the repo root (cwd when
        # uvicorn/pytest are launched) and make sure the parent dir exists —
        # SQLite will not create it for you.
        rel = url.removeprefix("sqlite:///./")
        os.makedirs(os.path.dirname(rel) or ".", exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create tables that don't exist yet. Idempotent — safe on every startup."""
    from apps.backend.auth import models  # noqa: F401  (registers tables on Base)

    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
