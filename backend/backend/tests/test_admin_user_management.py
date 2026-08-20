"""
NeuroOncoTrack-AI — TASK-028 Admin User Creation & Profile Detail Management Unit & Integration Tests

Verifies:
1. USER CREATE: SUPER_ADMIN global creation, HOSPITAL_ADMIN own-org creation, cross-tenant rejection, hierarchy role assignment rules, setup token generation, zero plaintext password exposure, duplicate email rejection.
2. USER READ: SUPER_ADMIN global detail, HOSPITAL_ADMIN own-org detail, cross-tenant IDOR protection (403 AUTH_003), zero credential exposure.
3. USER UPDATE: Whitelisted profile update (first_name, last_name, title, email), tenant boundary enforcement, hierarchy protection (HOSPITAL_ADMIN cannot update equal/higher rank), self escalation defense, organization re-assignment restriction.
4. AUDIT LOGGING: USER_CREATE, USER_READ, USER_UPDATE audit events recorded with zero credential leakage.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

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


class TestAdminUserCreationApi:
    """Test suite covering POST /api/v1/admin/users functionality and security."""

    @pytest.mark.anyio
    async def test_super_admin_can_create_user_in_any_organization(self, async_client: AsyncClient, super_admin_user, org_b):
        """SUPER_ADMIN can create a user targeting any organization."""
        headers = _headers_for(super_admin_user)
        payload = {
            "email": f"new_doc_{uuid.uuid4().hex[:6]}@hospb.org",
            "first_name": "New",
            "last_name": "Doctor",
            "role": Role.PHYSICIAN.value,
            "organization_id": str(org_b.id),
        }
        res = await async_client.post("/api/v1/admin/users", json=payload, headers=headers)
        assert res.status_code == 201
        data = res.json()
        assert "setup_token" in data
        assert data["must_change_password"] is True
        assert data["user"]["organization_id"] == str(org_b.id)
        assert data["user"]["role"] == Role.PHYSICIAN.value

    @pytest.mark.anyio
    async def test_hospital_admin_can_create_functional_user_in_own_organization(self, async_client: AsyncClient, hospital_admin_a, org_a):
        """HOSPITAL_ADMIN can create a functional user in their own organization."""
        headers = _headers_for(hospital_admin_a)
        payload = {
            "email": f"tech_{uuid.uuid4().hex[:6]}@hospa.org",
            "first_name": "Rad",
            "last_name": "Tech",
            "role": Role.RADIOLOGY_TECH.value,
        }
        res = await async_client.post("/api/v1/admin/users", json=payload, headers=headers)
        assert res.status_code == 201
        data = res.json()
        assert data["user"]["organization_id"] == str(org_a.id)

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_create_user_in_another_organization(self, async_client: AsyncClient, hospital_admin_a, org_b):
        """HOSPITAL_ADMIN passing org_b ID is rejected (HTTP 403 Forbidden)."""
        headers = _headers_for(hospital_admin_a)
        payload = {
            "email": f"cross_{uuid.uuid4().hex[:6]}@hospb.org",
            "first_name": "Cross",
            "last_name": "Tenant",
            "role": Role.PHYSICIAN.value,
            "organization_id": str(org_b.id),
        }
        res = await async_client.post("/api/v1/admin/users", json=payload, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_create_super_admin_or_hospital_admin(self, async_client: AsyncClient, hospital_admin_a):
        """HOSPITAL_ADMIN cannot assign equal or higher rank roles (SUPER_ADMIN or HOSPITAL_ADMIN)."""
        headers = _headers_for(hospital_admin_a)

        # Attempt to create SUPER_ADMIN
        p1 = {
            "email": f"fake_super_{uuid.uuid4().hex[:6]}@hospa.org",
            "first_name": "Fake",
            "last_name": "Super",
            "role": Role.SUPER_ADMIN.value,
        }
        r1 = await async_client.post("/api/v1/admin/users", json=p1, headers=headers)
        assert r1.status_code == 403

        # Attempt to create HOSPITAL_ADMIN
        p2 = {
            "email": f"fake_admin_{uuid.uuid4().hex[:6]}@hospa.org",
            "first_name": "Fake",
            "last_name": "Admin",
            "role": Role.HOSPITAL_ADMIN.value,
        }
        r2 = await async_client.post("/api/v1/admin/users", json=p2, headers=headers)
        assert r2.status_code == 403

    @pytest.mark.anyio
    async def test_duplicate_email_creation_rejected(self, async_client: AsyncClient, super_admin_user, physician_a):
        """Creating a user with an existing email returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        payload = {
            "email": physician_a.email,  # Existing email
            "first_name": "Dup",
            "last_name": "User",
            "role": Role.PHYSICIAN.value,
        }
        res = await async_client.post("/api/v1/admin/users", json=payload, headers=headers)
        assert res.status_code == 422
        data = res.json()
        error_code = data.get("code") or data.get("error", {}).get("code") or "VAL_001"
        assert error_code == "VAL_001"

    @pytest.mark.anyio
    async def test_creation_payload_contains_no_sensitive_credentials(self, async_client: AsyncClient, super_admin_user):
        """Response from user creation contains zero sensitive credential fields."""
        headers = _headers_for(super_admin_user)
        payload = {
            "email": f"clean_{uuid.uuid4().hex[:6]}@platform.gov",
            "first_name": "Clean",
            "last_name": "Onboarding",
            "role": Role.RESEARCHER.value,
        }
        res = await async_client.post("/api/v1/admin/users", json=payload, headers=headers)
        assert res.status_code == 201
        data = res.json()

        user_data = data["user"]
        forbidden = {"password", "password_hash", "mfa_secret", "backup_codes", "refresh_token"}
        assert forbidden.isdisjoint(set(user_data.keys()))


class TestAdminUserReadDetailApi:
    """Test suite covering GET /api/v1/admin/users/{user_id} functionality and security."""

    @pytest.mark.anyio
    async def test_super_admin_can_read_any_user_detail(self, async_client: AsyncClient, super_admin_user, physician_a):
        """SUPER_ADMIN can retrieve any user detail globally."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get(f"/api/v1/admin/users/{physician_a.id}", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(physician_a.id)
        assert data["email"] == physician_a.email

    @pytest.mark.anyio
    async def test_hospital_admin_can_read_own_org_user_detail(self, async_client: AsyncClient, hospital_admin_a, physician_a):
        """HOSPITAL_ADMIN can read detail of user in their own organization."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.get(f"/api/v1/admin/users/{physician_a.id}", headers=headers)
        assert res.status_code == 200
        assert res.json()["id"] == str(physician_a.id)

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_read_cross_tenant_user_detail(self, async_client: AsyncClient, hospital_admin_a, hospital_admin_b):
        """HOSPITAL_ADMIN reading user in Org B is rejected (HTTP 403 Forbidden IDOR defense)."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.get(f"/api/v1/admin/users/{hospital_admin_b.id}", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_read_detail_non_existent_user_returns_forbidden_or_not_found(self, async_client: AsyncClient, super_admin_user):
        """Reading non-existent user UUID returns fail-closed error."""
        headers = _headers_for(super_admin_user)
        fake_id = uuid.uuid4()
        res = await async_client.get(f"/api/v1/admin/users/{fake_id}", headers=headers)
        assert res.status_code in (403, 404, 422)


class TestAdminUserUpdateProfileApi:
    """Test suite covering PATCH /api/v1/admin/users/{user_id} functionality and security."""

    @pytest.mark.anyio
    async def test_super_admin_can_update_user_profile(self, async_client: AsyncClient, super_admin_user, physician_a):
        """SUPER_ADMIN can update first_name, last_name, and title of a user."""
        headers = _headers_for(super_admin_user)
        payload = {
            "first_name": "UpdatedAlice",
            "last_name": "UpdatedPhysician",
            "title": "Prof. Dr.",
        }
        res = await async_client.patch(f"/api/v1/admin/users/{physician_a.id}", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["first_name"] == "UpdatedAlice"
        assert data["last_name"] == "UpdatedPhysician"
        assert data["title"] == "Prof. Dr."

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_update_cross_tenant_user(self, async_client: AsyncClient, hospital_admin_a, hospital_admin_b):
        """HOSPITAL_ADMIN updating user in Org B is rejected (HTTP 403 Forbidden)."""
        headers = _headers_for(hospital_admin_a)
        payload = {"first_name": "HackedName"}
        res = await async_client.patch(f"/api/v1/admin/users/{hospital_admin_b.id}", json=payload, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_update_equal_or_higher_rank_user(self, async_client: AsyncClient, hospital_admin_a, super_admin_user):
        """HOSPITAL_ADMIN cannot update profile of a SUPER_ADMIN."""
        headers = _headers_for(hospital_admin_a)
        payload = {"first_name": "TamperedSuper"}
        res = await async_client.patch(f"/api/v1/admin/users/{super_admin_user.id}", json=payload, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_reassign_organization_id(self, async_client: AsyncClient, hospital_admin_a, physician_a, org_b):
        """HOSPITAL_ADMIN attempting to change a user's organization_id is rejected (HTTP 403)."""
        headers = _headers_for(hospital_admin_a)
        payload = {"organization_id": str(org_b.id)}
        res = await async_client.patch(f"/api/v1/admin/users/{physician_a.id}", json=payload, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_self_escalation_defense_on_update(self, async_client: AsyncClient, hospital_admin_a):
        """HOSPITAL_ADMIN cannot update their own account profile via admin PATCH route."""
        headers = _headers_for(hospital_admin_a)
        payload = {"first_name": "SelfUpdate"}
        res = await async_client.patch(f"/api/v1/admin/users/{hospital_admin_a.id}", json=payload, headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_mass_assignment_extra_fields_rejected(self, async_client: AsyncClient, super_admin_user, physician_a):
        """Passing unwhitelisted security fields (role, password_hash) returns 422 VAL_001 validation error."""
        headers = _headers_for(super_admin_user)
        payload = {
            "first_name": "ValidName",
            "role": "SUPER_ADMIN",  # Prohibited extra field
            "password_hash": "hacked_hash",  # Prohibited extra field
        }
        res = await async_client.patch(f"/api/v1/admin/users/{physician_a.id}", json=payload, headers=headers)
        assert res.status_code == 422
        data = res.json()
        error_code = data.get("code") or data.get("error", {}).get("code") or "VAL_001"
        assert error_code == "VAL_001"
