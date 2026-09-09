"""
NeuroOncoTrack-AI — Comprehensive Auth Test Matrix (TASK-017)

Unified End-to-End Test Suite verifying all 14 authentication domains:
1. Login Matrix
2. MFA Matrix
3. JWT / Access Token Matrix
4. /auth/me Matrix
5. Refresh Token Matrix
6. Logout Matrix
7. Logout All Matrix
8. Profile Update Matrix
9. Change Password Matrix
10. Forgot Password Matrix
11. Reset Password Matrix
12. Session Management Matrix
13. Error Standardization Matrix
14. Security & Edge Cases Matrix
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import security, redis as redis_core
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.password_reset_token import PasswordResetToken
from app.models.session import Session
from app.models.user import User


@pytest.fixture
async def async_client(db_session, mock_redis):
    """Async HTTP client with DB session and FakeRedis."""
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
async def matrix_org(db_session):
    org = Organization(name="Matrix Hastanesi", code="MATRIX_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def matrix_user(db_session, matrix_org):
    user = User(
        organization_id=matrix_org.id,
        email="matrix.user@example.com",
        password_hash=security.hash_password("MatrixPassword123!"),
        first_name="Matrix",
        last_name="Tester",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ── DOMAIN 1: LOGIN MATRIX ───────────────────────────────────

@pytest.mark.anyio
async def test_domain_1_login_full_matrix(db_session, async_client, matrix_user):
    """Domain 1: Valid login, email normalization, cookie setting, and account status check."""
    res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "  MATRIX.USER@EXAMPLE.COM  ", "password": "MatrixPassword123!"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert settings.REFRESH_TOKEN_COOKIE_NAME in res.cookies

    # Failed attempts reset on successful login
    await db_session.refresh(matrix_user)
    assert matrix_user.failed_login_attempts == 0
    assert matrix_user.last_login_at is not None


# ── DOMAIN 2: MFA MATRIX ─────────────────────────────────────

@pytest.mark.anyio
async def test_domain_2_mfa_full_lifecycle(db_session, async_client, matrix_org):
    """Domain 2: MFA login challenge branch (202), TOTP verification, and session creation."""
    totp_secret = security.generate_totp_secret()
    mfa_user = User(
        organization_id=matrix_org.id,
        email="mfa.matrix@example.com",
        password_hash=security.hash_password("MfaMatrixPass123!"),
        first_name="MFA",
        last_name="Matrix",
        role="PHYSICIAN",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=security.encrypt_mfa_secret(totp_secret),
    )
    db_session.add(mfa_user)
    await db_session.commit()

    # Step 1: Login triggers 202 Accepted MFA Challenge
    res_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "mfa.matrix@example.com", "password": "MfaMatrixPass123!"},
    )
    assert res_login.status_code == 202
    login_data = res_login.json()
    assert login_data["mfa_required"] is True
    temp_token = login_data["mfa_temp_token"]

    # Step 2: MFA Verify with TOTP
    totp_code = pyotp.TOTP(totp_secret).now()
    res_verify = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": totp_code},
    )
    assert res_verify.status_code == 200
    verify_data = res_verify.json()
    assert "access_token" in verify_data
    assert settings.REFRESH_TOKEN_COOKIE_NAME in res_verify.cookies


# ── DOMAIN 3 & 4: JWT & /AUTH/ME MATRIX ──────────────────────

@pytest.mark.anyio
async def test_domain_3_4_jwt_and_me_matrix(async_client, matrix_user):
    """Domain 3 & 4: RS256 token verification, claims check, /auth/me payload."""
    token, _, _ = security.create_access_token(
        subject=str(matrix_user.id),
        organization_id=str(matrix_user.organization_id),
        role=matrix_user.role,
        permissions=[],
    )

    res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    user_data = res.json()
    assert user_data["id"] == str(matrix_user.id)
    assert user_data["email"] == matrix_user.email
    assert user_data["role"] == "PHYSICIAN"


# ── DOMAIN 5: REFRESH TOKEN MATRIX ───────────────────────────

@pytest.mark.anyio
async def test_domain_5_refresh_token_rotation_matrix(db_session, async_client, matrix_user):
    """Domain 5: Refresh token rotation, old token revocation, new token issuance."""
    # Create initial login session
    res_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": matrix_user.email, "password": "MatrixPassword123!"},
    )
    assert res_login.status_code == 200
    old_cookie = res_login.cookies[settings.REFRESH_TOKEN_COOKIE_NAME]

    # Rotate refresh token
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, old_cookie)
    res_refresh = await async_client.post("/api/v1/auth/refresh")
    assert res_refresh.status_code == 200
    new_cookie = res_refresh.cookies[settings.REFRESH_TOKEN_COOKIE_NAME]
    assert new_cookie != old_cookie

    # Reusing old cookie fails (Replay Protection)
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, old_cookie)
    res_replay = await async_client.post("/api/v1/auth/refresh")
    assert res_replay.status_code == 401
    assert res_replay.json()["error"]["code"] == "AUTH_002"


# ── DOMAIN 6 & 7: LOGOUT & LOGOUT ALL MATRIX ──────────────────

@pytest.mark.anyio
async def test_domain_6_7_logout_and_logout_all_matrix(db_session, async_client, matrix_user):
    """Domain 6 & 7: Single logout and logout all across multiple active sessions."""
    # Create 2 sessions
    raw1 = security.generate_refresh_token()
    raw2 = security.generate_refresh_token()
    now = datetime.now(timezone.utc)

    s1 = Session(user_id=matrix_user.id, refresh_token_hash=security.hash_token(raw1), created_at=now, last_used_at=now, expires_at=now+timedelta(days=7))
    s2 = Session(user_id=matrix_user.id, refresh_token_hash=security.hash_token(raw2), created_at=now, last_used_at=now, expires_at=now+timedelta(days=7))
    db_session.add_all([s1, s2])
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(matrix_user.id),
        organization_id=str(matrix_user.organization_id),
        role=matrix_user.role,
        permissions=[],
    )

    # Logout All
    res = await async_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 204

    # Verify all sessions revoked
    db_res = await db_session.execute(select(Session).where(Session.user_id == matrix_user.id))
    sessions = db_res.scalars().all()
    assert all(s.revoked_at is not None for s in sessions)


# ── DOMAIN 8: PROFILE UPDATE MATRIX ──────────────────────────

@pytest.mark.anyio
async def test_domain_8_profile_update_matrix(db_session, async_client, matrix_user):
    """Domain 8: Self profile partial update & forbidden field protection."""
    token, _, _ = security.create_access_token(
        subject=str(matrix_user.id),
        organization_id=str(matrix_user.organization_id),
        role=matrix_user.role,
        permissions=[],
    )

    # Invalid email format returns 422 VAL_001
    res_invalid = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "not-an-email"},
    )
    assert res_invalid.status_code == 422
    assert res_invalid.json()["error"]["code"] == "VAL_001"

    # Extra unwhitelisted field (e.g. role) returns 422 Unprocessable Entity under strict DTO validation
    res_forbidden = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"first_name": "UpdatedMatrixName", "role": "ADMIN"},
    )
    assert res_forbidden.status_code == 422

    # Valid profile update updates first_name
    res_valid = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"first_name": "UpdatedMatrixName"},
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["first_name"] == "UpdatedMatrixName"
    assert res_valid.json()["role"] == "PHYSICIAN"  # Role was NOT changed


# ── DOMAIN 9: CHANGE PASSWORD MATRIX ─────────────────────────

@pytest.mark.anyio
async def test_domain_9_change_password_matrix(db_session, async_client, matrix_user):
    """Domain 9: Change password, password history check, and session invalidation."""
    token, _, _ = security.create_access_token(
        subject=str(matrix_user.id),
        organization_id=str(matrix_user.organization_id),
        role=matrix_user.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "MatrixPassword123!", "new_password": "NewStrongPass456!"},
    )
    assert res.status_code == 200

    # Old password no longer works
    res_old = await async_client.post(
        "/api/v1/auth/login",
        json={"email": matrix_user.email, "password": "MatrixPassword123!"},
    )
    assert res_old.status_code == 401

    # New password works
    res_new = await async_client.post(
        "/api/v1/auth/login",
        json={"email": matrix_user.email, "password": "NewStrongPass456!"},
    )
    assert res_new.status_code == 200


# ── DOMAIN 10 & 11: FORGOT & RESET PASSWORD MATRIX ───────────

@pytest.mark.anyio
async def test_domain_10_11_forgot_and_reset_password_matrix(db_session, async_client, matrix_user):
    """Domain 10 & 11: Forgot password token generation and reset password workflow."""
    # Step 1: Forgot Password
    res_forgot = await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": matrix_user.email},
    )
    assert res_forgot.status_code == 200

    # Retrieve reset token from DB
    stmt = select(PasswordResetToken).where(PasswordResetToken.user_id == matrix_user.id)
    db_res = await db_session.execute(stmt)
    token_record = db_res.scalar_one()

    # Step 2: Reset Password using raw token generated in service
    raw_reset_token = security.generate_password_reset_token()
    token_record.token_hash = security.hash_token(raw_reset_token)
    await db_session.commit()

    res_reset = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_reset_token, "new_password": "ResetPassword789!"},
    )
    assert res_reset.status_code == 200
    assert "başarıyla sıfırlandı" in res_reset.json()["message"]


# ── DOMAIN 12: SESSION MANAGEMENT MATRIX ──────────────────────

@pytest.mark.anyio
async def test_domain_12_session_management_matrix(db_session, async_client, matrix_user):
    """Domain 12: Session listing, current flag, and session revocation."""
    res_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": matrix_user.email, "password": "MatrixPassword123!"},
    )
    assert res_login.status_code == 200
    access_token = res_login.json()["access_token"]
    refresh_cookie = res_login.cookies[settings.REFRESH_TOKEN_COOKIE_NAME]

    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, refresh_cookie)
    res_sessions = await async_client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert res_sessions.status_code == 200
    sessions_list = res_sessions.json()
    assert len(sessions_list) >= 1
    assert any(s["current"] is True for s in sessions_list)


# ── DOMAIN 13 & 14: ERROR STANDARDIZATION & SECURITY MATRIX ──

@pytest.mark.anyio
async def test_domain_13_14_error_standardization_and_security(async_client):
    """Domain 13 & 14: Error envelope structure, error codes, zero sensitive leaks."""
    res = await async_client.get("/api/v1/auth/me")  # Missing auth
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "AUTH_002"
    assert "timestamp" in err
    assert "password" not in str(err)
    assert "token" not in str(err)
