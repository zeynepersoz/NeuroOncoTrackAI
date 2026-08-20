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
    rol_atamasi_kontrolu,
)
from app.core import security
from app.core.exceptions import ForbiddenError, register_exception_handlers
from app.core.permissions import (
    Permission,
    Role,
    ROLE_PERMISSIONS,
    ROLE_HIERARCHY_LEVELS,
    can_assign_role,
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


def test_revoked_permissions_always_overrides_extra_permissions():
    """Conflict Resolution Rule: revoked_permissions ALWAYS overrides extra_permissions."""
    # Add AND revoke report:sign on PHYSICIAN
    effective = get_effective_permissions(
        Role.PHYSICIAN,
        extra_permissions=[Permission.REPORT_SIGN, "ai:override"],
        revoked_permissions=[Permission.REPORT_SIGN, Permission.AI_OVERRIDE],
    )
    # Both REPORT_SIGN and AI_OVERRIDE must be revoked because revoked takes absolute precedence
    assert Permission.REPORT_SIGN.value not in effective
    assert Permission.AI_OVERRIDE.value not in effective


def test_permission_normalization_and_deduplication():
    """Verify enum/string normalization and deduplication."""
    from app.core.permissions import normalize_permission

    assert normalize_permission(Permission.REPORT_READ) == "report:read"
    assert normalize_permission("  report:read  ") == "report:read"

    effective = get_effective_permissions(
        Role.PHYSICIAN,
        extra_permissions=[Permission.MODEL_DEPLOY, "  model:deploy  ", Permission.MODEL_DEPLOY],
        revoked_permissions=["  report:sign  ", Permission.REPORT_SIGN],
    )
    assert "model:deploy" in effective
    assert Permission.REPORT_SIGN.value not in effective


def test_invalid_role_handling():
    """Verify handling when invalid role string is passed."""
    effective = get_effective_permissions("NON_EXISTENT_ROLE")
    assert effective == set()


def test_can_assign_role_hierarchy_ranking():
    """Verify canonical role hierarchy evaluator can_assign_role."""
    from app.core.permissions import can_assign_role

    assert can_assign_role(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN) is True
    assert can_assign_role(Role.SUPER_ADMIN, Role.PHYSICIAN) is True
    assert can_assign_role(Role.HOSPITAL_ADMIN, Role.PHYSICIAN) is True
    assert can_assign_role(Role.HOSPITAL_ADMIN, Role.AUDITOR) is True

    # Escalation and equal-level attempts blocked
    assert can_assign_role(Role.HOSPITAL_ADMIN, Role.HOSPITAL_ADMIN) is False
    assert can_assign_role(Role.HOSPITAL_ADMIN, Role.SUPER_ADMIN) is False
    assert can_assign_role(Role.PHYSICIAN, Role.AUDITOR) is False
    assert can_assign_role(Role.PHYSICIAN, Role.PHYSICIAN) is False


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
from app.api.v1.admin import router as admin_router

auth_test_app = FastAPI()
register_exception_handlers(auth_test_app)
auth_test_app.include_router(admin_router, prefix="/api/v1")


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


@pytest.mark.anyio
async def test_permission_require_all_vs_require_any(db_session, auth_test_client, test_user_fixture):
    """Test AND semantics (require_all=True) vs OR semantics (require_all=False)."""
    from app.api.deps import izin_gerektir

    user = test_user_fixture
    user.role = Role.PHYSICIAN.value
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
        permissions=list(get_effective_permissions(user.role)),
    )

    # AND (require_all=True) with missing permission -> fails
    dep_all = izin_gerektir(Permission.REPORT_APPROVE, Permission.MODEL_DEPLOY, require_all=True)
    with pytest.raises(ForbiddenError):
        await dep_all(user)

    # OR (require_all=False) with at least one matching permission -> succeeds
    dep_any = izin_gerektir(Permission.REPORT_APPROVE, Permission.MODEL_DEPLOY, require_all=False)
    resolved_user = await dep_any(user)
    assert resolved_user.id == user.id


@pytest.mark.anyio
async def test_empty_permission_or_role_fails_closed(test_user_fixture):
    """Empty permission or role list in dependency factory must fail-closed with ForbiddenError (403)."""
    from app.api.deps import izin_gerektir, rol_gerektir

    user = test_user_fixture

    dep_empty_perm = izin_gerektir()
    with pytest.raises(ForbiddenError) as exc_perm:
        await dep_empty_perm(user)
    assert exc_perm.value.code == "AUTH_003"

    dep_empty_role = rol_gerektir()
    with pytest.raises(ForbiddenError) as exc_role:
        await dep_empty_role(user)
    assert exc_role.value.code == "AUTH_003"


@pytest.mark.anyio
async def test_database_authority_active_revocation_stale_jwt(db_session, auth_test_client, test_user_fixture):
    """
    When permissions are revoked in the DB after JWT issuance,
    subsequent requests using the valid JWT evaluate live DB state and are blocked.
    """
    user = test_user_fixture
    user.role = Role.PHYSICIAN.value
    user.extra_permissions = None
    user.revoked_permissions = None
    await db_session.commit()

    # Issue valid JWT token
    token, _, _ = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
        permissions=list(get_effective_permissions(user.role)),
    )

    # Request succeeds initially
    resp1 = await auth_test_client.get(
        "/test/perm-report-approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200

    # Revoke report:approve in DB live state
    user.revoked_permissions = [Permission.REPORT_APPROVE.value]
    await db_session.commit()

    # Same JWT token is now blocked because DB state is authoritative
    resp2 = await auth_test_client.get(
        "/test/perm-report-approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 403
    assert resp2.json()["error"]["code"] == "AUTH_003"


def test_alias_exports_require_permission_and_require_role():
    """Verify require_permission and require_role aliases exist and match izin_gerektir and rol_gerektir."""
    from app.api.deps import izin_gerektir, require_permission, rol_gerektir, require_role

    assert require_permission is izin_gerektir
    assert require_role is rol_gerektir


# ── STEP 3: TASK-020 ABAC Tenant & Ownership Hardening Tests ─────────

def test_verify_organization_access_abac():
    """Verify verify_organization_access helper with tenant isolation and super admin bypass."""
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()

    # Same organization -> True
    assert verify_organization_access(user_org_id=org_a, resource_org_id=org_a, is_super=False) is True

    # Different organization -> False
    assert verify_organization_access(user_org_id=org_a, resource_org_id=org_b, is_super=False) is False

    # Super admin bypass -> True regardless of org mismatch
    assert verify_organization_access(user_org_id=org_a, resource_org_id=org_b, is_super=True) is True

    # Fail-closed on missing org attributes -> False
    assert verify_organization_access(user_org_id=None, resource_org_id=org_a, is_super=False) is False
    assert verify_organization_access(user_org_id=org_a, resource_org_id=None, is_super=False) is False


def test_verify_resource_ownership_abac():
    """Verify verify_resource_ownership helper with owner check and admin override."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # Same owner -> True
    assert verify_resource_ownership(user_id=user_a, resource_owner_id=user_a, is_admin_override=False) is True

    # Different owner -> False
    assert verify_resource_ownership(user_id=user_a, resource_owner_id=user_b, is_admin_override=False) is False

    # Admin override -> True
    assert verify_resource_ownership(user_id=user_a, resource_owner_id=user_b, is_admin_override=True) is True

    # Fail-closed on missing owner attributes -> False
    assert verify_resource_ownership(user_id=None, resource_owner_id=user_a, is_admin_override=False) is False
    assert verify_resource_ownership(user_id=user_a, resource_owner_id=None, is_admin_override=False) is False


def test_check_abac_access_matrix():
    """Verify combined ABAC evaluator across all role types and tenant scopes."""
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    other_org_id = uuid.uuid4()

    # SUPER_ADMIN bypasses all org and owner boundaries
    assert check_abac_access(user_id, org_id, Role.SUPER_ADMIN, other_org_id, other_user_id) is True

    # HOSPITAL_ADMIN bypasses owner check within same org
    assert check_abac_access(user_id, org_id, Role.HOSPITAL_ADMIN, org_id, other_user_id) is True

    # HOSPITAL_ADMIN blocked on cross-organization access
    assert check_abac_access(user_id, org_id, Role.HOSPITAL_ADMIN, other_org_id, other_user_id) is False

    # PHYSICIAN allowed for own resource within same org
    assert check_abac_access(user_id, org_id, Role.PHYSICIAN, org_id, user_id) is True

    # PHYSICIAN blocked for unowned resource within same org
    assert check_abac_access(user_id, org_id, Role.PHYSICIAN, org_id, other_user_id) is False

    # PHYSICIAN blocked for own resource in different org (cross-tenant IDOR protection)
    assert check_abac_access(user_id, org_id, Role.PHYSICIAN, other_org_id, user_id) is False

    # Fail-closed on missing user attributes
    assert check_abac_access(None, org_id, Role.PHYSICIAN, org_id, user_id) is False
    assert check_abac_access(user_id, None, Role.PHYSICIAN, org_id, user_id) is False


@pytest.mark.anyio
async def test_kurum_izolasyonu_kontrolu_dependency_abac(test_user_fixture):
    """Verify kurum_izolasyonu_kontrolu raises ForbiddenError (AUTH_003) on cross-tenant access."""
    user = test_user_fixture
    user.role = Role.PHYSICIAN.value

    same_org = user.organization_id
    diff_org = uuid.uuid4()

    # Same org -> passes without raising
    kurum_izolasyonu_kontrolu(user, same_org)

    # Different org -> raises ForbiddenError with HTTP 403 / AUTH_003
    with pytest.raises(ForbiddenError) as exc_info:
        kurum_izolasyonu_kontrolu(user, diff_org)
    assert exc_info.value.code == "AUTH_003"
    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_sahip_veya_admin_kontrolu_dependency_abac(test_user_fixture):
    """Verify sahip_veya_admin_kontrolu raises ForbiddenError on unowned cross-user access."""
    user = test_user_fixture
    user.role = Role.PHYSICIAN.value

    own_user_id = user.id
    other_user_id = uuid.uuid4()
    same_org = user.organization_id
    diff_org = uuid.uuid4()

    # Own resource in same org -> passes
    sahip_veya_admin_kontrolu(user, resource_owner_id=own_user_id, resource_org_id=same_org)

    # Other user resource in same org -> raises ForbiddenError (403)
    with pytest.raises(ForbiddenError) as exc_info1:
        sahip_veya_admin_kontrolu(user, resource_owner_id=other_user_id, resource_org_id=same_org)
    assert exc_info1.value.code == "AUTH_003"

    # Own user resource in different org -> raises ForbiddenError (403)
    with pytest.raises(ForbiddenError) as exc_info2:
        sahip_veya_admin_kontrolu(user, resource_owner_id=own_user_id, resource_org_id=diff_org)
    assert exc_info2.value.code == "AUTH_003"


@pytest.mark.anyio
async def test_query_level_tenant_filters(test_user_fixture):
    """Verify apply_tenant_filter and apply_ownership_filter query modifiers."""
    from sqlalchemy import select
    from app.models.user import User
    from app.api.deps import apply_tenant_filter

    user = test_user_fixture
    user.role = Role.PHYSICIAN.value

    q = select(User)
    filtered_q = apply_tenant_filter(q, User, user)
    compiled = str(filtered_q)

    # Verify query contains organization_id filter condition
    assert "users.organization_id = " in compiled

    # Super admin query should not add tenant restriction
    user.role = Role.SUPER_ADMIN.value
    super_q = apply_tenant_filter(q, User, user)
    assert "users.organization_id = " not in str(super_q)


# ── STEP 4: TASK-021 Role Hierarchy & Escalation Defense Tests ───────

def test_can_assign_role_current_target_role():
    """Verify can_assign_role evaluates target current role level to prevent equal/higher role modifications."""
    from app.core.permissions import can_assign_role

    # HOSPITAL_ADMIN modifying PHYSICIAN -> ALLOW
    assert can_assign_role(Role.HOSPITAL_ADMIN, Role.RADIOLOGY_TECH, current_target_role=Role.PHYSICIAN) is True

    # HOSPITAL_ADMIN modifying another HOSPITAL_ADMIN -> DENY
    assert can_assign_role(Role.HOSPITAL_ADMIN, Role.PHYSICIAN, current_target_role=Role.HOSPITAL_ADMIN) is False

    # HOSPITAL_ADMIN modifying SUPER_ADMIN -> DENY
    assert can_assign_role(Role.HOSPITAL_ADMIN, Role.PHYSICIAN, current_target_role=Role.SUPER_ADMIN) is False

    # Fail-closed on missing roles -> False
    assert can_assign_role(None, Role.PHYSICIAN) is False
    assert can_assign_role(Role.HOSPITAL_ADMIN, None) is False


def test_rol_atamasi_kontrolu_self_escalation_and_cross_tenant():
    """Verify rol_atamasi_kontrolu blocks self-escalation, cross-tenant modification, and hierarchy escalation."""
    from app.api.deps import rol_atamasi_kontrolu
    from app.models.user import User

    actor_id = uuid.uuid4()
    target_id = uuid.uuid4()
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()

    actor = User(id=actor_id, organization_id=org_a, role=Role.HOSPITAL_ADMIN.value, is_active=True)
    target = User(id=target_id, organization_id=org_a, role=Role.PHYSICIAN.value, is_active=True)

    # Valid role assignment in same org -> succeeds without error
    rol_atamasi_kontrolu(actor, target, Role.RADIOLOGY_TECH)

    # 1. Self-role escalation attempt -> raises ForbiddenError (403 / AUTH_003)
    with pytest.raises(ForbiddenError) as exc_self:
        rol_atamasi_kontrolu(actor, actor, Role.SUPER_ADMIN)
    assert exc_self.value.code == "AUTH_003"

    # 2. Cross-tenant role modification attempt -> raises ForbiddenError (403 / AUTH_003)
    cross_org_target = User(id=target_id, organization_id=org_b, role=Role.PHYSICIAN.value, is_active=True)
    with pytest.raises(ForbiddenError) as exc_tenant:
        rol_atamasi_kontrolu(actor, cross_org_target, Role.RADIOLOGY_TECH)
    assert exc_tenant.value.code == "AUTH_003"

    # 3. Hierarchy escalation attempt (HOSPITAL_ADMIN trying to assign SUPER_ADMIN) -> raises ForbiddenError
    with pytest.raises(ForbiddenError) as exc_hier:
        rol_atamasi_kontrolu(actor, target, Role.SUPER_ADMIN)
    assert exc_hier.value.code == "AUTH_003"


# ── STEP 5: TASK-022 Admin Permission Override Management API Tests ──

@pytest.mark.anyio
async def test_admin_get_user_permissions_endpoint(db_session, auth_test_client, test_user_fixture):
    """GET /api/v1/admin/users/{user_id}/permissions returns structured permission breakdown."""
    admin_user = test_user_fixture
    admin_user.role = Role.SUPER_ADMIN.value
    await db_session.commit()

    # Target user (PHYSICIAN)
    target_user = User(
        organization_id=admin_user.organization_id,
        email="target.physician@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Target",
        last_name="Physician",
        role=Role.PHYSICIAN.value,
        is_active=True,
    )
    db_session.add(target_user)
    await db_session.commit()
    await db_session.refresh(target_user)

    token, _, _ = security.create_access_token(
        subject=str(admin_user.id),
        organization_id=str(admin_user.organization_id),
        role=admin_user.role,
        permissions=list(get_effective_permissions(admin_user.role)),
    )

    resp = await auth_test_client.get(
        f"/api/v1/admin/users/{target_user.id}/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == str(target_user.id)
    assert data["role"] == Role.PHYSICIAN.value
    assert "report:sign" in data["base_permissions"]
    assert "report:sign" in data["effective_permissions"]


@pytest.mark.anyio
async def test_admin_grant_extra_permission_endpoint(db_session, auth_test_client, test_user_fixture):
    """POST /api/v1/admin/users/{user_id}/permissions/extra grants extra permission override."""
    admin_user = test_user_fixture
    admin_user.role = Role.SUPER_ADMIN.value
    await db_session.commit()

    target_user = User(
        organization_id=admin_user.organization_id,
        email="target.extra@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Target",
        last_name="Extra",
        role=Role.PHYSICIAN.value,
        extra_permissions=[],
        is_active=True,
    )
    db_session.add(target_user)
    await db_session.commit()
    await db_session.refresh(target_user)

    token, _, _ = security.create_access_token(
        subject=str(admin_user.id),
        organization_id=str(admin_user.organization_id),
        role=admin_user.role,
        permissions=list(get_effective_permissions(admin_user.role)),
    )

    # Grant extra permission: model:deploy
    resp = await auth_test_client.post(
        f"/api/v1/admin/users/{target_user.id}/permissions/extra",
        json={"permission": "model:deploy"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "model:deploy" in data["extra_permissions"]
    assert "model:deploy" in data["effective_permissions"]

    # Delete extra permission: model:deploy
    resp_del = await auth_test_client.delete(
        f"/api/v1/admin/users/{target_user.id}/permissions/extra/model:deploy",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_del.status_code == 200
    data_del = resp_del.json()
    assert "model:deploy" not in data_del["extra_permissions"]


@pytest.mark.anyio
async def test_admin_revoke_permission_endpoint(db_session, auth_test_client, test_user_fixture):
    """POST /api/v1/admin/users/{user_id}/permissions/revoked revokes a permission override."""
    admin_user = test_user_fixture
    admin_user.role = Role.SUPER_ADMIN.value
    await db_session.commit()

    target_user = User(
        organization_id=admin_user.organization_id,
        email="target.revoke@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Target",
        last_name="Revoke",
        role=Role.PHYSICIAN.value,
        revoked_permissions=[],
        is_active=True,
    )
    db_session.add(target_user)
    await db_session.commit()
    await db_session.refresh(target_user)

    token, _, _ = security.create_access_token(
        subject=str(admin_user.id),
        organization_id=str(admin_user.organization_id),
        role=admin_user.role,
        permissions=list(get_effective_permissions(admin_user.role)),
    )

    # Revoke report:sign from physician
    resp = await auth_test_client.post(
        f"/api/v1/admin/users/{target_user.id}/permissions/revoked",
        json={"permission": "report:sign"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "report:sign" in data["revoked_permissions"]
    assert "report:sign" not in data["effective_permissions"]

    # Un-revoke report:sign
    resp_del = await auth_test_client.delete(
        f"/api/v1/admin/users/{target_user.id}/permissions/revoked/report:sign",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_del.status_code == 200
    data_del = resp_del.json()
    assert "report:sign" not in data_del["revoked_permissions"]
    assert "report:sign" in data_del["effective_permissions"]


@pytest.mark.anyio
async def test_functional_role_blocked_from_admin_permission_endpoints(db_session, auth_test_client, test_user_fixture):
    """Functional role (PHYSICIAN) is blocked from accessing admin permission management endpoints (HTTP 403 / AUTH_003)."""
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
        f"/api/v1/admin/users/{user.id}/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "AUTH_003"


@pytest.mark.anyio
async def test_invalid_permission_string_returns_validation_error(db_session, auth_test_client, test_user_fixture):
    """Unknown or invalid permission string returns 422 Unprocessable Entity (VAL_001)."""
    admin_user = test_user_fixture
    admin_user.role = Role.SUPER_ADMIN.value
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(admin_user.id),
        organization_id=str(admin_user.organization_id),
        role=admin_user.role,
        permissions=list(get_effective_permissions(admin_user.role)),
    )

    resp = await auth_test_client.post(
        f"/api/v1/admin/users/{admin_user.id}/permissions/extra",
        json={"permission": "INVALID_PERM_NAME"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VAL_001"


# ── STEP 6: TASK-023 Authorization & Privilege Audit Logging Tests ───

def test_log_authorization_event_formatting_and_sanitization(caplog):
    """Verify log_authorization_event formats details and strips sensitive credentials."""
    import logging
    from app.core import audit

    caplog.set_level(logging.INFO, logger="app.audit")

    actor_id = uuid.uuid4()
    target_id = uuid.uuid4()
    org_id = uuid.uuid4()

    # Attempt to log with accidental sensitive details
    audit.log_authorization_event(
        event="PRIVILEGE_ESCALATION_ATTEMPT",
        actor_id=actor_id,
        target_user_id=target_id,
        organization_id=org_id,
        permission="system:config",
        result="DENIED",
        extra_details={
            "password": "SecretPassword123!",
            "password_hash": "argon2id$v=19...",
            "token": "bearer_jwt_string",
            "access_token": "eyJhbGci...",
            "mfa_secret": "JBSWY3DPEHPK3PXP",
            "safe_note": "User attempted unauthorized system config access",
        },
    )

    log_records = [rec for rec in caplog.records if rec.name == "app.audit"]
    assert len(log_records) == 1
    log_text = log_records[0].getMessage()

    # Verify event name and IDs are recorded
    assert "PRIVILEGE_ESCALATION_ATTEMPT" in log_text
    assert str(actor_id) in log_text
    assert str(target_id) in log_text
    assert "system:config" in log_text

    # Verify ALL sensitive fields are stripped
    assert "SecretPassword123!" not in log_text
    assert "argon2id" not in log_text
    assert "eyJhbGci" not in log_text
    assert "JBSWY3DPEHPK3PXP" not in log_text
    assert "safe_note" in log_text


def test_rol_atamasi_kontrolu_audit_logging_events(caplog):
    """Verify rol_atamasi_kontrolu records security audit events on failed escalation attempts."""
    import logging
    from app.api.deps import rol_atamasi_kontrolu

    caplog.set_level(logging.INFO, logger="app.audit")

    actor_id = uuid.uuid4()
    target_id = uuid.uuid4()
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()

    actor = User(id=actor_id, organization_id=org_a, role=Role.HOSPITAL_ADMIN.value, is_active=True)
    target = User(id=target_id, organization_id=org_a, role=Role.PHYSICIAN.value, is_active=True)

    # 1. Self-role escalation attempt
    with pytest.raises(ForbiddenError):
        rol_atamasi_kontrolu(actor, actor, Role.SUPER_ADMIN)

    # 2. Cross-tenant role modification attempt
    cross_org_target = User(id=target_id, organization_id=org_b, role=Role.PHYSICIAN.value, is_active=True)
    with pytest.raises(ForbiddenError):
        rol_atamasi_kontrolu(actor, cross_org_target, Role.RADIOLOGY_TECH)

    # 3. Hierarchy escalation attempt
    with pytest.raises(ForbiddenError):
        rol_atamasi_kontrolu(actor, target, Role.SUPER_ADMIN)

    audit_logs = [rec.getMessage() for rec in caplog.records if rec.name == "app.audit"]
    assert any("SELF_ROLE_ESCALATION_ATTEMPT" in log for log in audit_logs)
    assert any("CROSS_TENANT_ACCESS_DENIED" in log for log in audit_logs)
    assert any("PRIVILEGE_ESCALATION_ATTEMPT" in log for log in audit_logs)


# ── STEP 7: TASK-024 5-Tier Sensitive Clinical & AI Action Pipeline Tests 

@pytest.mark.anyio
async def test_5tier_pipeline_physician_report_sign_allowed(db_session, test_user_fixture):
    """Tier 1-5 PASS: Physician user with report:sign permission in same org signs report."""
    from app.api.deps import hassas_klinik_ve_ai_islem_kontrolu

    user = test_user_fixture
    user.role = Role.PHYSICIAN.value
    await db_session.commit()

    dep = hassas_klinik_ve_ai_islem_kontrolu(
        permission=Permission.REPORT_SIGN.value,
        resource_org_id=user.organization_id,
        resource_owner_id=user.id,
    )
    result_user = await dep(user)
    assert result_user.id == user.id


@pytest.mark.anyio
async def test_5tier_pipeline_non_physician_report_sign_denied(db_session, test_user_fixture):
    """Tier 3 FAIL: Non-physician (HOSPITAL_ADMIN) attempting report:sign is denied (HTTP 403 / AUTH_003)."""
    from app.api.deps import hassas_klinik_ve_ai_islem_kontrolu

    user = test_user_fixture
    user.role = Role.HOSPITAL_ADMIN.value
    # Add report:sign to extra_permissions for test
    user.extra_permissions = [Permission.REPORT_SIGN.value]
    await db_session.commit()

    dep = hassas_klinik_ve_ai_islem_kontrolu(
        permission=Permission.REPORT_SIGN.value,
        resource_org_id=user.organization_id,
    )
    with pytest.raises(ForbiddenError) as exc:
        await dep(user)
    assert exc.value.code == "AUTH_003"
    assert " yalnızca uzman hekimlere aittir" in exc.value.detail


@pytest.mark.anyio
async def test_5tier_pipeline_revoked_permission_wins(db_session, test_user_fixture):
    """Tier 2 FAIL: Revoked permission strictly overrides extra permission and base role permission."""
    from app.api.deps import hassas_klinik_ve_ai_islem_kontrolu

    user = test_user_fixture
    user.role = Role.PHYSICIAN.value
    # Grant in extra but revoke in revoked
    user.extra_permissions = [Permission.AI_RUN_SEGMENTATION.value]
    user.revoked_permissions = [Permission.AI_RUN_SEGMENTATION.value]
    await db_session.commit()

    dep = hassas_klinik_ve_ai_islem_kontrolu(
        permission=Permission.AI_RUN_SEGMENTATION.value,
        resource_org_id=user.organization_id,
    )
    with pytest.raises(ForbiddenError) as exc:
        await dep(user)
    assert exc.value.code == "AUTH_003"


@pytest.mark.anyio
async def test_5tier_pipeline_cross_tenant_idor_denied(db_session, test_user_fixture):
    """Tier 4 FAIL: Accessing clinical/AI resource of another organization returns HTTP 403 (AUTH_003)."""
    from app.api.deps import hassas_klinik_ve_ai_islem_kontrolu

    user = test_user_fixture
    user.role = Role.PHYSICIAN.value
    diff_org = uuid.uuid4()
    await db_session.commit()

    dep = hassas_klinik_ve_ai_islem_kontrolu(
        permission=Permission.PATIENT_READ.value,
        resource_org_id=diff_org,
    )
    with pytest.raises(ForbiddenError) as exc:
        await dep(user)
    assert exc.value.code == "AUTH_003"


# ── STEP 8: TASK-025 Combinatorial Security Matrix & Invariants ──────

@pytest.mark.anyio
async def test_auth_matrix_db_authority_over_stale_jwt(db_session, auth_test_client, test_user_fixture):
    """Invariant 10: DB state is authoritative over JWT claims (stale JWT role does not grant access)."""
    user = test_user_fixture
    user.role = Role.PHYSICIAN.value
    await db_session.commit()

    # JWT states role=SUPER_ADMIN, but DB state is PHYSICIAN
    token, _, _ = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=Role.SUPER_ADMIN.value,
        permissions=list(get_effective_permissions(Role.SUPER_ADMIN)),
    )

    # Calling an endpoint that requires SUPER_ADMIN or HOSPITAL_ADMIN role
    resp = await auth_test_client.get(
        "/test/role-admin-only",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "AUTH_003"


@pytest.mark.anyio
async def test_auth_matrix_locked_user_denied(db_session, auth_test_client, test_user_fixture):
    """Invariant 9: Locked or inactive user is denied access regardless of valid JWT."""
    user = test_user_fixture
    user.is_locked = True
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
    assert resp.status_code == 423
    assert resp.json()["error"]["code"] == "AUTH_004"


@pytest.mark.parametrize("role", list(Role))
def test_invariant_1_revoked_permissions_always_wins(role):
    """Invariant 1: revoked_permissions ALWAYS takes precedence over extra_permissions and base permissions."""
    all_perms = list(Permission)

    for perm in all_perms:
        perm_val = perm.value

        # Grant in extra_permissions AND revoke in revoked_permissions
        effective = get_effective_permissions(
            role=role,
            extra_permissions=[perm_val],
            revoked_permissions=[perm_val],
        )

        assert perm_val not in effective, f"Revoked permission '{perm_val}' leaked into effective permissions for role '{role}'!"


def test_role_hierarchy_matrix_all_49_actor_target_pairs():
    """Invariant 4: Role hierarchy evaluator enforces actor_level > target_level across all 49 role combinations."""
    all_roles = list(Role)

    for actor in all_roles:
        actor_level = ROLE_HIERARCHY_LEVELS.get(actor, 0)
        for target in all_roles:
            target_level = ROLE_HIERARCHY_LEVELS.get(target, 0)

            result = can_assign_role(actor, target)

            if actor == Role.SUPER_ADMIN:
                assert result is True, f"SUPER_ADMIN failed to assign role {target}"
            elif actor_level > target_level:
                assert result is True, f"Actor {actor} (level {actor_level}) should be allowed to assign target {target} (level {target_level})"
            else:
                assert result is False, f"Actor {actor} (level {actor_level}) MUST be denied from assigning target {target} (level {target_level})"


def test_invariant_3_self_role_escalation_denied():
    """Invariant 3: Users cannot modify or escalate their own role."""
    actor_id = uuid.uuid4()
    org_id = uuid.uuid4()

    actor = User(id=actor_id, organization_id=org_id, role=Role.HOSPITAL_ADMIN.value, is_active=True)

    # HOSPITAL_ADMIN attempting to assign SUPER_ADMIN to themselves -> ForbiddenError
    with pytest.raises(ForbiddenError) as exc_info:
        rol_atamasi_kontrolu(actor, actor, Role.SUPER_ADMIN)
    assert exc_info.value.code == "AUTH_003"


def test_invariant_2_cross_tenant_resource_access_denied():
    """Invariant 2: Cross-tenant resource access for non-super admins is strictly denied."""
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()

    # Functional roles (PHYSICIAN, AUDITOR, etc.) accessing resource in org_b -> False
    for role in [Role.PHYSICIAN, Role.RADIOLOGY_TECH, Role.RESEARCHER, Role.AUDITOR, Role.SERVICE]:
        assert check_abac_access(user_id, org_a, role, org_b, user_id) is False

    # HOSPITAL_ADMIN accessing resource in org_b -> False
    assert check_abac_access(user_id, org_a, Role.HOSPITAL_ADMIN, org_b, other_user_id) is False

    # SUPER_ADMIN accessing resource in org_b -> True
    assert check_abac_access(user_id, org_a, Role.SUPER_ADMIN, org_b, other_user_id) is True


def test_invariant_5_and_6_client_payload_spoofing_ignored():
    """Invariants 5 & 6: Client-provided organization_id or owner_id cannot bypass DB authority."""
    user_id = uuid.uuid4()
    real_org_id = uuid.uuid4()
    spoofed_org_id = uuid.uuid4()

    user = User(id=user_id, organization_id=real_org_id, role=Role.PHYSICIAN.value, is_active=True)

    # Attempting tenant check with spoofed org_id -> raises ForbiddenError
    with pytest.raises(ForbiddenError) as exc:
        kurum_izolasyonu_kontrolu(user, spoofed_org_id)
    assert exc.value.code == "AUTH_003"


@pytest.mark.anyio
async def test_invariant_7_and_8_super_admin_boundary_checks(db_session, test_user_fixture):
    """Invariants 7 & 8: SUPER_ADMIN bypasses tenant boundaries, but NOT authentication or revoked permission overrides."""
    from app.api.deps import hassas_klinik_ve_ai_islem_kontrolu

    user = test_user_fixture
    user.role = Role.SUPER_ADMIN.value
    user.revoked_permissions = [Permission.AI_RUN_SEGMENTATION.value]
    await db_session.commit()

    diff_org = uuid.uuid4()

    # SUPER_ADMIN with revoked permission -> denied by Tier 2 permission check
    dep_revoked = hassas_klinik_ve_ai_islem_kontrolu(
        permission=Permission.AI_RUN_SEGMENTATION.value,
        resource_org_id=diff_org,
    )
    with pytest.raises(ForbiddenError) as exc_rev:
        await dep_revoked(user)
    assert exc_rev.value.code == "AUTH_003"

    # SUPER_ADMIN with valid permission -> bypasses cross-tenant boundary successfully
    dep_valid = hassas_klinik_ve_ai_islem_kontrolu(
        permission=Permission.PATIENT_READ.value,
        resource_org_id=diff_org,
    )
    authorized_user = await dep_valid(user)
    assert authorized_user.id == user.id


def test_invariant_9_missing_security_attributes_fail_closed():
    """Invariant 9: Missing or None security attributes fail closed (return False or raise 403)."""
    # Missing user_id
    assert check_abac_access(None, uuid.uuid4(), Role.PHYSICIAN, uuid.uuid4(), uuid.uuid4()) is False

    # Missing organization_id
    assert check_abac_access(uuid.uuid4(), None, Role.PHYSICIAN, uuid.uuid4(), uuid.uuid4()) is False

    # Missing role
    assert can_assign_role(None, Role.PHYSICIAN) is False
    assert can_assign_role(Role.HOSPITAL_ADMIN, None) is False
