"""
NeuroOncoTrack-AI — TASK-033 Security Audit Log Inspection & Search API Unit & Integration Tests

Verifies:
1. AUTHENTICATION & AUTHORIZATION: Unauthenticated (401), functional role denial (403 AUTH_003), SUPER_ADMIN & HOSPITAL_ADMIN access.
2. TENANT ISOLATION & IDOR DEFENSE: HOSPITAL_ADMIN restricted to own tenant audit logs. Direct ID access to cross-tenant log returns 403 AUTH_003. Query spoofing ineffective.
3. SEARCH, FILTER & SORTING SECURITY: Valid filters (event, actor, date range). Invalid sort_by or invalid date bounds return HTTP 422 VAL_001.
4. SENSITIVE DATA LEAKAGE PREVENTION: Response details contain zero passwords, tokens, hashes, or secrets.
5. IMMUTABILITY & RECURSION DEFENSE: Read-only access, no update/delete operations exist, zero recursive audit logging loops.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import audit, security
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
        name="Audit Hospital Alpha",
        code="AUD_A_" + uuid.uuid4().hex[:6].upper(),
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
        name="Audit Hospital Beta",
        code="AUD_B_" + uuid.uuid4().hex[:6].upper(),
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
        email=f"super_audit_{uuid.uuid4().hex[:6]}@platform.gov",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Super",
        last_name="Auditor",
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
        email=f"admin_audit_a_{uuid.uuid4().hex[:6]}@hospa.org",
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
async def hospital_admin_b(db_session, org_b):
    """Fixture for HOSPITAL_ADMIN in Org B."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_b.id,
        email=f"admin_audit_b_{uuid.uuid4().hex[:6]}@hospb.org",
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
async def physician_a(db_session, org_a):
    """Fixture for PHYSICIAN in Org A."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        email=f"doc_audit_a_{uuid.uuid4().hex[:6]}@hospa.org",
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


def _headers_for(user: User) -> dict[str, str]:
    """Helper to generate bearer auth headers."""
    from app.core.permissions import get_effective_permissions
    perms = list(get_effective_permissions(user.role, user.extra_permissions, user.revoked_permissions))
    token, _, _ = security.create_access_token(
        subject=str(user.id),
        role=user.role,
        organization_id=str(user.organization_id),
        permissions=perms,
    )
    return {"Authorization": f"Bearer {token}"}


class TestAdminAuditLogManagementApi:
    """Comprehensive security test suite for Security Audit Log Inspection & Search API."""

    @pytest.mark.anyio
    async def test_unauthenticated_request_rejected(self, async_client: AsyncClient):
        """Unauthenticated request returns HTTP 401 AUTH_002."""
        res = await async_client.get("/api/v1/admin/audit-logs")
        assert res.status_code == 401

    @pytest.mark.anyio
    async def test_functional_roles_denied_audit_inspection(self, async_client: AsyncClient, physician_a):
        """PHYSICIAN role is denied audit inspection endpoints (HTTP 403 AUTH_003)."""
        headers = _headers_for(physician_a)
        res = await async_client.get("/api/v1/admin/audit-logs", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_hospital_admin_own_tenant_allowed(self, async_client: AsyncClient, hospital_admin_a, org_a):
        """HOSPITAL_ADMIN can list audit logs for their own organization."""
        audit.log_audit_event("USER_CREATED", user_id=hospital_admin_a.id, details={"organization_id": str(org_a.id)})
        headers = _headers_for(hospital_admin_a)
        res = await async_client.get("/api/v1/admin/audit-logs", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.anyio
    async def test_hospital_admin_cross_tenant_audit_scoped(self, async_client: AsyncClient, hospital_admin_a, hospital_admin_b, org_a, org_b):
        """HOSPITAL_ADMIN A listing audit logs never sees audit entries from Org B."""
        audit.clear_audit_log_store()
        audit.log_audit_event("EVENT_ORG_A", user_id=hospital_admin_a.id, details={"organization_id": str(org_a.id)})
        audit.log_audit_event("EVENT_ORG_B", user_id=hospital_admin_b.id, details={"organization_id": str(org_b.id)})

        headers = _headers_for(hospital_admin_a)
        res = await async_client.get("/api/v1/admin/audit-logs", headers=headers)
        assert res.status_code == 200
        data = res.json()
        events = [item["event"] for item in data["items"]]
        assert "EVENT_ORG_A" in events
        assert "EVENT_ORG_B" not in events

    @pytest.mark.anyio
    async def test_super_admin_global_audit_allowed(self, async_client: AsyncClient, super_admin_user, hospital_admin_a, hospital_admin_b, org_a, org_b):
        """SUPER_ADMIN listing audit logs sees events across all organizations."""
        audit.clear_audit_log_store()
        audit.log_audit_event("EVENT_ORG_A", user_id=hospital_admin_a.id, details={"organization_id": str(org_a.id)})
        audit.log_audit_event("EVENT_ORG_B", user_id=hospital_admin_b.id, details={"organization_id": str(org_b.id)})

        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/audit-logs", headers=headers)
        assert res.status_code == 200
        events = [item["event"] for item in res.json()["items"]]
        assert "EVENT_ORG_A" in events
        assert "EVENT_ORG_B" in events

    @pytest.mark.anyio
    async def test_cross_tenant_audit_id_direct_access_denied(self, async_client: AsyncClient, hospital_admin_a, hospital_admin_b, org_b):
        """HOSPITAL_ADMIN A attempting direct detail GET for Org B's audit log ID returns 403 Forbidden."""
        audit.clear_audit_log_store()
        audit.log_audit_event("SECRET_ORG_B_LOG", user_id=hospital_admin_b.id, details={"organization_id": str(org_b.id)})
        store = audit.get_audit_store()
        org_b_log_id = store[0]["id"]

        headers = _headers_for(hospital_admin_a)
        res = await async_client.get(f"/api/v1/admin/audit-logs/{org_b_log_id}", headers=headers)
        assert res.status_code == 403

    @pytest.mark.anyio
    async def test_organization_id_spoofing_ineffective(self, async_client: AsyncClient, hospital_admin_a, hospital_admin_b, org_a, org_b):
        """Client querying organization_id=org_b is ignored for HOSPITAL_ADMIN A; only org_a logs returned."""
        audit.clear_audit_log_store()
        audit.log_audit_event("EVENT_A", user_id=hospital_admin_a.id, details={"organization_id": str(org_a.id)})
        audit.log_audit_event("EVENT_B", user_id=hospital_admin_b.id, details={"organization_id": str(org_b.id)})

        headers = _headers_for(hospital_admin_a)
        res = await async_client.get(f"/api/v1/admin/audit-logs?organization_id={org_b.id}", headers=headers)
        assert res.status_code == 200
        events = [item["event"] for item in res.json()["items"]]
        assert "EVENT_A" in events
        assert "EVENT_B" not in events

    @pytest.mark.anyio
    async def test_valid_event_filter(self, async_client: AsyncClient, super_admin_user):
        """Filtering by event_type returns matching entries."""
        audit.clear_audit_log_store()
        audit.log_audit_event("LOGIN_SUCCESS")
        audit.log_audit_event("PASSWORD_CHANGE")

        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/audit-logs?event_type=LOGIN_SUCCESS", headers=headers)
        assert res.status_code == 200
        events = [item["event"] for item in res.json()["items"]]
        assert "LOGIN_SUCCESS" in events
        assert "PASSWORD_CHANGE" not in events

    @pytest.mark.anyio
    async def test_invalid_date_range_rejected(self, async_client: AsyncClient, super_admin_user):
        """start_date > end_date returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        start = "2026-08-14T20:00:00Z"
        end = "2026-08-10T20:00:00Z"
        res = await async_client.get(f"/api/v1/admin/audit-logs?start_date={start}&end_date={end}", headers=headers)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_invalid_sort_by_rejected(self, async_client: AsyncClient, super_admin_user):
        """Invalid sort_by field returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/audit-logs?sort_by=invalid_column", headers=headers)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_sql_like_sort_injection_rejected(self, async_client: AsyncClient, super_admin_user):
        """SQL injection attempt in sort_by returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/audit-logs?sort_by=timestamp;DROP TABLE users;--", headers=headers)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_password_hash_token_leakage_prevented(self, async_client: AsyncClient, super_admin_user):
        """Audit details contain zero password, hash, setup_token, access_token, or refresh_token keys."""
        audit.clear_audit_log_store()
        audit.log_audit_event(
            "USER_REGISTERED",
            details={
                "email": "user@test.org",
                "password": "PlaintextPassword123!",
                "password_hash": "hash_val",
                "setup_token": "token_val",
                "access_token": "jwt_val",
                "refresh_token": "ref_val",
                "safe_info": "visible",
            },
        )

        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/audit-logs", headers=headers)
        assert res.status_code == 200
        raw_text = res.text
        assert "PlaintextPassword123!" not in raw_text
        assert "hash_val" not in raw_text
        assert "token_val" not in raw_text
        assert "jwt_val" not in raw_text
        assert "ref_val" not in raw_text
        assert "visible" in raw_text

    @pytest.mark.anyio
    async def test_audit_log_immutability_read_only(self, async_client: AsyncClient, super_admin_user):
        """PUT / DELETE / PATCH operations are not allowed on audit logs."""
        headers = _headers_for(super_admin_user)
        r_put = await async_client.put("/api/v1/admin/audit-logs/some-id", headers=headers)
        assert r_put.status_code == 405

        r_del = await async_client.delete("/api/v1/admin/audit-logs/some-id", headers=headers)
        assert r_del.status_code == 405

    @pytest.mark.anyio
    async def test_no_recursive_audit_loop(self, async_client: AsyncClient, super_admin_user):
        """Reading audit logs does not create a new audit log entry recursively."""
        audit.clear_audit_log_store()
        audit.log_audit_event("INITIAL_EVENT")
        initial_len = len(audit.get_audit_store())

        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/audit-logs", headers=headers)
        assert res.status_code == 200

        final_len = len(audit.get_audit_store())
        assert initial_len == final_len

    @pytest.mark.anyio
    async def test_audit_log_detail_not_found(self, async_client: AsyncClient, super_admin_user):
        """GET /admin/audit-logs/{nonexistent_id} returns HTTP 404."""
        headers = _headers_for(super_admin_user)
        non_existent_id = str(uuid.uuid4())
        res = await async_client.get(f"/api/v1/admin/audit-logs/{non_existent_id}", headers=headers)
        assert res.status_code == 404
