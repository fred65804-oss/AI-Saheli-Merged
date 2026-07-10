"""Auth flow: signup, login, refresh rotation + reuse detection, logout, and
that the dashboard router actually enforces the access-token guard."""

import os

import pytest
from fastapi.testclient import TestClient

from apps.backend.auth.db import init_db
from apps.backend.main import app


@pytest.fixture(scope="module", autouse=True)
def _fresh_auth_db():
    db_path = "data/test_auth.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    init_db()
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _signup(client, email="alice@example.com", password="correct-horse-1", name="Alice"):
    return client.post("/auth/signup", json={"name": name, "email": email, "password": password})


def test_signup_creates_user_and_returns_tokens(client):
    r = _signup(client, email="signup1@example.com")
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "signup1@example.com"
    assert body["access_token"] and body["refresh_token"]


def test_signup_duplicate_email_rejected(client):
    _signup(client, email="dupe@example.com")
    r = _signup(client, email="dupe@example.com")
    assert r.status_code == 409


def test_signup_rejects_short_password(client):
    r = _signup(client, email="short1@example.com", password="short")
    assert r.status_code == 422


def test_login_wrong_password_rejected(client):
    _signup(client, email="login1@example.com", password="right-password-1")
    r = client.post(
        "/auth/login", json={"email": "login1@example.com", "password": "wrong-password"}
    )
    assert r.status_code == 401


def test_login_unknown_email_rejected(client):
    r = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever-1"}
    )
    assert r.status_code == 401


def test_login_success_returns_tokens(client):
    _signup(client, email="login2@example.com", password="right-password-1")
    r = client.post(
        "/auth/login", json={"email": "login2@example.com", "password": "right-password-1"}
    )
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_me_requires_valid_access_token(client):
    r = client.get("/auth/me")
    assert r.status_code == 401

    tokens = _signup(client, email="me1@example.com").json()
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 200
    assert r.json()["email"] == "me1@example.com"


def test_refresh_rotates_and_old_refresh_token_is_dead(client):
    tokens = _signup(client, email="refresh1@example.com").json()
    old_refresh = tokens["refresh_token"]

    r = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200
    new_tokens = r.json()
    assert new_tokens["refresh_token"] != old_refresh

    # Replaying the rotated-away token must fail.
    r2 = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401


def test_refresh_reuse_revokes_whole_family(client):
    tokens = _signup(client, email="refresh2@example.com").json()
    old_refresh = tokens["refresh_token"]

    first = client.post("/auth/refresh", json={"refresh_token": old_refresh}).json()
    # Reusing the already-rotated-away token looks like a stolen token being
    # replayed, so the whole family gets killed...
    client.post("/auth/refresh", json={"refresh_token": old_refresh})

    # ...including the legitimately-rotated descendant.
    r = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 401


def test_logout_revokes_refresh_token(client):
    tokens = _signup(client, email="logout1@example.com").json()
    r = client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 204
    r2 = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401


def test_analytics_route_requires_auth(client):
    r = client.get("/analytics/summary")
    assert r.status_code == 401


def test_analytics_route_accessible_with_token(client):
    tokens = _signup(client, email="dash1@example.com").json()
    r = client.get(
        "/analytics/summary", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert r.status_code == 200


def test_meta_stays_public(client):
    # /meta feeds the public chat page (languages, scheme cards) — no login wall.
    r = client.get("/meta")
    assert r.status_code == 200


def test_chat_route_stays_open_without_auth(client):
    r = client.post("/chat", json={"session_id": "auth-test", "message": "hello"})
    assert r.status_code == 200
