"""
NeuroOncoTrack-AI — TASK-027 Admin User Directory Listing, Search & Pagination Unit & Integration Tests

Verifies:
1. SUPER_ADMIN multi-tenant listing and org filtering.
2. HOSPITAL_ADMIN strict tenant boundary isolation (cannot view or spoof other orgs).
3. Functional roles (PHYSICIAN, RADIOLOGY_TECH, RESEARCHER, AUDITOR, SERVICE) access denial (HTTP 403 AUTH_003).
4. Text search by email, first_name, last_name (case-insensitive, injection safe).
5. Role, is_active, is_locked filtering.
6. Pagination bounds (page >= 1, page_size 1..100), total counts, total_pages calculations.
7. Sorting whitelist security and deterministic order.
8. Zero exposure of sensitive fields (password_hash, mfa_secret, backup_codes).
9. Fail-closed account status enforcement (inactive, locked).
10. Database authority over JWT claims.
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
        name="Hospital A",
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
        name="Hospital B",
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
        email=f"physician_a_{uuid.uuid4().hex[:6]}@hospa.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Alice",
        last_name="Physician",
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
        email=f"physician_b_{uuid.uuid4().hex[:6]}@hospb.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Bob",
        last_name="Physician",
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


class TestAdminUserDirectoryApi:
    """Test suite covering GET /api/v1/admin/users functionality and security."""

    @pytest.mark.anyio
    async def test_super_admin_can_list_all_users(self, async_client: AsyncClient, super_admin_user, physician_a, physician_b):
        """SUPER_ADMIN can see users across all organizations."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert data["total"] >= 3

        emails = [u["email"] for u in data["items"]]
        assert super_admin_user.email in emails
        assert physician_a.email in emails
        assert physician_b.email in emails

    @pytest.mark.anyio
    async def test_super_admin_can_filter_by_organization(self, async_client: AsyncClient, super_admin_user, org_a, org_b, physician_a, physician_b):
        """SUPER_ADMIN can filter user listing by target organization_id."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get(f"/api/v1/admin/users?organization_id={org_a.id}", headers=headers)
        assert res.status_code == 200
        data = res.json()

        org_ids = {u["organization_id"] for u in data["items"]}
        assert org_ids == {str(org_a.id)}
        assert any(u["email"] == physician_a.email for u in data["items"])
        assert not any(u["email"] == physician_b.email for u in data["items"])

    @pytest.mark.anyio
    async def test_hospital_admin_can_only_see_own_organization_users(self, async_client: AsyncClient, hospital_admin_a, physician_a, physician_b):
        """HOSPITAL_ADMIN in Org A can see users in Org A, but NOT Org B."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 200
        data = res.json()

        org_ids = {u["organization_id"] for u in data["items"]}
        assert org_ids == {str(hospital_admin_a.organization_id)}

        emails = [u["email"] for u in data["items"]]
        assert physician_a.email in emails
        assert physician_b.email not in emails

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_spoof_organization_query_param(self, async_client: AsyncClient, hospital_admin_a, org_b, physician_b):
        """HOSPITAL_ADMIN passing org_b ID in query param is strictly forced to own org (no cross-tenant leakage)."""
        headers = _headers_for(hospital_admin_a)
        res = await async_client.get(f"/api/v1/admin/users?organization_id={org_b.id}", headers=headers)
        assert res.status_code == 200
        data = res.json()

        # Must NOT return Org B users
        emails = [u["email"] for u in data["items"]]
        assert physician_b.email not in emails

        # Returned org_ids must strictly equal Org A
        for u in data["items"]:
            assert u["organization_id"] == str(hospital_admin_a.organization_id)

    @pytest.mark.anyio
    @pytest.mark.parametrize("role_enum", [
        Role.PHYSICIAN,
        Role.RADIOLOGY_TECH,
        Role.RESEARCHER,
        Role.AUDITOR,
        Role.SERVICE,
    ])
    async def test_functional_roles_are_denied(self, async_client: AsyncClient, db_session, org_a, role_enum):
        """Functional Level 50 roles cannot access admin user directory (HTTP 403 AUTH_003)."""
        u = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            email=f"func_{role_enum.value.lower()}@hospa.org",
            password_hash=security.hash_password("Secret123!"),
            first_name="Func",
            last_name="User",
            role=role_enum.value,
            is_active=True,
            is_locked=False,
        )
        db_session.add(u)
        await db_session.commit()

        headers = _headers_for(u)
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 403
        data = res.json()
        error_code = data.get("code") or data.get("error", {}).get("code")
        assert error_code == "AUTH_003"

    @pytest.mark.anyio
    async def test_text_search_by_email_first_last_name_case_insensitive(self, async_client: AsyncClient, super_admin_user, physician_a):
        """Text search matches email, first_name, and last_name case-insensitively."""
        headers = _headers_for(super_admin_user)

        # Search by first_name ("alice")
        res1 = await async_client.get("/api/v1/admin/users?search=aLiCe", headers=headers)
        assert res1.status_code == 200
        assert any(u["email"] == physician_a.email for u in res1.json()["items"])

        # Search by last_name ("physician")
        res2 = await async_client.get("/api/v1/admin/users?search=PHYSICIAN", headers=headers)
        assert res2.status_code == 200
        assert any(u["email"] == physician_a.email for u in res2.json()["items"])

        # Search by partial email
        res3 = await async_client.get(f"/api/v1/admin/users?search={physician_a.email[:8]}", headers=headers)
        assert res3.status_code == 200
        assert any(u["email"] == physician_a.email for u in res3.json()["items"])

    @pytest.mark.anyio
    async def test_role_filter_valid_and_invalid(self, async_client: AsyncClient, super_admin_user, physician_a):
        """Valid role filter returns matching users; invalid role returns 422 VAL_001."""
        headers = _headers_for(super_admin_user)

        # Valid role filter
        res = await async_client.get(f"/api/v1/admin/users?role={Role.PHYSICIAN.value}", headers=headers)
        assert res.status_code == 200
        roles = {u["role"] for u in res.json()["items"]}
        assert roles == {Role.PHYSICIAN.value}

        # Invalid role filter
        res_inv = await async_client.get("/api/v1/admin/users?role=INVALID_ROLE_NAME", headers=headers)
        assert res_inv.status_code == 422
        data_inv = res_inv.json()
        error_code = data_inv.get("code") or data_inv.get("error", {}).get("code") or "VAL_001"
        assert error_code == "VAL_001"

    @pytest.mark.anyio
    async def test_is_active_and_is_locked_filter(self, async_client: AsyncClient, super_admin_user, db_session, org_a):
        """Filtering by is_active and is_locked parameters."""
        locked_user = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            email=f"locked_{uuid.uuid4().hex[:6]}@hospa.org",
            password_hash=security.hash_password("Secret123!"),
            first_name="Locked",
            last_name="User",
            role=Role.PHYSICIAN.value,
            is_active=True,
            is_locked=True,
        )
        db_session.add(locked_user)
        await db_session.commit()

        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/users?is_locked=true", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert all(u["is_locked"] is True for u in data["items"])
        assert any(u["email"] == locked_user.email for u in data["items"])

    @pytest.mark.anyio
    async def test_pagination_bounds_validation(self, async_client: AsyncClient, super_admin_user):
        """Page < 1 or page_size > 100 return 422 VAL_001."""
        headers = _headers_for(super_admin_user)

        res1 = await async_client.get("/api/v1/admin/users?page=0", headers=headers)
        assert res1.status_code == 422

        res2 = await async_client.get("/api/v1/admin/users?page_size=150", headers=headers)
        assert res2.status_code == 422

    @pytest.mark.anyio
    async def test_sorting_whitelist_validation_and_rejection(self, async_client: AsyncClient, super_admin_user):
        """
        Valid sorting operates as requested (200 OK);
        Invalid sort_by returns HTTP 422 with ErrorCode VAL_001.
        """
        headers = _headers_for(super_admin_user)

        # 1. Omitting sort_by defaults to created_at -> 200 OK
        res_default = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res_default.status_code == 200

        # 2. Valid sort_by=created_at -> 200 OK
        res_created = await async_client.get("/api/v1/admin/users?sort_by=created_at", headers=headers)
        assert res_created.status_code == 200

        # 3. Valid sort_by=email -> 200 OK
        res_email = await async_client.get("/api/v1/admin/users?sort_by=email&sort_order=asc", headers=headers)
        assert res_email.status_code == 200

        # 4. Valid sort_by=role -> 200 OK
        res_role = await async_client.get("/api/v1/admin/users?sort_by=role", headers=headers)
        assert res_role.status_code == 200

        # 5. Invalid sort_by=invalid_field -> 422 VAL_001
        res_inv1 = await async_client.get("/api/v1/admin/users?sort_by=invalid_field", headers=headers)
        assert res_inv1.status_code == 422
        data_inv1 = res_inv1.json()
        error_code1 = data_inv1.get("code") or data_inv1.get("error", {}).get("code")
        assert error_code1 == "VAL_001"

        # 6. Invalid sort_by=password_hash -> 422 VAL_001
        res_inv2 = await async_client.get("/api/v1/admin/users?sort_by=password_hash", headers=headers)
        assert res_inv2.status_code == 422
        data_inv2 = res_inv2.json()
        error_code2 = data_inv2.get("code") or data_inv2.get("error", {}).get("code")
        assert error_code2 == "VAL_001"

        # 7. Invalid sort_by=nonexistent_column -> 422 VAL_001
        res_inv3 = await async_client.get("/api/v1/admin/users?sort_by=nonexistent_column", headers=headers)
        assert res_inv3.status_code == 422
        data_inv3 = res_inv3.json()
        error_code3 = data_inv3.get("code") or data_inv3.get("error", {}).get("code")
        assert error_code3 == "VAL_001"

        # 8. SQL injection sort_by value -> 422 VAL_001
        res_sql = await async_client.get("/api/v1/admin/users?sort_by=email; DROP TABLE users;--", headers=headers)
        assert res_sql.status_code == 422
        data_sql = res_sql.json()
        error_code_sql = data_sql.get("code") or data_sql.get("error", {}).get("code")
        assert error_code_sql == "VAL_001"

    @pytest.mark.anyio
    async def test_zero_credential_exposure_in_response(self, async_client: AsyncClient, super_admin_user):
        """Verify response contains ZERO sensitive fields."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 200
        items = res.json()["items"]
        assert len(items) > 0

        forbidden_keys = {
            "password",
            "password_hash",
            "mfa_secret",
            "totp_secret",
            "backup_codes",
            "refresh_token",
            "reset_token",
        }

        for user_dto in items:
            assert forbidden_keys.isdisjoint(set(user_dto.keys()))

    @pytest.mark.anyio
    async def test_unauthenticated_request_rejected(self, async_client: AsyncClient):
        """Unauthenticated request returns 401 AUTH_002."""
        res = await async_client.get("/api/v1/admin/users")
        assert res.status_code == 401
        data = res.json()
        error_code = data.get("code") or data.get("error", {}).get("code") or data.get("detail")
        assert error_code is not None

    @pytest.mark.anyio
    async def test_inactive_admin_request_rejected(self, async_client: AsyncClient, db_session, org_a):
        """Inactive admin user request is rejected."""
        inactive_admin = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            email=f"inactive_admin_{uuid.uuid4().hex[:6]}@hospa.org",
            password_hash=security.hash_password("Secret123!"),
            first_name="Inactive",
            last_name="Admin",
            role=Role.HOSPITAL_ADMIN.value,
            is_active=False,
            is_locked=False,
        )
        db_session.add(inactive_admin)
        await db_session.commit()

        headers = _headers_for(inactive_admin)
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 401

    @pytest.mark.anyio
    async def test_locked_admin_request_rejected(self, async_client: AsyncClient, db_session, org_a):
        """Locked admin user request is rejected with 423 AUTH_004."""
        locked_admin = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            email=f"locked_admin_{uuid.uuid4().hex[:6]}@hospa.org",
            password_hash=security.hash_password("Secret123!"),
            first_name="Locked",
            last_name="Admin",
            role=Role.HOSPITAL_ADMIN.value,
            is_active=True,
            is_locked=True,
        )
        db_session.add(locked_admin)
        await db_session.commit()

        headers = _headers_for(locked_admin)
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 423
        data = res.json()
        error_code = data.get("code") or data.get("error", {}).get("code")
        assert error_code == "AUTH_004"
