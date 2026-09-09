"""
NeuroOncoTrack-AI — Model Unit Tests

Tests for app.models (Organization, User, Session, PasswordHistory):
  - Entity creation & persistence
  - Required fields & defaults
  - Relationships (Organization -> User -> Sessions / PasswordHistory)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.organization import Organization
from app.models.password_history import PasswordHistory
from app.models.session import Session
from app.models.user import User


@pytest.mark.anyio
async def test_organization_creation(db_session):
    org = Organization(
        name="Ankara Hastanesi",
        code="ANK_01",
        description="Eğitim ve Araştırma Hastanesi",
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    assert org.id is not None
    assert isinstance(org.id, uuid.UUID)
    assert org.name == "Ankara Hastanesi"
    assert org.code == "ANK_01"
    assert org.is_active is True  # Default value
    assert org.created_at is not None
    assert org.updated_at is not None


@pytest.mark.anyio
async def test_user_creation_and_defaults(db_session):
    org = Organization(name="İstanbul Hastanesi", code="IST_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    user = User(
        organization_id=org.id,
        email="dr.ahmet@example.com",
        password_hash="argon2id_hash_sample",
        first_name="Ahmet",
        last_name="Yılmaz",
        title="Prof. Dr.",
        role="PHYSICIAN",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert isinstance(user.id, uuid.UUID)
    assert user.organization_id == org.id
    assert user.email == "dr.ahmet@example.com"
    assert user.full_name == "Ahmet Yılmaz"
    assert user.role == "PHYSICIAN"
    assert user.is_active is True  # Default
    assert user.is_locked is False  # Default
    assert user.failed_login_attempts == 0  # Default
    assert user.mfa_enabled is False  # Default
    assert user.must_change_password is True  # Default
    assert user.is_effectively_locked is False


@pytest.mark.anyio
async def test_session_creation_and_user_relationship(db_session):
    org = Organization(name="İzmir Hastanesi", code="IZM_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    user = User(
        organization_id=org.id,
        email="tech.mehmet@example.com",
        password_hash="hash_sample",
        first_name="Mehmet",
        last_name="Kaya",
        role="RADIOLOGY_TECH",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    now = datetime.now(timezone.utc)
    expires = now + timedelta_days(7)

    session_rec = Session(
        user_id=user.id,
        refresh_token_hash="sha256_hash_of_opaque_refresh_token",
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0",
        created_at=now,
        last_used_at=now,
        expires_at=expires,
    )
    db_session.add(session_rec)
    await db_session.commit()
    await db_session.refresh(session_rec)

    assert session_rec.id is not None
    assert session_rec.user_id == user.id
    assert session_rec.is_revoked is False
    assert session_rec.is_valid is True

    # Check relationship via Session query
    target_user_id = user.id
    result = await db_session.execute(
        select(Session).where(Session.user_id == target_user_id)
    )
    fetched_sessions = result.scalars().all()
    assert len(fetched_sessions) == 1
    assert fetched_sessions[0].refresh_token_hash == "sha256_hash_of_opaque_refresh_token"


@pytest.mark.anyio
async def test_password_history_creation(db_session):
    org = Organization(name="Bursa Hastanesi", code="BUR_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    user = User(
        organization_id=org.id,
        email="admin.ayse@example.com",
        password_hash="hash_v1",
        first_name="Ayşe",
        last_name="Demir",
        role="HOSPITAL_ADMIN",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    now = datetime.now(timezone.utc)
    pw_hist = PasswordHistory(
        user_id=user.id,
        password_hash="hash_v1",
        created_at=now,
    )
    db_session.add(pw_hist)
    await db_session.commit()
    await db_session.refresh(pw_hist)

    assert pw_hist.id is not None
    assert pw_hist.user_id == user.id
    assert pw_hist.password_hash == "hash_v1"


def timedelta_days(days: int):
    from datetime import timedelta
    return timedelta(days=days)
