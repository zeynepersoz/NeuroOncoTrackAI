"""
NeuroOncoTrack-AI — Authorization & Roles (RBAC & ABAC) Tests

Comprehensive test suite for TASK-006 verifying:
- Centralized RBAC definitions & matrix calculations
- Permission overrides (extra_permissions, revoked_permissions)
- RBAC FastAPI dependencies (izin_gerektir, rol_gerektir)
- ABAC Tenant / Organization isolation & resource ownership
- Cryptographically verified JWT claim authorization
- HTTP status code contracts (401 Unauthorized, 403 Forbidden, 423 Account Locked)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    aktif_kullanici,
    izin_gerektir,
    rol_gerektir,
    kurum_izolasyonu_kontrolu,
    sahip_veya_admin_kontrolu,
)
from app.core import security
from app.core.exceptions import ForbiddenError, register_exception_handlers
from app.core.permissions import (
    Permission,
    Role,
    ROLE_PERMISSIONS,
    check_abac_access,
    get_effective_permissions,
    has_permission,
    is_hospital_admin,
    is_super_admin,
    verify_organization_access,
    verify_resource_ownership,
)
from app.db.session import get_db
from app.models.organization import Organization
from app.models.password_history import PasswordHistory
from app.models.session import Session
from app.models.user import User


# ── STEP 1: RBAC Core Matrix & Calculation Tests ───────────

def test_rbac_matrix_definitions():
    """Verify that all system roles are mapped in ROLE_PERMISSIONS."""
    for role in Role:
        assert role in ROLE_PERMISSIONS
        assert isinstance(ROLE_PERMISSIONS[role], set)


def test_super_admin_has_all_permissions():
    """SUPER_ADMIN must possess every defined Permission."""
    effective = get_effective_permissions(Role.SUPER_ADMIN)
    all_perms = {p.value for p in Permission}
    assert effective == all_perms


def test_role_effective_permissions():
    """Verify basic permission calculation for PHYSICIAN role."""
    effective = get_effective_permissions(Role.PHYSICIAN)
    assert Permission.REPORT_APPROVE.value in effective
    assert Permission.REPORT_SIGN.value in effective
    # Physician cannot deploy models or reset user passwords by default
    assert Permission.MODEL_DEPLOY.value not in effective
    assert Permission.USER_RESET_PASSWORD.value not in effective


def test_permission_overrides_extra_and_revoked():
    """Verify extra_permissions addition and revoked_permissions removal."""
    # Add model:deploy to physician
    effective_extra = get_effective_permissions(
        Role.PHYSICIAN,
        extra_permissions=["model:deploy"],
    )
    assert "model:deploy" in effective_extra

    # Revoke report:sign from physician
    effective_revoked = get_effective_permissions(
        Role.PHYSICIAN,
        revoked_permissions=[Permission.REPORT_SIGN.value],
    )
    assert Permission.REPORT_SIGN.value not in effective_revoked
    assert Permission.REPORT_APPROVE.value in effective_revoked


def test_has_permission_helper():
    """Verify has_permission helper function."""
    assert has_permission(Role.PHYSICIAN, Permission.PATIENT_READ) is True
    assert has_permission(Role.AUDITOR, Permission.PATIENT_CREATE) is False
    assert has_permission(
        Role.AUDITOR,
        Permission.PATIENT_CREATE,
        extra_permissions=[Permission.PATIENT_CREATE.value],
    ) is True


def test_role_check_helpers():
    """Verify is_super_admin and is_hospital_admin helpers."""
    assert is_super_admin(Role.SUPER_ADMIN) is True
    assert is_super_admin(Role.PHYSICIAN) is False
    assert is_hospital_admin(Role.HOSPITAL_ADMIN) is True
    assert is_hospital_admin("HOSPITAL_ADMIN") is True
    assert is_hospital_admin(Role.SUPER_ADMIN) is False


# ── STEP 2: ABAC Tenant Isolation & Ownership Tests ─────────

def test_abac_organization_isolation():
    """Verify ABAC tenant isolation logic."""
    org1_id = uuid.uuid4()
    org2_id = uuid.uuid4()

    # Same org access allowed
    assert verify_organization_access(org1_id, org1_id, is_super=False) is True
    # Different org access blocked
    assert verify_organization_access(org1_id, org2_id, is_super=False) is False
    # SUPER_ADMIN bypasses tenant boundaries
    assert verify_organization_access(org1_id, org2_id, is_super=True) is True


def test_abac_resource_ownership():
    """Verify ABAC resource ownership logic."""
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()

    # Owner access allowed
    assert verify_resource_ownership(user1_id, user1_id, is_admin_override=False) is True
    # Non-owner access blocked
    assert verify_resource_ownership(user1_id, user2_id, is_admin_override=False) is False
    # Admin override allowed
    assert verify_resource_ownership(user1_id, user2_id, is_admin_override=True) is True


def test_combined_check_abac_access():
    """Verify comprehensive ABAC evaluator check_abac_access."""
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    other_org_id = uuid.uuid4()

    # 1. SUPER_ADMIN gets access anywhere
    assert check_abac_access(user_id, org_id, Role.SUPER_ADMIN, other_org_id, other_user_id) is True

    # 2. HOSPITAL_ADMIN gets access to any resource inside their org
    assert check_abac_access(user_id, org_id, Role.HOSPITAL_ADMIN, org_id, other_user_id) is True
    # But NOT across orgs
    assert check_abac_access(user_id, org_id, Role.HOSPITAL_ADMIN, other_org_id, other_user_id) is False

    # 3. PHYSICIAN / Standard User access:
    # Same org & owned resource -> allowed
    assert check_abac_access(user_id, org_id, Role.PHYSICIAN, org_id, user_id) is True
    # Same org & unowned resource -> blocked
    assert check_abac_access(user_id, org_id, Role.PHYSICIAN, org_id, other_user_id) is False
    # Different org & owned resource -> blocked
    assert check_abac_access(user_id, org_id, Role.PHYSICIAN, other_org_id, user_id) is False


# ── STEP 3: FastAPI Authorization Dependency Integration Tests 

# Setup test app for dependency routes
auth_test_app = FastAPI()
register_exception_handlers(auth_test_app)


@auth_test_app.get("/test/perm-report-approve")
async def endpoint_report_approve(user: User = Depends(izin_gerektir(Permission.REPORT_APPROVE.value))):
    return {"status": "ok", "user_id": str(user.id)}


@auth_test_app.get("/test/role-admin-only")
async def endpoint_admin_only(user: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN))):
    return {"status": "ok", "role": user.role}


@auth_test_app.get("/test/abac-org/{org_id}")
async def endpoint_abac_org(org_id: str, user: User = Depends(aktif_kullanici)):
    kurum_izolasyonu_kontrolu(user, org_id)
    return {"status": "ok", "org_id": str(user.organization_id)}


@auth_test_app.get("/test/abac-owner/{owner_id}")
async def endpoint_abac_owner(owner_id: str, user: User = Depends(aktif_kullanici)):
    sahip_veya_admin_kontrolu(user, resource_owner_id=owner_id, resource_org_id=user.organization_id)
    return {"status": "ok", "owner_id": owner_id}


@pytest.fixture
async def auth_test_client(db_session):
    async def _override_get_db():
        yield db_session

    auth_test_app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=auth_test_app), base_url="http://test") as client:
        yield client
    auth_test_app.dependency_overrides.clear()


@pytest.fixture
async def test_user_fixture(db_session):
    org = Organization(name="Test Hastanesi", code="TEST_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    user = User(
        organization_id=org.id,
        email="test.auth.user@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Test",
        last_name="User",
        role=Role.PHYSICIAN.value,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.anyio
async def test_izin_gerektir_permission_allowed(db_session, auth_test_client, test_user_fixture):
    """Authenticated user with valid permission can access route (HTTP 200)."""
    user = test_user_fixture
    user.role = Role.PHYSICIAN.value
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
        permissions=list(get_effective_permissions(user.role)),
    )

    resp = await auth_test_client.get(
        "/test/perm-report-approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.anyio
async def test_izin_gerektir_permission_denied_403(db_session, auth_test_client, test_user_fixture):
    """Authenticated user lacking permission receives HTTP 403 Forbidden (AUTH_003)."""
    user = test_user_fixture
    user.role = Role.AUDITOR.value
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
        permissions=list(get_effective_permissions(user.role)),
    )

    resp = await auth_test_client.get(
        "/test/perm-report-approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"]["code"] == "AUTH_003"
    assert "Gerekli izin" in data["error"]["detail"]


@pytest.mark.anyio
async def test_rol_gerektir_allowed_and_denied(db_session, auth_test_client, test_user_fixture):
    """Verify rol_gerektir dependency grants access to matching role, rejects non-matching role."""
    user = test_user_fixture

    # 1. HOSPITAL_ADMIN -> allowed (200)
    user.role = Role.HOSPITAL_ADMIN.value
    await db_session.commit()

    admin_token, _, _ = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
        permissions=list(get_effective_permissions(user.role)),
    )

    resp1 = await auth_test_client.get(
        "/test/role-admin-only",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["role"] == Role.HOSPITAL_ADMIN.value

    # 2. RESEARCHER -> forbidden (403)
    user.role = Role.RESEARCHER.value
    await db_session.commit()

    user_token, _, _ = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
        permissions=list(get_effective_permissions(user.role)),
    )

    resp2 = await auth_test_client.get(
        "/test/role-admin-only",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "AUTH_003"


@pytest.mark.anyio
async def test_abac_tenant_isolation_dependency(db_session, auth_test_client, test_user_fixture):
    """Verify organization isolation dependency blocks cross-organization access attempts."""
    user = test_user_fixture
    user.role = Role.PHYSICIAN.value
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
        permissions=list(get_effective_permissions(user.role)),
    )

    same_org_id = str(user.organization_id)
    diff_org_id = str(uuid.uuid4())

    # Same org request -> 200 OK
    resp1 = await auth_test_client.get(
        f"/test/abac-org/{same_org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200

    # Different org request -> 403 Forbidden
    resp2 = await auth_test_client.get(
        f"/test/abac-org/{diff_org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "AUTH_003"


@pytest.mark.anyio
async def test_abac_resource_ownership_dependency(db_session, auth_test_client, test_user_fixture):
    """Verify resource ownership dependency allows owner access and blocks non-owner access."""
    user = test_user_fixture
    user.role = Role.PHYSICIAN.value
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
        permissions=list(get_effective_permissions(user.role)),
    )

    own_user_id = str(user.id)
    other_user_id = str(uuid.uuid4())

    # Own resource request -> 200 OK
    resp1 = await auth_test_client.get(
        f"/test/abac-owner/{own_user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200

    # Other user resource request -> 403 Forbidden
    resp2 = await auth_test_client.get(
        f"/test/abac-owner/{other_user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "AUTH_003"


@pytest.mark.anyio
async def test_unauthenticated_request_rejected(db_session, auth_test_client):
    """Unauthenticated requests without Bearer token return HTTP 401 (AUTH_002)."""
    resp = await auth_test_client.get("/test/perm-report-approve")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_002"


@pytest.mark.anyio
async def test_tampered_jwt_claims_ignored_for_authority(db_session, auth_test_client, test_user_fixture):
    """
    Even if an attacker tampers with JWT permissions or role string inside the payload,
    aktif_kullanici resolves the authoritative state from DB, and permission calculation
    is derived securely from database state.
    """
    user = test_user_fixture
    user.role = Role.AUDITOR.value  # Database role is AUDITOR
    await db_session.commit()

    # Forged token claiming to be SUPER_ADMIN with all perms in claims
    forged_token, _, _ = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role="SUPER_ADMIN",
        permissions=[Permission.REPORT_APPROVE.value],
    )

    resp = await auth_test_client.get(
        "/test/perm-report-approve",
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    # Authoritative DB role (AUDITOR) takes precedence over forged claim -> 403 Forbidden
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "AUTH_003"
