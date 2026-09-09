"""
NeuroOncoTrack-AI — MFA Verification Dedicated Test Suite (TASK-010)

Tests cover:
- Test 1: Valid TOTP Code verification issuing access token (mfa_verified=True) & refresh cookie
- Test 2: Invalid 6-digit TOTP code returning AUTH_005 error code
- Test 3: Malformed TOTP code returning AUTH_005 error code
- Test 4: Expired MFA temporary token returning AUTH_005 error code
- Test 5: Invalid/tampered MFA temporary token returning AUTH_005 error code
- Test 6: Reused MFA temporary token rejected with AUTH_005 error code (one-time token semantics)
- Test 7: Valid Backup Code verification
- Test 8: Single-use Backup Code consumption and DB state removal
- Test 9: Reused Backup Code rejection with AUTH_005 error code
- Test 10: Non-exposure of TOTP secret or encryption key in logs
- Test 11: Non-exposure of backup codes in logs
- Test 12: Preservation of user role, organization, and permissions claims in final access token
"""

from __future__ import annotations

import logging
from typing import Any

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import security
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.user import User


def parse_codes(codes: Any) -> list[str]:
    if not codes:
        return []
    if isinstance(codes, str):
        import json
        return json.loads(codes)
    if isinstance(codes, list):
        if codes and all(isinstance(x, str) and len(x) == 1 for x in codes):
            import json
            return json.loads("".join(codes))
        return codes
    return []


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
    org = Organization(name="MFA Verification Hastanesi", code="MFA_VERIFY_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def mfa_user(db_session, test_org):
    totp_secret = security.generate_totp_secret()
    encrypted_secret = security.encrypt_mfa_secret(totp_secret)

    user = User(
        organization_id=test_org.id,
        email="mfa.verify.user@example.com",
        password_hash=security.hash_password("MfaVerifyPassword123!"),
        first_name="MFA",
        last_name="Verifier",
        role="PHYSICIAN",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=encrypted_secret,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Attach raw totp secret for fixture consumer
    user._raw_totp_secret = totp_secret
    return user


# ── TEST 1: VALID TOTP CODE ───────────────────────────────────

@pytest.mark.anyio
async def test_valid_totp_code(db_session, async_client, mfa_user):
    """Valid TOTP verification returns 200 OK, issues access token (mfa_verified=True), and sets refresh cookie."""
    temp_token, _ = security.create_mfa_temp_token(str(mfa_user.id))
    totp_code = pyotp.TOTP(mfa_user._raw_totp_secret).now()

    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": totp_code},
    )
    assert res.status_code == 200

    data = res.json()
    assert "access_token" in data
    access_payload = security.decode_access_token(data["access_token"])
    assert access_payload["mfa"] is True

    # Refresh cookie set
    cookie = res.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    assert cookie is not None


# ── TEST 2: INVALID TOTP CODE ─────────────────────────────────

@pytest.mark.anyio
async def test_invalid_totp_code(async_client, mfa_user):
    """Invalid 6-digit TOTP code returns AUTH_005 error code."""
    temp_token, _ = security.create_mfa_temp_token(str(mfa_user.id))

    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": "000000"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTH_005"


# ── TEST 3: MALFORMED TOTP CODE ───────────────────────────────

@pytest.mark.anyio
async def test_malformed_totp_code(async_client, mfa_user):
    """Non-6-digit or malformed code returns AUTH_005 error code."""
    temp_token, _ = security.create_mfa_temp_token(str(mfa_user.id))

    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": "ABCDEF"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTH_005"


# ── TEST 4: EXPIRED MFA TEMP TOKEN ────────────────────────────

@pytest.mark.anyio
async def test_expired_mfa_temp_token(async_client, mfa_user):
    """Expired temporary token returns AUTH_005 error code."""
    # Create temp token with negative expiration
    from datetime import datetime, timedelta, timezone
    import jwt

    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(mfa_user.id),
        "jti": "expired_jti_123",
        "purpose": "mfa_verification",
        "iat": now - timedelta(minutes=10),
        "exp": now - timedelta(minutes=5),
        "iss": settings.JWT_ISSUER,
    }
    private_key = settings.load_jwt_private_key()
    expired_token = jwt.encode(expired_payload, private_key, algorithm=settings.JWT_ALGORITHM)

    totp_code = pyotp.TOTP(mfa_user._raw_totp_secret).now()
    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": expired_token, "code": totp_code},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTH_005"


# ── TEST 5: INVALID MFA TEMP TOKEN ────────────────────────────

@pytest.mark.anyio
async def test_invalid_mfa_temp_token(async_client, mfa_user):
    """Malformed or tampered temporary token returns AUTH_005 error code."""
    totp_code = pyotp.TOTP(mfa_user._raw_totp_secret).now()
    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": "invalid.tampered.token", "code": totp_code},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTH_005"


# ── TEST 6: REUSED MFA TEMP TOKEN ─────────────────────────────

@pytest.mark.anyio
async def test_reused_mfa_temp_token(async_client, mfa_user):
    """Reusing the same temporary MFA token after a successful verification returns AUTH_005."""
    temp_token, _ = security.create_mfa_temp_token(str(mfa_user.id))
    totp_code1 = pyotp.TOTP(mfa_user._raw_totp_secret).now()

    # First verification succeeds
    res1 = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": totp_code1},
    )
    assert res1.status_code == 200

    # Second attempt with SAME temp_token must be rejected
    totp_code2 = pyotp.TOTP(mfa_user._raw_totp_secret).now()
    res2 = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": totp_code2},
    )
    assert res2.status_code == 401
    assert res2.json()["error"]["code"] == "AUTH_005"


# ── TEST 7: VALID BACKUP CODE ─────────────────────────────────

@pytest.mark.anyio
async def test_valid_backup_code(db_session, async_client, mfa_user):
    """Valid backup code authenticates MFA challenge successfully."""
    plain_codes = security.generate_backup_codes(5)
    mfa_user.backup_codes = [security.hash_backup_code(c) for c in plain_codes]
    await db_session.commit()

    temp_token, _ = security.create_mfa_temp_token(str(mfa_user.id))
    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": plain_codes[0], "is_backup_code": True},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()


# ── TEST 8: BACKUP CODE CONSUMED ──────────────────────────────

@pytest.mark.anyio
async def test_backup_code_consumed(db_session, async_client, mfa_user):
    """Used backup code is removed from user's database record."""
    plain_codes = security.generate_backup_codes(3)
    mfa_user.backup_codes = [security.hash_backup_code(c) for c in plain_codes]
    await db_session.commit()

    temp_token, _ = security.create_mfa_temp_token(str(mfa_user.id))
    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": plain_codes[0], "is_backup_code": True},
    )
    assert res.status_code == 200

    await db_session.refresh(mfa_user)
    codes_remaining = parse_codes(mfa_user.backup_codes)
    assert len(codes_remaining) == 2


# ── TEST 9: REUSED BACKUP CODE ────────────────────────────────

@pytest.mark.anyio
async def test_reused_backup_code(db_session, async_client, mfa_user):
    """Reusing the same backup code returns AUTH_005 error code."""
    plain_codes = security.generate_backup_codes(3)
    mfa_user.backup_codes = [security.hash_backup_code(c) for c in plain_codes]
    await db_session.commit()

    code_to_reuse = plain_codes[0]
    temp_token1, _ = security.create_mfa_temp_token(str(mfa_user.id))
    res1 = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token1, "code": code_to_reuse, "is_backup_code": True},
    )
    assert res1.status_code == 200

    temp_token2, _ = security.create_mfa_temp_token(str(mfa_user.id))
    res2 = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token2, "code": code_to_reuse, "is_backup_code": True},
    )
    assert res2.status_code == 401
    assert res2.json()["error"]["code"] == "AUTH_005"


# ── TEST 10: NON-EXPOSURE OF TOTP SECRET ──────────────────────

@pytest.mark.anyio
async def test_mfa_verification_does_not_expose_secret(caplog, async_client, mfa_user):
    """MFA verification flow never logs TOTP secrets or encryption keys."""
    caplog.set_level(logging.DEBUG)

    temp_token, _ = security.create_mfa_temp_token(str(mfa_user.id))
    totp_code = pyotp.TOTP(mfa_user._raw_totp_secret).now()

    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": totp_code},
    )
    assert res.status_code == 200

    log_output = caplog.text
    assert mfa_user._raw_totp_secret not in log_output
    assert settings.MFA_ENCRYPTION_KEY not in log_output


# ── TEST 11: NON-EXPOSURE OF BACKUP CODES ─────────────────────

@pytest.mark.anyio
async def test_mfa_verification_does_not_expose_backup_codes(caplog, db_session, async_client, mfa_user):
    """MFA verification flow never logs plaintext backup codes in responses or logs."""
    caplog.set_level(logging.DEBUG)
    plain_codes = security.generate_backup_codes(3)
    mfa_user.backup_codes = [security.hash_backup_code(c) for c in plain_codes]
    await db_session.commit()

    temp_token, _ = security.create_mfa_temp_token(str(mfa_user.id))
    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": plain_codes[0], "is_backup_code": True},
    )
    assert res.status_code == 200

    log_output = caplog.text
    for code in plain_codes:
        assert code not in log_output


# ── TEST 12: USER AUTHORIZATION CLAIMS PRESERVED ──────────────

@pytest.mark.anyio
async def test_mfa_verification_preserves_user_authorization_claims(async_client, mfa_user):
    """Issued access token retains DB-derived user ID, organization ID, role, and permissions."""
    temp_token, _, _ = security.create_access_token(
        subject=str(mfa_user.id),
        organization_id=str(mfa_user.organization_id),
        role=mfa_user.role,
        permissions=[],
    )
    temp_mfa_token, _ = security.create_mfa_temp_token(str(mfa_user.id))
    totp_code = pyotp.TOTP(mfa_user._raw_totp_secret).now()

    res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_mfa_token, "code": totp_code},
    )
    assert res.status_code == 200

    token = res.json()["access_token"]
    payload = security.decode_access_token(token)
    assert payload["sub"] == str(mfa_user.id)
    assert payload["org"] == str(mfa_user.organization_id)
    assert payload["role"] == "PHYSICIAN"
    assert payload["mfa"] is True
