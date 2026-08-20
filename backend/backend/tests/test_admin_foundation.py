"""
NeuroOncoTrack-AI — TASK-026 Admin Foundation & Canonical Authorization Matrix Unit Tests

Verifies:
1. Canonical Admin Authorization Matrix specification and completeness.
2. DTO Security: Zero exposure of sensitive fields (password_hash, mfa_secret, backup_codes).
3. Pagination Params: Page >= 1, 1 <= page_size <= 100, safe offset calculation.
4. Sorting Security: Whitelist validation prevents SQL injection in sort_by.
5. Role Hierarchy & Permission Integrity across all 7 canonical system roles.
6. Tenant Scope & ABAC Evaluators compatibility.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.core.permissions import (
    ROLE_HIERARCHY_LEVELS,
    ROLE_PERMISSIONS,
    Permission,
    Role,
    can_assign_role,
    get_effective_permissions,
    has_permission,
    is_hospital_admin,
    is_super_admin,
    normalize_permission,
    verify_organization_access,
)
from app.schemas.admin import (
    AdminAuditLogResponse,
    AdminDashboardStatsResponse,
    AdminOrganizationCreateRequest,
    AdminOrganizationResponse,
    AdminSessionResponse,
    AdminUserCreateRequest,
    AdminUserResponse,
    PaginatedResponse,
    PaginationParams,
    PermissionOverrideRequest,
    UserPermissionsResponse,
    validate_sort_field,
)


class TestCanonicalAuthorizationMatrix:
    """Verifies that all 7 canonical system roles match matrix specifications."""

    def test_all_system_roles_have_hierarchy_levels(self):
        """All 7 system roles must have defined hierarchy rank levels."""
        for r in Role:
            assert r in ROLE_HIERARCHY_LEVELS, f"Role {r} missing from ROLE_HIERARCHY_LEVELS"

        assert ROLE_HIERARCHY_LEVELS[Role.SUPER_ADMIN] == 100
        assert ROLE_HIERARCHY_LEVELS[Role.HOSPITAL_ADMIN] == 80
        assert ROLE_HIERARCHY_LEVELS[Role.PHYSICIAN] == 50
        assert ROLE_HIERARCHY_LEVELS[Role.RADIOLOGY_TECH] == 50
        assert ROLE_HIERARCHY_LEVELS[Role.RESEARCHER] == 50
        assert ROLE_HIERARCHY_LEVELS[Role.AUDITOR] == 50
        assert ROLE_HIERARCHY_LEVELS[Role.SERVICE] == 50

    def test_super_admin_has_all_permissions(self):
        """SUPER_ADMIN must possess all defined permissions."""
        super_perms = ROLE_PERMISSIONS[Role.SUPER_ADMIN]
        all_perms = set(Permission)
        assert super_perms == all_perms

    def test_hospital_admin_cannot_sign_reports(self):
        """HOSPITAL_ADMIN must NOT possess report approval or signing permissions."""
        h_perms = ROLE_PERMISSIONS[Role.HOSPITAL_ADMIN]
        assert Permission.REPORT_SIGN not in h_perms
        assert Permission.REPORT_APPROVE not in h_perms

    def test_hospital_admin_role_assignment_hierarchy(self):
        """HOSPITAL_ADMIN can assign functional roles, but CANNOT assign SUPER_ADMIN or HOSPITAL_ADMIN."""
        assert can_assign_role(Role.HOSPITAL_ADMIN, Role.PHYSICIAN) is True
        assert can_assign_role(Role.HOSPITAL_ADMIN, Role.RADIOLOGY_TECH) is True
        assert can_assign_role(Role.HOSPITAL_ADMIN, Role.RESEARCHER) is True
        assert can_assign_role(Role.HOSPITAL_ADMIN, Role.AUDITOR) is True
        assert can_assign_role(Role.HOSPITAL_ADMIN, Role.SERVICE) is True

        assert can_assign_role(Role.HOSPITAL_ADMIN, Role.SUPER_ADMIN) is False
        assert can_assign_role(Role.HOSPITAL_ADMIN, Role.HOSPITAL_ADMIN) is False

    def test_functional_roles_cannot_assign_any_role(self):
        """Level 50 functional roles cannot assign any role."""
        for r in [Role.PHYSICIAN, Role.RADIOLOGY_TECH, Role.RESEARCHER, Role.AUDITOR, Role.SERVICE]:
            for target in Role:
                assert can_assign_role(r, target) is False

    def test_tenant_isolation_boundary_evaluator(self):
        """SUPER_ADMIN bypasses tenant boundary; non-super admin requires exact org match."""
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()

        # SUPER_ADMIN bypasses
        assert verify_organization_access(org_a, org_b, is_super=True) is True

        # Non-super admin matching org passes
        assert verify_organization_access(org_a, org_a, is_super=False) is True

        # Non-super admin cross-org fails
        assert verify_organization_access(org_a, org_b, is_super=False) is False

        # Fail-closed on None
        assert verify_organization_access(None, org_b, is_super=False) is False
        assert verify_organization_access(org_a, None, is_super=False) is False


class TestPaginationAndSortingDTOs:
    """Verifies pagination parameters and sorting security helpers."""

    def test_pagination_defaults_and_offset(self):
        p = PaginationParams()
        assert p.page == 1
        assert p.page_size == 20
        assert p.offset == 0

        p2 = PaginationParams(page=3, page_size=15)
        assert p2.offset == 30

    def test_pagination_page_must_be_positive(self):
        with pytest.raises(ValidationError):
            PaginationParams(page=0)

        with pytest.raises(ValidationError):
            PaginationParams(page=-1)

    def test_pagination_page_size_max_limit(self):
        with pytest.raises(ValidationError):
            PaginationParams(page_size=101)

        with pytest.raises(ValidationError):
            PaginationParams(page_size=0)

    def test_paginated_response_calculation(self):
        res = PaginatedResponse.create(
            items=["item1", "item2"],
            total=45,
            page=2,
            page_size=20,
        )
        assert res.total == 45
        assert res.page == 2
        assert res.page_size == 20
        assert res.total_pages == 3
        assert res.items == ["item1", "item2"]

    def test_sorting_field_whitelist(self):
        allowed = {"created_at", "email", "role", "name"}
        assert validate_sort_field("email", allowed) == "email"
        assert validate_sort_field("CREATED_AT ", allowed) == "created_at"
        assert validate_sort_field("invalid_field; DROP TABLE users;--", allowed) == "created_at"
        assert validate_sort_field("password_hash", allowed, default="email") == "email"


class TestDTOSecurityAndSensitiveDataExclusion:
    """Verifies that Admin DTOs strictly exclude sensitive credentials."""

    def test_admin_user_response_schema_fields(self):
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        dto = AdminUserResponse(
            id=user_id,
            organization_id=org_id,
            email="doctor@hospital.org",
            first_name="Jane",
            last_name="Doe",
            title="Dr.",
            role=Role.PHYSICIAN.value,
            is_active=True,
            is_locked=False,
            failed_login_attempts=0,
            must_change_password=False,
            mfa_enabled=True,
            created_at=now,
        )

        serialized_keys = set(dto.model_dump().keys())

        # Assert sensitive keys are strictly absent from schema definition
        forbidden_keys = {
            "password",
            "password_hash",
            "mfa_secret",
            "totp_secret",
            "backup_codes",
            "refresh_token",
            "reset_token",
            "session_secret",
        }
        assert forbidden_keys.isdisjoint(serialized_keys)

    def test_admin_user_create_request_does_not_require_plaintext_password(self):
        """User onboarding request requires email, name, role, but NO plaintext password."""
        req = AdminUserCreateRequest(
            email="newuser@hospital.org",
            first_name="John",
            last_name="Smith",
            role=Role.PHYSICIAN,
        )
        assert req.email == "newuser@hospital.org"
        assert "password" not in req.model_dump()

    def test_organization_code_validation_normalizes_case(self):
        req = AdminOrganizationCreateRequest(
            name="General Hospital",
            code=" hospital-code_1 ",
        )
        assert req.code == "HOSPITAL-CODE_1"
