"""
NeuroOncoTrack-AI — Admin Schemas & DTO Foundation

Pydantic v2 schemas and DTOs for administrative endpoints.
Enforces zero exposure of sensitive credentials (password hashes, MFA secrets, backup codes).
Includes pagination models, sorting validation, search/filter criteria, and administrative responses.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.permissions import Role

T = TypeVar("T")


# ── 1. Pagination & Sorting DTOs ─────────────────────────────────────────────

class PaginationParams(BaseModel):
    """
    Standard pagination query parameters with strict bounds.
    Prevents database denial-of-service via oversized page requests.
    """

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page (max 100)")
    sort_by: str = Field(default="created_at", max_length=50, description="Sort field name")
    sort_order: Literal["asc", "desc"] = Field(default="desc", description="Sort direction")

    @property
    def offset(self) -> int:
        """Calculate SQL query OFFSET value safely."""
        return (self.page - 1) * self.page_size


def validate_sort_field(
    sort_by: str,
    allowed_fields: set[str],
    default: str = "created_at",
    raise_on_invalid: bool = False,
) -> str:
    """
    Whitelist validation for sorting field names.
    Prevents SQL column injection.
    If raise_on_invalid is True, raises ValidationError (HTTP 422 VAL_001) for unwhitelisted field names.
    """
    clean_field = sort_by.strip().lower()
    if clean_field in allowed_fields:
        return clean_field

    if raise_on_invalid:
        from app.core.exceptions import ValidationError
        raise ValidationError(detail=f"Geçersiz veya sıralanamayan alan: '{sort_by}'.")

    return default


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic wrapper response for paginated endpoint results."""

    items: list[T]
    total: int = Field(..., ge=0, description="Total record count matching criteria")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total available pages")

    @classmethod
    def create(cls, items: list[T], total: int, page: int, page_size: int) -> PaginatedResponse[T]:
        """Factory method to construct a validated paginated response with total page calculation."""
        total_pages = math.ceil(total / page_size) if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


# ── 2. User Permission Override DTOs (from TASK-022) ─────────────────────────

class UserPermissionsResponse(BaseModel):
    """User permissions breakdown response."""

    user_id: str
    email: str
    role: str
    base_permissions: list[str] = Field(default_factory=list)
    extra_permissions: list[str] = Field(default_factory=list)
    revoked_permissions: list[str] = Field(default_factory=list)
    effective_permissions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PermissionOverrideRequest(BaseModel):
    """Request payload for granting or revoking permission overrides."""

    permission: str = Field(
        ..., min_length=1, max_length=100, description="Permission name in resource:action format"
    )

    model_config = ConfigDict(extra="forbid")


# ── 3. Administrative User Management DTOs ────────────────────────────────────

class AdminUserResponse(BaseModel):
    """
    Public administrative user view.
    Zero exposure of password_hash, mfa_secret, totp_secret, or backup_codes.
    """

    id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr
    first_name: str
    last_name: str
    title: str | None = None
    role: str
    is_active: bool
    is_locked: bool
    locked_until: datetime | None = None
    failed_login_attempts: int
    must_change_password: bool
    mfa_enabled: bool
    created_at: datetime
    updated_at: datetime | None = None
    last_login_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AdminUserListResponse(PaginatedResponse[AdminUserResponse]):
    """Paginated user directory list response."""

    pass


class AdminUserCreateRequest(BaseModel):
    """
    Request payload for administrative user onboarding.
    Does NOT require administrators to specify or know the user's password.
    Direct onboarding sets must_change_password=True and generates a setup token.
    """

    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: Role
    title: str | None = Field(default=None, max_length=100)
    organization_id: uuid.UUID | None = Field(
        default=None,
        description="Target Organization UUID (Required for SUPER_ADMIN; auto-assigned for HOSPITAL_ADMIN)",
    )

    model_config = ConfigDict(extra="forbid")


class AdminUserCreateResponse(BaseModel):
    """
    Response returned when an administrator creates a new user account.
    Returns the user profile and initial password setup token.
    """

    user: AdminUserResponse
    setup_token: str = Field(..., description="One-time cryptographically secure token for initial password setup")
    must_change_password: bool = True


class AdminUserUpdateRequest(BaseModel):
    """Request payload for administrative partial profile updates."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = Field(default=None, description="Updated user email address")
    organization_id: uuid.UUID | None = Field(
        default=None, description="Reassign organization (SUPER_ADMIN only)"
    )

    model_config = ConfigDict(extra="forbid")


class AdminRoleChangeRequest(BaseModel):
    """Request payload for updating a target user's system role."""

    new_role: Role = Field(..., description="Target system role enum")

    @model_validator(mode="before")
    @classmethod
    def map_role_alias(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "role" in data and "new_role" not in data:
                data["new_role"] = data.pop("role")
        return data

    model_config = ConfigDict(extra="forbid")


# ── 4. Administrative Organization Management DTOs ───────────────────────────

class AdminOrganizationResponse(BaseModel):
    """Organization detail response for administrative inspection."""

    id: uuid.UUID
    name: str
    code: str
    org_type: str | None = None
    is_active: bool
    description: str | None = None
    user_count: int = Field(default=0, description="Total active users in organization")
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AdminOrganizationListResponse(BaseModel):
    """List response for organizations with pagination metadata."""

    items: list[AdminOrganizationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminOrganizationCreateRequest(BaseModel):
    """Request payload for creating a new organization (SUPER_ADMIN only)."""

    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_\-]+$")
    org_type: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("code", mode="before")
    def normalize_code(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().upper()
        return v

    model_config = ConfigDict(extra="forbid")


class AdminOrganizationUpdateRequest(BaseModel):
    """Request payload for updating organization details."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    org_type: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=1000)

    model_config = ConfigDict(extra="forbid")


# ── 5. Administrative Session Governance DTOs ────────────────────────────────

class AdminSessionResponse(BaseModel):
    """Active session detail for administrative governance and remote revocation."""

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None = None
    user_role: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    device_info: str | None = None
    is_revoked: bool
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminSessionListResponse(BaseModel):
    """List response for active sessions with pagination metadata."""

    items: list[AdminSessionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── 6. Administrative Security Audit Inspection DTOs ─────────────────────────

class AdminAuditLogFilterQuery(BaseModel):
    """Query parameters for searching and filtering security audit logs."""

    start_date: datetime | None = None
    end_date: datetime | None = None
    event_type: str | None = Field(default=None, max_length=100)
    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    result: Literal["GRANTED", "DENIED", "SUCCESS", "FAILURE"] | None = None


class AdminAuditLogResponse(BaseModel):
    """Sanitized security audit log entry response."""

    id: uuid.UUID | str
    event: str
    actor_id: str | None = None
    target_user_id: str | None = None
    organization_id: str | None = None
    result: str
    ip_address: str | None = None
    user_agent: str | None = None
    details: dict | None = Field(default_factory=dict, description="Sanitized audit event details")
    timestamp: datetime


class AdminAuditLogListResponse(BaseModel):
    """Paginated list response for security audit log search and inspection."""

    items: list[AdminAuditLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── 7. Admin Security Dashboard Metrics DTO ──────────────────────────────────

class AdminDashboardStatsResponse(BaseModel):
    """High-level system and security metrics for administrative dashboards."""

    total_users: int = Field(..., ge=0)
    active_users: int = Field(..., ge=0)
    locked_users: int = Field(..., ge=0)
    total_organizations: int = Field(..., ge=0)
    active_sessions: int = Field(..., ge=0)
    security_denials_24h: int = Field(..., ge=0)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class SecurityUserStats(BaseModel):
    total: int = Field(..., ge=0)
    active: int = Field(..., ge=0)
    inactive: int = Field(..., ge=0)
    locked: int = Field(..., ge=0)


class SecurityOrganizationStats(BaseModel):
    total: int = Field(..., ge=0)
    active: int = Field(..., ge=0)
    inactive: int = Field(..., ge=0)


class SecuritySessionStats(BaseModel):
    active: int = Field(..., ge=0)
    revoked: int = Field(..., ge=0)


class SecurityEventStats(BaseModel):
    total: int = Field(..., ge=0)
    failed_logins: int = Field(..., ge=0)
    authorization_denials: int = Field(..., ge=0)
    user_lifecycle_events: int = Field(..., ge=0)
    session_terminations: int = Field(..., ge=0)


class AdminSecurityOverviewResponse(BaseModel):
    """Overall system & security metrics response."""

    users: SecurityUserStats
    organizations: SecurityOrganizationStats
    sessions: SecuritySessionStats
    security_events: SecurityEventStats
    generated_at: datetime


class AdminSecurityTrendPoint(BaseModel):
    timestamp: str
    failed_logins: int = Field(..., ge=0)
    authorization_denials: int = Field(..., ge=0)
    user_locks: int = Field(..., ge=0)
    session_terminations: int = Field(..., ge=0)


class AdminSecurityTrendResponse(BaseModel):
    interval: str
    data: list[AdminSecurityTrendPoint]


class AdminOrganizationSecurityItem(BaseModel):
    organization_id: str
    name: str
    code: str
    is_active: bool
    user_count: int = Field(..., ge=0)
    active_user_count: int = Field(..., ge=0)
    locked_user_count: int = Field(..., ge=0)
    active_session_count: int = Field(..., ge=0)
    security_event_count: int = Field(..., ge=0)


class AdminOrganizationSecurityListResponse(BaseModel):
    organizations: list[AdminOrganizationSecurityItem]
