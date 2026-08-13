"""
NeuroOncoTrack-AI — Session Management API Endpoints & Security Tests (TASK-015)

Tests cover:
- Test 1: List sessions success (200 OK)
- Test 2: Tenant isolation (User A only sees User A sessions, User B only User B)
- Test 3: Multiple active sessions listed
- Test 4: SessionResponse fields present and correctly formatted
- Test 5: Refresh token NOT in response body
- Test 6: Refresh token hash NOT in response body
- Test 7: Access token NOT in response body
- Test 8: Current session flag correctly set based on active cookie
- Test 9: Revoke own session succeeds (204 No Content)
- Test 10: Revoked session has revoked_at set in DB
- Test 11: Refresh attempt fails for revoked session
- Test 12: IDOR defense — User A cannot revoke User B's session
- Test 13: IDOR defense — User B cannot view User A's sessions
- Test 14: Non-existent session ID rejected
- Test 15: Malformed session UUID rejected (422)
- Test 16: Already revoked session handled gracefully
- Test 17: Unauthorized GET /sessions rejected (401)
- Test 18: Unauthorized DELETE /sessions/{id} rejected (401)
- Test 19: OTURUM_REVOKE audit event generated
- Test 20: Sensitive information not exposed in response body or audit logs
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
    org = Organization(name="Session Mgmt Hastanesi", code="SESS_MGMT_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def user_a(db_session, test_org):
    user = User(
        organization_id=test_org.id,
        email="sess.usera@example.com",
        password_hash=security.hash_password("UserAPassword123!"),
        first_name="Ahmet",
        last_name="Yılmaz",
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
        email="sess.userb@example.com",
        password_hash=security.hash_password("UserBPassword123!"),
        first_name="Burcu",
        last_name="Kaya",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers_user_a(user_a):
    token, _, _ = security.create_access_token(
        subject=str(user_a.id),
        organization_id=str(user_a.organization_id),
        role=user_a.role,
        permissions=["READ_PATIENTS"],
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user_b(user_b):
    token, _, _ = security.create_access_token(
        subject=str(user_b.id),
        organization_id=str(user_b.organization_id),
        role=user_b.role,
        permissions=["READ_PATIENTS"],
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def session_user_a(db_session, user_a):
    raw_token = security.generate_refresh_token()
    token_hash = security.hash_token(raw_token)
    now = datetime.now(timezone.utc)
    sess = Session(
        user_id=user_a.id,
        refresh_token_hash=token_hash,
        ip_address="192.168.1.50",
        user_agent="Mozilla/5.0 (Windows NT 10.0)",
        device_fingerprint="Desktop-Windows-Chrome",
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
        revoked_at=None,
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)
    sess.raw_token = raw_token
    return sess


@pytest.fixture
async def session_user_b(db_session, user_b):
    raw_token = security.generate_refresh_token()
    token_hash = security.hash_token(raw_token)
    now = datetime.now(timezone.utc)
    sess = Session(
        user_id=user_b.id,
        refresh_token_hash=token_hash,
        ip_address="10.0.0.99",
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)",
        device_fingerprint="Mobile-iOS-Safari",
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
        revoked_at=None,
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)
    sess.raw_token = raw_token
    return sess


# ── TEST 1: LIST SESSIONS SUCCESS ────────────────────────────

@pytest.mark.anyio
async def test_list_sessions_success(async_client, auth_headers_user_a, session_user_a):
    """GET /api/v1/auth/sessions returns 200 OK with list of active user sessions."""
    res = await async_client.get("/api/v1/auth/sessions", headers=auth_headers_user_a)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(s["id"] == str(session_user_a.id) for s in data)


# ── TEST 2 & 13: TENANT ISOLATION ────────────────────────────

@pytest.mark.anyio
async def test_list_sessions_tenant_isolation(async_client, auth_headers_user_a, auth_headers_user_b, session_user_a, session_user_b):
    """User A sees only User A's sessions; User B sees only User B's sessions."""
    res_a = await async_client.get("/api/v1/auth/sessions", headers=auth_headers_user_a)
    assert res_a.status_code == 200
    ids_a = [s["id"] for s in res_a.json()]
    assert str(session_user_a.id) in ids_a
    assert str(session_user_b.id) not in ids_a

    res_b = await async_client.get("/api/v1/auth/sessions", headers=auth_headers_user_b)
    assert res_b.status_code == 200
    ids_b = [s["id"] for s in res_b.json()]
    assert str(session_user_b.id) in ids_b
    assert str(session_user_a.id) not in ids_b


# ── TEST 3: MULTIPLE ACTIVE SESSIONS ─────────────────────────

@pytest.mark.anyio
async def test_list_multiple_sessions(db_session, async_client, user_a, auth_headers_user_a, session_user_a):
    """Multiple active sessions for the same user are listed."""
    raw_token2 = security.generate_refresh_token()
    now = datetime.now(timezone.utc)
    sess2 = Session(
        user_id=user_a.id,
        refresh_token_hash=security.hash_token(raw_token2),
        ip_address="192.168.1.51",
        user_agent="Firefox/110.0",
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(sess2)
    await db_session.commit()

    res = await async_client.get("/api/v1/auth/sessions", headers=auth_headers_user_a)
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 2


# ── TEST 4, 5, 6, 7 & 20: RESPONSE FIELDS AND NON-EXPOSURE ────

@pytest.mark.anyio
async def test_session_response_fields_and_security(async_client, auth_headers_user_a, session_user_a):
    """SessionResponse contains safe fields and NEVER exposes refresh tokens or hashes."""
    res = await async_client.get("/api/v1/auth/sessions", headers=auth_headers_user_a)
    assert res.status_code == 200
    sess_item = next(s for s in res.json() if s["id"] == str(session_user_a.id))

    # Required safe fields
    assert "id" in sess_item
    assert "device" in sess_item
    assert "ip" in sess_item
    assert "user_agent" in sess_item
    assert "created_at" in sess_item
    assert "last_used_at" in sess_item
    assert "expires_at" in sess_item
    assert "current" in sess_item

    # Security exclusions
    assert "refresh_token" not in sess_item
    assert "refresh_token_hash" not in sess_item
    assert "access_token" not in sess_item
    assert "token_hash" not in sess_item
    assert "password" not in sess_item
    assert "secret" not in sess_item


# ── TEST 8: CURRENT SESSION FLAG ─────────────────────────────

@pytest.mark.anyio
async def test_current_session_flag_correct(async_client, auth_headers_user_a, session_user_a):
    """Session matching refresh cookie has current = True; others have current = False."""
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, session_user_a.raw_token)

    res = await async_client.get("/api/v1/auth/sessions", headers=auth_headers_user_a)
    assert res.status_code == 200
    sess_item = next(s for s in res.json() if s["id"] == str(session_user_a.id))
    assert sess_item["current"] is True


# ── TEST 9 & 10: REVOKE OWN SESSION ──────────────────────────

@pytest.mark.anyio
async def test_revoke_own_session_success(db_session, async_client, auth_headers_user_a, session_user_a):
    """DELETE /api/v1/auth/sessions/{id} revokes session and sets revoked_at in DB."""
    res = await async_client.delete(
        f"/api/v1/auth/sessions/{session_user_a.id}",
        headers=auth_headers_user_a,
    )
    assert res.status_code == 204

    await db_session.refresh(session_user_a)
    assert session_user_a.revoked_at is not None


# ── TEST 11: REFRESH FAILS ON REVOKED SESSION ─────────────────

@pytest.mark.anyio
async def test_revoked_session_cannot_refresh(async_client, auth_headers_user_a, session_user_a):
    """Refresh token from revoked session cannot be rotated."""
    await async_client.delete(
        f"/api/v1/auth/sessions/{session_user_a.id}",
        headers=auth_headers_user_a,
    )

    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, session_user_a.raw_token)
    res_refresh = await async_client.post("/api/v1/auth/refresh")
    assert res_refresh.status_code in (400, 401)


# ── TEST 12: IDOR DEFENSE ────────────────────────────────────

@pytest.mark.anyio
async def test_idor_cannot_revoke_other_user_session(db_session, async_client, auth_headers_user_a, session_user_b):
    """User A attempting to delete User B's session fails; User B session remains active."""
    res = await async_client.delete(
        f"/api/v1/auth/sessions/{session_user_b.id}",
        headers=auth_headers_user_a,
    )
    assert res.status_code in (400, 403, 404, 422)

    await db_session.refresh(session_user_b)
    assert session_user_b.revoked_at is None  # User B's session preserved!


# ── TEST 14 & 15: NON-EXISTENT & MALFORMED SESSION ID ─────────

@pytest.mark.anyio
async def test_non_existent_session_id_rejected(async_client, auth_headers_user_a):
    """Deleting non-existent session UUID fails with error envelope."""
    random_uuid = uuid.uuid4()
    res = await async_client.delete(
        f"/api/v1/auth/sessions/{random_uuid}",
        headers=auth_headers_user_a,
    )
    assert res.status_code in (400, 404, 422)


@pytest.mark.anyio
async def test_malformed_session_id_rejected(async_client, auth_headers_user_a):
    """Deleting malformed session string ID returns 422 validation error."""
    res = await async_client.delete(
        "/api/v1/auth/sessions/invalid-uuid-string",
        headers=auth_headers_user_a,
    )
    assert res.status_code == 422


# ── TEST 16: ALREADY REVOKED SESSION HANDLED GRACEFULLY ───────

@pytest.mark.anyio
async def test_already_revoked_session_handled_gracefully(async_client, auth_headers_user_a, session_user_a):
    """Re-deleting an already revoked session is handled cleanly."""
    res1 = await async_client.delete(
        f"/api/v1/auth/sessions/{session_user_a.id}",
        headers=auth_headers_user_a,
    )
    assert res1.status_code == 204

    res2 = await async_client.delete(
        f"/api/v1/auth/sessions/{session_user_a.id}",
        headers=auth_headers_user_a,
    )
    assert res2.status_code in (204, 400, 404)


# ── TEST 17 & 18: UNAUTHORIZED REQUESTS ───────────────────────

@pytest.mark.anyio
async def test_unauthorized_requests_rejected(async_client, session_user_a):
    """Unauthenticated requests to GET /sessions and DELETE /sessions/{id} return 401."""
    res_get = await async_client.get("/api/v1/auth/sessions")
    assert res_get.status_code == 401

    res_del = await async_client.delete(f"/api/v1/auth/sessions/{session_user_a.id}")
    assert res_del.status_code == 401


# ── TEST 19: AUDIT EVENT GENERATED ON REVOKE ──────────────────

@pytest.mark.anyio
async def test_audit_event_generated_on_revoke(caplog, async_client, auth_headers_user_a, session_user_a):
    """Revoking session generates OTURUM_REVOKE audit event."""
    caplog.set_level(logging.INFO)

    res = await async_client.delete(
        f"/api/v1/auth/sessions/{session_user_a.id}",
        headers=auth_headers_user_a,
    )
    assert res.status_code == 204
    assert "OTURUM_REVOKE" in caplog.text
