"""
NeuroOncoTrack-AI — Admin Permission Management Endpoints (v1)

Implements:
- GET    /api/v1/admin/users/{user_id}/permissions — View user permissions breakdown
- POST   /api/v1/admin/users/{user_id}/permissions/extra — Grant extra permission override
- DELETE /api/v1/admin/users/{user_id}/permissions/extra/{permission} — Remove extra permission override
- POST   /api/v1/admin/users/{user_id}/permissions/revoked — Revoke permission override
- DELETE /api/v1/admin/users/{user_id}/permissions/revoked/{permission} — Remove revoked permission override
"""

from __future__ import annotations

import hashlib
import math
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import asc, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import aktif_kullanici, rol_gerektir
from app.core import audit, redis as redis_core, security
from app.core.exceptions import ForbiddenError, ValidationError
from app.core.permissions import (
    Permission,
    Role,
    ROLE_PERMISSIONS,
    SYSTEM_ADMIN_PERMISSIONS,
    can_assign_role,
    get_effective_permissions,
    has_permission,
    is_super_admin,
    normalize_permission,
)
from app.db.session import get_db
from app.models.organization import Organization
from app.models.password_reset_token import PasswordResetToken
from app.models.session import Session
from app.models.user import User
from app.schemas.admin import (
    AdminAuditLogListResponse,
    AdminAuditLogResponse,
    AdminOrganizationCreateRequest,
    AdminOrganizationListResponse,
    AdminOrganizationResponse,
    AdminOrganizationSecurityItem,
    AdminOrganizationSecurityListResponse,
    AdminOrganizationUpdateRequest,
    AdminRoleChangeRequest,
    AdminSecurityOverviewResponse,
    AdminSecurityTrendPoint,
    AdminSecurityTrendResponse,
    AdminSessionListResponse,
    AdminSessionResponse,
    AdminUserCreateRequest,
    AdminUserCreateResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdateRequest,
    PermissionOverrideRequest,
    SecurityEventStats,
    SecurityOrganizationStats,
    SecuritySessionStats,
    SecurityUserStats,
    UserPermissionsResponse,
    validate_sort_field,
)

router = APIRouter(prefix="/admin", tags=["admin-management"])

ALLOWED_USER_SORT_FIELDS = {
    "created_at",
    "updated_at",
    "email",
    "first_name",
    "last_name",
    "role",
    "is_active",
    "is_locked",
}

ALLOWED_AUDIT_SORT_FIELDS = {
    "timestamp",
    "created_at",
    "event",
    "result",
    "actor_id",
}


def _ensure_list(val: Any) -> list[str]:
    """Safely convert list or JSON-serialized string / SQLite array fallback into a list of strings."""
    if not val:
        return []

    if isinstance(val, list):
        # Check for SQLite array fallback where list of single characters is produced
        if len(val) > 0 and all(isinstance(x, str) and len(x) == 1 for x in val):
            val = "".join(val)
        elif len(val) > 0 and isinstance(val[0], str) and val[0].startswith("["):
            val = val[0]
        else:
            res = []
            for item in val:
                if isinstance(item, str) and item.startswith("["):
                    res.extend(_ensure_list(item))
                elif item:
                    res.append(str(item))
            return res

    if isinstance(val, str):
        import json
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except Exception:
            pass
        clean = val.strip("[]'\"").replace("'", "").replace('"', "")
        if clean:
            return [x.strip() for x in clean.split(",") if x.strip()]

    return []


def _build_permissions_response(target_user: User) -> UserPermissionsResponse:
    """Build structured, normalized, and deterministically sorted permissions breakdown."""
    try:
        r_enum = Role(target_user.role) if isinstance(target_user.role, str) else target_user.role
    except ValueError:
        r_enum = None

    base_perms = sorted([p.value for p in ROLE_PERMISSIONS.get(r_enum, set())]) if r_enum else []
    extra_perms = sorted(list(set(_ensure_list(target_user.extra_permissions))))
    revoked_perms = sorted(list(set(_ensure_list(target_user.revoked_permissions))))
    effective_perms = sorted(list(get_effective_permissions(
        target_user.role,
        extra_permissions=extra_perms,
        revoked_permissions=revoked_perms,
    )))

    return UserPermissionsResponse(
        user_id=str(target_user.id),
        email=target_user.email,
        role=str(target_user.role),
        base_permissions=base_perms,
        extra_permissions=extra_perms,
        revoked_permissions=revoked_perms,
        effective_permissions=effective_perms,
    )


async def _resolve_and_authorize_target_user(
    user_id: str,
    actor: User,
    db: AsyncSession,
    check_self_modification: bool = True,
) -> User:
    """Fetch target user from DB and validate tenant boundary, self-modification, and hierarchy rank."""
    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        raise ValidationError(detail="Geçersiz kullanıcı kimliği (UUID).")

    result = await db.execute(select(User).where(User.id == user_uuid))
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise ForbiddenError(detail="Kullanıcı bulunamadı.")

    # Tenant isolation check (HOSPITAL_ADMIN can only manage users within their own organization)
    if not is_super_admin(actor.role):
        if str(actor.organization_id) != str(target_user.organization_id):
            audit.log_authorization_event(
                event="CROSS_TENANT_ACCESS_DENIED",
                actor_id=actor.id,
                target_user_id=target_user.id,
                organization_id=actor.organization_id,
                result="DENIED",
            )
            raise ForbiddenError(detail="Farklı kuruma ait kullanıcının izinleri değiştirilemez.")

        # HOSPITAL_ADMIN cannot modify SUPER_ADMIN or HOSPITAL_ADMIN users
        if is_super_admin(target_user.role) or target_user.role == Role.HOSPITAL_ADMIN.value:
            audit.log_authorization_event(
                event="PRIVILEGE_ESCALATION_ATTEMPT",
                actor_id=actor.id,
                target_user_id=target_user.id,
                organization_id=actor.organization_id,
                result="DENIED",
            )
            raise ForbiddenError(detail="Bu seviyedeki kullanıcının izinlerini değiştirme yetkiniz yoktur.")

    # Self-modification check (Admins cannot modify their own permissions to escalate rank)
    if check_self_modification and str(actor.id) == str(target_user.id) and not is_super_admin(actor.role):
        audit.log_authorization_event(
            event="SELF_PERMISSION_ESCALATION_ATTEMPT",
            actor_id=actor.id,
            target_user_id=target_user.id,
            organization_id=actor.organization_id,
            result="DENIED",
        )
        raise ForbiddenError(detail="Kendi izinlerinizi değiştiremezsiniz.")

    return target_user


def _validate_permission_name(perm_str: str) -> str:
    """Validate permission string against Permission enum definition."""
    norm_perm = normalize_permission(perm_str)
    all_perm_values = {p.value for p in Permission}
    if norm_perm not in all_perm_values:
        raise ValidationError(detail=f"Geçersiz veya bilinmeyen izin: '{perm_str}'.")
    return norm_perm


# ── 0. GET /admin/users ───────────────────────────────────────
@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="Kullanıcı dizinini listele, ara ve filtrele",
)
async def list_admin_users(
    request: Request,
    page: int = Query(default=1, ge=1, description="Sayfa numarası (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Sayfa başına öge sayısı (maks 100)"),
    search: str | None = Query(default=None, max_length=100, description="Email, ad veya soyad arama metni"),
    role: str | None = Query(default=None, description="Rol filtresi (Role enum)"),
    organization_id: uuid.UUID | None = Query(default=None, description="Organizasyon UUID filtresi"),
    is_active: bool | None = Query(default=None, description="Aktiflik durumu filtresi"),
    is_locked: bool | None = Query(default=None, description="Kilitlilik durumu filtresi"),
    sort_by: str = Query(default="created_at", max_length=50, description="Sıralama alanı"),
    sort_order: Literal["asc", "desc"] = Query(default="desc", description="Sıralama yönü (asc/desc)"),
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    """
    Paginated user directory listing for administrative monitoring.

    - Required Permission: user:list
    - Allowed Roles: SUPER_ADMIN (global scope), HOSPITAL_ADMIN (scoped to own organization)
    - Enforces fail-closed tenant boundary, role filter validation, sorting whitelist, and zero credential exposure.
    """
    # Explicit permission check for user:list
    if not has_permission(actor, Permission.USER_LIST):
        audit.log_authorization_event(
            event="UNAUTHORIZED_ATTEMPT",
            actor_id=actor.id,
            organization_id=actor.organization_id,
            permission=Permission.USER_LIST.value,
            result="DENIED",
        )
        raise ForbiddenError(detail="Bu işlem için kullanıcı listeleme yetkiniz yoktur.")

    # Role filter validation
    if role:
        norm_role = role.strip()
        all_roles = {r.value for r in Role}
        if norm_role not in all_roles:
            raise ValidationError(detail=f"Geçersiz veya bilinmeyen rol: '{role}'.")

    # Sorting security validation
    clean_sort_by = validate_sort_field(
        sort_by,
        ALLOWED_USER_SORT_FIELDS,
        default="created_at",
        raise_on_invalid=True,
    )
    sort_col = getattr(User, clean_sort_by)
    order_clause = desc(sort_col) if sort_order == "desc" else asc(sort_col)

    # Base query
    stmt = select(User)

    # Tenant Isolation: HOSPITAL_ADMIN is strictly locked to actor.organization_id
    if is_super_admin(actor.role):
        if organization_id is not None:
            stmt = stmt.where(User.organization_id == organization_id)
    else:
        # HOSPITAL_ADMIN: Always force filter to actor.organization_id
        stmt = stmt.where(User.organization_id == actor.organization_id)

    # Role filter
    if role:
        stmt = stmt.where(User.role == role.strip())

    # Active / Locked status filters
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)

    if is_locked is not None:
        stmt = stmt.where(User.is_locked == is_locked)

    # Search filter (case-insensitive across email, first_name, last_name)
    if search and search.strip():
        search_pattern = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.email).like(search_pattern),
                func.lower(User.first_name).like(search_pattern),
                func.lower(User.last_name).like(search_pattern),
            )
        )

    # Count matching total records after filters & tenant scoping
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total_count = total_result.scalar_one()

    # Apply order and pagination offset/limit
    stmt = stmt.order_by(order_clause, User.id.asc()).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    user_records = result.scalars().all()

    # Convert to sanitized AdminUserResponse DTOs
    items = [AdminUserResponse.model_validate(u) for u in user_records]

    audit.log_audit_event(
        event="USER_LIST",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "page": page,
            "page_size": page_size,
            "total": total_count,
            "organization_id": str(actor.organization_id),
            "searched": bool(search),
            "role_filtered": role,
        },
    )

    return AdminUserListResponse.create(
        items=items,
        total=total_count,
        page=page,
        page_size=page_size,
    )


# ── 0.1 POST /admin/users ─────────────────────────────────────
@router.post(
    "/users",
    response_model=AdminUserCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni kullanıcı hesabı oluştur",
)
async def create_admin_user(
    request: Request,
    payload: AdminUserCreateRequest,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserCreateResponse:
    """
    Administrative user onboarding without requiring administrators to know or store plaintext passwords.

    - Required Permission: user:create
    - Allowed Roles: SUPER_ADMIN, HOSPITAL_ADMIN
    - Hierarchy Check: can_assign_role(actor.role, payload.role)
    - Onboarding: Sets must_change_password=True, assigns random dummy password hash, returns secure setup token.
    """
    # Permission check
    if not has_permission(actor, Permission.USER_CREATE):
        audit.log_authorization_event(
            event="UNAUTHORIZED_ATTEMPT",
            actor_id=actor.id,
            organization_id=actor.organization_id,
            permission=Permission.USER_CREATE.value,
            result="DENIED",
        )
        raise ForbiddenError(detail="Bu işlem için kullanıcı oluşturma yetkiniz yoktur.")

    # Target Organization Scope
    if is_super_admin(actor.role):
        if payload.organization_id is not None:
            org_res = await db.execute(select(Organization).where(Organization.id == payload.organization_id))
            if not org_res.scalar_one_or_none():
                raise ValidationError(detail="Belirtilen organizasyon bulunamadı.")
            target_org_id = payload.organization_id
        else:
            target_org_id = actor.organization_id
    else:
        # HOSPITAL_ADMIN: Force to actor.organization_id
        if payload.organization_id is not None and str(payload.organization_id) != str(actor.organization_id):
            audit.log_authorization_event(
                event="CROSS_TENANT_ACCESS_DENIED",
                actor_id=actor.id,
                organization_id=actor.organization_id,
                result="DENIED",
            )
            raise ForbiddenError(detail="Başka kuruma ait kullanıcı oluşturamazsınız.")
        target_org_id = actor.organization_id

    # Role Hierarchy Check
    if not can_assign_role(actor.role, payload.role):
        audit.log_authorization_event(
            event="PRIVILEGE_ESCALATION_ATTEMPT",
            actor_id=actor.id,
            organization_id=actor.organization_id,
            result="DENIED",
        )
        raise ForbiddenError(detail=f"'{payload.role.value}' rolünü atama yetkiniz yoktur.")

    # Email Uniqueness Check
    clean_email = payload.email.strip().lower()
    email_res = await db.execute(select(User).where(func.lower(User.email) == clean_email))
    if email_res.scalar_one_or_none():
        raise ValidationError(detail="Bu e-posta adresi zaten kullanılmaktadır.")

    # Cryptographically secure setup token & dummy random password hash
    setup_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(setup_token.encode()).hexdigest()
    random_password_hash = security.hash_password(secrets.token_urlsafe(32))
    now = datetime.now(timezone.utc)

    new_user = User(
        id=uuid.uuid4(),
        organization_id=target_org_id,
        email=clean_email,
        password_hash=random_password_hash,
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        title=payload.title.strip() if payload.title else None,
        role=payload.role.value,
        is_active=True,
        is_locked=False,
        failed_login_attempts=0,
        must_change_password=True,
        created_by=actor.id,
    )
    db.add(new_user)
    await db.flush()

    # Register PasswordResetToken record for password setup
    reset_record = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=new_user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(hours=24),
        created_at=now,
    )
    db.add(reset_record)
    await db.commit()
    await db.refresh(new_user)

    audit.log_audit_event(
        event="USER_CREATE",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "created_user_id": str(new_user.id),
            "created_user_email": new_user.email,
            "created_user_role": new_user.role,
            "organization_id": str(new_user.organization_id),
        },
    )

    return AdminUserCreateResponse(
        user=AdminUserResponse.model_validate(new_user),
        setup_token=setup_token,
        must_change_password=True,
    )


# ── 0.2 GET /admin/users/{user_id} ────────────────────────────
@router.get(
    "/users/{user_id}",
    response_model=AdminUserResponse,
    summary="Kullanıcı detayını görüntüle",
)
async def get_admin_user_detail(
    user_id: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """
    Get detailed profile of a specific target user.

    - Required Permission: user:read
    - Tenant Scope: HOSPITAL_ADMIN only sees users within own organization.
    """
    if not has_permission(actor, Permission.USER_READ):
        audit.log_authorization_event(
            event="UNAUTHORIZED_ATTEMPT",
            actor_id=actor.id,
            organization_id=actor.organization_id,
            permission=Permission.USER_READ.value,
            result="DENIED",
        )
        raise ForbiddenError(detail="Bu işlem için kullanıcı okuma yetkiniz yoktur.")

    target_user = await _resolve_and_authorize_target_user(
        user_id=user_id,
        actor=actor,
        db=db,
        check_self_modification=False,
    )

    audit.log_audit_event(
        event="USER_READ",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "target_user_email": target_user.email,
            "organization_id": str(target_user.organization_id),
        },
    )

    return AdminUserResponse.model_validate(target_user)


# ── 0.3 PATCH /admin/users/{user_id} ──────────────────────────
@router.patch(
    "/users/{user_id}",
    response_model=AdminUserResponse,
    summary="Kullanıcı profil bilgilerini güncelle",
)
async def update_admin_user_profile(
    user_id: str,
    request: Request,
    payload: AdminUserUpdateRequest,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """
    Update whitelisted administrative user profile fields.

    - Required Permission: user:update
    - Tenant Scope & Hierarchy: Enforces tenant boundary and hierarchy rules.
    - Blacklisted: Role, password, extra/revoked permissions cannot be modified via profile update.
    """
    if not has_permission(actor, Permission.USER_UPDATE):
        audit.log_authorization_event(
            event="UNAUTHORIZED_ATTEMPT",
            actor_id=actor.id,
            organization_id=actor.organization_id,
            permission=Permission.USER_UPDATE.value,
            result="DENIED",
        )
        raise ForbiddenError(detail="Bu işlem için kullanıcı güncelleme yetkiniz yoktur.")

    target_user = await _resolve_and_authorize_target_user(
        user_id=user_id,
        actor=actor,
        db=db,
        check_self_modification=True,
    )

    updated = False

    if payload.first_name is not None:
        target_user.first_name = payload.first_name.strip()
        updated = True

    if payload.last_name is not None:
        target_user.last_name = payload.last_name.strip()
        updated = True

    if payload.title is not None:
        target_user.title = payload.title.strip() if payload.title else None
        updated = True

    if payload.email is not None:
        clean_email = payload.email.strip().lower()
        if clean_email != target_user.email.lower():
            dup_res = await db.execute(
                select(User).where(func.lower(User.email) == clean_email, User.id != target_user.id)
            )
            if dup_res.scalar_one_or_none():
                raise ValidationError(detail="Bu e-posta adresi zaten kullanılmaktadır.")
            target_user.email = clean_email
            updated = True

    if payload.organization_id is not None:
        if not is_super_admin(actor.role):
            audit.log_authorization_event(
                event="CROSS_TENANT_ACCESS_DENIED",
                actor_id=actor.id,
                target_user_id=target_user.id,
                organization_id=actor.organization_id,
                result="DENIED",
            )
            raise ForbiddenError(detail="Organizasyon değiştirme yetkiniz yoktur.")
        if str(payload.organization_id) != str(target_user.organization_id):
            org_res = await db.execute(select(Organization).where(Organization.id == payload.organization_id))
            if not org_res.scalar_one_or_none():
                raise ValidationError(detail="Belirtilen organizasyon bulunamadı.")
            target_user.organization_id = payload.organization_id
            updated = True

    if updated:
        db.add(target_user)
        await db.commit()
        await db.refresh(target_user)

    audit.log_audit_event(
        event="USER_UPDATE",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "target_user_email": target_user.email,
            "organization_id": str(target_user.organization_id),
            "updated": updated,
        },
    )

    return AdminUserResponse.model_validate(target_user)


# ── 0.4 PUT /admin/users/{user_id}/role ───────────────────────
@router.put(
    "/users/{user_id}/role",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Kullanıcı rolünü değiştir",
)
async def assign_admin_user_role(
    user_id: str,
    request: Request,
    payload: AdminRoleChangeRequest,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """
    Assign/update system role for a target user.

    - Permission Requirement: role:assign (Permission.ROLE_ASSIGN)
    - Allowed Roles: SUPER_ADMIN, HOSPITAL_ADMIN
    - Hierarchy Check: can_assign_role(actor.role, payload.new_role, target_user.role)
    - Self-Action Defense: Admins cannot change their own role rank.
    - Tenant Isolation: HOSPITAL_ADMIN can only change roles for users within own organization.
    """
    # Permission check for role:assign
    if not has_permission(actor, Permission.ROLE_ASSIGN):
        audit.log_authorization_event(
            event="UNAUTHORIZED_ATTEMPT",
            actor_id=actor.id,
            organization_id=actor.organization_id,
            permission=Permission.ROLE_ASSIGN.value,
            result="DENIED",
        )
        raise ForbiddenError(detail="Bu işlem için rol atama yetkiniz yoktur.")

    # Target user resolution & authorization (UUID, tenant scope, hierarchy rank, self-action check)
    target_user = await _resolve_and_authorize_target_user(
        user_id=user_id,
        actor=actor,
        db=db,
        check_self_modification=True,
    )

    # Validate role hierarchy assignment rules (actor rank > new_role rank AND actor rank > current_role rank)
    if not can_assign_role(actor.role, payload.new_role, current_target_role=target_user.role):
        audit.log_authorization_event(
            event="PRIVILEGE_ESCALATION_ATTEMPT",
            actor_id=actor.id,
            target_user_id=target_user.id,
            organization_id=actor.organization_id,
            result="DENIED",
        )
        raise ForbiddenError(detail=f"'{payload.new_role.value}' rolünü atama veya değiştirme yetkiniz yoktur.")

    old_role = str(target_user.role)

    # Check if role is unchanged (NO-OP)
    if old_role == payload.new_role.value:
        return AdminUserResponse.model_validate(target_user)

    # Apply role mutation
    target_user.role = payload.new_role.value
    db.add(target_user)
    await db.commit()
    await db.refresh(target_user)

    # Audit logging
    audit.log_audit_event(
        event="ROLE_GRANTED",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "target_user_email": target_user.email,
            "previous_role": old_role,
            "new_role": target_user.role,
            "organization_id": str(target_user.organization_id),
        },
    )

    return AdminUserResponse.model_validate(target_user)


# ── 0.5 POST /admin/users/{user_id}/lock ──────────────────────
@router.post(
    "/users/{user_id}/lock",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Kullanıcı hesabını kilitle",
)
async def lock_admin_user(
    user_id: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """
    Lock target user account (user:lock permission).
    """
    if not has_permission(actor, Permission.USER_LOCK):
        audit.log_authorization_event(
            event="UNAUTHORIZED_ATTEMPT",
            actor_id=actor.id,
            organization_id=actor.organization_id,
            permission=Permission.USER_LOCK.value,
            result="DENIED",
        )
        raise ForbiddenError(detail="Bu işlem için kullanıcı kilitleme yetkiniz yoktur.")

    target_user = await _resolve_and_authorize_target_user(
        user_id=user_id,
        actor=actor,
        db=db,
        check_self_modification=True,
    )

    if not target_user.is_locked:
        target_user.is_locked = True
        db.add(target_user)
        await db.commit()
        await db.refresh(target_user)

    audit.log_audit_event(
        event="USER_LOCKED",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "target_user_email": target_user.email,
            "organization_id": str(target_user.organization_id),
        },
    )

    return AdminUserResponse.model_validate(target_user)


# ── 0.6 POST /admin/users/{user_id}/unlock ────────────────────
@router.post(
    "/users/{user_id}/unlock",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Kullanıcı hesabı kilidini kaldır",
)
async def unlock_admin_user(
    user_id: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """
    Unlock target user account (user:lock permission).
    Resets failed login attempts and clears locked_until timestamp.
    """
    if not has_permission(actor, Permission.USER_LOCK):
        audit.log_authorization_event(
            event="UNAUTHORIZED_ATTEMPT",
            actor_id=actor.id,
            organization_id=actor.organization_id,
            permission=Permission.USER_LOCK.value,
            result="DENIED",
        )
        raise ForbiddenError(detail="Bu işlem için kullanıcı kilidi kaldırma yetkiniz yoktur.")

    target_user = await _resolve_and_authorize_target_user(
        user_id=user_id,
        actor=actor,
        db=db,
        check_self_modification=True,
    )

    target_user.is_locked = False
    target_user.locked_until = None
    target_user.failed_login_attempts = 0
    db.add(target_user)
    await db.commit()
    await db.refresh(target_user)

    audit.log_audit_event(
        event="USER_UNLOCKED",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "target_user_email": target_user.email,
            "organization_id": str(target_user.organization_id),
        },
    )

    return AdminUserResponse.model_validate(target_user)


# ── 0.7 POST /admin/users/{user_id}/activate ──────────────────
@router.post(
    "/users/{user_id}/activate",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Kullanıcı hesabını aktifleştir",
)
async def activate_admin_user(
    user_id: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """
    Activate target user account (user:update permission).
    """
    if not has_permission(actor, Permission.USER_UPDATE):
        audit.log_authorization_event(
            event="UNAUTHORIZED_ATTEMPT",
            actor_id=actor.id,
            organization_id=actor.organization_id,
            permission=Permission.USER_UPDATE.value,
            result="DENIED",
        )
        raise ForbiddenError(detail="Bu işlem için kullanıcı aktifleştirme yetkiniz yoktur.")

    target_user = await _resolve_and_authorize_target_user(
        user_id=user_id,
        actor=actor,
        db=db,
        check_self_modification=True,
    )

    if not target_user.is_active:
        target_user.is_active = True
        db.add(target_user)
        await db.commit()
        await db.refresh(target_user)

    audit.log_audit_event(
        event="USER_ACTIVATED",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "target_user_email": target_user.email,
            "organization_id": str(target_user.organization_id),
        },
    )

    return AdminUserResponse.model_validate(target_user)


# ── 0.8 POST /admin/users/{user_id}/deactivate ────────────────
@router.post(
    "/users/{user_id}/deactivate",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Kullanıcı hesabını pasife al",
)
async def deactivate_admin_user(
    user_id: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """
    Deactivate target user account (user:update permission).
    """
    if not has_permission(actor, Permission.USER_UPDATE):
        audit.log_authorization_event(
            event="UNAUTHORIZED_ATTEMPT",
            actor_id=actor.id,
            organization_id=actor.organization_id,
            permission=Permission.USER_UPDATE.value,
            result="DENIED",
        )
        raise ForbiddenError(detail="Bu işlem için kullanıcı pasife alma yetkiniz yoktur.")

    target_user = await _resolve_and_authorize_target_user(
        user_id=user_id,
        actor=actor,
        db=db,
        check_self_modification=True,
    )

    if target_user.is_active:
        target_user.is_active = False
        db.add(target_user)
        await db.commit()
        await db.refresh(target_user)

    audit.log_audit_event(
        event="USER_DEACTIVATED",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "target_user_email": target_user.email,
            "organization_id": str(target_user.organization_id),
        },
    )

    return AdminUserResponse.model_validate(target_user)


# ── 0.9 POST /admin/users/{user_id}/force-logout ─────────────
@router.post(
    "/users/{user_id}/force-logout",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Kullanıcının tüm oturumlarını sonlandır (Force Logout)",
)
async def force_logout_admin_user(
    user_id: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """
    Force logout target user:
    1. Revokes all active database refresh sessions for the target user (Session.revoked_at = now).
    2. Blacklists user tokens in Redis (bl:user:{target_user.id}) for access token TTL duration.
    """
    if not has_permission(actor, Permission.USER_LOCK):
        audit.log_authorization_event(
            event="UNAUTHORIZED_ATTEMPT",
            actor_id=actor.id,
            organization_id=actor.organization_id,
            permission=Permission.USER_LOCK.value,
            result="DENIED",
        )
        raise ForbiddenError(detail="Bu işlem için oturum sonlandırma yetkiniz yoktur.")

    target_user = await _resolve_and_authorize_target_user(
        user_id=user_id,
        actor=actor,
        db=db,
        check_self_modification=True,
    )

    now = datetime.now(timezone.utc)

    # Revoke all active DB sessions for target user
    sess_stmt = (
        update(Session)
        .where(Session.user_id == target_user.id, Session.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    sess_res = await db.execute(sess_stmt)
    revoked_count = getattr(sess_res, "rowcount", 0)

    if revoked_count == 0:
        dummy_sess = Session(
            user_id=target_user.id,
            refresh_token_hash=security.hash_token("FORCE_LOGOUT_" + uuid.uuid4().hex),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            created_at=now,
            last_used_at=now,
            expires_at=now,
            revoked_at=now,
            revocation_reason="FORCE_LOGOUT",
        )
        db.add(dummy_sess)

    await db.commit()
    await db.refresh(target_user)

    # Blacklist in Redis if available
    app_obj = getattr(request, "app", None)
    app_state = getattr(app_obj, "state", None) if app_obj else None
    redis_client = getattr(app_state, "redis", None) if app_state else None

    if redis_client:
        try:
            await redis_client.set(f"bl:user:{target_user.id}", "1", ex=3600)
        except Exception:
            pass

    audit.log_audit_event(
        event="USER_FORCE_LOGOUT",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "target_user_email": target_user.email,
            "revoked_session_count": revoked_count,
            "organization_id": str(target_user.organization_id),
        },
    )

    return AdminUserResponse.model_validate(target_user)


# ── 0.10 GET /admin/organizations ─────────────────────────────
@router.get(
    "/organizations",
    response_model=AdminOrganizationListResponse,
    summary="Kurumları listele",
)
async def list_admin_organizations(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminOrganizationListResponse:
    """
    List organizations with tenant isolation:
    - SUPER_ADMIN: Global scope (lists all organizations)
    - HOSPITAL_ADMIN: Scoped strictly to actor.organization_id
    """
    query = select(Organization)

    # Tenant isolation filtering
    if not is_super_admin(actor.role):
        query = query.where(Organization.id == actor.organization_id)
    elif search:
        search_term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Organization.name.ilike(search_term),
                Organization.code.ilike(search_term),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one_or_none() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(Organization.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    orgs = result.scalars().all()

    # Build response items with user count
    items: list[AdminOrganizationResponse] = []
    for org in orgs:
        cnt_stmt = select(func.count(User.id)).where(
            User.organization_id == org.id,
            User.is_active.is_(True),
        )
        cnt_res = await db.execute(cnt_stmt)
        user_cnt = cnt_res.scalar_one_or_none() or 0

        items.append(
            AdminOrganizationResponse(
                id=org.id,
                name=org.name,
                code=org.code,
                org_type=org.org_type,
                is_active=org.is_active,
                description=org.description,
                user_count=user_cnt,
                created_at=org.created_at,
                updated_at=org.updated_at,
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    audit.log_audit_event(
        event="ORGANIZATION_LIST",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "page": page,
            "page_size": page_size,
            "total": total,
            "tenant_scoped": not is_super_admin(actor.role),
        },
    )

    return AdminOrganizationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ── 0.11 POST /admin/organizations ────────────────────────────
@router.post(
    "/organizations",
    response_model=AdminOrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni kurum oluştur (SUPER_ADMIN only)",
)
async def create_admin_organization(
    request: Request,
    payload: AdminOrganizationCreateRequest,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminOrganizationResponse:
    """
    Create a new organization. Allowed for SUPER_ADMIN only.
    Enforces uppercase code normalization and duplicate prevention.
    """
    normalized_code = payload.code.upper()

    # Check for duplicate organization code
    dup_stmt = select(Organization).where(func.upper(Organization.code) == normalized_code)
    dup_res = await db.execute(dup_stmt)
    if dup_res.scalar_one_or_none():
        raise ValidationError(detail=f"'{normalized_code}' kurum kodu zaten kullanılmaktadır.")

    new_org = Organization(
        id=uuid.uuid4(),
        name=payload.name.strip(),
        code=normalized_code,
        org_type=payload.org_type.strip() if payload.org_type else None,
        description=payload.description.strip() if payload.description else None,
        is_active=True,
    )

    db.add(new_org)
    await db.commit()
    await db.refresh(new_org)

    audit.log_audit_event(
        event="ORGANIZATION_CREATE",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "organization_id": str(new_org.id),
            "name": new_org.name,
            "code": new_org.code,
        },
    )

    return AdminOrganizationResponse(
        id=new_org.id,
        name=new_org.name,
        code=new_org.code,
        org_type=new_org.org_type,
        is_active=new_org.is_active,
        description=new_org.description,
        user_count=0,
        created_at=new_org.created_at,
        updated_at=new_org.updated_at,
    )


# ── 0.12 GET /admin/organizations/{organization_id} ───────────
@router.get(
    "/organizations/{organization_id}",
    response_model=AdminOrganizationResponse,
    summary="Kurum detayını görüntüle",
)
async def get_admin_organization_detail(
    organization_id: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminOrganizationResponse:
    """
    Get organization details:
    - SUPER_ADMIN: Global scope (access any org detail)
    - HOSPITAL_ADMIN: Scoped strictly to actor.organization_id
    """
    try:
        org_uuid = uuid.UUID(organization_id)
    except (ValueError, TypeError):
        raise ValidationError(detail="Geçersiz kurum kimliği formatı.")

    if not is_super_admin(actor.role):
        if str(actor.organization_id) != str(org_uuid):
            audit.log_authorization_event(
                event="CROSS_TENANT_ACCESS_DENIED",
                actor_id=actor.id,
                organization_id=actor.organization_id,
                result="DENIED",
            )
            raise ForbiddenError(detail="Başka kuruma ait bilgilere erişemezsiniz.")

    stmt = select(Organization).where(Organization.id == org_uuid)
    res = await db.execute(stmt)
    org = res.scalar_one_or_none()

    if not org:
        raise ForbiddenError(detail="Kurum bulunamadı.")

    cnt_stmt = select(func.count(User.id)).where(
        User.organization_id == org.id,
        User.is_active.is_(True),
    )
    cnt_res = await db.execute(cnt_stmt)
    user_cnt = cnt_res.scalar_one_or_none() or 0

    audit.log_audit_event(
        event="ORGANIZATION_READ",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "organization_id": str(org.id),
            "code": org.code,
        },
    )

    return AdminOrganizationResponse(
        id=org.id,
        name=org.name,
        code=org.code,
        org_type=org.org_type,
        is_active=org.is_active,
        description=org.description,
        user_count=user_cnt,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


# ── 0.13 PATCH /admin/organizations/{organization_id} ──────────
@router.patch(
    "/organizations/{organization_id}",
    response_model=AdminOrganizationResponse,
    summary="Kurum bilgilerini güncelle",
)
async def update_admin_organization(
    organization_id: str,
    request: Request,
    payload: AdminOrganizationUpdateRequest,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminOrganizationResponse:
    """
    Update organization profile:
    - SUPER_ADMIN: Global scope, can update name, org_type, description.
    - HOSPITAL_ADMIN: Scoped to own tenant. Cannot update org_type or code.
    """
    try:
        org_uuid = uuid.UUID(organization_id)
    except (ValueError, TypeError):
        raise ValidationError(detail="Geçersiz kurum kimliği formatı.")

    if not is_super_admin(actor.role):
        if str(actor.organization_id) != str(org_uuid):
            audit.log_authorization_event(
                event="CROSS_TENANT_ACCESS_DENIED",
                actor_id=actor.id,
                organization_id=actor.organization_id,
                result="DENIED",
            )
            raise ForbiddenError(detail="Başka kuruma ait bilgileri güncelleyemezsiniz.")

        if payload.org_type is not None:
            raise ForbiddenError(detail="HOSPITAL_ADMIN yöneticileri kurum türünü (org_type) değiştiremez.")

    stmt = select(Organization).where(Organization.id == org_uuid)
    res = await db.execute(stmt)
    org = res.scalar_one_or_none()

    if not org:
        raise ForbiddenError(detail="Kurum bulunamadı.")

    updated = False
    if payload.name is not None and payload.name.strip() != org.name:
        org.name = payload.name.strip()
        updated = True

    if payload.description is not None and payload.description != org.description:
        org.description = payload.description.strip() if payload.description else None
        updated = True

    if is_super_admin(actor.role) and payload.org_type is not None and payload.org_type != org.org_type:
        org.org_type = payload.org_type.strip() if payload.org_type else None
        updated = True

    if updated:
        db.add(org)
        await db.commit()
        await db.refresh(org)

    cnt_stmt = select(func.count(User.id)).where(
        User.organization_id == org.id,
        User.is_active.is_(True),
    )
    cnt_res = await db.execute(cnt_stmt)
    user_cnt = cnt_res.scalar_one_or_none() or 0

    audit.log_audit_event(
        event="ORGANIZATION_UPDATE",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "organization_id": str(org.id),
            "updated": updated,
        },
    )

    return AdminOrganizationResponse(
        id=org.id,
        name=org.name,
        code=org.code,
        org_type=org.org_type,
        is_active=org.is_active,
        description=org.description,
        user_count=user_cnt,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


# ── 0.14 POST /admin/organizations/{organization_id}/deactivate ──
@router.post(
    "/organizations/{organization_id}/deactivate",
    response_model=AdminOrganizationResponse,
    summary="Kurumu pasife al (SUPER_ADMIN only)",
)
async def deactivate_admin_organization(
    organization_id: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminOrganizationResponse:
    """
    Deactivate an organization. Allowed for SUPER_ADMIN only.
    Idempotent operation.
    """
    try:
        org_uuid = uuid.UUID(organization_id)
    except (ValueError, TypeError):
        raise ValidationError(detail="Geçersiz kurum kimliği formatı.")

    stmt = select(Organization).where(Organization.id == org_uuid)
    res = await db.execute(stmt)
    org = res.scalar_one_or_none()

    if not org:
        raise ForbiddenError(detail="Kurum bulunamadı.")

    if org.is_active:
        org.is_active = False
        db.add(org)
        await db.commit()
        await db.refresh(org)

    cnt_stmt = select(func.count(User.id)).where(
        User.organization_id == org.id,
        User.is_active.is_(True),
    )
    cnt_res = await db.execute(cnt_stmt)
    user_cnt = cnt_res.scalar_one_or_none() or 0

    audit.log_audit_event(
        event="ORGANIZATION_DEACTIVATED",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "organization_id": str(org.id),
            "code": org.code,
        },
    )

    return AdminOrganizationResponse(
        id=org.id,
        name=org.name,
        code=org.code,
        org_type=org.org_type,
        is_active=org.is_active,
        description=org.description,
        user_count=user_cnt,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


# ── 0.15 GET /admin/sessions ──────────────────────────────────
@router.get(
    "/sessions",
    response_model=AdminSessionListResponse,
    summary="Aktif oturumları listele (System/Org-wide)",
)
async def list_admin_active_sessions(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    active_only: bool = Query(default=True),
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminSessionListResponse:
    """
    List active sessions system-wide or organization-scoped:
    - SUPER_ADMIN: Global active sessions across all tenants
    - HOSPITAL_ADMIN: Active sessions for users belonging to actor.organization_id ONLY
    """
    now = datetime.now(timezone.utc)
    query = select(Session).join(User, Session.user_id == User.id)

    if not is_super_admin(actor.role):
        query = query.where(User.organization_id == actor.organization_id)

    if active_only:
        query = query.where(Session.revoked_at.is_(None), Session.expires_at > now)

    count_stmt = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one_or_none() or 0

    offset = (page - 1) * page_size
    query = query.order_by(Session.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    sessions = result.scalars().all()

    items: list[AdminSessionResponse] = []
    for s in sessions:
        user_stmt = select(User).where(User.id == s.user_id)
        u_res = await db.execute(user_stmt)
        u = u_res.scalar_one_or_none()

        items.append(
            AdminSessionResponse(
                id=s.id,
                user_id=s.user_id,
                user_email=u.email if u else None,
                user_role=u.role if u else None,
                ip_address=s.ip_address,
                user_agent=s.user_agent,
                device_info=s.device_fingerprint,
                is_revoked=s.is_revoked,
                created_at=s.created_at,
                expires_at=s.expires_at,
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    audit.log_audit_event(
        event="SESSION_LIST",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "page": page,
            "page_size": page_size,
            "total": total,
            "tenant_scoped": not is_super_admin(actor.role),
        },
    )

    return AdminSessionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ── 0.16 DELETE /admin/sessions/{session_id} ─────────────────
@router.delete(
    "/sessions/{session_id}",
    response_model=AdminSessionResponse,
    summary="Oturumu uzaktan sonlandır (Remote Termination)",
)
async def terminate_admin_session_by_id(
    session_id: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminSessionResponse:
    """
    Remote session termination by session ID.
    Enforces tenant boundaries, role hierarchy, and self-action protections.
    """
    try:
        sess_uuid = uuid.UUID(session_id)
    except (ValueError, TypeError):
        raise ValidationError(detail="Geçersiz oturum kimliği formatı.")

    stmt = select(Session, User).join(User, Session.user_id == User.id).where(Session.id == sess_uuid)
    res = await db.execute(stmt)
    row = res.first()

    if not row:
        raise ForbiddenError(detail="Oturum bulunamadı.")

    session_obj, target_user = row

    # Hierarchy rank check via can_assign_role
    if not can_assign_role(actor.role, target_user.role, current_target_role=target_user.role):
        audit.log_authorization_event(
            event="PRIVILEGE_ESCALATION_ATTEMPT",
            actor_id=actor.id,
            target_user_id=target_user.id,
            organization_id=actor.organization_id,
            result="DENIED",
        )
        raise ForbiddenError(detail="Üst veya eşit yetkideki kullanıcının oturumunu sonlandıramazsınız.")

    # Tenant isolation check
    if not is_super_admin(actor.role):
        if str(actor.organization_id) != str(target_user.organization_id):
            audit.log_authorization_event(
                event="CROSS_TENANT_ACCESS_DENIED",
                actor_id=actor.id,
                organization_id=actor.organization_id,
                result="DENIED",
            )
            raise ForbiddenError(detail="Başka kuruma ait oturumları sonlandıramazsınız.")

    # Self-action defense
    if str(actor.id) == str(target_user.id):
        raise ForbiddenError(detail="Kendi aktif oturumunuzu bu endpoint üzerinden sonlandıramazsınız.")

    now = datetime.now(timezone.utc)

    if not session_obj.is_revoked:
        session_obj.revoked_at = now
        session_obj.revocation_reason = "ADMIN_TERMINATED"
        db.add(session_obj)
        await db.commit()
        await db.refresh(session_obj)

    # Blacklist user in Redis
    app_obj = getattr(request, "app", None)
    app_state = getattr(app_obj, "state", None) if app_obj else None
    redis_client = getattr(app_state, "redis", None) if app_state else None

    if redis_client:
        try:
            await redis_client.set(f"bl:user:{target_user.id}", "1", ex=3600)
        except Exception:
            pass

    audit.log_audit_event(
        event="SESSION_TERMINATED",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "session_id": str(session_obj.id),
            "organization_id": str(target_user.organization_id),
        },
    )

    return AdminSessionResponse(
        id=session_obj.id,
        user_id=session_obj.user_id,
        user_email=target_user.email,
        user_role=target_user.role,
        ip_address=session_obj.ip_address,
        user_agent=session_obj.user_agent,
        device_info=session_obj.device_fingerprint,
        is_revoked=session_obj.is_revoked,
        created_at=session_obj.created_at,
        expires_at=session_obj.expires_at,
    )


# ── 0.17 GET /admin/users/{user_id}/sessions ──────────────────
@router.get(
    "/users/{user_id}/sessions",
    response_model=AdminSessionListResponse,
    summary="Hedef kullanıcının aktif oturumlarını listele",
)
async def list_admin_target_user_sessions(
    user_id: str,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    active_only: bool = Query(default=True),
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminSessionListResponse:
    """
    List active sessions for a specific target user.
    Enforces tenant boundaries and hierarchy rank checks.
    """
    target_user = await _resolve_and_authorize_target_user(
        user_id=user_id,
        actor=actor,
        db=db,
        check_self_modification=False,
    )

    now = datetime.now(timezone.utc)
    query = select(Session).where(Session.user_id == target_user.id)

    if active_only:
        query = query.where(Session.revoked_at.is_(None), Session.expires_at > now)

    count_stmt = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one_or_none() or 0

    offset = (page - 1) * page_size
    query = query.order_by(Session.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    sessions = result.scalars().all()

    items = [
        AdminSessionResponse(
            id=s.id,
            user_id=s.user_id,
            user_email=target_user.email,
            user_role=target_user.role,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            device_info=s.device_fingerprint,
            is_revoked=s.is_revoked,
            created_at=s.created_at,
            expires_at=s.expires_at,
        )
        for s in sessions
    ]

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    audit.log_audit_event(
        event="SESSION_LIST",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "total": total,
        },
    )

    return AdminSessionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ── 0.18 POST /admin/users/{user_id}/sessions/{session_id}/terminate ──
@router.post(
    "/users/{user_id}/sessions/{session_id}/terminate",
    response_model=AdminSessionResponse,
    summary="Hedef kullanıcının tek bir oturumunu sonlandır",
)
async def terminate_admin_target_user_session(
    user_id: str,
    session_id: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminSessionResponse:
    """
    Terminate a single session for a specific target user.
    """
    target_user = await _resolve_and_authorize_target_user(
        user_id=user_id,
        actor=actor,
        db=db,
        check_self_modification=True,
    )

    try:
        sess_uuid = uuid.UUID(session_id)
    except (ValueError, TypeError):
        raise ValidationError(detail="Geçersiz oturum kimliği formatı.")

    stmt = select(Session).where(Session.id == sess_uuid, Session.user_id == target_user.id)
    res = await db.execute(stmt)
    session_obj = res.scalar_one_or_none()

    if not session_obj:
        raise ForbiddenError(detail="Oturum bulunamadı.")

    now = datetime.now(timezone.utc)

    if not session_obj.is_revoked:
        session_obj.revoked_at = now
        session_obj.revocation_reason = "ADMIN_TERMINATED"
        db.add(session_obj)
        await db.commit()
        await db.refresh(session_obj)

    app_obj = getattr(request, "app", None)
    app_state = getattr(app_obj, "state", None) if app_obj else None
    redis_client = getattr(app_state, "redis", None) if app_state else None

    if redis_client:
        try:
            await redis_client.set(f"bl:user:{target_user.id}", "1", ex=3600)
        except Exception:
            pass

    audit.log_audit_event(
        event="SESSION_TERMINATED",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "session_id": str(session_obj.id),
            "organization_id": str(target_user.organization_id),
        },
    )

    return AdminSessionResponse(
        id=session_obj.id,
        user_id=session_obj.user_id,
        user_email=target_user.email,
        user_role=target_user.role,
        ip_address=session_obj.ip_address,
        user_agent=session_obj.user_agent,
        device_info=session_obj.device_fingerprint,
        is_revoked=session_obj.is_revoked,
        created_at=session_obj.created_at,
        expires_at=session_obj.expires_at,
    )


# ── 0.19 POST /admin/users/{user_id}/sessions/terminate-all ──
@router.post(
    "/users/{user_id}/sessions/terminate-all",
    response_model=AdminSessionListResponse,
    summary="Hedef kullanıcının tüm oturumlarını sonlandır",
)
async def terminate_all_admin_target_user_sessions(
    user_id: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminSessionListResponse:
    """
    Terminate all active sessions for a target user.
    Idempotent operation.
    """
    target_user = await _resolve_and_authorize_target_user(
        user_id=user_id,
        actor=actor,
        db=db,
        check_self_modification=True,
    )

    now = datetime.now(timezone.utc)

    # Bulk update active sessions
    sess_stmt = (
        update(Session)
        .where(Session.user_id == target_user.id, Session.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason="ADMIN_TERMINATED_ALL")
    )
    sess_res = await db.execute(sess_stmt)
    revoked_count = getattr(sess_res, "rowcount", 0)
    await db.commit()

    # Redis user blacklist
    app_obj = getattr(request, "app", None)
    app_state = getattr(app_obj, "state", None) if app_obj else None
    redis_client = getattr(app_state, "redis", None) if app_state else None

    if redis_client:
        try:
            await redis_client.set(f"bl:user:{target_user.id}", "1", ex=3600)
        except Exception:
            pass

    # Fetch updated sessions for response
    query = select(Session).where(Session.user_id == target_user.id).order_by(Session.created_at.desc())
    res = await db.execute(query)
    sessions = res.scalars().all()

    items = [
        AdminSessionResponse(
            id=s.id,
            user_id=s.user_id,
            user_email=target_user.email,
            user_role=target_user.role,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            device_info=s.device_fingerprint,
            is_revoked=s.is_revoked,
            created_at=s.created_at,
            expires_at=s.expires_at,
        )
        for s in sessions
    ]

    audit.log_audit_event(
        event="USER_SESSIONS_TERMINATED",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "terminated_session_count": revoked_count,
            "organization_id": str(target_user.organization_id),
        },
    )

    return AdminSessionListResponse(
        items=items,
        total=len(items),
        page=1,
        page_size=max(len(items), 1),
        total_pages=1,
    )


# ── 1. GET /admin/users/{user_id}/permissions ─────────────────
@router.get(
    "/users/{user_id}/permissions",
    response_model=UserPermissionsResponse,
    summary="Kullanıcı izinlerini görüntüle",
)
async def get_user_permissions(
    user_id: str,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> UserPermissionsResponse:
    """Fetch structured permission breakdown (base, extra, revoked, effective) for target user."""
    target_user = await _resolve_and_authorize_target_user(user_id, actor, db, check_self_modification=False)
    return _build_permissions_response(target_user)


# ── 2. POST /admin/users/{user_id}/permissions/extra ──────────
@router.post(
    "/users/{user_id}/permissions/extra",
    response_model=UserPermissionsResponse,
    summary="Ekstra izin atama",
)
async def add_extra_permission(
    user_id: str,
    req_body: PermissionOverrideRequest,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> UserPermissionsResponse:
    """Grant an extra permission override to target user."""
    target_user = await _resolve_and_authorize_target_user(user_id, actor, db, check_self_modification=True)
    norm_perm = _validate_permission_name(req_body.permission)

    # Escalation protection: Non-SUPER_ADMIN cannot grant SYSTEM_ADMIN_PERMISSIONS
    if not is_super_admin(actor.role):
        sys_admin_values = {p.value for p in SYSTEM_ADMIN_PERMISSIONS}
        if norm_perm in sys_admin_values:
            audit.log_authorization_event(
                event="PRIVILEGE_ESCALATION_ATTEMPT",
                actor_id=actor.id,
                target_user_id=target_user.id,
                organization_id=actor.organization_id,
                permission=norm_perm,
                result="DENIED",
            )
            raise ForbiddenError(detail="Sistem yöneticisi seviyesindeki izinler atanamaz.")

    extra_set = set(_ensure_list(target_user.extra_permissions))
    extra_set.add(norm_perm)
    target_user.extra_permissions = sorted(list(extra_set))

    await db.commit()
    await db.refresh(target_user)

    audit.log_audit_event(
        event="YETKI_ATANDI",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "permission": norm_perm,
            "override_type": "extra",
            "organization_id": str(target_user.organization_id),
        },
    )

    return _build_permissions_response(target_user)


# ── 3. DELETE /admin/users/{user_id}/permissions/extra/{permission} ──
@router.delete(
    "/users/{user_id}/permissions/extra/{permission}",
    response_model=UserPermissionsResponse,
    summary="Ekstra izni kaldır",
)
async def remove_extra_permission(
    user_id: str,
    permission: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> UserPermissionsResponse:
    """Remove an extra permission override from target user."""
    target_user = await _resolve_and_authorize_target_user(user_id, actor, db, check_self_modification=True)
    norm_perm = _validate_permission_name(permission)

    extra_set = set(_ensure_list(target_user.extra_permissions))
    if norm_perm in extra_set:
        extra_set.remove(norm_perm)
        target_user.extra_permissions = sorted(list(extra_set))
        await db.commit()
        await db.refresh(target_user)

        audit.log_audit_event(
            event="YETKI_KALDIRILDI",
            user_id=actor.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            details={
                "target_user_id": str(target_user.id),
                "permission": norm_perm,
                "override_type": "extra_remove",
                "organization_id": str(target_user.organization_id),
            },
        )

    return _build_permissions_response(target_user)


# ── 4. POST /admin/users/{user_id}/permissions/revoked ─────────
@router.post(
    "/users/{user_id}/permissions/revoked",
    response_model=UserPermissionsResponse,
    summary="İzin iptal etme (Revoke)",
)
async def add_revoked_permission(
    user_id: str,
    req_body: PermissionOverrideRequest,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> UserPermissionsResponse:
    """Revoke a permission from target user."""
    target_user = await _resolve_and_authorize_target_user(user_id, actor, db, check_self_modification=True)
    norm_perm = _validate_permission_name(req_body.permission)

    revoked_set = set(_ensure_list(target_user.revoked_permissions))
    revoked_set.add(norm_perm)
    target_user.revoked_permissions = sorted(list(revoked_set))

    await db.commit()
    await db.refresh(target_user)

    audit.log_audit_event(
        event="YETKI_KALDIRILDI",
        user_id=actor.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        details={
            "target_user_id": str(target_user.id),
            "permission": norm_perm,
            "override_type": "revoked",
            "organization_id": str(target_user.organization_id),
        },
    )

    return _build_permissions_response(target_user)


# ── 5. DELETE /admin/users/{user_id}/permissions/revoked/{permission} ──
@router.delete(
    "/users/{user_id}/permissions/revoked/{permission}",
    response_model=UserPermissionsResponse,
    summary="İptal edilen izni kaldır (Un-revoke)",
)
async def remove_revoked_permission(
    user_id: str,
    permission: str,
    request: Request,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> UserPermissionsResponse:
    """Remove a revoked permission override from target user."""
    target_user = await _resolve_and_authorize_target_user(user_id, actor, db, check_self_modification=True)
    norm_perm = _validate_permission_name(permission)

    revoked_set = set(_ensure_list(target_user.revoked_permissions))
    if norm_perm in revoked_set:
        revoked_set.remove(norm_perm)
        target_user.revoked_permissions = sorted(list(revoked_set))
        await db.commit()
        await db.refresh(target_user)

        audit.log_audit_event(
            event="YETKI_ATANDI",
            user_id=actor.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            details={
                "target_user_id": str(target_user.id),
                "permission": norm_perm,
                "override_type": "revoked_remove",
                "organization_id": str(target_user.organization_id),
            },
        )

    return _build_permissions_response(target_user)


async def _get_combined_audit_logs(db: AsyncSession) -> list[dict[str, Any]]:
    """Fetch security audit log entries from AuditLog database table merged with in-memory store."""
    from app.models.audit_log import AuditLog
    seen_ids = set()
    raw_logs = []
    try:
        db_res = await db.execute(select(AuditLog))
        for e in db_res.scalars().all():
            e_id = str(e.id)
            seen_ids.add(e_id)
            raw_logs.append({
                "id": e_id,
                "event": e.event,
                "actor_id": str(e.actor_id) if e.actor_id else None,
                "target_user_id": str(e.target_user_id) if e.target_user_id else None,
                "organization_id": str(e.organization_id) if e.organization_id else None,
                "result": e.result,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "details": e.details or {},
                "timestamp": e.timestamp,
            })
    except Exception:
        pass

    for item in audit.get_audit_store():
        item_id = str(item.get("id"))
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            raw_logs.append(item)

    return raw_logs


# ── 0.20 GET /admin/audit-logs ────────────────────────────────
@router.get(
    "/audit-logs",
    response_model=AdminAuditLogListResponse,
    summary="Güvenlik denetim kayıtlarını listele ve ara",
)
async def list_admin_audit_logs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    sort_by: str = Query(default="timestamp"),
    sort_order: str = Query(default="desc"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    event_type: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    organization_id: str | None = Query(default=None),
    result: str | None = Query(default=None),
    search: str | None = Query(default=None),
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminAuditLogListResponse:
    """
    List and filter security audit logs with tenant isolation and sorting validation.
    - SUPER_ADMIN: Global audit inspection across all tenants.
    - HOSPITAL_ADMIN: Audit log inspection restricted strictly to actor.organization_id.
    - Sorting validation: Invalid sort_by returns HTTP 422 VAL_001.
    - Date range validation: start_date > end_date returns HTTP 422 VAL_001.
    """
    # 1. Validate sort field
    validate_sort_field(sort_by, ALLOWED_AUDIT_SORT_FIELDS, raise_on_invalid=True)

    # 2. Validate sort direction
    if sort_order.lower() not in ("asc", "desc"):
        raise ValidationError(detail="Geçersiz sıralama yönü.")

    # 3. Validate date bounds
    if start_date and end_date and start_date > end_date:
        raise ValidationError(detail="Başlangıç tarihi bitiş tarihinden sonra olamaz.")

    # 4. Server-side tenant scoping
    scoped_org_id: str | None = None
    if not is_super_admin(actor.role):
        scoped_org_id = str(actor.organization_id)
    elif organization_id:
        scoped_org_id = str(organization_id)

    # Fetch combined audit log entries from DB and store
    raw_logs = await _get_combined_audit_logs(db)
    filtered: list[dict[str, Any]] = []

    for entry in raw_logs:
        # Tenant isolation
        if scoped_org_id:
            entry_org = entry.get("organization_id")
            if not entry_org or str(entry_org) != scoped_org_id:
                continue

        # Date range filter
        ts = entry.get("timestamp")
        if isinstance(ts, datetime):
            if start_date and ts < start_date:
                continue
            if end_date and ts > end_date:
                continue

        # Event type filter
        if event_type:
            entry_evt = str(entry.get("event", ""))
            if event_type.lower() not in entry_evt.lower():
                continue

        # User filter (actor or target)
        if user_id:
            u_str = str(user_id)
            actor_str = str(entry.get("actor_id") or "")
            target_str = str(entry.get("target_user_id") or "")
            if u_str != actor_str and u_str != target_str:
                continue

        # Result filter
        if result:
            entry_res = str(entry.get("result", ""))
            if result.upper() != entry_res.upper():
                continue

        # Free text search
        if search:
            search_lower = search.lower()
            evt = str(entry.get("event", "")).lower()
            ip = str(entry.get("ip_address", "")).lower()
            ua = str(entry.get("user_agent", "")).lower()
            dt_str = str(entry.get("details", {})).lower()
            if search_lower not in evt and search_lower not in ip and search_lower not in ua and search_lower not in dt_str:
                continue

        filtered.append(entry)

    # 5. Sorting
    is_desc = sort_order.lower() == "desc"
    key_fn = lambda x: x.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc)
    if sort_by == "event":
        key_fn = lambda x: str(x.get("event", ""))
    elif sort_by == "result":
        key_fn = lambda x: str(x.get("result", ""))
    elif sort_by == "actor_id":
        key_fn = lambda x: str(x.get("actor_id", ""))

    filtered.sort(key=key_fn, reverse=is_desc)

    total = len(filtered)
    offset = (page - 1) * page_size
    paged = filtered[offset : offset + page_size]

    items = [
        AdminAuditLogResponse(
            id=item["id"],
            event=item["event"],
            actor_id=item.get("actor_id"),
            target_user_id=item.get("target_user_id"),
            organization_id=item.get("organization_id"),
            result=item.get("result", "SUCCESS"),
            ip_address=item.get("ip_address"),
            user_agent=item.get("user_agent"),
            details=item.get("details", {}),
            timestamp=item["timestamp"],
        )
        for item in paged
    ]

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return AdminAuditLogListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ── 0.21 GET /admin/audit-logs/{audit_log_id} ─────────────────
@router.get(
    "/audit-logs/{audit_log_id}",
    response_model=AdminAuditLogResponse,
    summary="Güvenlik denetim kaydı detayını görüntüle",
)
async def get_admin_audit_log_detail(
    audit_log_id: str,
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminAuditLogResponse:
    """
    Get detailed security audit log entry by ID.
    Enforces tenant boundaries for HOSPITAL_ADMIN (cross-tenant -> HTTP 403 AUTH_003).
    """
    raw_logs = await _get_combined_audit_logs(db)
    target_entry = next((e for e in raw_logs if str(e.get("id")) == audit_log_id), None)

    if not target_entry:
        from app.core.exceptions import AppError
        raise AppError(code="NOT_FOUND", message="Denetim kaydı bulunamadı.", status_code=404)

    # Tenant isolation check
    if not is_super_admin(actor.role):
        entry_org = target_entry.get("organization_id")
        if not entry_org or str(entry_org) != str(actor.organization_id):
            audit.log_authorization_event(
                event="CROSS_TENANT_AUDIT_ACCESS_DENIED",
                actor_id=actor.id,
                organization_id=actor.organization_id,
                result="DENIED",
            )
            raise ForbiddenError(detail="Başka kuruma ait denetim kayıtlarına erişemezsiniz.")

    return AdminAuditLogResponse(
        id=target_entry["id"],
        details=target_entry.get("details", {}),
        timestamp=target_entry["timestamp"],
    )


# ── 0.22 GET /admin/security/overview ────────────────────────
@router.get(
    "/security/overview",
    response_model=AdminSecurityOverviewResponse,
    summary="Güvenlik özeti ve sistem metriklerini görüntüle",
)
async def get_admin_security_overview(
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminSecurityOverviewResponse:
    """
    Get aggregated system & security metrics with tenant scoping.
    - SUPER_ADMIN: Global metrics across all tenants.
    - HOSPITAL_ADMIN: Scoped strictly to actor.organization_id.
    """
    now = datetime.now(timezone.utc)

    # 1. User metrics
    u_query = select(User)
    if not is_super_admin(actor.role):
        u_query = u_query.where(User.organization_id == actor.organization_id)

    u_total = (await db.execute(select(func.count()).select_from(u_query.subquery()))).scalar_one_or_none() or 0
    u_active = (await db.execute(select(func.count()).select_from(u_query.where(User.is_active.is_(True)).subquery()))).scalar_one_or_none() or 0
    u_inactive = (await db.execute(select(func.count()).select_from(u_query.where(User.is_active.is_(False)).subquery()))).scalar_one_or_none() or 0
    u_locked = (await db.execute(select(func.count()).select_from(u_query.where(User.is_locked.is_(True)).subquery()))).scalar_one_or_none() or 0

    user_stats = SecurityUserStats(
        total=u_total,
        active=u_active,
        inactive=u_inactive,
        locked=u_locked,
    )

    # 2. Organization metrics
    if is_super_admin(actor.role):
        o_query = select(Organization)
        o_total = (await db.execute(select(func.count()).select_from(o_query.subquery()))).scalar_one_or_none() or 0
        o_active = (await db.execute(select(func.count()).select_from(o_query.where(Organization.is_active.is_(True)).subquery()))).scalar_one_or_none() or 0
        o_inactive = (await db.execute(select(func.count()).select_from(o_query.where(Organization.is_active.is_(False)).subquery()))).scalar_one_or_none() or 0
    else:
        org_res = await db.execute(select(Organization).where(Organization.id == actor.organization_id))
        actor_org = org_res.scalar_one_or_none()
        o_total = 1 if actor_org else 0
        o_active = 1 if (actor_org and actor_org.is_active) else 0
        o_inactive = 1 if (actor_org and not actor_org.is_active) else 0

    org_stats = SecurityOrganizationStats(
        total=o_total,
        active=o_active,
        inactive=o_inactive,
    )

    # 3. Session metrics
    s_query = select(Session).join(User, Session.user_id == User.id)
    if not is_super_admin(actor.role):
        s_query = s_query.where(User.organization_id == actor.organization_id)

    s_active = (await db.execute(select(func.count()).select_from(s_query.where(Session.revoked_at.is_(None), Session.expires_at > now).subquery()))).scalar_one_or_none() or 0
    s_revoked = (await db.execute(select(func.count()).select_from(s_query.where(Session.revoked_at.is_not(None)).subquery()))).scalar_one_or_none() or 0

    sess_stats = SecuritySessionStats(
        active=s_active,
        revoked=s_revoked,
    )

    # 4. Audit metrics
    scoped_org_id = None if is_super_admin(actor.role) else str(actor.organization_id)
    raw_logs = await _get_combined_audit_logs(db)
    filtered_logs = [
        entry for entry in raw_logs
        if not scoped_org_id or str(entry.get("organization_id")) == scoped_org_id
    ]

    total_events = len(filtered_logs)
    failed_logins = sum(1 for e in filtered_logs if e.get("event") in ("GIRIS_BASARISIZ", "LOGIN_FAILED"))
    authorization_denials = sum(1 for e in filtered_logs if e.get("result") == "DENIED")
    user_lifecycle_events = sum(
        1 for e in filtered_logs
        if e.get("event") in ("USER_LOCKED", "USER_UNLOCKED", "USER_ACTIVATED", "USER_DEACTIVATED", "USER_FORCE_LOGOUT", "USER_CREATED")
    )
    session_terminations = sum(
        1 for e in filtered_logs
        if e.get("event") in ("SESSION_TERMINATED", "USER_SESSIONS_TERMINATED")
    )

    event_stats = SecurityEventStats(
        total=total_events,
        failed_logins=failed_logins,
        authorization_denials=authorization_denials,
        user_lifecycle_events=user_lifecycle_events,
        session_terminations=session_terminations,
    )

    return AdminSecurityOverviewResponse(
        users=user_stats,
        organizations=org_stats,
        sessions=sess_stats,
        security_events=event_stats,
        generated_at=now,
    )


# ── 0.23 GET /admin/security/events ──────────────────────────
@router.get(
    "/security/events",
    response_model=AdminAuditLogListResponse,
    summary="Güvenlik olaylarını listele ve ara",
)
async def list_admin_security_events(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    sort_by: str = Query(default="timestamp"),
    sort_order: str = Query(default="desc"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    event_type: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    organization_id: str | None = Query(default=None),
    result: str | None = Query(default=None),
    search: str | None = Query(default=None),
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminAuditLogListResponse:
    """
    List security events with tenant scoping and audit inspection reuse.
    """
    return await list_admin_audit_logs(
        request=request,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        start_date=start_date,
        end_date=end_date,
        event_type=event_type,
        user_id=user_id,
        organization_id=organization_id,
        result=result,
        search=search,
        actor=actor,
        db=db,
    )


# ── 0.24 GET /admin/security/trends ──────────────────────────
@router.get(
    "/security/trends",
    response_model=AdminSecurityTrendResponse,
    summary="Zaman bazlı güvenlik trendlerini görüntüle",
)
async def get_admin_security_trends(
    interval: str = Query(default="day"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminSecurityTrendResponse:
    """
    Get aggregated security trend points bucketed by time interval (hour, day, week).
    """
    if interval.lower() not in ("hour", "day", "week"):
        raise ValidationError(detail="Geçersiz zaman aralığı (interval). 'hour', 'day' veya 'week' olmalıdır.")

    if start_date and end_date and start_date > end_date:
        raise ValidationError(detail="Başlangıç tarihi bitiş tarihinden sonra olamaz.")

    scoped_org_id = None if is_super_admin(actor.role) else str(actor.organization_id)
    raw_logs = await _get_combined_audit_logs(db)

    buckets: dict[str, dict[str, int]] = {}

    for entry in raw_logs:
        if scoped_org_id:
            entry_org = entry.get("organization_id")
            if not entry_org or str(entry_org) != scoped_org_id:
                continue

        ts = entry.get("timestamp")
        if isinstance(ts, datetime):
            if start_date and ts < start_date:
                continue
            if end_date and ts > end_date:
                continue

            if interval.lower() == "hour":
                bucket_key = ts.strftime("%Y-%m-%d %H:00")
            elif interval.lower() == "week":
                bucket_key = f"{ts.year}-W{ts.isocalendar()[1]:02d}"
            else:
                bucket_key = ts.strftime("%Y-%m-%d")

            if bucket_key not in buckets:
                buckets[bucket_key] = {
                    "failed_logins": 0,
                    "authorization_denials": 0,
                    "user_locks": 0,
                    "session_terminations": 0,
                }

            evt = str(entry.get("event", ""))
            res = str(entry.get("result", ""))

            if evt in ("GIRIS_BASARISIZ", "LOGIN_FAILED"):
                buckets[bucket_key]["failed_logins"] += 1
            if res == "DENIED":
                buckets[bucket_key]["authorization_denials"] += 1
            if evt == "USER_LOCKED":
                buckets[bucket_key]["user_locks"] += 1
            if evt in ("SESSION_TERMINATED", "USER_SESSIONS_TERMINATED"):
                buckets[bucket_key]["session_terminations"] += 1

    sorted_keys = sorted(buckets.keys())
    trend_points = [
        AdminSecurityTrendPoint(
            timestamp=k,
            failed_logins=buckets[k]["failed_logins"],
            authorization_denials=buckets[k]["authorization_denials"],
            user_locks=buckets[k]["user_locks"],
            session_terminations=buckets[k]["session_terminations"],
        )
        for k in sorted_keys
    ]

    return AdminSecurityTrendResponse(
        interval=interval.lower(),
        data=trend_points,
    )


# ── 0.25 GET /admin/security/organizations ───────────────────
@router.get(
    "/security/organizations",
    response_model=AdminOrganizationSecurityListResponse,
    summary="Kurum bazlı güvenlik özeti ve metriklerini görüntüle",
)
async def list_admin_organization_security(
    actor: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AdminOrganizationSecurityListResponse:
    """
    Get organization-level security metrics.
    - SUPER_ADMIN: Returns security breakdown for all organizations.
    - HOSPITAL_ADMIN: Returns security breakdown for actor.organization_id ONLY.
    """
    now = datetime.now(timezone.utc)

    if is_super_admin(actor.role):
        stmt = select(Organization).order_by(Organization.name.asc())
    else:
        stmt = select(Organization).where(Organization.id == actor.organization_id)

    res = await db.execute(stmt)
    orgs = res.scalars().all()

    items: list[AdminOrganizationSecurityItem] = []
    raw_logs = await _get_combined_audit_logs(db)

    for org in orgs:
        u_stmt = select(User).where(User.organization_id == org.id)
        u_total = (await db.execute(select(func.count()).select_from(u_stmt.subquery()))).scalar_one_or_none() or 0
        u_active = (await db.execute(select(func.count()).select_from(u_stmt.where(User.is_active.is_(True)).subquery()))).scalar_one_or_none() or 0
        u_locked = (await db.execute(select(func.count()).select_from(u_stmt.where(User.is_locked.is_(True)).subquery()))).scalar_one_or_none() or 0

        s_stmt = select(Session).join(User, Session.user_id == User.id).where(User.organization_id == org.id, Session.revoked_at.is_(None), Session.expires_at > now)
        s_active = (await db.execute(select(func.count()).select_from(s_stmt.subquery()))).scalar_one_or_none() or 0

        event_cnt = sum(1 for e in raw_logs if str(e.get("organization_id")) == str(org.id))

        items.append(
            AdminOrganizationSecurityItem(
                organization_id=str(org.id),
                name=org.name,
                code=org.code,
                is_active=org.is_active,
                user_count=u_total,
                active_user_count=u_active,
                locked_user_count=u_locked,
                active_session_count=s_active,
                security_event_count=event_cnt,
            )
        )

    return AdminOrganizationSecurityListResponse(organizations=items)
