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

# Central registry for system-level administrative permissions
SYSTEM_ADMIN_PERMISSIONS: set[Permission] = {
    Permission.USER_CREATE,
    Permission.USER_DELETE,
    Permission.USER_LOCK,
    Permission.ROLE_ASSIGN,
    Permission.SYSTEM_CONFIG,
}

# Canonical Role Hierarchy Ranking
ROLE_HIERARCHY_LEVELS: dict[Role, int] = {
    Role.SUPER_ADMIN: 100,
    Role.HOSPITAL_ADMIN: 80,
    Role.PHYSICIAN: 50,
    Role.RADIOLOGY_TECH: 50,
    Role.RESEARCHER: 50,
    Role.AUDITOR: 50,
    Role.SERVICE: 50,
}


def normalize_permission(permission: Permission | str) -> str:
    """Normalize Permission enum or string literal to standard value string."""
    if isinstance(permission, Permission):
        return permission.value
    return str(permission).strip()


def get_effective_permissions(
    role: Role | str,
    extra_permissions: list[Permission | str] | None = None,
    revoked_permissions: list[Permission | str] | None = None,
) -> set[str]:
    """
    Calculate effective permissions for a user.

    effective = (role_base_permissions + extra) - revoked
    Conflict resolution: revoked_permissions ALWAYS takes precedence over extra_permissions.
    Supports string normalization and list deduplication.
    """
    try:
        r_enum = Role(role) if isinstance(role, str) else role
    except ValueError:
        r_enum = None

    base = {p.value for p in ROLE_PERMISSIONS.get(r_enum, set())} if r_enum else set()

    if extra_permissions:
        extra_set = {normalize_permission(p) for p in extra_permissions if p}
        base.update(extra_set)

    if revoked_permissions:
        revoked_set = {normalize_permission(p) for p in revoked_permissions if p}
        base -= revoked_set

    return base


def has_permission(
    user_or_role: Any,
    permission: Permission | str,
    extra_permissions: list[Permission | str] | None = None,
    revoked_permissions: list[Permission | str] | None = None,
) -> bool:
    """Check if a User object or role configuration grants a specific permission."""
    from app.models.user import User

    if isinstance(user_or_role, User):
        role = user_or_role.role
        extra = extra_permissions if extra_permissions is not None else user_or_role.extra_permissions
        revoked = revoked_permissions if revoked_permissions is not None else user_or_role.revoked_permissions
    else:
        role = user_or_role
        extra = extra_permissions
        revoked = revoked_permissions

    perm_str = normalize_permission(permission)
    effective = get_effective_permissions(role, extra, revoked)
    return perm_str in effective


def is_super_admin(role: Role | str) -> bool:
    """Check if role is SUPER_ADMIN."""
    r_val = role.value if isinstance(role, Role) else str(role)
    return r_val == Role.SUPER_ADMIN.value


def is_hospital_admin(role: Role | str) -> bool:
    """Check if role is HOSPITAL_ADMIN."""
    r_val = role.value if isinstance(role, Role) else str(role)
    return r_val == Role.HOSPITAL_ADMIN.value


def can_assign_role(
    actor_role: Role | str | None,
    target_role: Role | str | None,
    current_target_role: Role | str | None = None,
) -> bool:
    """
    Evaluates role hierarchy for role assignment and modification operations.

    Rules:
    - Fail-closed: Returns False if actor_role or target_role is None or invalid.
    - SUPER_ADMIN can assign any role.
    - Non-SUPER_ADMIN actor can only assign/modify roles strictly lower in rank (actor_level > target_level).
    - If current_target_role is provided, actor cannot modify a user with equal or higher rank (actor_level > current_target_level).
    - Level 50 functional roles (PHYSICIAN, RADIOLOGY_TECH, etc.) cannot assign any role.
    """
    if actor_role is None or target_role is None:
        return False

    try:
        a_enum = Role(actor_role) if isinstance(actor_role, str) else actor_role
        t_enum = Role(target_role) if isinstance(target_role, str) else target_role
    except ValueError:
        return False

    if a_enum == Role.SUPER_ADMIN:
        return True

    actor_level = ROLE_HIERARCHY_LEVELS.get(a_enum, 0)
    target_level = ROLE_HIERARCHY_LEVELS.get(t_enum, 0)

    if actor_level <= target_level:
        return False

    if current_target_role is not None:
        try:
            curr_enum = Role(current_target_role) if isinstance(current_target_role, str) else current_target_role
            curr_level = ROLE_HIERARCHY_LEVELS.get(curr_enum, 0)
            if actor_level <= curr_level:
                return False
        except ValueError:
            return False

    return True


# ── ABAC (Attribute-Based Access Control) Helpers ────────────

def verify_organization_access(
    user_org_id: str | uuid.UUID | None,
    resource_org_id: str | uuid.UUID | None,
    is_super: bool = False,
) -> bool:
    """
    ABAC Tenant Isolation Check.

    Users can only access resources belonging to their organization,
    unless they have SUPER_ADMIN status (is_super=True).
    Fail-closed: Returns False if user_org_id or resource_org_id is None.
    """
    if is_super:
        return True
    if user_org_id is None or resource_org_id is None:
        return False
    return str(user_org_id) == str(resource_org_id)


def verify_resource_ownership(
    user_id: str | uuid.UUID | None,
    resource_owner_id: str | uuid.UUID | None,
    is_admin_override: bool = False,
) -> bool:
    """
    ABAC Resource Ownership Check.

    Users can access resources they own (user_id == resource_owner_id),
    or if authorized via admin override.
    Fail-closed: Returns False if user_id or resource_owner_id is None.
    """
    if is_admin_override:
        return True
    if user_id is None or resource_owner_id is None:
        return False
    return str(user_id) == str(resource_owner_id)


def check_abac_access(
    user_id: str | uuid.UUID | None,
    user_org_id: str | uuid.UUID | None,
    user_role: Role | str,
    resource_org_id: str | uuid.UUID | None = None,
    resource_owner_id: str | uuid.UUID | None = None,
) -> bool:
    """
    Combined ABAC Access Evaluator.

    Evaluates both organization boundary matching and resource ownership.
    - SUPER_ADMIN bypasses organization and ownership boundary restrictions.
    - HOSPITAL_ADMIN can access all resources within their organization.
    - Standard roles must match organization AND (if owner is specified) match resource ownership.
    - Fail-closed: If user_id or user_org_id is None (and not SUPER_ADMIN), returns False.
    """
    role_str = user_role.value if isinstance(user_role, Role) else str(user_role)

    if role_str == Role.SUPER_ADMIN.value:
        return True

    if user_id is None or user_org_id is None:
        return False

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

