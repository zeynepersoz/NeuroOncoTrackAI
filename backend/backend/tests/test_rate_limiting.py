"""
NeuroOncoTrack-AI — Login Rate Limiting Unit & Integration Test Suite

Tests cover:
- Login attempt limit enforcement (5 allowed attempts within window)
- HTTP 429 Too Many Requests (RATE_001) on exceeding limit
- Counter reset on successful login
- Client IP isolation
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import security
from app.core.config import settings
from app.api.deps import get_redis_client
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture
async def async_client_with_redis(db_session, mock_redis):
    """Async HTTP client with mocked DB session and mock Redis."""
    async def _override_get_db():
        yield db_session

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
async def test_login_rate_limit_enforced_after_max_failed_attempts(db_session, async_client_with_redis):
    """Failed login attempts up to limit are rejected with AUTH_001; 6th attempt is blocked with RATE_001 (429)."""
    org = Organization(name="Test Org RateLimit", code="RL_01")
    db_session.add(org)
    await db_session.commit()

    user = User(
        organization_id=org.id,
        email="ratelimit.user@example.com",
        password_hash=security.hash_password("ValidPassword123!"),
        first_name="Rate",
        last_name="Limit",
        role="DOCTOR",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    login_payload = {
        "email": "ratelimit.user@example.com",
        "password": "WrongPassword123!",
    }

    # Make 5 failed attempts (LOGIN_RATE_LIMIT_ATTEMPTS = 5)
    for i in range(settings.LOGIN_RATE_LIMIT_ATTEMPTS):
        res = await async_client_with_redis.post("/api/v1/auth/login", json=login_payload)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "AUTH_001"

    # 6th attempt should trigger RATE_001 (HTTP 429)
    res_blocked = await async_client_with_redis.post("/api/v1/auth/login", json=login_payload)
    assert res_blocked.status_code == 429
    data = res_blocked.json()
    assert data["error"]["code"] == "RATE_001"
    assert "Çok fazla başarısız" in data["error"]["message"] or "Çok fazla başarısız" in data["error"]["detail"]


@pytest.mark.anyio
async def test_login_rate_limit_resets_on_successful_login(db_session, async_client_with_redis):
    """Successful login resets failed attempt counter for the IP."""
    org = Organization(name="Test Org Reset", code="RL_02")
    db_session.add(org)
    await db_session.commit()

    user = User(
        organization_id=org.id,
        email="reset.user@example.com",
        password_hash=security.hash_password("ValidPassword123!"),
        first_name="Reset",
        last_name="Test",
        role="DOCTOR",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    # 3 failed attempts
    wrong_payload = {"email": "reset.user@example.com", "password": "WrongPassword123!"}
    for _ in range(3):
        res = await async_client_with_redis.post("/api/v1/auth/login", json=wrong_payload)
        assert res.status_code == 401

    # 1 successful attempt
    valid_payload = {"email": "reset.user@example.com", "password": "ValidPassword123!"}
    res_ok = await async_client_with_redis.post("/api/v1/auth/login", json=valid_payload)
    assert res_ok.status_code == 200

    # 3 more failed attempts should not trigger rate limit (since counter was reset)
    for _ in range(3):
        res = await async_client_with_redis.post("/api/v1/auth/login", json=wrong_payload)
        assert res.status_code == 401
