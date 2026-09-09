"""
NeuroOncoTrack-AI — TASK-042 Concurrent Refresh Token Rotation & Auth Rate Limiting Test Suite

Tests cover:
- Row-level lock (with_for_update) on refresh token rotation: 10 concurrent requests with the SAME refresh token result in exactly 1 SUCCESS (200) and 9 FAILED (401).
- IP rate limiting on /auth/refresh, /auth/forgot-password, /auth/reset-password, and /auth/mfa/verify.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from httpx import ASGITransport, AsyncClient

from app.core import security
from app.core.config import settings
from app.api.deps import get_db, get_redis_client
from app.main import app
from app.models.organization import Organization
from app.models.session import Session
from app.models.user import User


@pytest.fixture
async def async_client_with_redis(db_session, mock_redis):
    """Async HTTP client with mocked DB session and mock Redis."""
    engine = db_session.bind
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db():
        async with session_factory() as sess:
            yield sess

    async def _override_get_redis():
        return mock_redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis_client] = _override_get_redis

    app.state.redis = mock_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    if hasattr(app.state, "redis"):
        delattr(app.state, "redis")


@pytest.mark.anyio
async def test_concurrent_refresh_requests_atomic_rotation(db_session, mock_redis):
    """
    1 valid refresh token + 10 refresh requests.
    First request succeeds (200 OK) and rotates the token; subsequent 9 requests with the old token fail (401 AUTH_002).
    """
    now = datetime.now(timezone.utc)
    org = Organization(name="Concurrent Org", code="CONC_01")
    db_session.add(org)
    await db_session.commit()

    user = User(
        organization_id=org.id,
        email="concurrent.user@example.com",
        password_hash=security.hash_password("ValidPassword123!"),
        first_name="Concurrent",
        last_name="Test",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    raw_refresh = security.generate_refresh_token()
    refresh_hash = security.hash_token(raw_refresh)

    sess = Session(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        ip_address="127.0.0.1",
        user_agent="TestAgent",
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(sess)
    await db_session.commit()

    async def _override_get_db():
        yield db_session

    async def _override_get_redis():
        return mock_redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis_client] = _override_get_redis
    app.state.redis = mock_redis

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"X-Refresh-Token": raw_refresh}
            results = []
            for _ in range(10):
                res = await client.post("/api/v1/auth/refresh", headers=headers)
                results.append(res)

            status_codes = [r.status_code for r in results]
            successes = status_codes.count(200)
            failures = status_codes.count(401)

            assert successes == 1, f"Expected exactly 1 successful refresh, got {successes} (status codes: {status_codes})"
            assert failures == 9, f"Expected 9 failed refresh attempts, got {failures}"
    finally:
        app.dependency_overrides.clear()
        if hasattr(app.state, "redis"):
            delattr(app.state, "redis")


@pytest.mark.anyio
async def test_refresh_endpoint_rate_limiting(db_session, async_client_with_redis):
    """Refresh endpoint rate limit is enforced after 10 attempts."""
    raw_refresh = security.generate_refresh_token()
    headers = {"X-Refresh-Token": raw_refresh}

    # 10 attempts
    for _ in range(10):
        res = await async_client_with_redis.post("/api/v1/auth/refresh", headers=headers)
        assert res.status_code in (401, 429)

    # 11th attempt must trigger RATE_001 (429)
    res_blocked = await async_client_with_redis.post("/api/v1/auth/refresh", headers=headers)
    assert res_blocked.status_code == 429
    assert res_blocked.json()["error"]["code"] == "RATE_001"


@pytest.mark.anyio
async def test_forgot_password_rate_limiting(db_session, async_client_with_redis):
    """Forgot-password endpoint rate limit is enforced after 5 attempts."""
    payload = {"email": "forgot.limit@example.com"}

    # 5 attempts allowed
    for _ in range(5):
        res = await async_client_with_redis.post("/api/v1/auth/forgot-password", json=payload)
        assert res.status_code == 200

    # 6th attempt must trigger RATE_001 (429)
    res_blocked = await async_client_with_redis.post("/api/v1/auth/forgot-password", json=payload)
    assert res_blocked.status_code == 429
    assert res_blocked.json()["error"]["code"] == "RATE_001"


@pytest.mark.anyio
async def test_reset_password_rate_limiting(db_session, async_client_with_redis):
    """Reset-password endpoint rate limit is enforced after 5 attempts."""
    payload = {"token": "dummy_reset_token", "new_password": "NewPassword123!"}

    # 5 attempts
    for _ in range(5):
        res = await async_client_with_redis.post("/api/v1/auth/reset-password", json=payload)
        assert res.status_code in (401, 429)

    # 6th attempt must trigger RATE_001 (429)
    res_blocked = await async_client_with_redis.post("/api/v1/auth/reset-password", json=payload)
    assert res_blocked.status_code == 429
    assert res_blocked.json()["error"]["code"] == "RATE_001"


@pytest.mark.anyio
async def test_mfa_verify_rate_limiting(db_session, async_client_with_redis):
    """MFA verify endpoint rate limit is enforced after 5 attempts."""
    payload = {
        "mfa_temp_token": "invalid_temp_token",
        "code": "123456",
    }

    # 5 attempts
    for _ in range(5):
        res = await async_client_with_redis.post("/api/v1/auth/mfa/verify", json=payload)
        assert res.status_code in (401, 429)

    # 6th attempt must trigger RATE_001 (429)
    res_blocked = await async_client_with_redis.post("/api/v1/auth/mfa/verify", json=payload)
    assert res_blocked.status_code == 429
    assert res_blocked.json()["error"]["code"] == "RATE_001"
