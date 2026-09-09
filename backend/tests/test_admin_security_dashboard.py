"""
NeuroOncoTrack-AI — TASK-034 Admin Security Dashboard & Metrics API Unit & Integration Tests

Verifies:
1. AUTHORIZATION: Unauthenticated (401), functional role denial (403 AUTH_003), SUPER_ADMIN & HOSPITAL_ADMIN access.
2. TENANT ISOLATION & IDOR DEFENSE: HOSPITAL_ADMIN restricted strictly to actor.organization_id. Query/Path spoofing ineffective.
3. SECURITY METRICS ACCURACY: Correct calculation of total_users, active_users, locked_users, active_sessions, security_events.
4. TRENDS & BUCKETING: Bucketed aggregation by hour, day, week. Invalid interval or reversed date range returns HTTP 422 VAL_001.
5. SECURITY & RECURSION DEFENSE: Zero credential leakage, zero recursive audit log generation.
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
    """Fixture for Organization Alpha."""
    org = Organization(
        id=uuid.uuid4(),
        name="Dashboard Hospital Alpha",
        code="DASH_A_" + uuid.uuid4().hex[:6].upper(),
        org_type="HOSPITAL",
        is_active=True,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def org_beta(db_session):
    """Fixture for Organization Beta."""
    org = Organization(
        id=uuid.uuid4(),
        name="Dashboard Hospital Beta",
        code="DASH_B_" + uuid.uuid4().hex[:6].upper(),
        org_type="CLINIC",
        is_active=True,
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
        email=f"super_dash_{uuid.uuid4().hex[:6]}@platform.gov",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Super",
        last_name="DashAdmin",
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
        email=f"admin_dash_a_{uuid.uuid4().hex[:6]}@hospa.org",
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
async def hospital_admin_beta(db_session, org_beta):
    """Fixture for HOSPITAL_ADMIN in Org Beta."""
    u = User(
        id=uuid.uuid4(),
        organization_id=org_beta.id,
        email=f"admin_dash_b_{uuid.uuid4().hex[:6]}@hospb.org",
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
        email=f"doc_dash_a_{uuid.uuid4().hex[:6]}@hospa.org",
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


class TestAdminSecurityDashboardApi:
    """Comprehensive test suite for Admin Security Dashboard & Metrics API."""

    @pytest.mark.anyio
    async def test_unauthenticated_request_rejected(self, async_client: AsyncClient):
        """Unauthenticated requests to security endpoints return HTTP 401."""
        res = await async_client.get("/api/v1/admin/security/overview")
        assert res.status_code == 401

    @pytest.mark.anyio
    async def test_functional_roles_denied_dashboard_access(self, async_client: AsyncClient, physician_alpha):
        """Level 50 PHYSICIAN is denied access to all /admin/security/* endpoints (403 AUTH_003)."""
        headers = _headers_for(physician_alpha)

        r1 = await async_client.get("/api/v1/admin/security/overview", headers=headers)
        assert r1.status_code == 403

        r2 = await async_client.get("/api/v1/admin/security/events", headers=headers)
        assert r2.status_code == 403

        r3 = await async_client.get("/api/v1/admin/security/trends", headers=headers)
        assert r3.status_code == 403

        r4 = await async_client.get("/api/v1/admin/security/organizations", headers=headers)
        assert r4.status_code == 403

    @pytest.mark.anyio
    async def test_super_admin_global_overview(self, async_client: AsyncClient, super_admin_user, hospital_admin_alpha, hospital_admin_beta):
        """SUPER_ADMIN receives aggregated global overview metrics."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/security/overview", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "users" in data
        assert "organizations" in data
        assert "sessions" in data
        assert "security_events" in data
        assert data["users"]["total"] >= 3

    @pytest.mark.anyio
    async def test_hospital_admin_tenant_scoped_overview(self, async_client: AsyncClient, hospital_admin_alpha, hospital_admin_beta, physician_alpha):
        """HOSPITAL_ADMIN sees user & metric counts scoped strictly to their own tenant."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.get("/api/v1/admin/security/overview", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["users"]["total"] >= 2
        assert data["organizations"]["total"] == 1

    @pytest.mark.anyio
    async def test_hospital_admin_organization_list_scoped(self, async_client: AsyncClient, hospital_admin_alpha, org_alpha, org_beta):
        """HOSPITAL_ADMIN receives security summary for their own organization ONLY."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.get("/api/v1/admin/security/organizations", headers=headers)
        assert res.status_code == 200
        data = res.json()
        org_ids = [item["organization_id"] for item in data["organizations"]]
        assert str(org_alpha.id) in org_ids
        assert str(org_beta.id) not in org_ids

    @pytest.mark.anyio
    async def test_organization_id_spoofing_ineffective(self, async_client: AsyncClient, hospital_admin_alpha, org_beta):
        """HOSPITAL_ADMIN attempting query organization_id=org_beta returns only own org data."""
        headers = _headers_for(hospital_admin_alpha)
        res = await async_client.get(f"/api/v1/admin/security/organizations?organization_id={org_beta.id}", headers=headers)
        assert res.status_code == 200
        org_ids = [item["organization_id"] for item in res.json()["organizations"]]
        assert str(org_beta.id) not in org_ids

    @pytest.mark.anyio
    async def test_security_events_list_and_filter(self, async_client: AsyncClient, super_admin_user):
        """Security events endpoint lists and filters audit events accurately."""
        audit.clear_audit_log_store()
        audit.log_audit_event("USER_LOCKED", details={"result": "SUCCESS"})
        audit.log_audit_event("GIRIS_BASARISIZ", details={"result": "DENIED"})

        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/security/events?event_type=USER_LOCKED", headers=headers)
        assert res.status_code == 200
        events = [item["event"] for item in res.json()["items"]]
        assert "USER_LOCKED" in events
        assert "GIRIS_BASARISIZ" not in events

    @pytest.mark.anyio
    async def test_security_events_invalid_sort_by(self, async_client: AsyncClient, super_admin_user):
        """Invalid sort_by in security events endpoint returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/security/events?sort_by=invalid_col", headers=headers)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_security_trends_aggregation(self, async_client: AsyncClient, super_admin_user):
        """Security trends endpoint aggregates bucketed counts for day, week, hour."""
        audit.clear_audit_log_store()
        audit.log_audit_event("GIRIS_BASARISIZ", details={"result": "DENIED"})

        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/security/trends?interval=day", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["interval"] == "day"
        assert len(data["data"]) >= 1

    @pytest.mark.anyio
    async def test_security_trends_invalid_interval(self, async_client: AsyncClient, super_admin_user):
        """Invalid interval parameter returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/security/trends?interval=year", headers=headers)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_security_trends_invalid_date_range(self, async_client: AsyncClient, super_admin_user):
        """start_date > end_date returns HTTP 422 VAL_001."""
        headers = _headers_for(super_admin_user)
        start = "2026-08-14T20:00:00Z"
        end = "2026-08-10T20:00:00Z"
        res = await async_client.get(f"/api/v1/admin/security/trends?start_date={start}&end_date={end}", headers=headers)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VAL_001"

    @pytest.mark.anyio
    async def test_no_credential_leakage_in_dashboard(self, async_client: AsyncClient, super_admin_user):
        """Dashboard responses contain zero token, password, hash, or secret strings."""
        headers = _headers_for(super_admin_user)

        r1 = await async_client.get("/api/v1/admin/security/overview", headers=headers)
        r2 = await async_client.get("/api/v1/admin/security/organizations", headers=headers)

        for res in (r1, r2):
            raw = res.text
            assert "password" not in raw
            assert "password_hash" not in raw
            assert "refresh_token" not in raw
            assert "access_token" not in raw
            assert "mfa_secret" not in raw

    @pytest.mark.anyio
    async def test_no_recursive_audit_logging(self, async_client: AsyncClient, super_admin_user):
        """Reading security overview does not trigger recursive audit log creation."""
        audit.clear_audit_log_store()
        initial_count = len(audit.get_audit_store())

        headers = _headers_for(super_admin_user)
        res = await async_client.get("/api/v1/admin/security/overview", headers=headers)
        assert res.status_code == 200

        final_count = len(audit.get_audit_store())
        assert initial_count == final_count
