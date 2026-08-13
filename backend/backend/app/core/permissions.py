"""
NeuroOncoTrack-AI — Permissions & Roles

Permission format: resource:action
Roles are mapped to permission sets.
Role names are never checked directly in endpoint code —
all access control is done through permissions.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """System roles as defined in the architecture document."""

    SUPER_ADMIN = "SUPER_ADMIN"
    HOSPITAL_ADMIN = "HOSPITAL_ADMIN"
    PHYSICIAN = "PHYSICIAN"
    RADIOLOGY_TECH = "RADIOLOGY_TECH"
    RESEARCHER = "RESEARCHER"
    AUDITOR = "AUDITOR"
    SERVICE = "SERVICE"


class Permission(str, Enum):
    """
    All permissions in resource:action format.

    This enum is the single source of truth for the permission system.
    The permission matrix in the architecture document is validated
    against this definition via automated tests.
    """

    # ── User Management ──────────────────────────────────────
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_LIST = "user:list"
    USER_RESET_PASSWORD = "user:reset_password"
    USER_LOCK = "user:lock"
    ROLE_ASSIGN = "role:assign"

    # ── Patient & Case ───────────────────────────────────────
    PATIENT_CREATE = "patient:create"
    PATIENT_READ = "patient:read"
    PATIENT_READ_ANONYMIZED = "patient:read_anonymized"
    PATIENT_UPDATE = "patient:update"
    PATIENT_DELETE = "patient:delete"
    PATIENT_LIST = "patient:list"
    CONSENT_MANAGE = "consent:manage"

    # ── Imaging Study ────────────────────────────────────────
    STUDY_UPLOAD = "study:upload"
    STUDY_READ = "study:read"
    STUDY_DOWNLOAD = "study:download"
    STUDY_DELETE = "study:delete"

    # ── AI ────────────────────────────────────────────────────
    AI_RUN_SEGMENTATION = "ai:run_segmentation"
    AI_RUN_BIOPSY = "ai:run_biopsy"
    AI_RUN_XAI = "ai:run_xai"
    AI_VIEW_RESULT = "ai:view_result"
    AI_OVERRIDE = "ai:override"
    MODEL_DEPLOY = "model:deploy"
    MODEL_LIST_VERSIONS = "model:list_versions"

    # ── Report ───────────────────────────────────────────────
    REPORT_GENERATE = "report:generate"
    REPORT_READ = "report:read"
    REPORT_EDIT_DRAFT = "report:edit_draft"
    REPORT_APPROVE = "report:approve"
    REPORT_SIGN = "report:sign"
    REPORT_EXPORT_PDF = "report:export_pdf"

    # ── FHIR ─────────────────────────────────────────────────
    FHIR_READ = "fhir:read"
    FHIR_WRITE = "fhir:write"
    FHIR_SYNC = "fhir:sync"

    # ── Audit & System ───────────────────────────────────────
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"
    SYSTEM_CONFIG = "system:config"
    SYSTEM_HEALTH = "system:health"
    SYSTEM_METRICS = "system:metrics"


# ── Role → Permission Mapping ───────────────────────────────
# Matches the permission matrix from the architecture document.
# Conditional/scoped permissions (◐) are included here;
# scope enforcement (e.g. own-org, own-cases) is handled at the service layer.

ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.SUPER_ADMIN: set(Permission),  # All permissions

    Role.HOSPITAL_ADMIN: {
        # User management — scoped to own organization
        Permission.USER_CREATE,
        Permission.USER_READ,
        Permission.USER_UPDATE,
        Permission.USER_DELETE,
        Permission.USER_LIST,
        Permission.USER_RESET_PASSWORD,
        Permission.USER_LOCK,
        Permission.ROLE_ASSIGN,
        # Patient
        Permission.PATIENT_CREATE,
        Permission.PATIENT_READ,
        Permission.PATIENT_READ_ANONYMIZED,
        Permission.PATIENT_UPDATE,
        Permission.PATIENT_DELETE,
        Permission.PATIENT_LIST,
        Permission.CONSENT_MANAGE,
        # Study
        Permission.STUDY_UPLOAD,
        Permission.STUDY_READ,
        Permission.STUDY_DOWNLOAD,
        Permission.STUDY_DELETE,
        # AI
        Permission.AI_RUN_SEGMENTATION,
        Permission.AI_RUN_BIOPSY,
        Permission.AI_RUN_XAI,
        Permission.AI_VIEW_RESULT,
        Permission.MODEL_LIST_VERSIONS,
        # Report — NOT approve/sign (by design)
        Permission.REPORT_GENERATE,
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT_PDF,
        # FHIR
        Permission.FHIR_READ,
        Permission.FHIR_WRITE,
        Permission.FHIR_SYNC,
        # Audit — scoped to own organization
        Permission.AUDIT_READ,
        # System
        Permission.SYSTEM_HEALTH,
        Permission.SYSTEM_METRICS,
    },

    Role.PHYSICIAN: {
        # User — own profile only
        Permission.USER_UPDATE,
        # Patient — own cases
        Permission.PATIENT_CREATE,
        Permission.PATIENT_READ,
        Permission.PATIENT_READ_ANONYMIZED,
        Permission.PATIENT_UPDATE,
        Permission.PATIENT_LIST,
        Permission.CONSENT_MANAGE,
        # Study — own cases
        Permission.STUDY_UPLOAD,
        Permission.STUDY_READ,
        Permission.STUDY_DOWNLOAD,
        # AI
        Permission.AI_RUN_SEGMENTATION,
        Permission.AI_RUN_BIOPSY,
        Permission.AI_RUN_XAI,
        Permission.AI_VIEW_RESULT,
        Permission.AI_OVERRIDE,
        Permission.MODEL_LIST_VERSIONS,
        # Report — full access including approve & sign
        Permission.REPORT_GENERATE,
        Permission.REPORT_READ,
        Permission.REPORT_EDIT_DRAFT,
        Permission.REPORT_APPROVE,
        Permission.REPORT_SIGN,
        Permission.REPORT_EXPORT_PDF,
        # FHIR
        Permission.FHIR_READ,
        Permission.FHIR_WRITE,
        Permission.FHIR_SYNC,
        # Audit — own actions only
        Permission.AUDIT_READ,
    },

    Role.RADIOLOGY_TECH: {
        # User — own profile only
        Permission.USER_UPDATE,
        # Patient — own cases
        Permission.PATIENT_CREATE,
        Permission.PATIENT_READ,
        Permission.PATIENT_READ_ANONYMIZED,
        Permission.PATIENT_LIST,
        # Study
        Permission.STUDY_UPLOAD,
        Permission.STUDY_READ,
        Permission.STUDY_DOWNLOAD,
        # AI
        Permission.AI_RUN_SEGMENTATION,
        Permission.AI_VIEW_RESULT,
        Permission.MODEL_LIST_VERSIONS,
        # Report — read & export only
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT_PDF,
        # FHIR
        Permission.FHIR_READ,
        # Audit — own actions only
        Permission.AUDIT_READ,
    },

    Role.RESEARCHER: {
        # User — own profile only
        Permission.USER_UPDATE,
        # Patient — anonymized only
        Permission.PATIENT_READ_ANONYMIZED,
        # Study — anonymized
        Permission.STUDY_READ,
        Permission.STUDY_DOWNLOAD,
        # AI — anonymized data
        Permission.AI_RUN_SEGMENTATION,
        Permission.AI_RUN_BIOPSY,
        Permission.AI_RUN_XAI,
        Permission.AI_VIEW_RESULT,
        Permission.MODEL_LIST_VERSIONS,
        # Report — anonymized
        Permission.REPORT_READ,
        # Audit — own actions only
        Permission.AUDIT_READ,
        # System — model performance metrics only
        Permission.SYSTEM_METRICS,
    },

    Role.AUDITOR: {
        # User — own profile only
        Permission.USER_UPDATE,
        # Audit — full access
        Permission.AUDIT_READ,
        Permission.AUDIT_EXPORT,
        # System
        Permission.SYSTEM_HEALTH,
        Permission.SYSTEM_METRICS,
        # Model versions — read only
        Permission.MODEL_LIST_VERSIONS,
    },

    Role.SERVICE: {
        # Patient — anonymized
        Permission.PATIENT_READ_ANONYMIZED,
        # Study
        Permission.STUDY_UPLOAD,
        Permission.STUDY_READ,
        Permission.STUDY_DOWNLOAD,
        # AI
        Permission.AI_RUN_SEGMENTATION,
        Permission.AI_RUN_BIOPSY,
        Permission.AI_RUN_XAI,
        Permission.AI_VIEW_RESULT,
        Permission.MODEL_LIST_VERSIONS,
        # Report
        Permission.REPORT_GENERATE,
        # FHIR
        Permission.FHIR_READ,
        Permission.FHIR_WRITE,
        Permission.FHIR_SYNC,
        # System
        Permission.SYSTEM_HEALTH,
    },
}


def get_effective_permissions(
    role: Role | str,
    extra_permissions: list[str] | None = None,
    revoked_permissions: list[str] | None = None,
) -> set[str]:
    """
    Calculate effective permissions for a user.

    effective = (role_base_permissions + extra) - revoked
    """
    try:
        r_enum = Role(role) if isinstance(role, str) else role
    except ValueError:
        r_enum = None

    base = {p.value for p in ROLE_PERMISSIONS.get(r_enum, set())} if r_enum else set()

    if extra_permissions:
        base.update(extra_permissions)

    if revoked_permissions:
        base -= set(revoked_permissions)

    return base


def has_permission(
    role: Role | str,
    permission: Permission | str,
    extra_permissions: list[str] | None = None,
    revoked_permissions: list[str] | None = None,
) -> bool:
    """Check if a given role configuration grants a specific permission."""
    perm_str = permission.value if isinstance(permission, Permission) else str(permission)
    effective = get_effective_permissions(role, extra_permissions, revoked_permissions)
    return perm_str in effective


def is_super_admin(role: Role | str) -> bool:
    """Check if role is SUPER_ADMIN."""
    r_val = role.value if isinstance(role, Role) else str(role)
    return r_val == Role.SUPER_ADMIN.value


def is_hospital_admin(role: Role | str) -> bool:
    """Check if role is HOSPITAL_ADMIN."""
    r_val = role.value if isinstance(role, Role) else str(role)
    return r_val == Role.HOSPITAL_ADMIN.value


# ── ABAC (Attribute-Based Access Control) Helpers ────────────

def verify_organization_access(
    user_org_id: str | uuid.UUID,
    resource_org_id: str | uuid.UUID,
    is_super: bool = False,
) -> bool:
    """
    ABAC Tenant Isolation Check.

    Users can only access resources belonging to their organization,
    unless they have SUPER_ADMIN status (is_super=True).
    """
    if is_super:
        return True
    return str(user_org_id) == str(resource_org_id)


def verify_resource_ownership(
    user_id: str | uuid.UUID,
    resource_owner_id: str | uuid.UUID,
    is_admin_override: bool = False,
) -> bool:
    """
    ABAC Resource Ownership Check.

    Users can access resources they own (user_id == resource_owner_id),
    or if authorized via admin override.
    """
    if is_admin_override:
        return True
    return str(user_id) == str(resource_owner_id)


def check_abac_access(
    user_id: str | uuid.UUID,
    user_org_id: str | uuid.UUID,
    user_role: Role | str,
    resource_org_id: str | uuid.UUID | None = None,
    resource_owner_id: str | uuid.UUID | None = None,
) -> bool:
    """
    Combined ABAC Access Evaluator.

    Evaluates both organization boundary matching and resource ownership.
    - SUPER_ADMIN bypasses all restrictions.
    - HOSPITAL_ADMIN can access all resources within their organization.
    - Standard roles must match organization AND (if owner is specified) match resource ownership.
    """
    role_str = user_role.value if isinstance(user_role, Role) else str(user_role)

    if role_str == Role.SUPER_ADMIN.value:
        return True

    # Check Organization Access if specified
    if resource_org_id is not None:
        if str(user_org_id) != str(resource_org_id):
            return False

    # If within same org and is HOSPITAL_ADMIN, allow access
    if role_str == Role.HOSPITAL_ADMIN.value:
        return True

    # Check Resource Ownership if specified
    if resource_owner_id is not None:
        if str(user_id) != str(resource_owner_id):
            return False

    return True

