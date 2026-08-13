"""
NeuroOncoTrack-AI — Reset Password API Endpoints & Security Tests (TASK-014)

Tests cover:
- Test 1: Valid reset password (200 OK, updates password hash, marks token used)
- Test 2: Invalid token (non-existent token rejected)
- Test 3: Expired token (expires_at <= now rejected)
- Test 4: Reused token (used_at IS NOT NULL rejected)
- Test 5: Malformed token (empty / whitespace rejected)
- Test 6: Weak password (failing strength validation rejected with 422)
- Test 7: Password reuse (matching current password rejected)
- Test 8: Password reuse (matching historical password in last 5 rejected)
- Test 9: Password history persistence (old password hash archived)
- Test 10: Old password no longer works for login
- Test 11: New password works for login
- Test 12: Active sessions revoked upon password reset
- Test 13: Refresh token after reset rejected
- Test 14: Token marked as used in DB
- Test 15: Token cannot be used twice
- Test 16: Sensitive data not exposed in response body or audit logs
- Test 17: PAROLA_SIFIRLANDI audit event generated
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import security
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.password_history import PasswordHistory
from app.models.password_reset_token import PasswordResetToken
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
    org = Organization(name="Reset Password Hastanesi", code="RESET_PW_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def user_for_reset(db_session, test_org):
    old_pass = "OldPassword123!"
    user = User(
        organization_id=test_org.id,
        email="reset.user@example.com",
        password_hash=security.hash_password(old_pass),
        first_name="Kemal",
        last_name="Demir",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    user.plain_old_password = old_pass
    return user


@pytest.fixture
async def valid_reset_token(db_session, user_for_reset):
    raw_token = security.generate_refresh_token()
    token_hash = security.hash_token(raw_token)
    now = datetime.now(timezone.utc)
    token_record = PasswordResetToken(
        user_id=user_for_reset.id,
        token_hash=token_hash,
        created_at=now,
        expires_at=now + timedelta(minutes=15),
        used_at=None,
    )
    db_session.add(token_record)
    await db_session.commit()
    await db_session.refresh(token_record)
    token_record.raw_token = raw_token
    return token_record


# ── TEST 1: VALID RESET PASSWORD ─────────────────────────────

@pytest.mark.anyio
async def test_valid_reset_password(db_session, async_client, user_for_reset, valid_reset_token):
    """Valid reset password request updates password hash, marks token used, and succeeds."""
    new_password = "BrandNewSecretPass123!"
    res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": valid_reset_token.raw_token, "new_password": new_password},
    )
    assert res.status_code == 200
    assert "başarıyla sıfırlandı" in res.json()["message"]

    # Verify password updated
    await db_session.refresh(user_for_reset)
    assert security.verify_password(new_password, user_for_reset.password_hash)


# ── TEST 2: INVALID TOKEN ─────────────────────────────────────

@pytest.mark.anyio
async def test_invalid_token(async_client):
    """Non-existent reset token is rejected with error."""
    res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": "non_existent_token_string_12345", "new_password": "NewValidPassword123!"},
    )
    assert res.status_code in (400, 401, 422)


# ── TEST 3: EXPIRED TOKEN ─────────────────────────────────────

@pytest.mark.anyio
async def test_expired_token(db_session, async_client, user_for_reset):
    """Reset token with expires_at in the past is rejected."""
    raw_token = security.generate_refresh_token()
    token_hash = security.hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expired_record = PasswordResetToken(
        user_id=user_for_reset.id,
        token_hash=token_hash,
        created_at=now - timedelta(minutes=30),
        expires_at=now - timedelta(minutes=15),
        used_at=None,
    )
    db_session.add(expired_record)
    await db_session.commit()

    res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "NewValidPassword123!"},
    )
    assert res.status_code in (400, 401, 422)


# ── TEST 4: REUSED TOKEN ──────────────────────────────────────

@pytest.mark.anyio
async def test_reused_token(db_session, async_client, user_for_reset):
    """Reset token with used_at != None is rejected."""
    raw_token = security.generate_refresh_token()
    token_hash = security.hash_token(raw_token)
    now = datetime.now(timezone.utc)
    used_record = PasswordResetToken(
        user_id=user_for_reset.id,
        token_hash=token_hash,
        created_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(minutes=10),
        used_at=now - timedelta(minutes=2),
    )
    db_session.add(used_record)
    await db_session.commit()

    res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "NewValidPassword123!"},
    )
    assert res.status_code in (400, 401, 422)


# ── TEST 5: MALFORMED TOKEN ───────────────────────────────────

@pytest.mark.anyio
async def test_malformed_token(async_client):
    """Empty or malformed token string is rejected."""
    res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": "", "new_password": "NewValidPassword123!"},
    )
    assert res.status_code == 422


# ── TEST 6: WEAK PASSWORD ─────────────────────────────────────

@pytest.mark.anyio
async def test_weak_password(async_client, valid_reset_token):
    """Weak new password failing policy validation returns 422 error."""
    res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": valid_reset_token.raw_token, "new_password": "weak"},
    )
    assert res.status_code == 422


# ── TEST 7: PASSWORD REUSE CURRENT ───────────────────────────

@pytest.mark.anyio
async def test_password_reuse_current(async_client, user_for_reset, valid_reset_token):
    """New password matching current active password is rejected."""
    res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": valid_reset_token.raw_token, "new_password": user_for_reset.plain_old_password},
    )
    assert res.status_code in (400, 422)


# ── TEST 8: PASSWORD REUSE HISTORY ───────────────────────────

@pytest.mark.anyio
async def test_password_reuse_history(db_session, async_client, user_for_reset, valid_reset_token):
    """New password matching any of last 5 historical passwords is rejected."""
    hist_password = "HistoricalPass123!"
    hist_entry = PasswordHistory(
        user_id=user_for_reset.id,
        password_hash=security.hash_password(hist_password),
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(hist_entry)
    await db_session.commit()

    res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": valid_reset_token.raw_token, "new_password": hist_password},
    )
    assert res.status_code in (400, 422)


# ── TEST 9: PASSWORD HISTORY PERSISTENCE ──────────────────────

@pytest.mark.anyio
async def test_password_history_persistence(db_session, async_client, user_for_reset, valid_reset_token):
    """Old password hash is archived into PasswordHistory upon successful reset."""
    old_hash = user_for_reset.password_hash

    res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": valid_reset_token.raw_token, "new_password": "BrandNewPassword123!"},
    )
    assert res.status_code == 200

    stmt = select(PasswordHistory).where(PasswordHistory.user_id == user_for_reset.id)
    history_records = (await db_session.execute(stmt)).scalars().all()
    assert any(h.password_hash == old_hash for h in history_records)


# ── TEST 10 & 11: OLD & NEW PASSWORD LOGIN BEHAVIOR ───────────

@pytest.mark.anyio
async def test_old_and_new_password_login_behavior(async_client, user_for_reset, valid_reset_token):
    """Old password fails login after reset; new password succeeds for login."""
    new_password = "NewValidPassword456!"

    # Reset
    res_reset = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": valid_reset_token.raw_token, "new_password": new_password},
    )
    assert res_reset.status_code == 200

    # Old password login fails
    res_old_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_for_reset.email, "password": user_for_reset.plain_old_password},
    )
    assert res_old_login.status_code in (400, 401)

    # New password login succeeds
    res_new_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_for_reset.email, "password": new_password},
    )
    assert res_new_login.status_code == 200


# ── TEST 12 & 13: SESSION REVOCATION AND REFRESH REJECTION ───

@pytest.mark.anyio
async def test_active_sessions_revoked_and_refresh_rejected(db_session, async_client, user_for_reset, valid_reset_token):
    """Password reset revokes active database sessions and rejects refresh attempts."""
    raw_refresh = security.generate_refresh_token()
    refresh_hash = security.hash_token(raw_refresh)
    now = datetime.now(timezone.utc)
    active_session = Session(
        user_id=user_for_reset.id,
        refresh_token_hash=refresh_hash,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
        revoked_at=None,
    )
    db_session.add(active_session)
    await db_session.commit()

    # Reset password
    res_reset = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": valid_reset_token.raw_token, "new_password": "NewValidPassword789!"},
    )
    assert res_reset.status_code == 200

    # Session revoked in DB
    await db_session.refresh(active_session)
    assert active_session.revoked_at is not None

    # Refresh attempt fails
    async_client.cookies.set("refresh_token", raw_refresh)
    res_refresh = await async_client.post("/api/v1/auth/refresh")
    assert res_refresh.status_code in (400, 401)


# ── TEST 14 & 15: TOKEN MARKED AS USED & SINGLE USE ENFORCED ──

@pytest.mark.anyio
async def test_token_cannot_be_used_twice(db_session, async_client, user_for_reset, valid_reset_token):
    """Token is marked used on first call; second reset call with same token fails."""
    new_pass1 = "FirstResetPass123!"
    new_pass2 = "SecondResetPass123!"

    # First reset succeeds
    res1 = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": valid_reset_token.raw_token, "new_password": new_pass1},
    )
    assert res1.status_code == 200

    await db_session.refresh(valid_reset_token)
    assert valid_reset_token.used_at is not None

    # Second reset fails
    res2 = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": valid_reset_token.raw_token, "new_password": new_pass2},
    )
    assert res2.status_code in (400, 401, 422)


# ── TEST 16: SENSITIVE DATA NOT EXPOSED ───────────────────────

@pytest.mark.anyio
async def test_sensitive_data_not_exposed(caplog, async_client, valid_reset_token):
    """Response body and log output contain zero plaintext passwords, tokens, or hashes."""
    caplog.set_level(logging.DEBUG)

    new_password = "SecurePasswordExposureCheck123!"
    res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": valid_reset_token.raw_token, "new_password": new_password},
    )
    assert res.status_code == 200

    body = res.json()
    assert "token" not in body
    assert "password" not in body
    assert "password_hash" not in body
    assert "access_token" not in body

    log_text = caplog.text
    assert new_password not in log_text
    assert valid_reset_token.raw_token not in log_text


# ── TEST 17: AUDIT EVENT GENERATED ────────────────────────────

@pytest.mark.anyio
async def test_audit_event_generated(caplog, async_client, valid_reset_token):
    """Successful reset generates PAROLA_SIFIRLANDI audit event."""
    caplog.set_level(logging.INFO)

    res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": valid_reset_token.raw_token, "new_password": "NewAuditEventPass123!"},
    )
    assert res.status_code == 200
    assert "PAROLA_SIFIRLANDI" in caplog.text
