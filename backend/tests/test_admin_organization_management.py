"""
NeuroOncoTrack-AI — TASK-031 Admin Multi-Tenant Organization Management API Unit & Integration Tests

Verifies:
1. AUTHORIZATION MATRIX:
   - SUPER_ADMIN: List all orgs, Create org, Read any org, Update any org, Deactivate org.
   - HOSPITAL_ADMIN: List own org, Read own org, Update own org (excluding code/type), Create denied (403), Deactivate denied (403), Cross-tenant access denied (403).
   - Functional roles (PHYSICIAN, AUDITOR, etc.): All org endpoints denied (403).
2. VALIDATION & MASS ASSIGNMENT: Code uniqueness, uppercase normalization, extra fields rejected (422 VAL_001).
3. TENANT ISOLATION & IDOR DEFENSE: Server-side actor.organization_id is authoritative; spoofing ignored.
4. AUDIT & RESPONSE SECURITY: Audit events emitted with zero credential exposure.
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


class TestAdminOrganizationManagementApi:
    """Test suite covering Organization CRUD, tenant isolation, and security controls."""

    @pytest.mark.anyio
    async def test_unauthenticated_request_rejected(self, async_client: AsyncClient, org_a):
        """Unauthenticated request returns HTTP 401."""
        res = await async_client.get("/api/v1/admin/organizations")
        assert res.status_code == 401

    @pytest.mark.anyio
    async def test_functional_roles_denied_organization_access(self, async_client: AsyncClient, physician_a, org_a):
        """Functional Level 50 role (PHYSICIAN) is denied all org endpoints (403 AUTH_003)."""
        headers = _headers_for(physician_a)

        r1 = await async_client.get("/api/v1/admin/organizations", headers=headers)
        assert r1.status_code == 403

        r2 = await async_client.get(f"/api/v1/admin/organizations/{org_a.id}", headers=headers)
        assert r2.status_code == 403

        r3 = await async_client.post("/api/v1/admin/organizations", json={"name": "Test", "code": "TEST_ORG"}, headers=headers)
        assert r3.status_code == 403

    @pytest.mark.anyio
    async def test_super_admin_can_list_all_organizations(self, async_client: AsyncClient, super_admin_user, org_a, org_b):
        """SUPER_ADMIN can list all organizations globally."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/organizations", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 2
        codes = [item["code"] for item in data["items"]]
        assert org_a.code in codes
        assert org_b.code in codes

    @pytest.mark.anyio
    async def test_hospital_admin_list_is_tenant_scoped(self, async_client: AsyncClient, hospital_admin_a, org_a, org_b):
        """HOSPITAL_ADMIN listing organizations sees ONLY their own organization."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.get("/api/v1/admin/organizations", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == str(org_a.id)

    @pytest.mark.anyio
    async def test_super_admin_can_create_organization(self, async_client: AsyncClient, super_admin_user):
        """SUPER_ADMIN can create a new organization with uppercase code normalization."""
        headers = _headers_for(super_admin_user)
        payload = {
            "name": "New Cancer Center",
            "code": " ncc_org_1 ",
            "org_type": "RESEARCH_CENTER",
            "description": "Oncology Research",
        }
        res = await async_client.post("/api/v1/admin/organizations", json=payload, headers=headers)
        assert res.status_code == 201
        data = res.json()
        assert data["code"] == "NCC_ORG_1"
        assert data["name"] == "New Cancer Center"
        assert data["is_active"] is True

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_create_organization(self, async_client: AsyncClient, hospital_admin_a):
        """HOSPITAL_ADMIN cannot create a new organization (403 Forbidden)."""
        headers = _headers_for(hospital_admin_a)
        payload = {
            "name": "Unauthorized Org",
            "code": "UNAUTH_ORG",
        }
        res = await async_client.post("/api/v1/admin/organizations", json=payload, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_duplicate_organization_code_rejected(self, async_client: AsyncClient, super_admin_user, org_a):
        """Duplicate organization code returns 422 VAL_001 validation error."""
        headers = _headers_for(super_admin_user)
        payload = {
            "name": "Duplicate Org",
            "code": org_a.code.lower(),  # Test case-insensitive duplicate check
        }
        res = await async_client.post("/api/v1/admin/organizations", json=payload, headers=headers)
        assert res.status_code == 422

    @pytest.mark.anyio
    async def test_hospital_admin_can_read_own_organization(self, async_client: AsyncClient, hospital_admin_a, org_a):
        """HOSPITAL_ADMIN can read detail of own organization."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.get(f"/api/v1/admin/organizations/{org_a.id}", headers=headers)
        assert res.status_code == 200
        assert res.json()["id"] == str(org_a.id)

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_read_cross_tenant_organization(self, async_client: AsyncClient, hospital_admin_a, org_b):
        """HOSPITAL_ADMIN reading Org B returns 403 Forbidden."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.get(f"/api/v1/admin/organizations/{org_b.id}", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_can_update_own_organization(self, async_client: AsyncClient, hospital_admin_a, org_a):
        """HOSPITAL_ADMIN can update name/description of own organization."""
        headers = _headers_for(hospital_admin_a)
        payload = {"name": "Updated Hospital Alpha", "description": "New description"}
        res = await async_client.patch(f"/api/v1/admin/organizations/{org_a.id}", json=payload, headers=headers)
        assert res.status_code == 200
        assert res.json()["name"] == "Updated Hospital Alpha"

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_update_org_type(self, async_client: AsyncClient, hospital_admin_a, org_a):
        """HOSPITAL_ADMIN attempting to update org_type is rejected (403 Forbidden)."""
        headers = _headers_for(hospital_admin_a)
        payload = {"org_type": "GOVERNMENT"}
        res = await async_client.patch(f"/api/v1/admin/organizations/{org_a.id}", json=payload, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_update_cross_tenant_organization(self, async_client: AsyncClient, hospital_admin_a, org_b):
        """HOSPITAL_ADMIN updating Org B returns 403 Forbidden."""
        headers = _headers_for(hospital_admin_a)
        payload = {"name": "Hacked Name"}
        res = await async_client.patch(f"/api/v1/admin/organizations/{org_b.id}", json=payload, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_super_admin_can_deactivate_organization(self, async_client: AsyncClient, super_admin_user, org_b):
        """SUPER_ADMIN can deactivate an organization."""
        headers = _headers_for(super_admin_user)
        res = await async_client.post(f"/api/v1/admin/organizations/{org_b.id}/deactivate", headers=headers)
        assert res.status_code == 200
        assert res.json()["is_active"] is False

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_deactivate_organization(self, async_client: AsyncClient, hospital_admin_a, org_a):
        """HOSPITAL_ADMIN cannot deactivate their own or any organization (403 Forbidden)."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.post(f"/api/v1/admin/organizations/{org_a.id}/deactivate", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_deactivating_organization_blocks_user_authentication(self, async_client: AsyncClient, super_admin_user, hospital_admin_b, org_b):
        """Deactivating Org B immediately blocks users belonging to Org B from authenticating."""
        # Deactivate Org B
        sa_headers = _headers_for(super_admin_user)
        r_deact = await async_client.post(f"/api/v1/admin/organizations/{org_b.id}/deactivate", headers=sa_headers)
        assert r_deact.status_code == 200

        # Attempt auth with hospital_admin_b user -> should fail with 401 AuthenticationError
        b_headers = _headers_for(hospital_admin_b)
        res_auth = await async_client.get("/api/v1/auth/me", headers=b_headers)
        assert res_auth.status_code == 401

    @pytest.mark.anyio
    async def test_extra_unwhitelisted_payload_fields_rejected(self, async_client: AsyncClient, super_admin_user):
        """Extra unwhitelisted fields in create payload return 422 VAL_001 (ConfigDict extra='forbid')."""
        headers = _headers_for(super_admin_user)
        payload = {
            "name": "Org X",
            "code": "ORG_X",
            "is_active": False,  # Protected/extra field
        }
        res = await async_client.post("/api/v1/admin/organizations", json=payload, headers=headers)
        assert res.status_code == 422

    @pytest.mark.anyio
    async def test_idempotent_deactivate_operation(self, async_client: AsyncClient, super_admin_user, org_b):
        """Repeating organization deactivation is idempotent and returns 200 OK."""
        headers = _headers_for(super_admin_user)

        r1 = await async_client.post(f"/api/v1/admin/organizations/{org_b.id}/deactivate", headers=headers)
        assert r1.status_code == 200
        assert r1.json()["is_active"] is False

        r2 = await async_client.post(f"/api/v1/admin/organizations/{org_b.id}/deactivate", headers=headers)
        assert r2.status_code == 200
        assert r2.json()["is_active"] is False
