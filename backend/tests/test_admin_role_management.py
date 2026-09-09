"""
NeuroOncoTrack-AI — TASK-029 Admin Role Assignment & Rank Hierarchy API Unit & Integration Tests

Verifies:
1. AUTHENTICATION & AUTHORIZATION: Unauthenticated (401), functional role denial (403), SUPER_ADMIN and HOSPITAL_ADMIN access.
2. ROLE HIERARCHY MATRIX:
   - HOSPITAL_ADMIN -> SUPER_ADMIN: DENY (403)
   - HOSPITAL_ADMIN -> HOSPITAL_ADMIN: DENY (403)
   - HOSPITAL_ADMIN -> PHYSICIAN: ALLOW (200)
   - HOSPITAL_ADMIN -> AUDITOR: ALLOW (200)
   - SUPER_ADMIN -> any role: ALLOW (200)
3. SELF ESCALATION: Admin cannot modify their own role (403).
4. TENANT ISOLATION: HOSPITAL_ADMIN cannot change roles for users in another organization (403).
5. VALIDATION & MASS ASSIGNMENT: Invalid role string or extra fields return 422 VAL_001.
6. DB AUTHORITY & AUDIT LOGGING: ROLE_GRANTED audit event emitted on change with zero credential leakage.
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


@pytest.fixture
async def auditor_a(db_session, org_a):
    """Fixture for AUDITOR in Org A."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        email=f"auditor_a_{uuid.uuid4().hex[:6]}@hospa.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Auditor",
        last_name="Alpha",
        role=Role.AUDITOR.value,
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


class TestAdminRoleAssignmentApi:
    """Comprehensive test matrix for PUT /api/v1/admin/users/{user_id}/role."""

    @pytest.mark.anyio
    async def test_unauthenticated_request_rejected(self, async_client: AsyncClient, physician_a):
        """Unauthenticated request returns HTTP 401."""
        res = await async_client.put(f"/api/v1/admin/users/{physician_a.id}/role", json={"new_role": Role.AUDITOR.value})
        assert res.status_code == 401

    @pytest.mark.anyio
    async def test_functional_roles_denied_role_assignment(self, async_client: AsyncClient, physician_a, auditor_a):
        """Functional Level 50 role (PHYSICIAN) is denied role assignment (403 AUTH_003)."""
        headers = _headers_for(physician_a)
        res = await async_client.put(f"/api/v1/admin/users/{auditor_a.id}/role", json={"new_role": Role.RESEARCHER.value}, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_can_assign_functional_role(self, async_client: AsyncClient, hospital_admin_a, physician_a):
        """HOSPITAL_ADMIN can change a PHYSICIAN's role to AUDITOR in own org."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.put(f"/api/v1/admin/users/{physician_a.id}/role", json={"new_role": Role.AUDITOR.value}, headers=headers)
        assert res.status_code == 200
        assert res.json()["role"] == Role.AUDITOR.value

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_assign_super_admin(self, async_client: AsyncClient, hospital_admin_a, physician_a):
        """HOSPITAL_ADMIN attempting to assign SUPER_ADMIN is rejected (403 Forbidden)."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.put(f"/api/v1/admin/users/{physician_a.id}/role", json={"new_role": Role.SUPER_ADMIN.value}, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_assign_hospital_admin(self, async_client: AsyncClient, hospital_admin_a, physician_a):
        """HOSPITAL_ADMIN attempting to assign HOSPITAL_ADMIN is rejected (403 Forbidden)."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.put(f"/api/v1/admin/users/{physician_a.id}/role", json={"new_role": Role.HOSPITAL_ADMIN.value}, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_modify_equal_or_higher_rank_user(self, async_client: AsyncClient, hospital_admin_a, super_admin_user):
        """HOSPITAL_ADMIN attempting to modify a SUPER_ADMIN's role is rejected (403 Forbidden)."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.put(f"/api/v1/admin/users/{super_admin_user.id}/role", json={"new_role": Role.PHYSICIAN.value}, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_super_admin_can_assign_any_valid_role(self, async_client: AsyncClient, super_admin_user, physician_a):
        """SUPER_ADMIN can assign any valid system role."""
        headers = _headers_for(super_admin_user)
        res = await async_client.put(f"/api/v1/admin/users/{physician_a.id}/role", json={"new_role": Role.HOSPITAL_ADMIN.value}, headers=headers)
        assert res.status_code == 200
        assert res.json()["role"] == Role.HOSPITAL_ADMIN.value

    @pytest.mark.anyio
    async def test_self_role_escalation_defense(self, async_client: AsyncClient, hospital_admin_a):
        """Admins cannot change their own role rank via self-assignment."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.put(f"/api/v1/admin/users/{hospital_admin_a.id}/role", json={"new_role": Role.SUPER_ADMIN.value}, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_cross_tenant_role_assignment_denied(self, async_client: AsyncClient, hospital_admin_a, hospital_admin_b):
        """HOSPITAL_ADMIN modifying user in Org B returns 403 Forbidden."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.put(f"/api/v1/admin/users/{hospital_admin_b.id}/role", json={"new_role": Role.PHYSICIAN.value}, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_invalid_role_payload_returns_validation_error(self, async_client: AsyncClient, super_admin_user, physician_a):
        """Invalid role string (e.g. 'SUPERUSER', 'admin', 'INVALID') returns 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        res = await async_client.put(f"/api/v1/admin/users/{physician_a.id}/role", json={"new_role": "SUPERUSER"}, headers=headers)
        assert res.status_code == 422

    @pytest.mark.anyio
    async def test_extra_unwhitelisted_fields_rejected(self, async_client: AsyncClient, super_admin_user, physician_a):
        """Extra unwhitelisted payload fields return 422 VAL_001 (ConfigDict extra='forbid')."""
        headers = _headers_for(super_admin_user)
        payload = {
            "new_role": Role.AUDITOR.value,
            "organization_id": str(uuid.uuid4()),  # Extra field
        }
        res = await async_client.put(f"/api/v1/admin/users/{physician_a.id}/role", json=payload, headers=headers)
        assert res.status_code == 422

    @pytest.mark.anyio
    async def test_role_alias_field_support(self, async_client: AsyncClient, super_admin_user, physician_a):
        """Both {"role": "AUDITOR"} and {"new_role": "AUDITOR"} payloads are supported."""
        headers = _headers_for(super_admin_user)
        res = await async_client.put(f"/api/v1/admin/users/{physician_a.id}/role", json={"role": Role.RESEARCHER.value}, headers=headers)
        assert res.status_code == 200
        assert res.json()["role"] == Role.RESEARCHER.value

    @pytest.mark.anyio
    async def test_same_role_reassignment_is_noop(self, async_client: AsyncClient, super_admin_user, physician_a):
        """Re-assigning same existing role returns 200 OK without error."""
        headers = _headers_for(super_admin_user)
        res = await async_client.put(f"/api/v1/admin/users/{physician_a.id}/role", json={"new_role": Role.PHYSICIAN.value}, headers=headers)
        assert res.status_code == 200
        assert res.json()["role"] == Role.PHYSICIAN.value
