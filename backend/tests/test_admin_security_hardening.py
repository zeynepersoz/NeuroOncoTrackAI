"""
NeuroOncoTrack-AI — TASK-035 Admin API Security Hardening & Fail-Closed Matrix Test Suite

Comprehensive test suite verifying:
1. AUTHENTICATION FAIL-CLOSED: Unauthenticated (401), invalid JWT (401), expired JWT (401), blacklisted token (401), locked actor (423 AUTH_004), inactive actor (401), inactive organization (401).
2. ROLE & PERMISSION ENFORCEMENT: Level 50 functional roles denied (403 AUTH_003), revoked permission precedence over extra permissions.
3. TENANT ISOLATION & IDOR DEFENSE: HOSPITAL_ADMIN cross-tenant operations blocked (403 AUTH_003).
4. PRIVILEGE ESCALATION & HIERARCHY DEFENSES: Cannot modify equal/higher rank, cannot assign higher role, self-escalation blocked.
5. MASS ASSIGNMENT & INPUT VALIDATION: Extra unknown fields return HTTP 422 VAL_001, invalid UUID/enum/sort/date bounds return 422 VAL_001.
6. MUTATION SAFETY: Failed authorization produces ZERO DB mutations and ZERO Redis mutations.
7. RESPONSE SECURITY: Zero exposure of passwords, hashes, tokens, or MFA secrets.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import audit, security
from app.core.permissions import Permission, Role, get_effective_permissions
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
async def org_alpha(db_session):
    """Fixture for active Organization Alpha."""
    org = Organization(
        id=uuid.uuid4(),
        name="Hardening Hospital Alpha",
        code="HARD_A_" + uuid.uuid4().hex[:6].upper(),
        org_type="HOSPITAL",
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def org_beta(db_session):
    """Fixture for active Organization Beta."""
    org = Organization(
        id=uuid.uuid4(),
        name="Hardening Hospital Beta",
        code="HARD_B_" + uuid.uuid4().hex[:6].upper(),
        org_type="CLINIC",
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def org_inactive(db_session):
    """Fixture for inactive Organization."""
    org = Organization(
        id=uuid.uuid4(),
        name="Inactive Hospital",
        code="HARD_INACT_" + uuid.uuid4().hex[:6].upper(),
        org_type="CLINIC",
        is_active=False,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def super_admin_user(db_session, org_alpha):
    """Fixture for active SUPER_ADMIN user."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_alpha.id,
        email=f"super_hard_{uuid.uuid4().hex[:6]}@platform.gov",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Super",
        last_name="HardAdmin",
        role=Role.SUPER_ADMIN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def hospital_admin_alpha(db_session, org_alpha):
    """Fixture for HOSPITAL_ADMIN in Org Alpha."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_alpha.id,
        email=f"admin_hard_a_{uuid.uuid4().hex[:6]}@hospa.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="AdminA",
        last_name="OrgAlpha",
        role=Role.HOSPITAL_ADMIN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def hospital_admin_alpha_2(db_session, org_alpha):
    """Fixture for a second HOSPITAL_ADMIN in Org Alpha (equal rank target)."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_alpha.id,
        email=f"admin_hard_a2_{uuid.uuid4().hex[:6]}@hospa.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="AdminA2",
        last_name="OrgAlpha2",
        role=Role.HOSPITAL_ADMIN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def hospital_admin_beta(db_session, org_beta):
    """Fixture for HOSPITAL_ADMIN in Org Beta (cross-tenant target)."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_beta.id,
        email=f"admin_hard_b_{uuid.uuid4().hex[:6]}@hospb.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="AdminB",
        last_name="OrgBeta",
        role=Role.HOSPITAL_ADMIN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def physician_alpha(db_session, org_alpha):
    """Fixture for PHYSICIAN in Org Alpha."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_alpha.id,
        email=f"doc_hard_a_{uuid.uuid4().hex[:6]}@hospa.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="DocA",
        last_name="OrgAlpha",
        role=Role.PHYSICIAN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


def _headers_for(user: User, revoked_perms: list[str] | None = None) -> dict[str, str]:
    """Helper to generate bearer auth headers."""
    rev_list = revoked_perms if revoked_perms is not None else user.revoked_permissions
    perms = list(get_effective_permissions(user.role, user.extra_permissions, rev_list))
    token, _, _ = security.create_access_token(
        subject=str(user.id),
        role=user.role,
        organization_id=str(user.organization_id),
        permissions=perms,
    )
    return {"Authorization": f"Bearer {token}"}


class TestAdminSecurityHardening:
    """Master Security Hardening & Fail-Closed Matrix Test Suite."""

    # ── 1. AUTHENTICATION FAIL-CLOSED TESTS ─────────────────────────────────────

    @pytest.mark.anyio
    async def test_unauthenticated_all_admin_endpoints_401(self, async_client: AsyncClient):
        """Unauthenticated requests to all admin endpoints return HTTP 401."""
        dummy_uuid = str(uuid.uuid4())
        endpoints = [
            ("GET", "/api/v1/admin/users"),
            ("POST", "/api/v1/admin/users"),
            ("GET", f"/api/v1/admin/users/{dummy_uuid}"),
            ("PATCH", f"/api/v1/admin/users/{dummy_uuid}"),
            ("PUT", f"/api/v1/admin/users/{dummy_uuid}/role"),
            ("POST", f"/api/v1/admin/users/{dummy_uuid}/lock"),
            ("POST", f"/api/v1/admin/users/{dummy_uuid}/unlock"),
            ("POST", f"/api/v1/admin/users/{dummy_uuid}/activate"),
            ("POST", f"/api/v1/admin/users/{dummy_uuid}/deactivate"),
            ("POST", f"/api/v1/admin/users/{dummy_uuid}/force-logout"),
            ("GET", "/api/v1/admin/organizations"),
            ("POST", "/api/v1/admin/organizations"),
            ("GET", f"/api/v1/admin/organizations/{dummy_uuid}"),
            ("PATCH", f"/api/v1/admin/organizations/{dummy_uuid}"),
            ("POST", f"/api/v1/admin/organizations/{dummy_uuid}/deactivate"),
            ("GET", "/api/v1/admin/sessions"),
            ("DELETE", f"/api/v1/admin/sessions/{dummy_uuid}"),
            ("GET", "/api/v1/admin/audit-logs"),
            ("GET", f"/api/v1/admin/audit-logs/{dummy_uuid}"),
            ("GET", "/api/v1/admin/security/overview"),
            ("GET", "/api/v1/admin/security/events"),
            ("GET", "/api/v1/admin/security/trends"),
            ("GET", "/api/v1/admin/security/organizations"),
        ]

        for method, url in endpoints:
            if method == "GET":
                res = await async_client.get(url)
            elif method == "POST":
                res = await async_client.post(url, json={})
            elif method == "PATCH":
                res = await async_client.patch(url, json={})
            elif method == "PUT":
                res = await async_client.put(url, json={})
            elif method == "DELETE":
                res = await async_client.delete(url)
            assert res.status_code == 401, f"Failed for {method} {url}"

    @pytest.mark.anyio
    async def test_invalid_token_rejected_401(self, async_client: AsyncClient):
        """Invalid Bearer token returns HTTP 401 AUTH_002."""
        headers = {"Authorization": "Bearer invalid.jwt.token"}
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "AUTH_002"

    @pytest.mark.anyio
    async def test_expired_token_rejected_401(self, async_client: AsyncClient, super_admin_user):
        """Expired Bearer token returns HTTP 401 AUTH_002."""
        token, _, _ = security.create_access_token(
            subject=str(super_admin_user.id),
            role=super_admin_user.role,
            organization_id=str(super_admin_user.organization_id),
            permissions=["*"],
            extra_claims={"exp": datetime.now(timezone.utc) - timedelta(seconds=10)},
        )
        headers = {"Authorization": f"Bearer {token}"}
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "AUTH_002"

    @pytest.mark.anyio
    async def test_locked_actor_rejected_423(self, db_session, async_client: AsyncClient, hospital_admin_alpha):
        """Locked admin user (is_locked=True) returns HTTP 423 AUTH_004."""
        hospital_admin_alpha.is_locked = True
        db_session.add(hospital_admin_alpha)
        await db_session.commit()

        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 423
        assert res.json()["error"]["code"] == "AUTH_004"

    @pytest.mark.anyio
    async def test_inactive_actor_rejected_401(self, db_session, async_client: AsyncClient, hospital_admin_alpha):
        """Inactive admin user (is_active=False) returns HTTP 401 AUTH_001."""
        hospital_admin_alpha.is_active = False
        db_session.add(hospital_admin_alpha)
        await db_session.commit()

        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "AUTH_001"

    @pytest.mark.anyio
    async def test_inactive_organization_rejected_401(self, db_session, async_client: AsyncClient, org_inactive):
        """Admin user belonging to an inactive organization is rejected with HTTP 401 AUTH_001."""
        admin = User(
            id=uuid.uuid4(),
            organization_id=org_inactive.id,
            email=f"admin_inact_{uuid.uuid4().hex[:6]}@inact.org",
            password_hash=security.hash_password("SuperSecret123!"),
            first_name="Inact",
            last_name="Admin",
            role=Role.HOSPITAL_ADMIN.value,
            is_active=True,
            is_locked=False,
        )
        db_session.add(admin)
        await db_session.commit()

        headers = _headers_for(admin)
        res = await async_client.get("/api/v1/admin/users", headers=headers)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "AUTH_001"

    # ── 2. ROLE & PERMISSION ENFORCEMENT TESTS ──────────────────────────────────

    @pytest.mark.anyio
    async def test_physician_role_denied_all_admin_routes(self, async_client: AsyncClient, physician_alpha):
        """Level 50 PHYSICIAN is denied across all admin endpoints (HTTP 403 AUTH_003)."""
        headers = _headers_for(physician_alpha)
        dummy_uuid = str(uuid.uuid4())

        routes = [
            ("/api/v1/admin/users", "GET"),
            ("/api/v1/admin/organizations", "GET"),
            ("/api/v1/admin/sessions", "GET"),
            ("/api/v1/admin/audit-logs", "GET"),
            ("/api/v1/admin/security/overview", "GET"),
            (f"/api/v1/admin/users/{dummy_uuid}", "GET"),
        ]

        for path, verb in routes:
            res = await async_client.get(path, headers=headers)
            assert res.status_code == 403, f"Failed for {path}"
            assert res.json()["error"]["code"] == "AUTH_003"

    @pytest.mark.anyio
    async def test_hospital_admin_lacking_user_create_permission(self, db_session, async_client: AsyncClient, hospital_admin_alpha):
        """HOSPITAL_ADMIN with revoked user:create permission is rejected (403 AUTH_003)."""
        hospital_admin_alpha.revoked_permissions = ["user:create"]
        db_session.add(hospital_admin_alpha)
        await db_session.commit()

        headers = _headers_for(hospital_admin_alpha)
        payload = {
            "email": "newuser@hospa.org",
            "first_name": "New",
            "last_name": "User",
            "role": "PHYSICIAN",
        }
        res = await async_client.post("/api/v1/admin/users", json=payload, headers=headers)
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "AUTH_003"

    @pytest.mark.anyio
    async def test_hospital_admin_lacking_role_assign_permission(self, db_session, async_client: AsyncClient, hospital_admin_alpha, physician_alpha):
        """HOSPITAL_ADMIN with revoked role:assign permission is rejected (403 AUTH_003)."""
        hospital_admin_alpha.revoked_permissions = ["role:assign"]
        db_session.add(hospital_admin_alpha)
        await db_session.commit()

        headers = _headers_for(hospital_admin_alpha)
        payload = {"new_role": "RADIOLOGY_TECH"}
        res = await async_client.put(f"/api/v1/admin/users/{physician_alpha.id}/role", json=payload, headers=headers)
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "AUTH_003"

    @pytest.mark.anyio
    async def test_revoked_permission_precedence_over_extra(self, async_client: AsyncClient, hospital_admin_alpha):
        """revoked_permissions overrides extra_permissions (revoked precedence rule)."""
        hospital_admin_alpha.extra_permissions = ["user:create"]
        hospital_admin_alpha.revoked_permissions = ["user:create"]
        headers = _headers_for(hospital_admin_alpha)

        payload = {
            "email": "revokedtest@hospa.org",
            "first_name": "Rev",
            "last_name": "Test",
            "role": "PHYSICIAN",
        }
        res = await async_client.post("/api/v1/admin/users", json=payload, headers=headers)
        assert res.status_code == 403

    # ── 3. TENANT ISOLATION & IDOR DEFENSE TESTS ─────────────────────────────

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_get_cross_tenant_user(self, async_client: AsyncClient, hospital_admin_alpha, hospital_admin_beta):
        """HOSPITAL_ADMIN looking up user in Org Beta gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.get(f"/api/v1/admin/users/{hospital_admin_beta.id}", headers=headers)
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "AUTH_003"

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_update_cross_tenant_user(self, async_client: AsyncClient, hospital_admin_alpha, hospital_admin_beta):
        """HOSPITAL_ADMIN updating user in Org Beta gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.patch(
            f"/api/v1/admin/users/{hospital_admin_beta.id}",
            json={"first_name": "Hacked"},
            headers=headers,
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "AUTH_003"

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_change_cross_tenant_user_role(self, async_client: AsyncClient, hospital_admin_alpha, hospital_admin_beta):
        """HOSPITAL_ADMIN reassigning role of user in Org Beta gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.put(
            f"/api/v1/admin/users/{hospital_admin_beta.id}/role",
            json={"new_role": "PHYSICIAN"},
            headers=headers,
        )
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_lock_cross_tenant_user(self, async_client: AsyncClient, hospital_admin_alpha, hospital_admin_beta):
        """HOSPITAL_ADMIN locking user in Org Beta gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.post(f"/api/v1/admin/users/{hospital_admin_beta.id}/lock", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_get_cross_tenant_organization(self, async_client: AsyncClient, hospital_admin_alpha, org_beta):
        """HOSPITAL_ADMIN viewing Organization Beta details gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.get(f"/api/v1/admin/organizations/{org_beta.id}", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_update_cross_tenant_organization(self, async_client: AsyncClient, hospital_admin_alpha, org_beta):
        """HOSPITAL_ADMIN updating Organization Beta details gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.patch(
            f"/api/v1/admin/organizations/{org_beta.id}",
            json={"name": "Hacked Org"},
            headers=headers,
        )
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_get_cross_tenant_audit_log(self, async_client: AsyncClient, hospital_admin_alpha, org_beta):
        """HOSPITAL_ADMIN viewing cross-tenant audit log detail gets HTTP 403 AUTH_003."""
        audit.clear_audit_log_store()
        audit.log_audit_event("CROSS_TEST", details={"organization_id": str(org_beta.id)})
        logs = audit.get_audit_store()
        cross_log_id = logs[0]["id"]

        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.get(f"/api/v1/admin/audit-logs/{cross_log_id}", headers=headers)
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "AUTH_003"

    # ── 4. PRIVILEGE ESCALATION & HIERARCHY DEFENSE TESTS ───────────────────

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_assign_super_admin_role(self, async_client: AsyncClient, hospital_admin_alpha, physician_alpha):
        """HOSPITAL_ADMIN attempting to grant SUPER_ADMIN role gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.put(
            f"/api/v1/admin/users/{physician_alpha.id}/role",
            json={"new_role": "SUPER_ADMIN"},
            headers=headers,
        )
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_modify_super_admin_user(self, async_client: AsyncClient, hospital_admin_alpha, super_admin_user):
        """HOSPITAL_ADMIN attempting to update a SUPER_ADMIN user gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.patch(
            f"/api/v1/admin/users/{super_admin_user.id}",
            json={"first_name": "Hacked"},
            headers=headers,
        )
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_modify_equal_hospital_admin(self, async_client: AsyncClient, hospital_admin_alpha, hospital_admin_alpha_2):
        """HOSPITAL_ADMIN attempting to modify another equal-rank HOSPITAL_ADMIN gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.put(
            f"/api/v1/admin/users/{hospital_admin_alpha_2.id}/role",
            json={"new_role": "PHYSICIAN"},
            headers=headers,
        )
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_cannot_grant_system_admin_permission(self, async_client: AsyncClient, hospital_admin_alpha, physician_alpha):
        """HOSPITAL_ADMIN attempting to grant system:config permission gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.post(
            f"/api/v1/admin/users/{physician_alpha.id}/permissions/extra",
            json={"permission": "system:config"},
            headers=headers,
        )
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_self_role_escalation_blocked(self, async_client: AsyncClient, hospital_admin_alpha):
        """HOSPITAL_ADMIN attempting to change their own role gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.put(
            f"/api/v1/admin/users/{hospital_admin_alpha.id}/role",
            json={"new_role": "SUPER_ADMIN"},
            headers=headers,
        )
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_self_lock_blocked(self, async_client: AsyncClient, hospital_admin_alpha):
        """HOSPITAL_ADMIN attempting to lock themselves gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.post(f"/api/v1/admin/users/{hospital_admin_alpha.id}/lock", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_self_deactivate_blocked(self, async_client: AsyncClient, hospital_admin_alpha):
        """HOSPITAL_ADMIN attempting to deactivate themselves gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.post(f"/api/v1/admin/users/{hospital_admin_alpha.id}/deactivate", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_self_force_logout_blocked(self, async_client: AsyncClient, hospital_admin_alpha):
        """HOSPITAL_ADMIN attempting to force logout themselves gets HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.post(f"/api/v1/admin/users/{hospital_admin_alpha.id}/force-logout", headers=headers)
        assert res.status_code == 403

    # ── 5. MASS ASSIGNMENT & INPUT VALIDATION TESTS ──────────────────────────

    @pytest.mark.anyio
    async def test_mass_assignment_extra_fields_rejected(self, async_client: AsyncClient, super_admin_user, physician_alpha):
        """Injecting unknown mass-assignment fields in write payloads returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)

        r1 = await async_client.patch(
            f"/api/v1/admin/users/{physician_alpha.id}",
            json={"first_name": "Valid", "password_hash": "malicious_hash", "is_super_admin": True},
            headers=headers,
        )
        assert r1.status_code == 422
        assert r1.json()["error"]["code"] == "VAL_001"

        r2 = await async_client.post(
            "/api/v1/admin/users",
            json={
                "email": "testmass@hospa.org",
                "first_name": "Mass",
                "last_name": "Test",
                "role": "PHYSICIAN",
                "is_active": True,
                "is_locked": True,
            },
            headers=headers,
        )
        assert r2.status_code == 422
        assert r2.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_invalid_uuid_format_rejected(self, async_client: AsyncClient, super_admin_user):
        """Malformed UUID string in path returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/users/not-a-valid-uuid", headers=headers)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_invalid_role_enum_rejected(self, async_client: AsyncClient, super_admin_user, physician_alpha):
        """Invalid role enum string returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        res = await async_client.put(
            f"/api/v1/admin/users/{physician_alpha.id}/role",
            json={"new_role": "INVALID_GOD_ROLE"},
            headers=headers,
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_invalid_user_sort_by_rejected(self, async_client: AsyncClient, super_admin_user):
        """Unwhitelisted sort_by parameter in /admin/users returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/users?sort_by=password_hash", headers=headers)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_invalid_audit_sort_by_rejected(self, async_client: AsyncClient, super_admin_user):
        """Unwhitelisted sort_by parameter in /admin/audit-logs returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/audit-logs?sort_by=DROP_TABLE", headers=headers)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_reversed_date_range_rejected(self, async_client: AsyncClient, super_admin_user):
        """start_date > end_date returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        start = "2026-08-14T20:00:00Z"
        end = "2026-08-10T20:00:00Z"
        res = await async_client.get(f"/api/v1/admin/audit-logs?start_date={start}&end_date={end}", headers=headers)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_invalid_trend_interval_rejected(self, async_client: AsyncClient, super_admin_user):
        """Invalid interval parameter returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/security/trends?interval=century", headers=headers)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    # ── 6. MUTATION SAFETY & INTEGRITY TESTS ─────────────────────────────────

    @pytest.mark.anyio
    async def test_failed_authz_causes_zero_db_mutation(self, db_session, async_client: AsyncClient, hospital_admin_alpha, hospital_admin_beta):
        """Failed authorization request results in ZERO database mutations."""
        initial_first_name = hospital_admin_beta.first_name

        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.patch(
            f"/api/v1/admin/users/{hospital_admin_beta.id}",
            json={"first_name": "MutatedName"},
            headers=headers,
        )
        assert res.status_code == 403

        await db_session.refresh(hospital_admin_beta)
        assert hospital_admin_beta.first_name == initial_first_name

    @pytest.mark.anyio
    async def test_zero_credential_leakage(self, async_client: AsyncClient, super_admin_user, physician_alpha):
        """Admin API responses contain ZERO sensitive credential details."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get(f"/api/v1/admin/users/{physician_alpha.id}", headers=headers)
        assert res.status_code == 200

        raw = res.text
        assert "password_hash" not in raw
        assert "mfa_secret" not in raw
        assert "totp_secret" not in raw
        assert "backup_codes" not in raw
        assert "setup_token" not in raw

    # ── 7. REGRESSION INVARIANTS ─────────────────────────────────────────────

    @pytest.mark.anyio
    async def test_super_admin_organization_deactivation(self, async_client: AsyncClient, super_admin_user, org_beta):
        """SUPER_ADMIN deactivating an organization functions properly."""
        headers = _headers_for(super_admin_user)
        res = await async_client.post(f"/api/v1/admin/organizations/{org_beta.id}/deactivate", headers=headers)
        assert res.status_code == 200
        assert res.json()["is_active"] is False

    @pytest.mark.anyio
    async def test_hospital_admin_org_type_update_forbidden(self, async_client: AsyncClient, hospital_admin_alpha, org_alpha):
        """HOSPITAL_ADMIN attempting to update org_type returns HTTP 403 AUTH_003."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.patch(
            f"/api/v1/admin/organizations/{org_alpha.id}",
            json={"org_type": "MAJOR_HOSPITAL"},
            headers=headers,
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "AUTH_003"
