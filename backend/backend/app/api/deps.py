"""
NeuroOncoTrack-AI — API Dependencies

Central authentication and authorization dependencies.
Endpoint routers must NOT perform manual token parsing.

aktif_kullanici() — resolves the authenticated user from the Bearer token
izin_gerektir()  — verifies the user has required permissions

These will be fully implemented in TASK-006.
Foundation is placed here now for import compatibility.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security, redis as redis_core
from app.core.exceptions import (
    AccountLockedError,
    AuthenticationError,
    ForbiddenError,
    InvalidTokenError,
    ValidationError,
)
from app.db.session import get_db
from app.models.user import User

# HTTP Bearer scheme for Swagger UI integration
bearer_scheme = HTTPBearer(auto_error=False)


async def get_redis_client(request: Request) -> redis_core.Redis | None:
    """
    Dependency to resolve active Redis client.

    Checks app.state.redis first (for testing/app lifecycle),
    falling back to core get_redis() helper. Returns None if Redis is unavailable.
    """
    app_obj = getattr(request, "app", None)
    app_state = getattr(app_obj, "state", None) if app_obj else None
    redis_client = getattr(app_state, "redis", None) if app_state else None

    if redis_client is not None:
        return redis_client

    try:
        return await redis_core.get_redis()
    except Exception:
        return None



async def aktif_kullanici(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Central auth dependency — resolves the current authenticated user from Bearer JWT.

    Flow:
    1. Extract Authorization header Bearer token
    2. Validate JWT signature (RS256) & claims (sub, iss, aud, exp, iat, nbf, jti)
    3. Check Redis blacklist (if Redis client available)
    4. Query DB for user & organization status
    5. Reject inactive or locked users
    6. Return authenticated user
    """
    if not credentials or not credentials.credentials:
        raise InvalidTokenError(detail="Erişim jetonu bulunamadı.")

    token = credentials.credentials

    try:
        payload = security.decode_access_token(token)
    except Exception as e:
        raise InvalidTokenError(detail="Geçersiz veya süresi dolmuş jeton.") from e

    jti = payload.get("jti")
    user_id_str = payload.get("sub")
    payload_iat = payload.get("iat")

    if not jti or not user_id_str:
        raise InvalidTokenError(detail="Jeton eksik talepler içeriyor.")

    # Redis blacklist check if redis client state is available
    app_obj = getattr(request, "app", None)
    app_state = getattr(app_obj, "state", None) if app_obj else None
    redis_client = getattr(app_state, "redis", None) if app_state else None

    redis_blacklisted = False
    if redis_client is not None:
        try:
            if await redis_core.is_token_blacklisted(redis_client, jti) or await redis_client.exists(f"bl:user:{user_id_str}"):
                redis_blacklisted = True
        except Exception:
            redis_blacklisted = False

    if redis_blacklisted:
        raise InvalidTokenError(detail="Jeton iptal edilmiş (kara listede).")

    # Fetch User from DB
    try:
        user_uuid = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise InvalidTokenError(detail="Geçersiz kullanıcı kimliği.")

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if not user:
        raise InvalidTokenError(detail="Kullanıcı bulunamadı.")

    if not user.is_active:
        raise AuthenticationError(detail="Kullanıcı hesabı pasif durumda.")

    if user.is_effectively_locked:
        raise AccountLockedError(detail="Kullanıcı hesabı kilitli.")

    if user.organization and not user.organization.is_active:
        raise AuthenticationError(detail="Kullanıcının bağlı olduğu kurum pasif durumda.")

    # ── DB Revocation Fallback & Fail-Closed Validation ──────────────────
    # 1. Direct Session DB validation if sid claim exists in access token
    sid_str = payload.get("sid")
    if sid_str:
        try:
            sid_uuid = uuid.UUID(str(sid_str))
            from app.models.session import Session
            sess_res = await db.execute(select(Session).where(Session.id == sid_uuid))
            sess = sess_res.scalar_one_or_none()
            if not sess or sess.revoked_at is not None:
                raise InvalidTokenError(detail="Jeton iptal edilmiş (oturum sonlandırıldı).")
        except InvalidTokenError:
            raise
        except (ValueError, TypeError):
            pass
        except Exception:
            pass

    # 2. Account-wide timestamp-based fallback validation
    if payload_iat is not None:
        try:
            from datetime import datetime, timezone, timedelta
            if isinstance(payload_iat, (int, float)):
                token_iat_dt = datetime.fromtimestamp(payload_iat, tz=timezone.utc)
            elif isinstance(payload_iat, datetime):
                token_iat_dt = payload_iat
            else:
                token_iat_dt = None

            if token_iat_dt:
                if token_iat_dt.tzinfo is None:
                    token_iat_dt = token_iat_dt.replace(tzinfo=timezone.utc)

                ACCOUNT_WIDE_REASONS = [
                    "FORCE_LOGOUT",
                    "LOGOUT_ALL",
                    "ADMIN_TERMINATED_ALL",
                    "PASSWORD_CHANGED",
                    "PASSWORD_RESET",
                ]

                from app.models.session import Session
                max_rev_res = await db.execute(
                    select(func.max(Session.revoked_at)).where(
                        Session.user_id == user.id,
                        Session.revoked_at.is_not(None),
                        Session.revocation_reason.in_(ACCOUNT_WIDE_REASONS),
                    )
                )
                max_revoked_at = max_rev_res.scalar_one_or_none()

                if max_revoked_at is not None:
                    if isinstance(max_revoked_at, str):
                        try:
                            rev_dt = datetime.fromisoformat(max_revoked_at)
                        except Exception:
                            rev_dt = None
                    elif isinstance(max_revoked_at, datetime):
                        rev_dt = max_revoked_at
                    else:
                        rev_dt = None

                    if rev_dt is not None:
                        if rev_dt.tzinfo is None:
                            rev_dt = rev_dt.replace(tzinfo=timezone.utc)

                        # Check if user has any active session created AFTER max_revoked_at
                        max_act_res = await db.execute(
                            select(func.max(Session.created_at)).where(
                                Session.user_id == user.id,
                                Session.revoked_at.is_(None),
                            )
                        )
                        max_active_created_at = max_act_res.scalar_one_or_none()

                        active_dt = None
                        if max_active_created_at is not None:
                            if isinstance(max_active_created_at, str):
                                try:
                                    active_dt = datetime.fromisoformat(max_active_created_at)
                                except Exception:
                                    active_dt = None
                            elif isinstance(max_active_created_at, datetime):
                                active_dt = max_active_created_at

                            if active_dt and active_dt.tzinfo is None:
                                active_dt = active_dt.replace(tzinfo=timezone.utc)

                        # If no active session was created after rev_dt, enforce revocation
                        if active_dt is None or active_dt < rev_dt:
                            if token_iat_dt <= (rev_dt + timedelta(seconds=1)):
                                raise InvalidTokenError(detail="Jeton iptal edilmiş (oturum sonlandırıldı).")
        except InvalidTokenError:
            raise
        except Exception:
            pass

    return user


def izin_gerektir(*perms: Permission | str, require_all: bool = True):
    """
    Permission-checking dependency factory (RBAC).

    Accepts Permission enums or string literals. Normalizes all permissions.
    If no valid permissions are specified (empty perms), fails closed (rejects access).

    Usage:
        @router.post("/reports/{id}/approve")
        async def approve(user: User = Depends(izin_gerektir(Permission.REPORT_APPROVE))):
            ...
    """
    async def _dep(user: User = Depends(aktif_kullanici)) -> User:
        from app.core.permissions import get_effective_permissions, normalize_permission

        normalized_perms = [normalize_permission(p) for p in perms if p is not None]

        if not normalized_perms:
            raise ForbiddenError(detail="Yetki gereksinimi belirtilmemiş.")

        effective = get_effective_permissions(
            user.role, user.extra_permissions, user.revoked_permissions
        )

        if require_all:
            missing = [p for p in normalized_perms if p not in effective]
            if missing:
                raise ForbiddenError(missing=missing)
        else:
            has_any = any(p in effective for p in normalized_perms)
            if not has_any:
                raise ForbiddenError(missing=normalized_perms)

        return user
    return _dep


def rol_gerektir(*allowed_roles: Role | str):
    """
    Role-checking dependency factory (RBAC).

    Accepts Role enums or string literals. Normalizes all roles.
    If no valid roles are specified (empty allowed_roles), fails closed (rejects access).

    Usage:
        @router.get("/admin/system-stats")
        async def stats(user: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN))):
            ...
    """
    async def _dep(user: User = Depends(aktif_kullanici)) -> User:
        from app.core.permissions import Role

        valid_roles = set()
        for r in allowed_roles:
            if isinstance(r, Role):
                valid_roles.add(r.value)
            elif isinstance(r, str):
                valid_roles.add(r.strip())

        if not valid_roles:
            raise ForbiddenError(detail="Rol gereksinimi belirtilmemiş.")

        user_role_str = user.role.value if isinstance(user.role, Role) else str(user.role).strip()

        if user_role_str not in valid_roles:
            raise ForbiddenError(detail="Bu işlem için rol yetkiniz yetersiz.")

        return user
    return _dep


# Central aliases for import flexibility
require_permission = izin_gerektir
require_role = rol_gerektir


def kurum_izolasyonu_kontrolu(user: User, resource_org_id: uuid.UUID | str | None) -> None:
    """
    ABAC Organization / Tenant Isolation check helper.

    Validates that user.organization_id matches resource_org_id.
    SUPER_ADMIN bypasses organization restrictions.
    Fail-closed: Missing resource_org_id or user.organization_id (when not SUPER_ADMIN) is denied.
    Raises ForbiddenError (HTTP 403 / AUTH_003) on mismatch.
    """
    from app.core.permissions import verify_organization_access, is_super_admin

    if not user or not user.is_active:
        raise ForbiddenError(detail="Aktif kullanıcı doğrulanamadı.")

    if resource_org_id is None and not is_super_admin(user.role):
        raise ForbiddenError(detail="Kurum kimliği eksik (fail-closed).")

    if not user.organization_id and not is_super_admin(user.role):
        raise ForbiddenError(detail="Kullanıcı kuruma bağlı değil (fail-closed).")

    if not verify_organization_access(
        user_org_id=user.organization_id,
        resource_org_id=resource_org_id,
        is_super=is_super_admin(user.role),
    ):
        raise ForbiddenError(detail="Farklı kuruma ait kaynağa erişim yetkiniz yoktur.")


def sahip_veya_admin_kontrolu(
    user: User,
    resource_owner_id: uuid.UUID | str | None,
    resource_org_id: uuid.UUID | str | None = None,
) -> None:
    """
    ABAC Resource Ownership & Privilege check helper.

    Validates that:
    1. Organization boundary is matched (if resource_org_id is provided).
    2. User is the resource owner OR holds SUPER_ADMIN or HOSPITAL_ADMIN privilege within same org.
    Fail-closed: Missing resource_owner_id or unauthenticated user is denied.
    Raises ForbiddenError (HTTP 403 / AUTH_003) if checks fail.
    """
    from app.core.permissions import check_abac_access

    if not user or not user.is_active:
        raise ForbiddenError(detail="Aktif kullanıcı doğrulanamadı.")

    if resource_org_id is not None:
        kurum_izolasyonu_kontrolu(user, resource_org_id)

    allowed = check_abac_access(
        user_id=user.id,
        user_org_id=user.organization_id,
        user_role=user.role,
        resource_org_id=resource_org_id,
        resource_owner_id=resource_owner_id,
    )

    if not allowed:
        raise ForbiddenError(detail="Bu kaynak üzerinde işlem yapma yetkiniz bulunmamaktadır.")


def apply_tenant_filter(query: Any, model: Any, user: User) -> Any:
    """
    Applies DB query-level organization isolation filter to SQLAlchemy query.

    SUPER_ADMIN gets unfiltered access across all tenants.
    All other roles get automatic WHERE model.organization_id == user.organization_id.
    Fail-closed: If user has no organization_id and is not SUPER_ADMIN, appends impossible condition.
    """
    from app.core.permissions import is_super_admin

    if is_super_admin(user.role):
        return query

    org_col = getattr(model, "organization_id", None)
    if org_col is None:
        return query

    if not user.organization_id:
        return query.where(org_col == None)  # Fail-closed

    return query.where(org_col == user.organization_id)


def apply_ownership_filter(query: Any, model: Any, user: User, owner_column_name: str = "user_id") -> Any:
    """
    Applies DB query-level resource ownership filter to SQLAlchemy query.

    SUPER_ADMIN and HOSPITAL_ADMIN bypass ownership filtering within their org scope.
    Functional roles get automatic WHERE model.owner_column == user.id.
    """
    from app.core.permissions import is_super_admin, is_hospital_admin

    if is_super_admin(user.role) or is_hospital_admin(user.role):
        return query

    owner_col = getattr(model, owner_column_name, None)
    if owner_col is None:
        return query

    return query.where(owner_col == user.id)


def rol_atamasi_kontrolu(
    actor: User,
    target_user: User,
    new_role: Role | str,
) -> None:
    """
    Role assignment / modification authorization helper.

    Enforces:
    1. Self-role escalation defense: actor.id == target_user.id -> ForbiddenError (HTTP 403 / AUTH_003).
    2. Tenant isolation: actor cannot modify users in different orgs (unless SUPER_ADMIN).
    3. Hierarchy ranking: can_assign_role(actor.role, new_role, target_user.role) must be True.
    Raises ForbiddenError (HTTP 403 / AUTH_003) if any check fails.
    """
    from app.core import audit
    from app.core.permissions import can_assign_role, is_super_admin
    from app.core.exceptions import ForbiddenError

    if not actor or not actor.is_active:
        raise ForbiddenError(detail="Aktif kullanıcı doğrulanamadı.")

    # Prevent self-role modification (self-escalation / self-downgrade)
    if str(actor.id) == str(target_user.id):
        audit.log_authorization_event(
            event="SELF_ROLE_ESCALATION_ATTEMPT",
            actor_id=actor.id,
            target_user_id=target_user.id,
            organization_id=actor.organization_id,
            role=str(new_role),
            result="DENIED",
        )
        raise ForbiddenError(detail="Kullanıcı kendi rolünü değiştiremez.")

    # Tenant boundary check (HOSPITAL_ADMIN cannot assign roles across organizations)
    if not is_super_admin(actor.role):
        if str(actor.organization_id) != str(target_user.organization_id):
            audit.log_authorization_event(
                event="CROSS_TENANT_ACCESS_DENIED",
                actor_id=actor.id,
                target_user_id=target_user.id,
                organization_id=actor.organization_id,
                role=str(new_role),
                result="DENIED",
            )
            raise ForbiddenError(detail="Farklı kuruma ait kullanıcının rolü değiştirilemez.")

    # Hierarchy ranking check
    if not can_assign_role(actor.role, new_role, target_user.role):
        audit.log_authorization_event(
            event="PRIVILEGE_ESCALATION_ATTEMPT",
            actor_id=actor.id,
            target_user_id=target_user.id,
            organization_id=actor.organization_id,
            role=str(new_role),
            result="DENIED",
        )
        raise ForbiddenError(detail="Bu rol değişikliği için hiyerarşik yetkiniz yetersiz.")


def hassas_klinik_ve_ai_islem_kontrolu(
    permission: Permission | str,
    resource_org_id: uuid.UUID | str | None = None,
    resource_owner_id: uuid.UUID | str | None = None,
    enforce_physician_signature_policy: bool = False,
) -> Callable[[User], User]:
    """
    Centralized 5-Tier Authorization Pipeline for Sensitive Clinical & AI Actions:
    1. Tier 1: Authentication & Active User check (aktif_kullanici)
    2. Tier 2: RBAC Permission check (has_permission with base + extra - revoked precedence)
    3. Tier 3: Role Policy & Clinical Rule check (e.g. REPORT_SIGN requires PHYSICIAN role)
    4. Tier 4: Tenant / Organization Isolation check (kurum_izolasyonu_kontrolu)
    5. Tier 5: Resource Ownership / Administrative Scope check (sahip_veya_admin_kontrolu)

    Fail-closed: Returns HTTP 403 Forbidden (AUTH_003) on any policy failure and logs audit events.
    """
    async def _dep(user: User = Depends(aktif_kullanici)) -> User:
        from app.core import audit
        from app.core.permissions import Permission, Role, has_permission, is_super_admin, normalize_permission

        norm_perm = normalize_permission(permission)

        # Tier 1: User active check
        if not user or not user.is_active or user.is_locked:
            audit.log_authorization_event(
                event="SENSITIVE_ACTION_DENIED",
                actor_id=user.id if user else None,
                permission=norm_perm,
                result="DENIED",
                extra_details={"reason": "User unauthenticated, inactive, or locked"},
            )
            raise ForbiddenError(detail="Aktif kullanıcı doğrulanamadı.")

        # Tier 2: RBAC Permission Check (evaluates base + extra - revoked)
        if not has_permission(user, norm_perm):
            audit.log_authorization_event(
                event="SENSITIVE_ACTION_DENIED",
                actor_id=user.id,
                organization_id=user.organization_id,
                permission=norm_perm,
                result="DENIED",
                extra_details={"reason": "Gerekli yetki/izin yetersiz veya iptal edilmiş"},
            )
            raise ForbiddenError(detail=f"Gerekli izin bulunmamaktadır: '{norm_perm}'.")

        # Tier 3: Role Policy Check for Sensitive Medical Actions
        user_role_str = user.role.value if isinstance(user.role, Role) else str(user.role)
        if norm_perm == Permission.REPORT_SIGN.value or enforce_physician_signature_policy:
            if not is_super_admin(user.role) and user_role_str != Role.PHYSICIAN.value:
                audit.log_authorization_event(
                    event="SENSITIVE_ACTION_DENIED",
                    actor_id=user.id,
                    organization_id=user.organization_id,
                    permission=norm_perm,
                    role=user_role_str,
                    result="DENIED",
                    extra_details={"reason": "Medical report signing requires PHYSICIAN role"},
                )
                raise ForbiddenError(detail="Tıbbi rapor imzalama yetkisi yalnızca uzman hekimlere aittir.")

        # Tier 4: Tenant Isolation Check (if resource_org_id provided)
        if resource_org_id is not None:
            try:
                kurum_izolasyonu_kontrolu(user, resource_org_id)
            except ForbiddenError as exc:
                audit.log_authorization_event(
                    event="CROSS_TENANT_ACCESS_DENIED",
                    actor_id=user.id,
                    organization_id=user.organization_id,
                    permission=norm_perm,
                    result="DENIED",
                    extra_details={"resource_org_id": str(resource_org_id)},
                )
                raise exc

        # Tier 5: Resource Scope & Ownership Check (if resource_owner_id provided)
        if resource_owner_id is not None:
            try:
                sahip_veya_admin_kontrolu(user, resource_owner_id, resource_org_id)
            except ForbiddenError as exc:
                audit.log_authorization_event(
                    event="RESOURCE_OWNERSHIP_DENIED",
                    actor_id=user.id,
                    organization_id=user.organization_id,
                    permission=norm_perm,
                    result="DENIED",
                    extra_details={"resource_owner_id": str(resource_owner_id)},
                )
                raise exc

        # Successful authorization
        audit.log_authorization_event(
            event="SENSITIVE_ACTION_GRANTED",
            actor_id=user.id,
            organization_id=user.organization_id,
            permission=norm_perm,
            role=user_role_str,
            result="GRANTED",
        )

        return user

    return _dep


require_sensitive_action = hassas_klinik_ve_ai_islem_kontrolu

