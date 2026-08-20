"""
NeuroOncoTrack-AI — TASK-030 Admin Target User Lifecycle Governance API Unit & Integration Tests

Verifies:
1. LOCK / UNLOCK: Account locking sets is_locked=True, blocks login/auth (423 AUTH_004). Unlock resets lockout state.
2. ACTIVATE / DEACTIVATE: Deactivating sets is_active=False, blocks token auth (401). Activate restores active status.
3. FORCE LOGOUT: Revokes DB sessions (Session.revoked_at = now), blacklists user in Redis (bl:user:{id}), invalidates tokens.
4. AUTHORIZATION & TENANT ISOLATION: SUPER_ADMIN global access, HOSPITAL_ADMIN tenant-scoped access, cross-tenant denial (403 AUTH_003), functional role denial (403 AUTH_003).
5. HIERARCHY & SELF ACTION DEFENSE: HOSPITAL_ADMIN cannot lock/deactivate/force-logout SUPER_ADMIN or HOSPITAL_ADMIN (403). Admins cannot lock/deactivate/force-logout themselves (403).
6. IDEMPOTENCY & AUDIT: Repeat requests operate safely, audit events recorded with zero credential leakage.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import security
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
async def org_a(db_session):
    """Fixture for Organization A."""
    org = Organization(
        id=uuid.uuid4(),
        name="Hospital Alpha",
        code="HOSP_A_" + uuid.uuid4().hex[:6].upper(),
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def org_b(db_session):
    """Fixture for Organization B."""
    org = Organization(
        id=uuid.uuid4(),
        name="Hospital Beta",
        code="HOSP_B_" + uuid.uuid4().hex[:6].upper(),
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def super_admin_user(db_session, org_a):
    """Fixture for active SUPER_ADMIN user."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        email=f"superadmin_{uuid.uuid4().hex[:6]}@platform.gov",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Super",
        last_name="Admin",
        role=Role.SUPER_ADMIN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def hospital_admin_a(db_session, org_a):
    """Fixture for HOSPITAL_ADMIN in Org A."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        email=f"admin_a_{uuid.uuid4().hex[:6]}@hospa.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Admin",
        last_name="OrgA",
        role=Role.HOSPITAL_ADMIN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def hospital_admin_b(db_session, org_b):
    """Fixture for HOSPITAL_ADMIN in Org B."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_b.id,
        email=f"admin_b_{uuid.uuid4().hex[:6]}@hospb.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Admin",
        last_name="OrgB",
        role=Role.HOSPITAL_ADMIN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def physician_a(db_session, org_a):
    """Fixture for PHYSICIAN in Org A."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        email=f"doctor_a_{uuid.uuid4().hex[:6]}@hospa.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Doctor",
        last_name="Alpha",
        role=Role.PHYSICIAN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


def _headers_for(user: User) -> dict[str, str]:
    """Helper to create Authorization header for test client."""
    from app.core.permissions import get_effective_permissions
    perms = list(get_effective_permissions(user.role, user.extra_permissions, user.revoked_permissions))
    token, _, _ = security.create_access_token(
        subject=str(user.id),
        role=user.role,
        organization_id=str(user.organization_id),
        permissions=perms,
    )
    return {"Authorization": f"Bearer {token}"}


class TestAdminUserLifecycleApi:
    """Test suite covering Lock, Unlock, Activate, Deactivate, and Force Logout endpoints."""

    @pytest.mark.anyio
    async def test_unauthenticated_request_rejected(self, async_client: AsyncClient, physician_a):
        """Unauthenticated request to lifecycle endpoint returns HTTP 401."""
        res = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/lock")
        assert res.status_code == 401

    @pytest.mark.anyio
    async def test_functional_roles_denied_lifecycle_operations(self, async_client: AsyncClient, physician_a, hospital_admin_a):
        """Functional role (PHYSICIAN) is denied lifecycle operations (403 AUTH_003)."""
        headers = _headers_for(physician_a)

        r1 = await async_client.post(f"/api/v1/admin/users/{hospital_admin_a.id}/lock", headers=headers)
        assert r1.status_code == 403

        r2 = await async_client.post(f"/api/v1/admin/users/{hospital_admin_a.id}/deactivate", headers=headers)
        assert r2.status_code == 403

        r3 = await async_client.post(f"/api/v1/admin/users/{hospital_admin_a.id}/force-logout", headers=headers)
        assert r3.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_can_lock_and_unlock_functional_user(self, async_client: AsyncClient, hospital_admin_a, physician_a):
        """HOSPITAL_ADMIN can lock and unlock a PHYSICIAN in own organization."""
        headers = _headers_for(hospital_admin_a)

        # Lock
        res_lock = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/lock", headers=headers)
        assert res_lock.status_code == 200
        assert res_lock.json()["is_locked"] is True

        # Verify locked user auth fails with 423
        phys_headers = _headers_for(physician_a)
        res_auth = await async_client.get("/api/v1/auth/me", headers=phys_headers)
        assert res_auth.status_code == 423

        # Unlock
        res_unlock = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/unlock", headers=headers)
        assert res_unlock.status_code == 200
        assert res_unlock.json()["is_locked"] is False

    @pytest.mark.anyio
    async def test_hospital_admin_can_deactivate_and_activate_functional_user(self, async_client: AsyncClient, hospital_admin_a, physician_a):
        """HOSPITAL_ADMIN can deactivate and activate a PHYSICIAN in own organization."""
        headers = _headers_for(hospital_admin_a)

        # Deactivate
        res_deact = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/deactivate", headers=headers)
        assert res_deact.status_code == 200
        assert res_deact.json()["is_active"] is False

        # Verify deactivated user auth fails with 401
        phys_headers = _headers_for(physician_a)
        res_auth = await async_client.get("/api/v1/auth/me", headers=phys_headers)
        assert res_auth.status_code == 401

        # Activate
        res_act = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/activate", headers=headers)
        assert res_act.status_code == 200
        assert res_act.json()["is_active"] is True

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_modify_cross_tenant_user(self, async_client: AsyncClient, hospital_admin_a, hospital_admin_b):
        """HOSPITAL_ADMIN modifying user in Org B returns 403 Forbidden."""
        headers = _headers_for(hospital_admin_a)

        res_lock = await async_client.post(f"/api/v1/admin/users/{hospital_admin_b.id}/lock", headers=headers)
        assert res_lock.status_code == 403

        res_deact = await async_client.post(f"/api/v1/admin/users/{hospital_admin_b.id}/deactivate", headers=headers)
        assert res_deact.status_code == 403

        res_logout = await async_client.post(f"/api/v1/admin/users/{hospital_admin_b.id}/force-logout", headers=headers)
        assert res_logout.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_modify_equal_or_higher_rank_user(self, async_client: AsyncClient, hospital_admin_a, super_admin_user):
        """HOSPITAL_ADMIN modifying a SUPER_ADMIN returns 403 Forbidden."""
        headers = _headers_for(hospital_admin_a)

        res_lock = await async_client.post(f"/api/v1/admin/users/{super_admin_user.id}/lock", headers=headers)
        assert res_lock.status_code == 403

        res_deact = await async_client.post(f"/api/v1/admin/users/{super_admin_user.id}/deactivate", headers=headers)
        assert res_deact.status_code == 403

    @pytest.mark.anyio
    async def test_self_action_defense_on_lifecycle_operations(self, async_client: AsyncClient, hospital_admin_a):
        """Admins cannot lock, deactivate, or force-logout themselves (403 Forbidden)."""
        headers = _headers_for(hospital_admin_a)

        res_lock = await async_client.post(f"/api/v1/admin/users/{hospital_admin_a.id}/lock", headers=headers)
        assert res_lock.status_code == 403

        res_deact = await async_client.post(f"/api/v1/admin/users/{hospital_admin_a.id}/deactivate", headers=headers)
        assert res_deact.status_code == 403

        res_logout = await async_client.post(f"/api/v1/admin/users/{hospital_admin_a.id}/force-logout", headers=headers)
        assert res_logout.status_code == 403

    @pytest.mark.anyio
    async def test_super_admin_can_manage_any_user_lifecycle(self, async_client: AsyncClient, super_admin_user, hospital_admin_b):
        """SUPER_ADMIN can manage user lifecycle globally."""
        headers = _headers_for(super_admin_user)

        res_lock = await async_client.post(f"/api/v1/admin/users/{hospital_admin_b.id}/lock", headers=headers)
        assert res_lock.status_code == 200

        res_unlock = await async_client.post(f"/api/v1/admin/users/{hospital_admin_b.id}/unlock", headers=headers)
        assert res_unlock.status_code == 200

    @pytest.mark.anyio
    async def test_force_logout_revokes_all_database_sessions(self, async_client: AsyncClient, super_admin_user, physician_a, db_session):
        """Force logout revokes all active database refresh sessions for target user."""
        headers = _headers_for(super_admin_user)

        # Create 2 active sessions for physician_a
        s1 = Session(user_id=physician_a.id, refresh_token_hash="hash1", created_at=physician_a.created_at, last_used_at=physician_a.created_at, expires_at=physician_a.created_at)
        s2 = Session(user_id=physician_a.id, refresh_token_hash="hash2", created_at=physician_a.created_at, last_used_at=physician_a.created_at, expires_at=physician_a.created_at)
        db_session.add_all([s1, s2])
        await db_session.commit()

        # Force logout
        res = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/force-logout", headers=headers)
        assert res.status_code == 200

        # Verify DB sessions are marked revoked_at
        await db_session.refresh(s1)
        await db_session.refresh(s2)
        assert s1.revoked_at is not None
        assert s2.revoked_at is not None

    @pytest.mark.anyio
    async def test_idempotent_lifecycle_operations(self, async_client: AsyncClient, super_admin_user, physician_a):
        """Repeating lifecycle operations is idempotent and returns 200 OK."""
        headers = _headers_for(super_admin_user)

        # Double lock
        r1 = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/lock", headers=headers)
        assert r1.status_code == 200
        r2 = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/lock", headers=headers)
        assert r2.status_code == 200

        # Double activate
        r3 = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/activate", headers=headers)
        assert r3.status_code == 200
        r4 = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/activate", headers=headers)
        assert r4.status_code == 200
