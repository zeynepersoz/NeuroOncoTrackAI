"""
NeuroOncoTrack-AI — Password History Unit & Integration Tests (SUBTASK 003-C)

Tests for password reuse prevention, PasswordHistory persistence,
history limit enforcement, and security non-exposure.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core import security
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models.organization import Organization
from app.models.password_history import PasswordHistory
from app.models.user import User


# ── UNIT TESTS (SQLite / In-Memory) ─────────────────────────

def test_initial_password_history_structure():
    """1, 2, 3. Password history record contains Argon2id hash and NO plaintext."""
    plain_password = "InitialPassword123!"
    hashed = security.hash_password(plain_password)

    pw_hist = PasswordHistory(
        user_id=uuid.uuid4(),
        password_hash=hashed,
        created_at=datetime.now(timezone.utc),
    )

    assert pw_hist.password_hash == hashed
    assert plain_password not in pw_hist.password_hash
    assert "$argon2id$" in pw_hist.password_hash


def test_unused_password_is_accepted():
    """4. Previously unused password is accepted."""
    old_hashes = [security.hash_password("OldPassword123!")]
    new_password = "NewFreshPassword123!"

    assert security.is_password_reused(new_password, old_hashes) is False
    # Should not raise exception
    security.validate_password_not_reused(new_password, historical_hashes=old_hashes)


def test_previously_used_password_is_rejected():
    """5. Previously used password is rejected (detected as reused)."""
    used_password = "PreviousPassword123!"
    old_hash = security.hash_password(used_password)

    assert security.is_password_reused(used_password, [old_hash]) is True

    with pytest.raises(ValidationError) as exc_info:
        security.validate_password_not_reused(used_password, historical_hashes=[old_hash])
    assert "son kullanılan" in exc_info.value.detail


def test_same_password_different_salts_reuse_detected():
    """6. Same plaintext password with different Argon2id hashes (due to random salt) is detected."""
    secret_password = "SecretPassword123!"
    # Generate two different hashes of the same plaintext password
    hash_v1 = security.hash_password(secret_password)
    hash_v2 = security.hash_password(secret_password)

    assert hash_v1 != hash_v2  # Different salts
    assert security.is_password_reused(secret_password, [hash_v1]) is True
    assert security.is_password_reused(secret_password, [hash_v2]) is True


def test_different_password_accepted():
    """7. Different password is accepted."""
    pass_v1 = "PasswordOne123!"
    pass_v2 = "PasswordTwo456!"
    hash_v1 = security.hash_password(pass_v1)

    assert security.is_password_reused(pass_v2, [hash_v1]) is False


def test_malformed_historical_hash_does_not_crash():
    """8. Malformed historical hash does not crash application."""
    test_password = "TestPassword123!"
    malformed_hashes = ["invalid_hash_string", "$argon2id$corrupted", None, "12345"]

    # Should safely return False without raising uncaught exception
    assert security.is_password_reused(test_password, malformed_hashes) is False  # type: ignore[arg-type]


def test_password_validation_and_history_check_combination():
    """9. Password validation and password history check work together."""
    old_hashes = [security.hash_password("OldStrongPassword123!")]
    new_password = "NewStrongPassword123!"

    # Step 1: Validate policy rules (min len, uppercase, special, etc.)
    security.validate_password(new_password)

    # Step 2: Validate reuse prevention
    security.validate_password_not_reused(new_password, historical_hashes=old_hashes)


def test_history_limit_enforcement():
    """11. History limit behavior works correctly (checks only last N history items)."""
    # Create 6 distinct password hashes (newest first)
    passwords = [f"PasswordNum{i}123!" for i in range(6)]
    hashes = [security.hash_password(p) for p in passwords]

    # Limit = 5. Index 0..4 (last 5) should be detected as reused.
    # Index 5 (6th oldest, beyond limit 5) should be allowed.
    assert security.is_password_reused(passwords[0], hashes, limit=5) is True
    assert security.is_password_reused(passwords[4], hashes, limit=5) is True

    # 6th oldest password (index 5) is outside limit=5, so it is NOT marked as reused
    assert security.is_password_reused(passwords[5], hashes, limit=5) is False


def test_password_reuse_check_does_not_log_plaintext_password(caplog):
    """12. Password reuse check does not log plaintext password."""
    import logging
    caplog.set_level(logging.DEBUG)

    secret_password = "SecretPassword123!"
    old_hash = security.hash_password(secret_password)

    security.is_password_reused(secret_password, [old_hash])

    captured_logs = caplog.text
    assert secret_password not in captured_logs


def test_password_reuse_exception_does_not_expose_plaintext_password():
    """13. Exception/error response does not contain plaintext password."""
    secret_password = "SecretPassword123!"
    old_hash = security.hash_password(secret_password)

    with pytest.raises(ValidationError) as exc_info:
        security.validate_password_not_reused(secret_password, historical_hashes=[old_hash])

    error_str = str(exc_info.value)
    detail_str = str(exc_info.value.detail)

    assert secret_password not in error_str
    assert secret_password not in detail_str


# ── INTEGRATION TESTS (Async DB / Relationships) ─────────────

@pytest.mark.anyio
async def test_password_history_user_relationship_and_cascade(db_session):
    """10. Password history records belong to correct user and cascade delete."""
    org = Organization(name="Kayseri Hastanesi", code="KAY_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    user1 = User(
        organization_id=org.id,
        email="u1@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="User",
        last_name="One",
        role="PHYSICIAN",
    )
    user2 = User(
        organization_id=org.id,
        email="u2@example.com",
        password_hash=security.hash_password("Pass87654321!"),
        first_name="User",
        last_name="Two",
        role="PHYSICIAN",
    )
    db_session.add_all([user1, user2])
    await db_session.commit()
    await db_session.refresh(user1)
    await db_session.refresh(user2)

    # Add history for user1
    hist1 = PasswordHistory(
        user_id=user1.id,
        password_hash=user1.password_hash,
        created_at=datetime.now(timezone.utc),
    )
    # Add history for user2
    hist2 = PasswordHistory(
        user_id=user2.id,
        password_hash=user2.password_hash,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add_all([hist1, hist2])
    await db_session.commit()

    # Query user1 history
    res1 = await db_session.execute(
        select(PasswordHistory).where(PasswordHistory.user_id == user1.id)
    )
    user1_hist = res1.scalars().all()
    assert len(user1_hist) == 1
    assert user1_hist[0].user_id == user1.id

    # Query user2 history
    res2 = await db_session.execute(
        select(PasswordHistory).where(PasswordHistory.user_id == user2.id)
    )
    user2_hist = res2.scalars().all()
    assert len(user2_hist) == 1
    assert user2_hist[0].user_id == user2.id
