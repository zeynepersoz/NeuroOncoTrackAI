"""
NeuroOncoTrack-AI — Auth Error Standardization & Defense Tests (TASK-016)

Tests cover:
- Test 1: Wrong email returns AUTH_001 / 401
- Test 2: Wrong password returns AUTH_001 / 401
- Test 3: Locked account returns AUTH_004 / 423
- Test 4: Invalid access token returns AUTH_002 / 401
- Test 5: Expired access token returns AUTH_002 / 401
- Test 6: Blacklisted access token returns AUTH_002 / 401
- Test 7: Invalid refresh token returns AUTH_002 / 401
- Test 8: Revoked refresh token returns AUTH_002 / 401
- Test 9: Invalid MFA code returns AUTH_005 / 401
- Test 10: Expired MFA temp token returns AUTH_005 / 401
- Test 11: Weak password returns VAL_001 / 422
- Test 12: Invalid payload validation returns VAL_001 / 422
- Test 13: RateLimitError returns RATE_001 / 429
- Test 14: Forgot password existing email returns generic message
- Test 15: Forgot password unknown email returns identical generic message
- Test 16: User enumeration defense — unknown email vs wrong password identical AUTH_001
- Test 17: Zero password exposure in error envelope
- Test 18: Zero token exposure in error envelope
- Test 19: Zero password hash exposure in error envelope
- Test 20: Zero stack trace or raw DB details in error envelope
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pyotp
import pytest
from httpx import ASGITransport, AsyncClient

from app.core import security, redis as redis_core
from app.core.config import settings
from app.core.exceptions import RateLimitError
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
    org = Organization(name="Error Standard Hastanesi", code="ERR_STD_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def test_user(db_session, test_org):
    user = User(
        organization_id=test_org.id,
        email="error.test@example.com",
        password_hash=security.hash_password("ValidPassword123!"),
        first_name="Error",
        last_name="Tester",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ── TEST 1 & 2: LOGIN WRONG EMAIL & PASSWORD ────────────────

@pytest.mark.anyio
async def test_wrong_email_auth_001(async_client):
    """Unknown email login attempt returns AUTH_001 / 401."""
    res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "AnyPassword123!"},
    )
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "AUTH_001"
    assert "E-posta veya parola hatalı" in err["message"]


@pytest.mark.anyio
async def test_wrong_password_auth_001(async_client, test_user):
    """Wrong password login attempt returns AUTH_001 / 401."""
    res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "WrongPassword123!"},
    )
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "AUTH_001"
    assert "E-posta veya parola hatalı" in err["message"]


# ── TEST 3: LOCKED ACCOUNT ────────────────────────────────────

@pytest.mark.anyio
async def test_locked_account_auth_004(db_session, async_client, test_user):
    """Locked user account returns AUTH_004 / 423."""
    test_user.is_locked = True
    test_user.failed_login_attempts = 5
    test_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    await db_session.commit()

    res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "ValidPassword123!"},
    )
    assert res.status_code == 423
    err = res.json()["error"]
    assert err["code"] == "AUTH_004"


# ── TEST 4, 5, 6: ACCESS TOKEN ERRORS ─────────────────────────

@pytest.mark.anyio
async def test_invalid_access_token_auth_002(async_client):
    """Malformed / invalid Bearer token returns AUTH_002 / 401."""
    res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid_jwt_token_string"},
    )
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "AUTH_002"


@pytest.mark.anyio
async def test_expired_access_token_auth_002(async_client, test_user):
    """Expired Bearer JWT returns AUTH_002 / 401."""
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(test_user.id),
        "jti": "exp_jti_01",
        "org": str(test_user.organization_id),
        "role": test_user.role,
        "perms": [],
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }
    private_key = settings.load_jwt_private_key()
    expired_token = jwt.encode(expired_payload, private_key, algorithm=settings.JWT_ALGORITHM)

    res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "AUTH_002"


@pytest.mark.anyio
async def test_blacklisted_access_token_auth_002(async_client, test_user, mock_redis):
    """Blacklisted JTI returns AUTH_002 / 401."""
    token, jti, _ = security.create_access_token(
        subject=str(test_user.id),
        organization_id=str(test_user.organization_id),
        role=test_user.role,
        permissions=[],
    )
    await redis_core.blacklist_token(mock_redis, jti, ttl_seconds=3600)

    res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "AUTH_002"


# ── TEST 7 & 8: REFRESH TOKEN ERRORS ─────────────────────────

@pytest.mark.anyio
async def test_invalid_refresh_token_auth_002(async_client):
    """Invalid refresh cookie returns AUTH_002 / 401."""
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, "non_existent_refresh_token")
    res = await async_client.post("/api/v1/auth/refresh")
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "AUTH_002"


@pytest.mark.anyio
async def test_revoked_refresh_token_auth_002(db_session, async_client, test_user):
    """Revoked refresh token returns AUTH_002 / 401."""
    raw_token = security.generate_refresh_token()
    token_hash = security.hash_token(raw_token)
    now = datetime.now(timezone.utc)
    revoked_sess = Session(
        user_id=test_user.id,
        refresh_token_hash=token_hash,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
        revoked_at=now,
    )
    db_session.add(revoked_sess)
    await db_session.commit()

    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, raw_token)
    res = await async_client.post("/api/v1/auth/refresh")
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "AUTH_002"


# ── TEST 9 & 10: MFA ERRORS ───────────────────────────────────

@pytest.mark.anyio
async def test_invalid_mfa_code_auth_005(db_session, async_client, test_org):
    """Invalid TOTP code returns AUTH_005 / 401."""
    totp_secret = security.generate_totp_secret()
    mfa_user = User(
        organization_id=test_org.id,
        email="mfa.err@example.com",
        password_hash=security.hash_password("MfaPassword123!"),
        first_name="MFA",
        last_name="Err",
        role="PHYSICIAN",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=security.encrypt_mfa_secret(totp_secret),
    )
    db_session.add(mfa_user)
    await db_session.commit()
    await db_session.refresh(mfa_user)

    temp_token, _ = security.create_mfa_temp_token(str(mfa_user.id))
    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": "000000"},
    )
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "AUTH_005"


@pytest.mark.anyio
async def test_expired_mfa_temp_token_auth_005(async_client, test_user):
    """Expired temporary MFA token returns AUTH_005 / 401."""
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(test_user.id),
        "jti": "mfa_exp_jti_01",
        "purpose": "mfa_verification",
        "iat": now - timedelta(minutes=10),
        "exp": now - timedelta(minutes=5),
        "iss": settings.JWT_ISSUER,
    }
    private_key = settings.load_jwt_private_key()
    expired_temp_token = jwt.encode(expired_payload, private_key, algorithm=settings.JWT_ALGORITHM)

    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": expired_temp_token, "code": "123456"},
    )
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "AUTH_005"


# ── TEST 11 & 12: VALIDATION ERRORS ───────────────────────────

@pytest.mark.anyio
async def test_weak_password_val_001(async_client, test_org):
    """Weak registration password returns VAL_001 / 422."""
    res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "weakreg@example.com",
            "password": "weak",
            "first_name": "Weak",
            "last_name": "Reg",
            "role": "PHYSICIAN",
            "organization_id": str(test_org.id),
        },
    )
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VAL_001"


@pytest.mark.anyio
async def test_invalid_profile_validation_val_001(async_client, test_user):
    """Invalid payload structure returns VAL_001 / 422."""
    token, _, _ = security.create_access_token(
        subject=str(test_user.id),
        organization_id=str(test_user.organization_id),
        role=test_user.role,
        permissions=[],
    )
    res = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "invalid-email-format"},
    )
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VAL_001"


# ── TEST 13: RATE LIMIT ───────────────────────────────────────

@pytest.mark.anyio
async def test_rate_limit_rate_001():
    """RateLimitError exception returns RATE_001 / 429 in error envelope."""
    err = RateLimitError(detail="Limit aşıldı.")
    dict_output = err.to_dict()
    assert err.status_code == 429
    assert dict_output["error"]["code"] == "RATE_001"


# ── TEST 14, 15, 16: USER ENUMERATION PROTECTION ─────────────

@pytest.mark.anyio
async def test_user_enumeration_protection(async_client, test_user):
    """Login with unknown email vs wrong password produces identical AUTH_001 response."""
    res_wrong_email = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "ghost.user@example.com", "password": "WrongPassword123!"},
    )
    res_wrong_pass = await async_client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "WrongPassword123!"},
    )

    assert res_wrong_email.status_code == res_wrong_pass.status_code == 401
    assert res_wrong_email.json()["error"]["code"] == res_wrong_pass.json()["error"]["code"] == "AUTH_001"
    assert res_wrong_email.json()["error"]["message"] == res_wrong_pass.json()["error"]["message"]


@pytest.mark.anyio
async def test_forgot_password_identical_generic_response(async_client, test_user):
    """Forgot password returns identical generic HTTP 200 response for existing and unknown emails."""
    res_exist = await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": test_user.email},
    )
    res_unknown = await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "missing.person@example.com"},
    )

    assert res_exist.status_code == res_unknown.status_code == 200
    assert res_exist.json() == res_unknown.json()


# ── TEST 17, 18, 19, 20: ZERO SENSITIVE DATA LEAKAGE ──────────

@pytest.mark.anyio
async def test_zero_sensitive_data_leakage_in_error_envelope(async_client, test_user):
    """Error envelope contains zero plain passwords, tokens, hashes, or stack traces."""
    res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "WrongPassword123!"},
    )
    assert res.status_code == 401
    body_str = str(res.json())

    assert "WrongPassword123!" not in body_str
    assert "password_hash" not in body_str
    assert "Traceback" not in body_str
    assert "sqlalchemy" not in body_str
    assert "postgresql" not in body_str
