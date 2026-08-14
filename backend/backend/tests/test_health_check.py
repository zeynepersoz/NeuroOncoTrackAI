"""
NeuroOncoTrack-AI — Health Check & Readiness Probe Test Suite

Tests cover:
- /health readiness probe when all components (DB & Redis) are healthy (HTTP 200, status: healthy)
- /health degraded mode when Redis is unreachable (HTTP 200, status: degraded)
- /health unhealthy mode when DB is unreachable (HTTP 503, status: unhealthy)
- /health/liveness fast liveness probe (HTTP 200, status: alive)
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_redis_client
from app.db.session import get_db
from app.main import app


@pytest.fixture
async def health_client(db_session, mock_redis):
    """HTTP client with DB session and mock Redis."""
    async def _override_get_db():
        yield db_session

    async def _override_get_redis():
        return mock_redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis_client] = _override_get_redis

    # Add ping method to mock_redis if needed
    if not hasattr(mock_redis, "ping"):
        async def _ping():
            return True
        mock_redis.ping = _ping

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_health_check_healthy_when_db_and_redis_up(health_client):
    """When DB and Redis respond successfully, returns HTTP 200 with status='healthy'."""
    res = await health_client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "components" in data
    assert data["components"]["database"]["status"] == "up"
    assert "latency_ms" in data["components"]["database"]
    assert data["components"]["redis"]["status"] == "up"
    assert "latency_ms" in data["components"]["redis"]


@pytest.mark.anyio
async def test_health_check_degraded_when_redis_fails(db_session):
    """When DB is up but Redis raises an error on ping, returns HTTP 200 with status='degraded'."""
    class FailingRedis:
        async def ping(self):
            raise Exception("Redis connection refused")

    async def _override_get_db():
        yield db_session

    async def _override_failing_redis():
        return FailingRedis()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis_client] = _override_failing_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "degraded"
        assert data["components"]["database"]["status"] == "up"
        assert data["components"]["redis"]["status"] == "down"
        assert "error" in data["components"]["redis"]

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_health_check_unhealthy_when_db_fails(mock_redis):
    """When DB connection/query fails, returns HTTP 503 Service Unavailable with status='unhealthy'."""
    class FailingDB:
        async def execute(self, query):
            raise Exception("Database connection lost")

    async def _override_failing_db():
        yield FailingDB()

    async def _override_redis():
        return mock_redis

    if not hasattr(mock_redis, "ping"):
        async def _ping():
            return True
        mock_redis.ping = _ping

    app.dependency_overrides[get_db] = _override_failing_db
    app.dependency_overrides[get_redis_client] = _override_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "unhealthy"
        assert data["components"]["database"]["status"] == "down"
        assert "Database connection lost" in data["components"]["database"]["error"]

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_liveness_check_returns_alive(health_client):
    """Fast liveness probe endpoint returns 200 OK with status='alive'."""
    res = await health_client.get("/health/liveness")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "alive"
