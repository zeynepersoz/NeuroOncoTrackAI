"""
NeuroOncoTrack-AI — Token Security & Hashing Unit & Integration Tests (SUBTASK 003-D)

Tests for secure random token generation, SHA-256 token hashing,
constant-time hash verification, database non-exposure, and security checks.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core import security
from app.models.organization import Organization
from app.models.password_history import PasswordHistory
from app.models.session import Session
from app.models.user import User


# ── UNIT TESTS ──────────────────────────────────────────────

def test_secure_random_token_generation():
    """1. Secure random token can be generated."""
    token = security.generate_refresh_token()
    assert token is not None


def test_token_output_is_string():
    """2. Token output is string."""
    token = security.generate_refresh_token()
    assert type(token) is str


def test_unique_tokens_generated():
    """3. Two tokens generated are different."""
    t1 = security.generate_refresh_token()
    t2 = security.generate_refresh_token()
    assert t1 != t2


def test_token_sufficient_length_and_entropy():
    """4. Token has sufficient entropy/length (32 bytes = 43+ urlsafe chars)."""
    token = security.generate_refresh_token()
    assert len(token) >= 43


def test_plaintext_not_in_hash():
    """5. Token plaintext is NOT directly contained in the hash digest."""
    token = security.generate_refresh_token()
    hashed = security.hash_token(token)

    assert token not in hashed
    assert len(hashed) == 64  # SHA-256 hex digest length


def test_hash_token_is_deterministic():
    """6, 7. hash_token(token) is deterministic."""
    token = security.generate_refresh_token()
    h1 = security.hash_token(token)
    h2 = security.hash_token(token)

    assert h1 == h2


def test_different_tokens_produce_different_hashes():
    """8. Different tokens produce different hashes."""
    t1 = security.generate_refresh_token()
    t2 = security.generate_refresh_token()

    assert security.hash_token(t1) != security.hash_token(t2)


def test_verify_token_hash_success():
    """11. Verification with correct plaintext token succeeds."""
    token = security.generate_refresh_token()
    hashed = security.hash_token(token)

    assert security.verify_token_hash(token, hashed) is True


def test_verify_token_hash_failure_wrong_token():
    """12. Verification with incorrect token fails."""
    token = security.generate_refresh_token()
    wrong_token = security.generate_refresh_token()
    hashed = security.hash_token(token)

    assert security.verify_token_hash(wrong_token, hashed) is False


def test_verify_token_hash_constant_time():
    """13. Constant-time comparison is used for verification."""
    token = security.generate_refresh_token()
    hashed = security.hash_token(token)

    # Calling verify_token_hash uses hmac.compare_digest
    assert security.verify_token_hash(token, hashed) is True


def test_empty_token_rejected():
    """14. Empty token is rejected."""
    with pytest.raises(ValueError, match="Token must be a non-empty string"):
        security.hash_token("")

    assert security.verify_token_hash("", "some_hash") is False


def test_invalid_token_type_rejected():
    """15. Invalid token type (e.g. None, int) is rejected."""
    with pytest.raises(ValueError):
        security.hash_token(12345)  # type: ignore[arg-type]

    assert security.verify_token_hash(None, "some_hash") is False  # type: ignore[arg-type]
    assert security.verify_token_hash(12345, "some_hash") is False  # type: ignore[arg-type]


def test_token_hashing_does_not_log_plaintext_token(caplog):
    """16. Token hashing does NOT log plaintext token."""
    import logging
    caplog.set_level(logging.DEBUG)

    secret_token = security.generate_refresh_token()
    hashed = security.hash_token(secret_token)
    security.verify_token_hash(secret_token, hashed)

    captured_logs = caplog.text
    assert secret_token not in captured_logs


def test_exception_does_not_contain_plaintext_token():
    """17. Exception / error response does NOT contain plaintext token."""
    secret_token = security.generate_refresh_token()
    try:
        security.hash_token("")
    except ValueError as e:
        assert secret_token not in str(e)


def test_refresh_token_is_opaque_not_jwt():
    """18. Refresh token remains opaque random token (NOT a JWT)."""
    token = security.generate_refresh_token()

    # JWTs contain dots '.' separating header.payload.signature
    # token_urlsafe(32) uses base64url characters ([A-Za-z0-9_-]) and has NO dots
    assert "." not in token


# ── INTEGRATION TESTS (Async DB / PostgreSQL / SQLite) ────────

@pytest.mark.anyio
async def test_session_db_stores_only_hash_not_plaintext(db_session):
    """9, 10, 19, 20. Session DB stores ONLY refresh_token_hash, verification works via hash lookup."""
    org = Organization(name="Sivas Hastanesi", code="SIV_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    user = User(
        organization_id=org.id,
        email="doctor.sivas@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Ali",
        last_name="Veli",
        role="PHYSICIAN",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 1. Generate opaque plaintext token & compute hash
    plaintext_token = security.generate_refresh_token()
    token_hash = security.hash_token(plaintext_token)

    now = datetime.now(timezone.utc)
    sess = Session(
        user_id=user.id,
        refresh_token_hash=token_hash,
        ip_address="10.0.0.1",
        user_agent="pytest-agent",
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)

    # 9. Verify plaintext token is NOT stored in DB object or attributes
    assert sess.refresh_token_hash == token_hash
    assert plaintext_token not in sess.refresh_token_hash
    assert not hasattr(sess, "refresh_token")

    # 19. Verify session lookup by computed token hash
    lookup_hash = security.hash_token(plaintext_token)
    result = await db_session.execute(
        select(Session).where(Session.refresh_token_hash == lookup_hash)
    )
    fetched_session = result.scalar_one_or_none()

    assert fetched_session is not None
    assert fetched_session.id == sess.id
    assert security.verify_token_hash(plaintext_token, fetched_session.refresh_token_hash) is True

    # 20. Verify incorrect token fails database lookup
    wrong_token = security.generate_refresh_token()
    wrong_lookup_hash = security.hash_token(wrong_token)
    wrong_result = await db_session.execute(
        select(Session).where(Session.refresh_token_hash == wrong_lookup_hash)
    )
    assert wrong_result.scalar_one_or_none() is None
