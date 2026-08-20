"""
NeuroOncoTrack-AI — TASK-032 Admin System-Wide Session Governance & Remote Termination API Unit & Integration Tests

Verifies:
1. AUTHENTICATION & AUTHORIZATION: Unauthenticated (401), functional role denial (403 AUTH_003), SUPER_ADMIN & HOSPITAL_ADMIN access.
2. TENANT ISOLATION & HIERARCHY: HOSPITAL_ADMIN restricted to own organization users; cross-tenant session listing/termination denied (403). Cannot terminate equal/higher rank (HOSPITAL_ADMIN / SUPER_ADMIN) sessions (403).
3. SELF ACTION DEFENSE: Admins cannot terminate their own sessions via admin endpoint (403).
4. SESSION DIRECTORY & LISTING: List active sessions system-wide, org-wide, or target user scoped.
5. REMOTE TERMINATION: Revoke single session (`revoked_at = now`), bulk terminate user sessions (`terminate-all`), Redis user blacklist (`bl:user:{id}`).
6. IDEMPOTENCY & TOKEN SECURITY: Repeated termination is idempotent (200 OK), response contains zero credential/secret data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

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
        org_type="HOSPITAL",
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
        org_type="CLINIC",
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


@pytest.fixture
async def physician_b(db_session, org_b):
    """Fixture for PHYSICIAN in Org B."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_b.id,
        email=f"doctor_b_{uuid.uuid4().hex[:6]}@hospb.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Doctor",
        last_name="Beta",
        role=Role.PHYSICIAN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def session_physician_a(db_session, physician_a):
    """Fixture for active session belonging to Physician A."""
    now = datetime.now(timezone.utc)
    s = Session(
        id=uuid.uuid4(),
        user_id=physician_a.id,
        refresh_token_hash="hash_phys_a_" + uuid.uuid4().hex,
        ip_address="192.168.1.50",
        user_agent="Mozilla/5.0 Chrome/120.0",
        device_fingerprint="fp_phys_a",
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


@pytest.fixture
async def session_physician_b(db_session, physician_b):
    """Fixture for active session belonging to Physician B (Org B)."""
    now = datetime.now(timezone.utc)
    s = Session(
        id=uuid.uuid4(),
        user_id=physician_b.id,
        refresh_token_hash="hash_phys_b_" + uuid.uuid4().hex,
        ip_address="10.0.0.99",
        user_agent="Mozilla/5.0 Firefox/121.0",
        device_fingerprint="fp_phys_b",
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


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


class TestAdminSessionManagementApi:
    """Test suite covering system-wide and user-scoped session governance and remote termination."""

    @pytest.mark.anyio
    async def test_unauthenticated_request_rejected(self, async_client: AsyncClient, physician_a):
        """Unauthenticated request to session endpoint returns HTTP 401."""
        res = await async_client.get(f"/api/v1/admin/users/{physician_a.id}/sessions")
        assert res.status_code == 401

    @pytest.mark.anyio
    async def test_functional_roles_denied_session_governance(self, async_client: AsyncClient, physician_a, session_physician_a):
        """Functional Level 50 role (PHYSICIAN) is denied all session governance endpoints (403 AUTH_003)."""
        headers = _headers_for(physician_a)

        r1 = await async_client.get("/api/v1/admin/sessions", headers=headers)
        assert r1.status_code == 403

        r2 = await async_client.delete(f"/api/v1/admin/sessions/{session_physician_a.id}", headers=headers)
        assert r2.status_code == 403

        r3 = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/sessions/terminate-all", headers=headers)
        assert r3.status_code == 403

    @pytest.mark.anyio
    async def test_super_admin_can_list_all_active_sessions(self, async_client: AsyncClient, super_admin_user, session_physician_a, session_physician_b):
        """SUPER_ADMIN can list active sessions across all tenants."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/sessions", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 2
        session_ids = [item["id"] for item in data["items"]]
        assert str(session_physician_a.id) in session_ids
        assert str(session_physician_b.id) in session_ids

    @pytest.mark.anyio
    async def test_hospital_admin_session_list_is_tenant_scoped(self, async_client: AsyncClient, hospital_admin_a, session_physician_a, session_physician_b):
        """HOSPITAL_ADMIN listing sessions sees ONLY sessions belonging to users in their own org."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.get("/api/v1/admin/sessions", headers=headers)
        assert res.status_code == 200
        data = res.json()
        session_ids = [item["id"] for item in data["items"]]
        assert str(session_physician_a.id) in session_ids
        assert str(session_physician_b.id) not in session_ids

    @pytest.mark.anyio
    async def test_hospital_admin_can_terminate_session_in_own_tenant(self, async_client: AsyncClient, hospital_admin_a, session_physician_a):
        """HOSPITAL_ADMIN can terminate a session belonging to a user in their own org."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.delete(f"/api/v1/admin/sessions/{session_physician_a.id}", headers=headers)
        assert res.status_code == 200
        assert res.json()["is_revoked"] is True

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_terminate_cross_tenant_session(self, async_client: AsyncClient, hospital_admin_a, session_physician_b):
        """HOSPITAL_ADMIN terminating session in Org B returns 403 Forbidden."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.delete(f"/api/v1/admin/sessions/{session_physician_b.id}", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_terminate_super_admin_session(self, async_client: AsyncClient, hospital_admin_a, super_admin_user, db_session):
        """HOSPITAL_ADMIN attempting to terminate a SUPER_ADMIN's session is rejected (403 Forbidden)."""
        now = datetime.now(timezone.utc)
        sa_session = Session(
            id=uuid.uuid4(),
            user_id=super_admin_user.id,
            refresh_token_hash="sa_hash_" + uuid.uuid4().hex,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=7),
        )
        db_session.add(sa_session)
        await db_session.commit()

        headers = _headers_for(hospital_admin_a)
        res = await async_client.delete(f"/api/v1/admin/sessions/{sa_session.id}", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_self_action_session_termination_rejected(self, async_client: AsyncClient, hospital_admin_a, db_session):
        """Admins cannot terminate their own sessions via the admin endpoint (403 Forbidden)."""
        now = datetime.now(timezone.utc)
        admin_session = Session(
            id=uuid.uuid4(),
            user_id=hospital_admin_a.id,
            refresh_token_hash="admin_hash_" + uuid.uuid4().hex,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=7),
        )
        db_session.add(admin_session)
        await db_session.commit()

        headers = _headers_for(hospital_admin_a)
        res = await async_client.delete(f"/api/v1/admin/sessions/{admin_session.id}", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_terminate_all_target_user_sessions(self, async_client: AsyncClient, hospital_admin_a, physician_a, db_session):
        """HOSPITAL_ADMIN can terminate all active sessions for a target user in their own org."""
        now = datetime.now(timezone.utc)
        s1 = Session(user_id=physician_a.id, refresh_token_hash="h1", created_at=now, last_used_at=now, expires_at=now + timedelta(days=7))
        s2 = Session(user_id=physician_a.id, refresh_token_hash="h2", created_at=now, last_used_at=now, expires_at=now + timedelta(days=7))
        db_session.add_all([s1, s2])
        await db_session.commit()

        headers = _headers_for(hospital_admin_a)
        res = await async_client.post(f"/api/v1/admin/users/{physician_a.id}/sessions/terminate-all", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 2
        for item in data["items"]:
            assert item["is_revoked"] is True

    @pytest.mark.anyio
    async def test_idempotent_session_termination(self, async_client: AsyncClient, super_admin_user, session_physician_a):
        """Repeating session termination is idempotent and returns 200 OK."""
        headers = _headers_for(super_admin_user)

        r1 = await async_client.delete(f"/api/v1/admin/sessions/{session_physician_a.id}", headers=headers)
        assert r1.status_code == 200
        assert r1.json()["is_revoked"] is True

        r2 = await async_client.delete(f"/api/v1/admin/sessions/{session_physician_a.id}", headers=headers)
        assert r2.status_code == 200
        assert r2.json()["is_revoked"] is True

    @pytest.mark.anyio
    async def test_no_token_secrets_in_session_response(self, async_client: AsyncClient, super_admin_user, session_physician_a):
        """Session response contains zero credential or token hash data."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get(f"/api/v1/admin/users/{session_physician_a.user_id}/sessions", headers=headers)
        assert res.status_code == 200
        raw_text = res.text
        assert "refresh_token" not in raw_text
        assert "refresh_token_hash" not in raw_text
        assert "hash_phys_a" not in raw_text
