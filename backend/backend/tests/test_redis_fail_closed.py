"""
NeuroOncoTrack-AI — TASK-038 Redis Fail-Closed Security & DB Fallback Test Suite

Comprehensive test suite verifying the 10 scenarios from the TASK-038 Scenario Matrix:
1. Redis UP + Normal Token + Active DB User -> ALLOW
2. Redis UP + Blacklisted Token (JTI in Redis) -> DENY (401)
3. Redis UP + User Blacklist (bl:user:{id} in Redis) -> DENY (401)
4. Redis DOWN + Normal Token (Active DB Session) -> ALLOW (via DB Fallback)
5. Redis DOWN + Previously Blacklisted Token (DB Session Revoked) -> DENY (via DB Fallback)
6. Redis DOWN + Force-Logout Access Token -> DENY (via DB Fallback)
7. Redis DOWN + Refresh Token on Revoked Session -> DENY (via DB Session)
8. Redis UP + Expired JWT -> DENY (401)
9. Redis UP + Revoked Session -> DENY (401)
10. Redis DOWN + Invalid JWT -> DENY (401)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import security
from app.core.config import settings
from app.core.permissions import Role
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
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
async def org_fc(db_session):
    """Fixture for test Organization."""
    org = Organization(
        id=uuid.uuid4(),
        name="Fail Closed Hospital",
        code="FC_HOSP_" + uuid.uuid4().hex[:6].upper(),
        org_type="HOSPITAL",
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def admin_fc(db_session, org_fc):
    """Fixture for active admin user."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_fc.id,
        email=f"admin_fc_{uuid.uuid4().hex[:6]}@fc.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Admin",
        last_name="FailClosed",
        role=Role.SUPER_ADMIN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


class TestRedisFailClosedSecurity:
    """Task-038 Redis Fail-Closed & Hybrid DB Fallback Matrix Test Suite."""

    @pytest.mark.anyio
    async def test_scenario_1_redis_up_normal_token_allow(self, async_client: AsyncClient, admin_fc):
        """Scenario 1: Redis UP + Normal Token + Active User -> ALLOW (200 OK)."""
        token, _, _ = security.create_access_token(
            subject=str(admin_fc.id),
            role=admin_fc.role,
            organization_id=str(admin_fc.organization_id),
            permissions=["*"],
        )
        headers = {"Authorization": f"Bearer {token}"}
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 200

    @pytest.mark.anyio
    async def test_scenario_2_redis_up_blacklisted_jti_deny(self, async_client: AsyncClient, admin_fc):
        """Scenario 2: Redis UP + Blacklisted JTI -> DENY (401 AUTH_002)."""
        token, jti, _ = security.create_access_token(
            subject=str(admin_fc.id),
            role=admin_fc.role,
            organization_id=str(admin_fc.organization_id),
            permissions=["*"],
        )

        mock_redis = AsyncMock()

        async def _exists(key):
            if key == f"bl:jti:{jti}":
                return True
            return False

        mock_redis.exists = AsyncMock(side_effect=_exists)
        app.state.redis = mock_redis

        try:
            headers = {"Authorization": f"Bearer {token}"}
            res = await async_client.get("/api/v1/admin/users", headers=headers)
            assert res.status_code == 401
            assert res.json()["error"]["code"] == "AUTH_002"
        finally:
            app.state.redis = None

    @pytest.mark.anyio
    async def test_scenario_3_redis_up_user_blacklist_deny(self, async_client: AsyncClient, admin_fc):
        """Scenario 3: Redis UP + User Blacklist (bl:user:{id}) -> DENY (401 AUTH_002)."""
        token, _, _ = security.create_access_token(
            subject=str(admin_fc.id),
            role=admin_fc.role,
            organization_id=str(admin_fc.organization_id),
            permissions=["*"],
        )

        mock_redis = AsyncMock()

        async def _exists(key):
            if key == f"bl:user:{admin_fc.id}":
                return True
            return False

        mock_redis.exists = AsyncMock(side_effect=_exists)
        app.state.redis = mock_redis

        try:
            headers = {"Authorization": f"Bearer {token}"}
            res = await async_client.get("/api/v1/admin/users", headers=headers)
            assert res.status_code == 401
            assert res.json()["error"]["code"] == "AUTH_002"
        finally:
            app.state.redis = None

    @pytest.mark.anyio
    async def test_scenario_4_redis_down_normal_token_allow_db_fallback(self, async_client: AsyncClient, admin_fc):
        """Scenario 4: Redis DOWN + Normal Token -> ALLOW (200 OK via DB Fallback)."""
        app.state.redis = None  # Simulating Redis connection failure / outage

        token, _, _ = security.create_access_token(
            subject=str(admin_fc.id),
            role=admin_fc.role,
            organization_id=str(admin_fc.organization_id),
            permissions=["*"],
        )

        headers = {"Authorization": f"Bearer {token}"}
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 200

    @pytest.mark.anyio
    async def test_scenario_5_and_6_redis_down_force_logout_deny_db_fallback(
        self, db_session, async_client: AsyncClient, admin_fc
    ):
        """Scenario 5 & 6: Redis DOWN + Force-Logged-Out Access Token -> DENY (401 AUTH_002 via DB Fallback)."""
        # Issue token at t0
        now = datetime.now(timezone.utc)
        token, _, _ = security.create_access_token(
            subject=str(admin_fc.id),
            role=admin_fc.role,
            organization_id=str(admin_fc.organization_id),
            permissions=["*"],
        )

        # Force logout at t1 (now + 2 seconds), creating DB session revocation
        rev_time = now + timedelta(seconds=2)
        sess = Session(
            id=uuid.uuid4(),
            user_id=admin_fc.id,
            refresh_token_hash=security.hash_token("dummy_refresh"),
            ip_address="127.0.0.1",
            user_agent="TestAgent",
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=1),
            revoked_at=rev_time,
            revocation_reason="FORCE_LOGOUT",
        )
        db_session.add(sess)
        await db_session.commit()

        # Simulate Redis outage
        app.state.redis = None

        headers = {"Authorization": f"Bearer {token}"}
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "AUTH_002"

    @pytest.mark.anyio
    async def test_scenario_7_redis_down_refresh_token_revoked_session_deny(
        self, db_session, async_client: AsyncClient, admin_fc
    ):
        """Scenario 7: Redis DOWN + Refresh Token on Revoked Session -> DENY (401)."""
        now = datetime.now(timezone.utc)
        raw_refresh = security.generate_refresh_token()
        refresh_hash = security.hash_token(raw_refresh)

        sess = Session(
            id=uuid.uuid4(),
            user_id=admin_fc.id,
            refresh_token_hash=refresh_hash,
            ip_address="127.0.0.1",
            user_agent="TestAgent",
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=1),
            revoked_at=now,
            revocation_reason="LOGGED_OUT",
        )
        db_session.add(sess)
        await db_session.commit()

        app.state.redis = None

        res = await async_client.post(
            "/api/v1/auth/refresh",
            headers={"X-Refresh-Token": raw_refresh},
        )
        assert res.status_code == 401

    @pytest.mark.anyio
    async def test_scenario_8_redis_up_expired_jwt_deny(self, async_client: AsyncClient, admin_fc):
        """Scenario 8: Redis UP + Expired JWT -> DENY (401)."""
        token, _, _ = security.create_access_token(
            subject=str(admin_fc.id),
            role=admin_fc.role,
            organization_id=str(admin_fc.organization_id),
            permissions=["*"],
            extra_claims={"exp": datetime.now(timezone.utc) - timedelta(seconds=10)},
        )
        headers = {"Authorization": f"Bearer {token}"}
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "AUTH_002"

    @pytest.mark.anyio
    async def test_scenario_9_redis_up_revoked_session_deny(self, db_session, async_client: AsyncClient, admin_fc):
        """Scenario 9: Redis UP + Revoked Session -> DENY (401)."""
        now = datetime.now(timezone.utc)
        token, _, _ = security.create_access_token(
            subject=str(admin_fc.id),
            role=admin_fc.role,
            organization_id=str(admin_fc.organization_id),
            permissions=["*"],
        )

        sess = Session(
            id=uuid.uuid4(),
            user_id=admin_fc.id,
            refresh_token_hash=security.hash_token("dummy_token"),
            ip_address="127.0.0.1",
            user_agent="TestAgent",
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=1),
            revoked_at=now + timedelta(seconds=1),
            revocation_reason="ADMIN_TERMINATED_ALL",
        )
        db_session.add(sess)
        await db_session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "AUTH_002"

    @pytest.mark.anyio
    async def test_scenario_10_redis_down_invalid_jwt_deny(self, async_client: AsyncClient):
        """Scenario 10: Redis DOWN + Invalid JWT -> DENY (401)."""
        app.state.redis = None
        headers = {"Authorization": "Bearer malformed.invalid.jwt"}
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "AUTH_002"

    @pytest.mark.anyio
    async def test_scenario_d_single_token_logout_redis_down_deny(
        self, db_session, async_client: AsyncClient, admin_fc
    ):
        """Task-040 Scenario D: /logout with single token -> Redis DOWN -> Access Token DENIED (401 AUTH_002)."""
        now = datetime.now(timezone.utc)
        sess_id = uuid.uuid4()
        raw_refresh = security.generate_refresh_token()
        refresh_hash = security.hash_token(raw_refresh)

        # Active DB session
        sess = Session(
            id=sess_id,
            user_id=admin_fc.id,
            refresh_token_hash=refresh_hash,
            ip_address="127.0.0.1",
            user_agent="TestAgent",
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=1),
        )
        db_session.add(sess)
        await db_session.commit()

        # Create Access token linked to sid
        token, jti, _ = security.create_access_token(
            subject=str(admin_fc.id),
            role=admin_fc.role,
            organization_id=str(admin_fc.organization_id),
            permissions=["*"],
            extra_claims={"sid": str(sess_id)},
        )

        # Call /logout with cookie & bearer token
        async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, raw_refresh)
        headers = {"Authorization": f"Bearer {token}"}
        logout_res = await async_client.post("/api/v1/auth/logout", headers=headers)
        assert logout_res.status_code == 204

        # Simulate Redis outage after logout
        app.state.redis = None

        # Re-request with same access token during Redis outage
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "AUTH_002"

    @pytest.mark.anyio
    async def test_scenario_g_multi_session_isolation_redis_down(
        self, db_session, async_client: AsyncClient, admin_fc
    ):
        """Task-040 Scenario G: Session A logout, Redis DOWN -> Session B token still ALLOWED (200 OK)."""
        now = datetime.now(timezone.utc)

        # Session A
        sess_a_id = uuid.uuid4()
        sess_a = Session(
            id=sess_a_id,
            user_id=admin_fc.id,
            refresh_token_hash=security.hash_token("refresh_a"),
            ip_address="127.0.0.1",
            user_agent="Device A",
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=1),
            revoked_at=now,
            revocation_reason="LOGOUT",
        )
        db_session.add(sess_a)

        # Session B
        sess_b_id = uuid.uuid4()
        sess_b = Session(
            id=sess_b_id,
            user_id=admin_fc.id,
            refresh_token_hash=security.hash_token("refresh_b"),
            ip_address="127.0.0.2",
            user_agent="Device B",
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=1),
            revoked_at=None,
        )
        db_session.add(sess_b)
        await db_session.commit()

        # Session B access token
        token_b, _, _ = security.create_access_token(
            subject=str(admin_fc.id),
            role=admin_fc.role,
            organization_id=str(admin_fc.organization_id),
            permissions=["*"],
            extra_claims={"sid": str(sess_b_id)},
        )

        # Redis is DOWN
        app.state.redis = None

        headers_b = {"Authorization": f"Bearer {token_b}"}
        res_b = await async_client.get("/api/v1/admin/users", headers=headers_b)
        assert res_b.status_code == 200

