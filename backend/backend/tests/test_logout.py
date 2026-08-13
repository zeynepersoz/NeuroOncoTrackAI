"""
NeuroOncoTrack-AI — Logout API Endpoints & Invalidation Tests (TASK-008)

Tests cover:
- Test 1: Successful Logout returning HTTP 204 No Content
- Test 2: Access Token Blacklisted in Redis (subsequent protected route access rejected with HTTP 401)
- Test 3: Refresh Token Revoked in DB (subsequent refresh attempt rejected with HTTP 401)
- Test 4: Cookie Cleared (Set-Cookie response header contains expiration/deletion directive)
- Test 5: No Refresh Cookie (Logout succeeds HTTP 204 gracefully when no cookie provided)
- Test 6: Already Revoked Session (Logout handles already revoked session without 500 exception)
- Test 7: Audit Event (CIKIS event abstraction invoked)
- Test 8: Sensitive Data Non-Exposure (No passwords, access tokens, or refresh tokens in logs)
- Test 9: User Isolation (User A's logout does not revoke User B's active session)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import security
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.session import Session
from app.models.user import User


@pytest.fixture
async def async_client(db_session, mock_redis):
    """Async HTTP client for testing FastAPI endpoints with DB session and FakeRedis."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.state.redis = mock_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    if hasattr(app.state, "redis"):
        delattr(app.state, "redis")


@pytest.fixture
async def test_org(db_session):
    org = Organization(name="Logout Test Hastanesi", code="LOGOUT_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def user_a(db_session, test_org):
    user = User(
        organization_id=test_org.id,
        email="user.a@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="User",
        last_name="A",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def user_b(db_session, test_org):
    user = User(
        organization_id=test_org.id,
        email="user.b@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="User",
        last_name="B",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ── TEST 1: SUCCESSFUL LOGOUT (HTTP 204) ───────────────────────

@pytest.mark.anyio
async def test_successful_logout_returns_204(db_session, async_client, user_a):
    """POST /api/v1/auth/logout with valid credentials returns HTTP 204 No Content."""
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "user.a@example.com", "password": "Pass12345678!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_res.status_code == 204
    assert len(logout_res.content) == 0


# ── TEST 2: ACCESS TOKEN BLACKLISTED ─────────────────────────

@pytest.mark.anyio
async def test_access_token_blacklisted_after_logout(db_session, async_client, user_a):
    """Access token used after logout is rejected by /me with HTTP 401 Unauthorized."""
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "user.a@example.com", "password": "Pass12345678!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify token works before logout
    me_before = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_before.status_code == 200

    # Logout
    logout_res = await async_client.post("/api/v1/auth/logout", headers=headers)
    assert logout_res.status_code == 204

    # Verify token is blacklisted and rejected after logout
    me_after = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_after.status_code == 401
    assert me_after.json()["error"]["code"] == "AUTH_002"


# ── TEST 3: REFRESH TOKEN REVOKED ─────────────────────────────

@pytest.mark.anyio
async def test_refresh_token_revoked_after_logout(db_session, async_client, user_a):
    """Refresh token and DB session are marked revoked after logout; /refresh returns 401."""
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "user.a@example.com", "password": "Pass12345678!"},
    )
    token = login_res.json()["access_token"]
    refresh_cookie = login_res.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    assert refresh_cookie is not None

    headers = {"Authorization": f"Bearer {token}"}
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, refresh_cookie)

    # Logout
    logout_res = await async_client.post("/api/v1/auth/logout", headers=headers)
    assert logout_res.status_code == 204

    # Verify session revoked in DB
    ref_hash = security.hash_token(refresh_cookie)
    sess_res = await db_session.execute(select(Session).where(Session.refresh_token_hash == ref_hash))
    sess = sess_res.scalar_one_or_none()
    assert sess is not None
    assert sess.revoked_at is not None

    # Attempting to refresh with old cookie fails with 401
    refresh_res = await async_client.post("/api/v1/auth/refresh")
    assert refresh_res.status_code == 401


# ── TEST 4: COOKIE CLEARED ───────────────────────────────────

@pytest.mark.anyio
async def test_cookie_cleared_on_logout(db_session, async_client, user_a):
    """Logout response headers contain deletion directive for refresh token cookie."""
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "user.a@example.com", "password": "Pass12345678!"},
    )
    token = login_res.json()["access_token"]

    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_res.status_code == 204

    set_cookie = logout_res.headers.get("Set-Cookie", "")
    assert settings.REFRESH_TOKEN_COOKIE_NAME in set_cookie
    # Deletion directive in HTTP cookies sets empty value or past expiration/max-age 0
    assert '""' in set_cookie or "Max-Age=0" in set_cookie or "expires=" in set_cookie.lower() or f"{settings.REFRESH_TOKEN_COOKIE_NAME}=;" in set_cookie


# ── TEST 5: NO REFRESH COOKIE ────────────────────────────────

@pytest.mark.anyio
async def test_logout_without_refresh_cookie_succeeds(db_session, async_client, user_a):
    """Logout with valid access token but without refresh cookie returns 204 without errors."""
    token, _, _ = security.create_access_token(
        subject=str(user_a.id),
        organization_id=str(user_a.organization_id),
        role=user_a.role,
        permissions=[],
    )

    # Call logout without attaching any cookies
    async_client.cookies.clear()
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_res.status_code == 204


# ── TEST 6: ALREADY REVOKED SESSION ──────────────────────────

@pytest.mark.anyio
async def test_logout_with_already_revoked_session(db_session, async_client, user_a):
    """Logout when refresh session is already revoked succeeds gracefully with 204."""
    now = datetime.now(timezone.utc)
    token_str = security.generate_refresh_token()
    token_hash = security.hash_token(token_str)

    # Pre-revoked session
    sess = Session(
        user_id=user_a.id,
        refresh_token_hash=token_hash,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
        revoked_at=now,
    )
    db_session.add(sess)
    await db_session.commit()

    access_token, _, _ = security.create_access_token(
        subject=str(user_a.id),
        organization_id=str(user_a.organization_id),
        role=user_a.role,
        permissions=[],
    )

    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, token_str)
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_res.status_code == 204


# ── TEST 7: AUDIT EVENT ──────────────────────────────────────

@pytest.mark.anyio
async def test_audit_event_logged_on_logout(caplog, db_session, async_client, user_a):
    """Audit event 'CIKIS' is recorded on successful logout."""
    caplog.set_level(logging.INFO)

    token, _, _ = security.create_access_token(
        subject=str(user_a.id),
        organization_id=str(user_a.organization_id),
        role=user_a.role,
        permissions=[],
    )

    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_res.status_code == 204

    # Verify audit event in log output
    assert "AUDIT EVENT: CIKIS" in caplog.text
    assert str(user_a.id) in caplog.text


# ── TEST 8: SENSITIVE DATA NON-EXPOSURE ──────────────────────

@pytest.mark.anyio
async def test_logout_non_exposure_in_logs(caplog, db_session, async_client, user_a):
    """Logout process never logs passwords, access tokens, refresh tokens, or secret keys."""
    caplog.set_level(logging.DEBUG)

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "user.a@example.com", "password": "Pass12345678!"},
    )
    token = login_res.json()["access_token"]
    refresh_cookie = login_res.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)

    caplog.clear()
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_res.status_code == 204

    log_output = caplog.text
    assert "Pass12345678!" not in log_output
    assert token not in log_output
    assert refresh_cookie not in log_output
    assert "BEGIN PRIVATE KEY" not in log_output


# ── TEST 9: USER ISOLATION ────────────────────────────────────

@pytest.mark.anyio
async def test_user_isolation_logout_does_not_revoke_other_user(db_session, async_client, user_a, user_b):
    """User A's logout does not revoke User B's active refresh session."""
    # User A login
    res_a = await async_client.post("/api/v1/auth/login", json={"email": "user.a@example.com", "password": "Pass12345678!"})
    token_a = res_a.json()["access_token"]
    cookie_a = res_a.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)

    # User B login
    res_b = await async_client.post("/api/v1/auth/login", json={"email": "user.b@example.com", "password": "Pass12345678!"})
    cookie_b = res_b.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)

    # User A performs logout while sending cookie_a
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, cookie_a)
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert logout_res.status_code == 204

    # Verify User B's session in DB is still active (revoked_at is None)
    hash_b = security.hash_token(cookie_b)
    sess_b_res = await db_session.execute(select(Session).where(Session.refresh_token_hash == hash_b))
    sess_b = sess_b_res.scalar_one_or_none()
    assert sess_b is not None
    assert sess_b.revoked_at is None

    # User B can still refresh token using cookie_b
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, cookie_b)
    ref_b_res = await async_client.post("/api/v1/auth/refresh")
    assert ref_b_res.status_code == 200
