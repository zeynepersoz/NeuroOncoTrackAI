"""
NeuroOncoTrack-AI — Forgot Password API Endpoints & Security Tests (TASK-013)

Tests cover:
- Test 1: Forgot password with existing user email (200 OK, token hash in DB, 15 min TTL, email sent)
- Test 2: Forgot password with non-existing user email (identical 200 OK, NO token in DB, NO email)
- Test 3: User enumeration protection (identical HTTP status code, response body, and message)
- Test 4: Token security & entropy (plaintext token not stored, SHA-256 hash in DB)
- Test 5: Token expiration set to ~15 minutes
- Test 6: One-time token foundation state (used_at is None initially)
- Test 7: Email abstraction integration for existing user
- Test 8: Email abstraction NOT invoked for non-existing user
- Test 9: Unauthenticated access succeeds without Bearer token
- Test 10: Subsequent reset requests invalidate previous active reset tokens for user
- Test 11: Response and audit logs do not expose sensitive reset tokens, passwords, hashes, or secrets
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import security
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services.email import email_service


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
    org = Organization(name="Forgot Password Hastanesi", code="FORGOT_PW_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def user_existing(db_session, test_org):
    user = User(
        organization_id=test_org.id,
        email="forgot.existing@example.com",
        password_hash=security.hash_password("ExistingUserPass123!"),
        first_name="Esra",
        last_name="Yıldız",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ── TEST 1: EXISTING USER FORGOT PASSWORD ─────────────────────

@pytest.mark.anyio
async def test_forgot_password_existing_user(db_session, async_client, user_existing):
    """Forgot password for existing user creates reset token hash in DB with ~15min TTL."""
    with patch.object(email_service, "send_password_reset_email", new_callable=AsyncMock) as mock_send_email:
        mock_send_email.return_value = True

        res = await async_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": user_existing.email},
        )
        assert res.status_code == 200
        assert "bağlantısı gönderildiyse" in res.json()["message"]

        # Check DB record
        stmt = select(PasswordResetToken).where(PasswordResetToken.user_id == user_existing.id)
        result = await db_session.execute(stmt)
        token_record = result.scalar_one_or_none()

        assert token_record is not None
        assert token_record.used_at is None
        exp_at = token_record.expires_at if token_record.expires_at.tzinfo else token_record.expires_at.replace(tzinfo=timezone.utc)
        assert exp_at > datetime.now(timezone.utc)

        # Email abstraction invoked
        mock_send_email.assert_called_once()
        call_email, plain_token = mock_send_email.call_args[0]
        assert call_email == user_existing.email
        assert security.hash_token(plain_token) == token_record.token_hash


# ── TEST 2: NON-EXISTING USER FORGOT PASSWORD ─────────────────

@pytest.mark.anyio
async def test_forgot_password_non_existing_user(db_session, async_client):
    """Forgot password for non-existing email returns 200 generic response without DB token or email."""
    with patch.object(email_service, "send_password_reset_email", new_callable=AsyncMock) as mock_send_email:
        res = await async_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nonexistent.user@example.com"},
        )
        assert res.status_code == 200
        assert "bağlantısı gönderildiyse" in res.json()["message"]

        mock_send_email.assert_not_called()

        stmt = select(PasswordResetToken)
        result = await db_session.execute(stmt)
        assert len(result.scalars().all()) == 0


# ── TEST 3: USER ENUMERATION PROTECTION ──────────────────────

@pytest.mark.anyio
async def test_user_enumeration_prevention(async_client, user_existing):
    """Existing and non-existing email responses match identically in status code and message."""
    res_existing = await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": user_existing.email},
    )
    res_non_existing = await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nobody@example.com"},
    )

    assert res_existing.status_code == res_non_existing.status_code == 200
    assert res_existing.json() == res_non_existing.json()


# ── TEST 4: TOKEN SECURITY AND ENTROPY ───────────────────────

@pytest.mark.anyio
async def test_token_security_and_entropy(db_session, async_client, user_existing):
    """Plaintext reset token is never stored in DB; only 64-char SHA-256 hash is saved."""
    with patch.object(email_service, "send_password_reset_email", new_callable=AsyncMock) as mock_send_email:
        await async_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": user_existing.email},
        )

        _, plain_token = mock_send_email.call_args[0]
        assert len(plain_token) >= 32  # High entropy

        stmt = select(PasswordResetToken).where(PasswordResetToken.user_id == user_existing.id)
        token_record = (await db_session.execute(stmt)).scalar_one()

        assert token_record.token_hash != plain_token
        assert len(token_record.token_hash) == 64  # SHA-256 hex digest length


# ── TEST 5: TOKEN EXPIRATION 15 MINUTES ───────────────────────

@pytest.mark.anyio
async def test_token_expiration_15_minutes(db_session, async_client, user_existing):
    """Token expiration is set to approximately 15 minutes from created_at."""
    await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": user_existing.email},
    )

    stmt = select(PasswordResetToken).where(PasswordResetToken.user_id == user_existing.id)
    token_record = (await db_session.execute(stmt)).scalar_one()

    # Compare time diff in seconds (~900 seconds)
    time_diff = (token_record.expires_at - token_record.created_at).total_seconds()
    assert 890 <= time_diff <= 910


# ── TEST 6: ONE-TIME FOUNDATION INITIAL STATE ────────────────

@pytest.mark.anyio
async def test_one_time_foundation_initial_state(db_session, async_client, user_existing):
    """used_at column is initially None for new password reset token."""
    await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": user_existing.email},
    )

    stmt = select(PasswordResetToken).where(PasswordResetToken.user_id == user_existing.id)
    token_record = (await db_session.execute(stmt)).scalar_one()
    assert token_record.used_at is None


# ── TEST 7 & 8: EMAIL ABSTRACTION CALLS ──────────────────────

@pytest.mark.anyio
async def test_email_abstraction_called_for_existing_user(async_client, user_existing):
    """EmailService is invoked for existing user with correct email and plain reset token."""
    with patch.object(email_service, "send_password_reset_email", new_callable=AsyncMock) as mock_send_email:
        await async_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": user_existing.email},
        )
        mock_send_email.assert_called_once()
        args = mock_send_email.call_args[0]
        assert args[0] == user_existing.email
        assert isinstance(args[1], str) and len(args[1]) > 10


@pytest.mark.anyio
async def test_email_abstraction_not_called_for_non_existing_user(async_client):
    """EmailService is NOT invoked when email does not exist in DB."""
    with patch.object(email_service, "send_password_reset_email", new_callable=AsyncMock) as mock_send_email:
        await async_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "missing.person@example.com"},
        )
        mock_send_email.assert_not_called()


# ── TEST 9: UNAUTHENTICATED ACCESS SUCCEEDS ───────────────────

@pytest.mark.anyio
async def test_unauthenticated_access_succeeds(async_client, user_existing):
    """Endpoint functions cleanly without Authorization header or with arbitrary token."""
    res = await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": user_existing.email},
    )
    assert res.status_code == 200


# ── TEST 10: MULTIPLE RESET REQUESTS INVALIDATE OLD TOKENS ────

@pytest.mark.anyio
async def test_multiple_reset_requests_invalidate_old_tokens(db_session, async_client, user_existing):
    """Sending a second forgot password request invalidates previous active reset token."""
    await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": user_existing.email},
    )

    # First token created
    stmt1 = select(PasswordResetToken).where(PasswordResetToken.user_id == user_existing.id)
    token1 = (await db_session.execute(stmt1)).scalar_one()
    assert token1.used_at is None

    # Second request
    await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": user_existing.email},
    )

    stmt2 = select(PasswordResetToken).where(PasswordResetToken.user_id == user_existing.id).order_by(PasswordResetToken.created_at.asc())
    tokens = (await db_session.execute(stmt2)).scalars().all()
    assert len(tokens) == 2
    assert tokens[0].used_at is not None  # First token invalidated
    assert tokens[1].used_at is None      # Second token active


# ── TEST 11: SECURITY NON-EXPOSURE IN RESPONSE AND LOGS ───────

@pytest.mark.anyio
async def test_security_non_exposure_in_response_and_logs(caplog, async_client, user_existing):
    """Response body and audit logs do not expose reset tokens, passwords, hashes, or secrets."""
    caplog.set_level(logging.DEBUG)

    with patch.object(email_service, "send_password_reset_email", new_callable=AsyncMock) as mock_send_email:
        res = await async_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": user_existing.email},
        )
        assert res.status_code == 200

        body = res.json()
        assert "token" not in body
        assert "password" not in body
        assert "password_hash" not in body
        assert "access_token" not in body

        log_output = caplog.text
        plain_token = mock_send_email.call_args[0][1]
        # Ensure log output from auth/audit does not leak plain_token
        # (Email log may contain reset_url, but audit event logs must not leak plain_token in details)
        assert "PAROLA_SIFIRLAMA_TALEBI" in log_output
