"""
NeuroOncoTrack-AI — Real Infrastructure Integration Tests

Tests ORM persistence against live PostgreSQL 16 database
and live Redis 7 client (Docker container services).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from redis.asyncio import Redis

from app.core import security, redis as redis_core
from app.models.organization import Organization
from app.models.user import User
from app.models.session import Session
from app.models.password_history import PasswordHistory

POSTGRES_TEST_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/neurooncotrack"
REDIS_TEST_URL = "redis://localhost:6379/0"


@pytest.fixture
async def pg_session():
    """Provides a live PostgreSQL database session for integration testing."""
    engine = create_async_engine(POSTGRES_TEST_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def real_redis():
    """Provides a live Redis client for integration testing."""
    r = Redis.from_url(REDIS_TEST_URL)
    yield r
    await r.aclose()


@pytest.mark.integration
@pytest.mark.anyio
async def test_real_postgres_user_and_organization_crud(pg_session: AsyncSession):
    # 1. Create Organization in real PostgreSQL
    unique_code = f"ORG_{uuid.uuid4().hex[:6].upper()}"
    org = Organization(
        name="Ankara Şehir Hastanesi",
        code=unique_code,
        settings={"mfa_required": True, "department": "Radiology"},
    )
    pg_session.add(org)
    await pg_session.commit()
    await pg_session.refresh(org)

    assert org.id is not None
    assert org.code == unique_code
    assert org.settings["mfa_required"] is True

    # 2. Create User in real PostgreSQL with ARRAY and JSONB
    user_email = f"doctor_{uuid.uuid4().hex[:6]}@example.com"
    pw_hash = security.hash_password("ComplexPass123!")

    user = User(
        organization_id=org.id,
        email=user_email,
        password_hash=pw_hash,
        first_name="Kemal",
        last_name="Öztürk",
        title="Doç. Dr.",
        role="PHYSICIAN",
        extra_permissions=["report:approve", "ai:override"],
        revoked_permissions=[],
        backup_codes=[security.hash_backup_code("CODE1234")],
    )
    pg_session.add(user)
    await pg_session.commit()
    await pg_session.refresh(user)

    assert user.id is not None
    assert user.email == user_email
    assert "report:approve" in user.extra_permissions
    assert security.verify_password("ComplexPass123!", user.password_hash) is True

    # 3. Create Session in real PostgreSQL
    now = datetime.now(timezone.utc)
    opaque_refresh = security.generate_refresh_token()
    refresh_hash = security.hash_token(opaque_refresh)

    sess = Session(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        ip_address="127.0.0.1",
        user_agent="pytest-integration-agent",
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
    )
    pg_session.add(sess)
    await pg_session.commit()
    await pg_session.refresh(sess)

    assert sess.id is not None
    assert sess.refresh_token_hash == refresh_hash
    assert sess.is_valid is True

    # 4. Create PasswordHistory entry in real PostgreSQL
    pw_hist = PasswordHistory(
        user_id=user.id,
        password_hash=user.password_hash,
        created_at=now,
    )
    pg_session.add(pw_hist)
    await pg_session.commit()
    await pg_session.refresh(pw_hist)

    assert pw_hist.id is not None
    assert pw_hist.user_id == user.id

    # Verify reuse detection against real PostgreSQL stored hashes
    result = await pg_session.execute(
        select(PasswordHistory.password_hash).where(PasswordHistory.user_id == user.id)
    )
    db_hashes = list(result.scalars().all())
    assert security.is_password_reused("ComplexPass123!", db_hashes) is True
    assert security.is_password_reused("DifferentPass123!", db_hashes) is False


@pytest.mark.integration
@pytest.mark.anyio
async def test_real_redis_blacklist_and_rate_limit(real_redis: Redis):
    test_jti = f"jti_{uuid.uuid4().hex}"
    test_ip = f"192.168.1.{uuid.uuid4().int % 250 + 1}"

    # Test Blacklist in real Redis
    assert await redis_core.is_token_blacklisted(real_redis, test_jti) is False
    await redis_core.blacklist_token(real_redis, test_jti, ttl_seconds=60)
    assert await redis_core.is_token_blacklisted(real_redis, test_jti) is True

    # Test Rate Limiting in real Redis
    allowed, count = await redis_core.check_rate_limit(real_redis, test_ip)
    assert allowed is True

    for i in range(5):
        new_count = await redis_core.increment_rate_limit(real_redis, test_ip)

    allowed_after, current_count = await redis_core.check_rate_limit(real_redis, test_ip)
    assert current_count == 5
    assert allowed_after is False  # 5 attempts reached

    # Clean up rate limit key
    await redis_core.reset_rate_limit(real_redis, test_ip)
    allowed_reset, count_reset = await redis_core.check_rate_limit(real_redis, test_ip)
    assert allowed_reset is True
    assert count_reset == 0
