"""
NeuroOncoTrack-AI — Change Password API Endpoints & Security Tests (TASK-012)

Tests cover:
- Test 1: Successful password change updates DB hash, allows new login, rejects old login
- Test 2: Incorrect current password returns 401 Unauthorized
- Test 3: Missing current_password returns 422 Unprocessable Entity
- Test 4: New password too short (<12 chars) returns 422
- Test 5: New password missing uppercase returns 422
- Test 6: New password missing lowercase returns 422
- Test 7: New password missing digit returns 422
- Test 8: New password missing special character returns 422
- Test 9: New password identical to current password returns 422
- Test 10: Reusing last 5 historical passwords returns 422
- Test 11: Change password without Authorization header returns 401
- Test 12: Change password with invalid token returns 401
- Test 13: Change password with expired token returns 401
- Test 14: Existing active sessions are revoked in DB after password change
- Test 15: Response and logs do not expose sensitive credentials, hashes, or tokens
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import security
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.password_history import PasswordHistory
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
    org = Organization(name="Change Password Hastanesi", code="CHG_PW_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def user_main(db_session, test_org):
    old_pw = "OriginalPass123!"
    user = User(
        organization_id=test_org.id,
        email="changepw.user@example.com",
        password_hash=security.hash_password(old_pw),
        first_name="Zeynep",
        last_name="Tekin",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    user._raw_password = old_pw
    return user


# ── TEST 1: SUCCESSFUL CHANGE PASSWORD ────────────────────────

@pytest.mark.anyio
async def test_successful_change_password(db_session, async_client, user_main):
    """Valid current password and new password updates hash, allows new login, rejects old login."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    new_pw = "BrandNewPassword123!"
    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": user_main._raw_password, "new_password": new_pw},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["message"] == "Parola başarıyla değiştirildi."

    await db_session.refresh(user_main)
    assert security.verify_password(new_pw, user_main.password_hash) is True
    assert security.verify_password(user_main._raw_password, user_main.password_hash) is False

    # Login with new password succeeds
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_main.email, "password": new_pw},
    )
    assert login_res.status_code == 200

    # Login with old password fails
    old_login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_main.email, "password": user_main._raw_password},
    )
    assert old_login_res.status_code == 401


# ── TEST 2: WRONG CURRENT PASSWORD ────────────────────────────

@pytest.mark.anyio
async def test_wrong_current_password_rejected(async_client, user_main):
    """Incorrect current password returns 401 Unauthorized."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "WrongPassword123!", "new_password": "BrandNewPassword123!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 401


# ── TEST 3: MISSING CURRENT PASSWORD ──────────────────────────

@pytest.mark.anyio
async def test_missing_current_password_rejected(async_client, user_main):
    """Missing current_password field returns 422 Unprocessable Entity."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"new_password": "BrandNewPassword123!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


# ── TESTS 4-8: NEW PASSWORD STRENGTH VALIDATION ────────────────

@pytest.mark.anyio
async def test_new_password_too_short(async_client, user_main):
    """New password shorter than 12 characters returns 422."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": user_main._raw_password, "new_password": "Short1!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


@pytest.mark.anyio
async def test_new_password_missing_uppercase(async_client, user_main):
    """New password missing uppercase letter returns 422."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": user_main._raw_password, "new_password": "nouppercase123!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


@pytest.mark.anyio
async def test_new_password_missing_lowercase(async_client, user_main):
    """New password missing lowercase letter returns 422."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": user_main._raw_password, "new_password": "NOLOWERCASE123!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


@pytest.mark.anyio
async def test_new_password_missing_digit(async_client, user_main):
    """New password missing digit returns 422."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": user_main._raw_password, "new_password": "NoDigitsInPassword!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


@pytest.mark.anyio
async def test_new_password_missing_special_char(async_client, user_main):
    """New password missing special character returns 422."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": user_main._raw_password, "new_password": "NoSpecialChar1234"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


# ── TEST 9: SAME NEW PASSWORD ──────────────────────────────────

@pytest.mark.anyio
async def test_same_new_password_rejected(async_client, user_main):
    """New password identical to current password returns 422 validation error."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": user_main._raw_password, "new_password": user_main._raw_password},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


# ── TEST 10: PASSWORD HISTORY REUSE REJECTED ──────────────────

@pytest.mark.anyio
async def test_reusing_recent_history_password_rejected(db_session, async_client, user_main):
    """Reusing any of the last 5 historical passwords returns 422."""
    hist_pw = "HistoricalPassword123!"
    hist_hash = security.hash_password(hist_pw)
    pw_hist = PasswordHistory(
        user_id=user_main.id,
        password_hash=hist_hash,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(pw_hist)
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": user_main._raw_password, "new_password": hist_pw},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


# ── TESTS 11-13: AUTHENTICATION FAILURES ──────────────────────

@pytest.mark.anyio
async def test_change_password_unauthorized(async_client):
    """Change password without Authorization header returns 401 Unauthorized."""
    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "OldPass12345!", "new_password": "NewPass12345!"},
    )
    assert res.status_code == 401


@pytest.mark.anyio
async def test_change_password_invalid_token(async_client):
    """Change password with invalid token returns 401 Unauthorized."""
    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "OldPass12345!", "new_password": "NewPass12345!"},
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    assert res.status_code == 401


@pytest.mark.anyio
async def test_change_password_expired_token(async_client, user_main):
    """Change password with expired token returns 401 Unauthorized."""
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(user_main.id),
        "jti": "expired_jti_123",
        "org": str(user_main.organization_id),
        "role": user_main.role,
        "perms": [],
        "mfa": False,
        "iat": now - timedelta(minutes=60),
        "nbf": now - timedelta(minutes=60),
        "exp": now - timedelta(minutes=5),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }
    private_key = settings.load_jwt_private_key()
    expired_token = jwt.encode(expired_payload, private_key, algorithm=settings.JWT_ALGORITHM)

    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": user_main._raw_password, "new_password": "BrandNewPassword123!"},
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res.status_code == 401


# ── TEST 14: SESSIONS INVALIDATED AFTER PASSWORD CHANGE ───────

@pytest.mark.anyio
async def test_sessions_invalidated_after_password_change(db_session, async_client, user_main):
    """Active refresh sessions for user are marked revoked after password change."""
    # Create an active session
    raw_token = security.generate_refresh_token()
    token_hash = security.hash_token(raw_token)
    now = datetime.now(timezone.utc)
    sess = Session(
        user_id=user_main.id,
        refresh_token_hash=token_hash,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)
    assert sess.revoked_at is None

    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    new_pw = "BrandNewPassword123!"
    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": user_main._raw_password, "new_password": new_pw},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    await db_session.refresh(sess)
    assert sess.revoked_at is not None


# ── TEST 15: SECURITY NON-EXPOSURE IN RESPONSE AND LOGS ───────

@pytest.mark.anyio
async def test_security_non_exposure_in_response_and_logs(caplog, async_client, user_main):
    """Response body and logs do not expose plaintext passwords, hashes, or secrets."""
    caplog.set_level(logging.DEBUG)

    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    new_pw = "SuperSecretPassword123!"
    res = await async_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": user_main._raw_password, "new_password": new_pw},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    body = res.json()
    assert "password" not in body
    assert "password_hash" not in body
    assert "current_password" not in body
    assert "new_password" not in body
    assert "access_token" not in body

    log_output = caplog.text
    assert new_pw not in log_output
    assert user_main._raw_password not in log_output
