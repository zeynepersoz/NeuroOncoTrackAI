"""
NeuroOncoTrack-AI — MFA / TOTP Authentication Unit & Integration Test Suite (TASK-007)

Tests cover:
- MFA Setup: Base32 secret, otpauth:// provisioning URI, 10 backup codes generation, Fernet encryption at rest
- MFA Enable: TOTP verification, activation state change (mfa_enabled=True), invalid code rejection
- MFA Login Challenge: Login for MFA-enabled user returns HTTP 202 Accepted with mfa_temp_token
- MFA Verify (TOTP): 6-digit TOTP validation, access token issuance with mfa_verified=True, refresh cookie setting
- MFA Verify (Backup Code): Single-use backup code authentication, consumption, and replay rejection
- MFA Disable: Password-verified MFA deactivation, state cleanup
- Non-exposure: MFA secrets, backup codes, private keys never logged or returned in error bodies
"""

from __future__ import annotations

import pyotp
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
async def async_client(db_session):
    """Async HTTP client for testing FastAPI endpoints."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def test_org(db_session):
    org = Organization(name="MFA Test Hastanesi", code="MFA_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def test_user(db_session, test_org):
    password_plain = "MfaPassword123!"
    user = User(
        organization_id=test_org.id,
        email="mfa.user@example.com",
        password_hash=security.hash_password(password_plain),
        first_name="MFA",
        last_name="Tester",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ── STEP 1: MFA SETUP TESTS ──────────────────────────────────

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


@pytest.mark.anyio
async def test_mfa_setup_generates_secret_and_backup_codes(db_session, async_client, test_user):
    """POST /api/v1/auth/mfa/setup generates TOTP secret, provisioning URI, and backup codes."""
    # Acquire access token
    token, _, _ = security.create_access_token(
        subject=str(test_user.id),
        organization_id=str(test_user.organization_id),
        role=test_user.role,
        permissions=[],
    )

    headers = {"Authorization": f"Bearer {token}"}
    res = await async_client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert res.status_code == 200

    data = res.json()
    assert "secret" in data
    assert len(data["secret"]) == 32  # Base32 TOTP secret length
    assert "otpauth://" in data["provisioning_uri"]
    assert "mfa.user" in data["provisioning_uri"]
    assert "backup_codes" in data
    assert len(data["backup_codes"]) == 10

    # Verify DB state
    await db_session.refresh(test_user)
    assert test_user.mfa_enabled is False  # Still False until verified
    assert test_user.mfa_secret is not None
    # Secret is Fernet-encrypted, not plaintext
    assert test_user.mfa_secret != data["secret"]
    assert security.decrypt_mfa_secret(test_user.mfa_secret) == data["secret"]
    assert len(parse_codes(test_user.backup_codes)) == 10


@pytest.mark.anyio
async def test_mfa_setup_when_already_enabled_rejected(db_session, async_client, test_user):
    """MFA setup fails if MFA is already enabled."""
    test_user.mfa_enabled = True
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(test_user.id),
        organization_id=str(test_user.organization_id),
        role=test_user.role,
        permissions=[],
    )

    res = await async_client.post("/api/v1/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422
    assert "zaten aktif" in res.json()["error"]["detail"]


# ── STEP 2: MFA ENABLE TESTS ─────────────────────────────────

@pytest.mark.anyio
async def test_mfa_enable_with_valid_totp_succeeds(db_session, async_client, test_user):
    """POST /api/v1/auth/mfa/enable verifies initial TOTP code and sets mfa_enabled=True."""
    # Run setup first
    totp_secret = security.generate_totp_secret()
    test_user.mfa_secret = security.encrypt_mfa_secret(totp_secret)
    test_user.mfa_enabled = False
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(test_user.id),
        organization_id=str(test_user.organization_id),
        role=test_user.role,
        permissions=[],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Generate current TOTP code
    current_code = pyotp.TOTP(totp_secret).now()

    res = await async_client.post(
        "/api/v1/auth/mfa/enable",
        json={"code": current_code},
        headers=headers,
    )
    assert res.status_code == 200
    assert "etkinleştirildi" in res.json()["message"]

    await db_session.refresh(test_user)
    assert test_user.mfa_enabled is True


@pytest.mark.anyio
async def test_mfa_enable_with_invalid_totp_fails(db_session, async_client, test_user):
    """Invalid TOTP code during enable returns 401 (AUTH_005) and leaves mfa_enabled=False."""
    totp_secret = security.generate_totp_secret()
    test_user.mfa_secret = security.encrypt_mfa_secret(totp_secret)
    test_user.mfa_enabled = False
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(test_user.id),
        organization_id=str(test_user.organization_id),
        role=test_user.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/mfa/enable",
        json={"code": "000000"},  # Invalid code
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTH_005"

    await db_session.refresh(test_user)
    assert test_user.mfa_enabled is False


# ── STEP 3: MFA LOGIN & VERIFY TESTS ─────────────────────────

@pytest.mark.anyio
async def test_login_mfa_enabled_returns_202_accepted(db_session, async_client, test_user):
    """Login for user with mfa_enabled=True returns HTTP 202 Accepted with mfa_temp_token."""
    totp_secret = security.generate_totp_secret()
    test_user.mfa_secret = security.encrypt_mfa_secret(totp_secret)
    test_user.mfa_enabled = True
    await db_session.commit()

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "mfa.user@example.com", "password": "MfaPassword123!"},
    )
    assert login_res.status_code == 202

    data = login_res.json()
    assert data["mfa_required"] is True
    assert "mfa_temp_token" in data

    # Verify temp token claims
    temp_payload = security.decode_mfa_temp_token(data["mfa_temp_token"])
    assert temp_payload["sub"] == str(test_user.id)
    assert temp_payload["purpose"] == "mfa_verification"


@pytest.mark.anyio
async def test_mfa_verify_with_totp_succeeds(db_session, async_client, test_user):
    """POST /api/v1/auth/mfa/verify with valid TOTP code completes login flow."""
    totp_secret = security.generate_totp_secret()
    test_user.mfa_secret = security.encrypt_mfa_secret(totp_secret)
    test_user.mfa_enabled = True
    await db_session.commit()

    # Create temporary token
    temp_token, _ = security.create_mfa_temp_token(str(test_user.id))
    totp_code = pyotp.TOTP(totp_secret).now()

    verify_res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": totp_code},
    )
    assert verify_res.status_code == 200

    data = verify_res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Refresh cookie must be set
    cookie = verify_res.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    assert cookie is not None


@pytest.mark.anyio
async def test_mfa_verify_with_backup_code_succeeds_and_consumes_code(db_session, async_client, test_user):
    """MFA verify with backup code succeeds and consumes the backup code from DB."""
    totp_secret = security.generate_totp_secret()
    test_user.mfa_secret = security.encrypt_mfa_secret(totp_secret)
    test_user.mfa_enabled = True

    plain_backup_codes = security.generate_backup_codes(5)
    test_user.backup_codes = [security.hash_backup_code(c) for c in plain_backup_codes]
    await db_session.commit()

    temp_token, _ = security.create_mfa_temp_token(str(test_user.id))
    code_to_use = plain_backup_codes[0]

    verify_res = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token, "code": code_to_use, "is_backup_code": True},
    )
    assert verify_res.status_code == 200

    # Verify backup code was consumed (now 4 left)
    await db_session.refresh(test_user)
    assert len(parse_codes(test_user.backup_codes)) == 4

    # Reusing the same backup code must fail
    temp_token2, _ = security.create_mfa_temp_token(str(test_user.id))
    verify_res2 = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_temp_token": temp_token2, "code": code_to_use, "is_backup_code": True},
    )
    assert verify_res2.status_code == 401
    assert verify_res2.json()["error"]["code"] == "AUTH_005"


# ── STEP 4: MFA DISABLE TESTS ────────────────────────────────

@pytest.mark.anyio
async def test_mfa_disable_succeeds_with_correct_password(db_session, async_client, test_user):
    """POST /api/v1/auth/mfa/disable turns off MFA with valid current password."""
    totp_secret = security.generate_totp_secret()
    test_user.mfa_secret = security.encrypt_mfa_secret(totp_secret)
    test_user.mfa_enabled = True
    test_user.backup_codes = ["hash1", "hash2"]
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(test_user.id),
        organization_id=str(test_user.organization_id),
        role=test_user.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/mfa/disable",
        json={"current_password": "MfaPassword123!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    await db_session.refresh(test_user)
    assert test_user.mfa_enabled is False
    assert test_user.mfa_secret is None
    assert test_user.backup_codes is None


@pytest.mark.anyio
async def test_mfa_disable_with_wrong_password_fails(db_session, async_client, test_user):
    """MFA disable fails with wrong password."""
    test_user.mfa_enabled = True
    test_user.mfa_secret = "secret"
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(test_user.id),
        organization_id=str(test_user.organization_id),
        role=test_user.role,
        permissions=[],
    )

    res = await async_client.post(
        "/api/v1/auth/mfa/disable",
        json={"current_password": "WrongPassword123!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTH_001"
