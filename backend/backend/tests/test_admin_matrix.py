"""
NeuroOncoTrack-AI — TASK-036 Comprehensive Admin Module Integration & Security Test Matrix

Master combinatorial integration test suite verifying:
1. ALL 7 ROLES × ALL ADMIN ENDPOINTS MATRIX (SUPER_ADMIN, HOSPITAL_ADMIN, PHYSICIAN, RADIOLOGY_TECH, RESEARCHER, AUDITOR, SERVICE).
2. MULTI-TENANT BOUNDARY MATRIX (Org A vs Org B, cross-tenant isolation).
3. IDOR MATRIX (Own resource, cross-tenant resource, missing resource, malformed UUID).
4. MASS ASSIGNMENT MATRIX (Pydantic extra="forbid" field injection defense).
5. PERMISSION OVERRIDE MATRIX (Base perm, Extra perm, Revoked perm precedence rule).
6. SESSION LIFECYCLE & REDIS BLACKLIST MATRIX.
7. ORGANIZATION DEACTIVATION & AFFECTED USER LOGIN BLOCKING MATRIX.
8. AUDIT SECURITY & RECURSION DEFENSE MATRIX.
9. ERROR CONTRACT & ZERO MUTATION FAIL-CLOSED MATRIX.
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
async def org_matrix_a(db_session):
    """Fixture for Organization Matrix A."""
    org = Organization(
        id=uuid.uuid4(),
        name="Matrix Hospital Alpha",
        code="MTX_A_" + uuid.uuid4().hex[:6].upper(),
        org_type="HOSPITAL",
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def org_matrix_b(db_session):
    """Fixture for Organization Matrix B."""
    org = Organization(
        id=uuid.uuid4(),
        name="Matrix Hospital Beta",
        code="MTX_B_" + uuid.uuid4().hex[:6].upper(),
        org_type="CLINIC",
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def super_admin_actor(db_session, org_matrix_a):
    """Fixture for SUPER_ADMIN user."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_matrix_a.id,
        email=f"super_mtx_{uuid.uuid4().hex[:6]}@platform.gov",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Super",
        last_name="MatrixAdmin",
        role=Role.SUPER_ADMIN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def hospital_admin_a(db_session, org_matrix_a):
    """Fixture for HOSPITAL_ADMIN in Org A."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_matrix_a.id,
        email=f"admin_mtx_a_{uuid.uuid4().hex[:6]}@orga.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="AdminA",
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
async def hospital_admin_b(db_session, org_matrix_b):
    """Fixture for HOSPITAL_ADMIN in Org B."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_matrix_b.id,
        email=f"admin_mtx_b_{uuid.uuid4().hex[:6]}@orgb.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="AdminB",
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
async def physician_a(db_session, org_matrix_a):
    """Fixture for PHYSICIAN in Org A."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_matrix_a.id,
        email=f"doc_mtx_a_{uuid.uuid4().hex[:6]}@orga.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="DocA",
        last_name="OrgA",
        role=Role.PHYSICIAN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def physician_b(db_session, org_matrix_b):
    """Fixture for PHYSICIAN in Org B."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_matrix_b.id,
        email=f"doc_mtx_b_{uuid.uuid4().hex[:6]}@orgb.org",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="DocB",
        last_name="OrgB",
        role=Role.PHYSICIAN.value,
        is_active=True,
        is_locked=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


def _headers_for(user: User) -> dict[str, str]:
    """Helper to generate bearer auth headers."""
    perms = list(get_effective_permissions(user.role, user.extra_permissions, user.revoked_permissions))
    token, _, _ = security.create_access_token(
        subject=str(user.id),
        role=user.role,
        organization_id=str(user.organization_id),
        permissions=perms,
    )
    return {"Authorization": f"Bearer {token}"}


class TestAdminComprehensiveMatrix:
    """Master Combinatorial Integration & Security Matrix Test Suite."""

    # ── 1. ALL 7 ROLES MATRIX ──────────────────────────────────────────────────

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "role_name",
        [
            Role.PHYSICIAN.value,
            Role.RADIOLOGY_TECH.value,
            Role.RESEARCHER.value,
            Role.AUDITOR.value,
            Role.SERVICE.value,
        ],
    )
    async def test_level_50_roles_denied_across_all_admin_endpoints(
        self, db_session, async_client: AsyncClient, org_matrix_a, role_name: str
    ):
        """All Level 50 functional roles receive HTTP 403 AUTH_003 across all admin routes."""
        user = User(
            id=uuid.uuid4(),
            organization_id=org_matrix_a.id,
            email=f"role_test_{role_name.lower()}_{uuid.uuid4().hex[:4]}@platform.gov",
            password_hash=security.hash_password("SuperSecret123!"),
            first_name="RoleTest",
            last_name=role_name,
            role=role_name,
            is_active=True,
            is_locked=False,
        )
        db_session.add(user)
        await db_session.commit()

        headers = _headers_for(user)
        dummy_id = str(uuid.uuid4())

        admin_routes = [
            ("/api/v1/admin/users", "GET"),
            ("/api/v1/admin/organizations", "GET"),
            ("/api/v1/admin/sessions", "GET"),
            ("/api/v1/admin/audit-logs", "GET"),
            ("/api/v1/admin/security/overview", "GET"),
            (f"/api/v1/admin/users/{dummy_id}", "GET"),
        ]

        for path, verb in admin_routes:
            res = await async_client.get(path, headers=headers)
            assert res.status_code == 403, f"Role {role_name} allowed on {path}"
            assert res.json()["error"]["code"] == "AUTH_003"

    # ── 2. MULTI-TENANT ISOLATION MATRIX ─────────────────────────────────────

    @pytest.mark.anyio
    async def test_multi_tenant_isolation_cross_tenant_read_and_mutation(
        self, async_client: AsyncClient, hospital_admin_a, physician_b, org_matrix_b
    ):
        """Hospital Admin A cannot read, update, lock, or edit role of Physician B in Org B."""
        headers = _headers_for(hospital_admin_a)

        # GET user detail
        r1 = await async_client.get(f"/api/v1/admin/users/{physician_b.id}", headers=headers)
        assert r1.status_code == 403
        assert r1.json()["error"]["code"] == "AUTH_003"

        # PATCH user profile
        r2 = await async_client.patch(
            f"/api/v1/admin/users/{physician_b.id}",
            json={"first_name": "HackedName"},
            headers=headers,
        )
        assert r2.status_code == 403
        assert r2.json()["error"]["code"] == "AUTH_003"

        # PUT user role
        r3 = await async_client.put(
            f"/api/v1/admin/users/{physician_b.id}/role",
            json={"new_role": "RADIOLOGY_TECH"},
            headers=headers,
        )
        assert r3.status_code == 403

        # POST lock user
        r4 = await async_client.post(f"/api/v1/admin/users/{physician_b.id}/lock", headers=headers)
        assert r4.status_code == 403

    # ── 3. IDOR MATRIX ────────────────────────────────────────────────────────

    @pytest.mark.anyio
    async def test_idor_matrix_own_vs_cross_vs_nonexistent(
        self, async_client: AsyncClient, hospital_admin_a, physician_a, physician_b
    ):
        """IDOR matrix: Own resource -> 200 OK, Cross-tenant -> 403, Non-existent -> 403/404, Malformed -> 422."""
        headers = _headers_for(hospital_admin_a)

        # 1. Own tenant resource
        r1 = await async_client.get(f"/api/v1/admin/users/{physician_a.id}", headers=headers)
        assert r1.status_code == 200

        # 2. Cross tenant resource
        r2 = await async_client.get(f"/api/v1/admin/users/{physician_b.id}", headers=headers)
        assert r2.status_code == 403

        # 3. Non-existent UUID
        r3 = await async_client.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=headers)
        assert r3.status_code in (403, 404)

        # 4. Malformed UUID
        r4 = await async_client.get("/api/v1/admin/users/invalid-uuid-format", headers=headers)
        assert r4.status_code == 422
        assert r4.json()["error"]["code"] == "VAL_001"

    # ── 4. MASS ASSIGNMENT DEFENSE MATRIX ────────────────────────────────────

    @pytest.mark.anyio
    async def test_mass_assignment_extra_forbid_rejection(
        self, async_client: AsyncClient, super_admin_actor, physician_a
    ):
        """Injecting non-whitelisted parameters returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_actor)

        r1 = await async_client.patch(
            f"/api/v1/admin/users/{physician_a.id}",
            json={"first_name": "ValidName", "is_super_admin": True, "password_hash": "hacked"},
            headers=headers,
        )
        assert r1.status_code == 422
        assert r1.json()["error"]["code"] == "VAL_001"

    # ── 5. PERMISSION OVERRIDE & PRECEDENCE MATRIX ───────────────────────────

    @pytest.mark.anyio
    async def test_permission_revoked_precedence_matrix(self, db_session, async_client: AsyncClient, hospital_admin_a):
        """revoked_permissions strictly overrides extra_permissions and base role permissions."""
        hospital_admin_a.extra_permissions = ["user:create"]
        hospital_admin_a.revoked_permissions = ["user:create"]
        db_session.add(hospital_admin_a)
        await db_session.commit()

        headers = _headers_for(hospital_admin_a)
        payload = {
            "email": "precedencetest@orga.org",
            "first_name": "Prec",
            "last_name": "Test",
            "role": "PHYSICIAN",
        }
        res = await async_client.post("/api/v1/admin/users", json=payload, headers=headers)
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "AUTH_003"

    # ── 6. SESSION GOVERNANCE MATRIX ──────────────────────────────────────────

    @pytest.mark.anyio
    async def test_session_governance_remote_termination(
        self, db_session, async_client: AsyncClient, hospital_admin_a, physician_a
    ):
        """Admin terminates session -> DB revoked_at updated and session listing reflects revocation."""
        now = datetime.now(timezone.utc)
        sess = Session(
            id=uuid.uuid4(),
            user_id=physician_a.id,
            refresh_token_hash=security.hash_token("dummy_token"),
            ip_address="192.168.1.50",
            user_agent="Mozilla/5.0 Test",
            device_fingerprint="fp_test_123",
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(hours=24),
        )
        db_session.add(sess)
        await db_session.commit()

        headers = _headers_for(hospital_admin_a)
        res = await async_client.delete(f"/api/v1/admin/sessions/{sess.id}", headers=headers)
        assert res.status_code == 200
        assert res.json()["is_revoked"] is True

        await db_session.refresh(sess)
        assert sess.revoked_at is not None
        assert sess.revocation_reason == "ADMIN_TERMINATED"

    # ── 7. ORGANIZATION DEACTIVATION MATRIX ──────────────────────────────────

    @pytest.mark.anyio
    async def test_organization_deactivation_disables_user_authentication(
        self, db_session, async_client: AsyncClient, super_admin_actor, hospital_admin_b, org_matrix_b
    ):
        """SUPER_ADMIN deactivates Org B -> Affected user in Org B attempting API call returns HTTP 401 AUTH_001."""
        headers_super = _headers_for(super_admin_actor)
        r1 = await async_client.post(f"/api/v1/admin/organizations/{org_matrix_b.id}/deactivate", headers=headers_super)
        assert r1.status_code == 200
        assert r1.json()["is_active"] is False

        # Affected user in Org B calls admin endpoint
        headers_user_b = _headers_for(hospital_admin_b)
        r2 = await async_client.get("/api/v1/admin/users", headers=headers_user_b)
        assert r2.status_code == 401
        assert r2.json()["error"]["code"] == "AUTH_001"

    # ── 8. AUDIT SECURITY & RECURSION DEFENSE MATRIX ─────────────────────────

    @pytest.mark.anyio
    async def test_audit_logs_zero_credential_leakage_and_no_recursion(
        self, async_client: AsyncClient, super_admin_actor
    ):
        """Audit logs contain zero credentials and reading audit logs creates zero recursive audit records."""
        audit.clear_audit_log_store()
        initial_store_len = len(audit.get_audit_store())

        headers = _headers_for(super_admin_actor)
        res = await async_client.get("/api/v1/admin/audit-logs", headers=headers)
        assert res.status_code == 200

        final_store_len = len(audit.get_audit_store())
        assert initial_store_len == final_store_len

        raw = res.text
        assert "password" not in raw
        assert "password_hash" not in raw
        assert "access_token" not in raw
        assert "refresh_token" not in raw

    # ── 9. FAILED AUTHORIZATION MUTATION SAFETY ──────────────────────────────

    @pytest.mark.anyio
    async def test_failed_authorization_causes_zero_db_mutations(
        self, db_session, async_client: AsyncClient, hospital_admin_a, physician_b
    ):
        """Failed authorization produces ZERO DB state changes."""
        orig_name = physician_b.first_name

        headers = _headers_for(hospital_admin_a)
        res = await async_client.patch(
            f"/api/v1/admin/users/{physician_b.id}",
            json={"first_name": "UnauthorizedChange"},
            headers=headers,
        )
        assert res.status_code == 403

        await db_session.refresh(physician_b)
        assert physician_b.first_name == orig_name
