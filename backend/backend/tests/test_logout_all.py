"""
NeuroOncoTrack-AI — Logout All API Endpoints & Multi-Session Invalidation Tests (TASK-009)

Tests cover:
- Test 1: Successful logout-all returning HTTP 204 No Content
- Test 2 & 3: Multi-session creation (3+ sessions) and verification that all user sessions are marked revoked in DB
- Test 4: All refresh attempts with previously issued refresh tokens fail with HTTP 401
- Test 5: Current access token fails with HTTP 401 after logout-all
- Test 6: Current refresh cookie is cleared in response headers
- Test 7: User/Tenant isolation — User A's logout-all leaves User B's active sessions intact
- Test 8: Already revoked sessions handled gracefully without exceptions
- Test 9: User with no active sessions calling logout-all returns HTTP 204 No Content
- Test 10: Missing authentication header returns HTTP 401 Unauthorized
- Test 11: Invalid/malformed access token returns HTTP 401 Unauthorized
- Test 12: Sensitive information non-exposure in logs during logout-all
- Test 13: Regression distinction test — /logout revokes ONLY current session; /logout-all revokes ALL user sessions
"""

from __future__ import annotations

import logging
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
    org = Organization(name="Logout All Test Hastanesi", code="LOGOUT_ALL_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def user_a(db_session, test_org):
    user = User(
        organization_id=test_org.id,
        email="logoutall.a@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="LogoutAll",
        last_name="UserA",
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
        email="logoutall.b@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="LogoutAll",
        last_name="UserB",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ── TEST 1: SUCCESSFUL LOGOUT-ALL ─────────────────────────────

@pytest.mark.anyio
async def test_successful_logout_all_returns_204(db_session, async_client, user_a):
    """POST /api/v1/auth/logout-all with valid credentials returns HTTP 204 No Content."""
    token, _, _ = security.create_access_token(
        subject=str(user_a.id),
        organization_id=str(user_a.organization_id),
        role=user_a.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 204
    assert len(res.content) == 0


# ── TEST 2 & 3: MULTI-SESSION CREATION & ALL-REVOCATION ───────

@pytest.mark.anyio
async def test_logout_all_revokes_all_sessions(db_session, async_client, user_a):
    """Creating 3 independent sessions and calling logout-all marks all 3 sessions revoked in DB."""
    now = datetime.now(timezone.utc)
    tokens = [security.generate_refresh_token() for _ in range(3)]
    hashes = [security.hash_token(t) for t in tokens]

    # Create 3 active sessions for user_a
    for h in hashes:
        db_session.add(
            Session(
                user_id=user_a.id,
                refresh_token_hash=h,
                created_at=now,
                last_used_at=now,
                expires_at=now + timedelta(days=7),
            )
        )
    await db_session.commit()

    # Verify all 3 sessions are active before logout-all
    sess_res_before = await db_session.execute(
        select(Session).where(Session.user_id == user_a.id, Session.revoked_at.is_(None))
    )
    assert len(sess_res_before.scalars().all()) == 3

    # Call logout-all
    access_token, _, _ = security.create_access_token(
        subject=str(user_a.id),
        organization_id=str(user_a.organization_id),
        role=user_a.role,
        permissions=[],
    )
    res = await async_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert res.status_code == 204

    # Verify all 3 sessions are now marked revoked in DB
    sess_res_after = await db_session.execute(
        select(Session).where(Session.user_id == user_a.id)
    )
    all_sessions = sess_res_after.scalars().all()
    assert len(all_sessions) == 3
    for s in all_sessions:
        assert s.revoked_at is not None


# ── TEST 4: ALL REFRESH TOKENS FAIL ───────────────────────────

@pytest.mark.anyio
async def test_all_refresh_tokens_fail_after_logout_all(db_session, async_client, user_a):
    """Attempting refresh with any previously issued refresh token returns HTTP 401 Unauthorized."""
    # Login 3 times to get 3 cookies
    cookies = []
    tokens = []
    for _ in range(3):
        res = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "logoutall.a@example.com", "password": "Pass12345678!"},
        )
        assert res.status_code == 200
        tokens.append(res.json()["access_token"])
        cookies.append(res.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME))

    # Call logout-all using last token
    logout_all_res = await async_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {tokens[-1]}"},
    )
    assert logout_all_res.status_code == 204

    # Attempt refresh using each of the 3 cookies -> all must fail with 401
    for c in cookies:
        async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, c)
        ref_res = await async_client.post("/api/v1/auth/refresh")
        assert ref_res.status_code == 401
        assert ref_res.json()["error"]["code"] == "AUTH_002"


# ── TEST 5: CURRENT ACCESS TOKEN FAILS ────────────────────────

@pytest.mark.anyio
async def test_current_access_token_fails_after_logout_all(db_session, async_client, user_a):
    """Access token used to execute logout-all is blacklisted and rejected by /me with HTTP 401."""
    token, _, _ = security.create_access_token(
        subject=str(user_a.id),
        organization_id=str(user_a.organization_id),
        role=user_a.role,
        permissions=[],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Verify working before logout-all
    me_before = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_before.status_code == 200

    # Call logout-all
    logout_all_res = await async_client.post("/api/v1/auth/logout-all", headers=headers)
    assert logout_all_res.status_code == 204

    # Verify access token rejected on /me
    me_after = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_after.status_code == 401


# ── TEST 6: CURRENT REFRESH COOKIE CLEARED ────────────────────

@pytest.mark.anyio
async def test_refresh_cookie_cleared_on_logout_all(db_session, async_client, user_a):
    """Set-Cookie header on logout-all contains refresh token deletion directive."""
    res_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "logoutall.a@example.com", "password": "Pass12345678!"},
    )
    token = res_login.json()["access_token"]

    res_logout = await async_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_logout.status_code == 204

    set_cookie = res_logout.headers.get("Set-Cookie", "")
    assert settings.REFRESH_TOKEN_COOKIE_NAME in set_cookie


# ── TEST 7: USER / TENANT ISOLATION ───────────────────────────

@pytest.mark.anyio
async def test_logout_all_user_isolation(db_session, async_client, user_a, user_b):
    """User A's logout-all revokes User A's sessions while leaving User B's sessions active."""
    # User A login
    res_a = await async_client.post("/api/v1/auth/login", json={"email": "logoutall.a@example.com", "password": "Pass12345678!"})
    token_a = res_a.json()["access_token"]

    # User B login
    res_b = await async_client.post("/api/v1/auth/login", json={"email": "logoutall.b@example.com", "password": "Pass12345678!"})
    token_b = res_b.json()["access_token"]
    cookie_b = res_b.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)

    # User A executes logout-all
    logout_res = await async_client.post("/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {token_a}"})
    assert logout_res.status_code == 204

    # User A sessions are revoked
    sess_a_res = await db_session.execute(select(Session).where(Session.user_id == user_a.id))
    for sa in sess_a_res.scalars().all():
        assert sa.revoked_at is not None

    # User B sessions remain untouched and active
    sess_b_res = await db_session.execute(select(Session).where(Session.user_id == user_b.id))
    sessions_b = sess_b_res.scalars().all()
    assert len(sessions_b) == 1
    assert sessions_b[0].revoked_at is None

    # User B can still refresh token using cookie_b
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, cookie_b)
    ref_b = await async_client.post("/api/v1/auth/refresh")
    assert ref_b.status_code == 200


# ── TEST 8: ALREADY REVOKED SESSIONS ─────────────────────────

@pytest.mark.anyio
async def test_logout_all_handles_pre_revoked_sessions(db_session, async_client, user_a):
    """Pre-revoked sessions remain revoked; active sessions get revoked; returns 204 without error."""
    now = datetime.now(timezone.utc)
    # 1 pre-revoked session, 1 active session
    s1 = Session(user_id=user_a.id, refresh_token_hash="hash1", created_at=now, last_used_at=now, expires_at=now + timedelta(days=7), revoked_at=now)
    s2 = Session(user_id=user_a.id, refresh_token_hash="hash2", created_at=now, last_used_at=now, expires_at=now + timedelta(days=7))
    db_session.add_all([s1, s2])
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(user_a.id),
        organization_id=str(user_a.organization_id),
        role=user_a.role,
        permissions=[],
    )

    res = await async_client.post("/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 204

    await db_session.refresh(s1)
    await db_session.refresh(s2)
    assert s1.revoked_at is not None
    assert s2.revoked_at is not None


# ── TEST 9: NO ACTIVE SESSIONS ───────────────────────────────

@pytest.mark.anyio
async def test_logout_all_with_zero_active_sessions(db_session, async_client, user_a):
    """Calling logout-all with zero active sessions returns 204 No Content safely."""
    token, _, _ = security.create_access_token(
        subject=str(user_a.id),
        organization_id=str(user_a.organization_id),
        role=user_a.role,
        permissions=[],
    )

    res = await async_client.post("/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 204


# ── TEST 10 & 11: AUTHENTICATION FAILURES ─────────────────────

@pytest.mark.anyio
async def test_logout_all_missing_auth_returns_401(async_client):
    """Calling logout-all without Authorization header returns 401 Unauthorized."""
    res = await async_client.post("/api/v1/auth/logout-all")
    assert res.status_code == 401


@pytest.mark.anyio
async def test_logout_all_invalid_token_returns_401(async_client):
    """Calling logout-all with malformed Bearer token returns 401 Unauthorized."""
    res = await async_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": "Bearer invalid.malformed.token"},
    )
    assert res.status_code == 401


# ── TEST 12: SENSITIVE INFORMATION NON-EXPOSURE ─────────────

@pytest.mark.anyio
async def test_logout_all_non_exposure_in_logs(caplog, db_session, async_client, user_a):
    """Audit log recorded during logout-all contains 'CIKIS_TUM_OTURUMLAR' and no sensitive tokens/passwords."""
    caplog.set_level(logging.INFO)

    res_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "logoutall.a@example.com", "password": "Pass12345678!"},
    )
    token = res_login.json()["access_token"]
    cookie = res_login.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)

    caplog.clear()
    res_logout = await async_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_logout.status_code == 204

    log_text = caplog.text
    assert "AUDIT EVENT: CIKIS_TUM_OTURUMLAR" in log_text
    assert str(user_a.id) in log_text
    assert "Pass12345678!" not in log_text
    assert token not in log_text
    assert cookie not in log_text


# ── TEST 13: TASK-008 VS TASK-009 DISTINCTION REGRESSION ─────

@pytest.mark.anyio
async def test_logout_vs_logout_all_distinction_regression(db_session, async_client, user_a):
    """
    Verifies functional distinction:
    - /logout revokes ONLY the single session matching the refresh cookie.
    - /logout-all revokes ALL active sessions belonging to the user.
    """
    # Create 2 sessions (S1, S2) for user_a
    res1 = await async_client.post("/api/v1/auth/login", json={"email": "logoutall.a@example.com", "password": "Pass12345678!"})
    token1 = res1.json()["access_token"]
    cookie1 = res1.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)

    res2 = await async_client.post("/api/v1/auth/login", json={"email": "logoutall.a@example.com", "password": "Pass12345678!"})
    token2 = res2.json()["access_token"]
    cookie2 = res2.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)

    # 1. Call /logout with cookie1
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, cookie1)
    res_logout = await async_client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token1}"})
    assert res_logout.status_code == 204

    # Verify S1 is revoked, but S2 remains active
    hash1 = security.hash_token(cookie1)
    hash2 = security.hash_token(cookie2)

    sess1 = (await db_session.execute(select(Session).where(Session.refresh_token_hash == hash1))).scalar_one_or_none()
    sess2 = (await db_session.execute(select(Session).where(Session.refresh_token_hash == hash2))).scalar_one_or_none()

    assert sess1.revoked_at is not None  # S1 revoked
    assert sess2.revoked_at is None      # S2 still active!

    # S2 can still be refreshed
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, cookie2)
    ref2_res = await async_client.post("/api/v1/auth/refresh")
    assert ref2_res.status_code == 200

    # 2. Call /logout-all with rotated token from refresh
    token2_new = ref2_res.json()["access_token"]
    logout_all_res = await async_client.post("/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {token2_new}"})
    assert logout_all_res.status_code == 204

    # Verify ALL sessions for user_a are now revoked
    all_sess = (await db_session.execute(select(Session).where(Session.user_id == user_a.id))).scalars().all()
    for s in all_sess:
        assert s.revoked_at is not None
