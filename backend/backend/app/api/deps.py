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
from sqlalchemy import select
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

    if not jti or not user_id_str:
        raise InvalidTokenError(detail="Jeton eksik talepler içeriyor.")

    # Redis blacklist check if redis client state is available
    app_obj = getattr(request, "app", None)
    app_state = getattr(app_obj, "state", None) if app_obj else None
    redis_client = getattr(app_state, "redis", None) if app_state else None

    if redis_client:
        if await redis_core.is_token_blacklisted(redis_client, jti):
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

    return user


def izin_gerektir(*perms: str, require_all: bool = True):
    """
    Permission-checking dependency factory (RBAC).

    Usage:
        @router.post("/reports/{id}/approve")
        async def approve(user: User = Depends(izin_gerektir("report:approve"))):
            ...
    """
    async def _dep(user: User = Depends(aktif_kullanici)) -> User:
        from app.core.permissions import get_effective_permissions
        effective = get_effective_permissions(
            user.role, user.extra_permissions, user.revoked_permissions
        )

        if require_all:
            missing = [p for p in perms if p not in effective]
            if missing:
                raise ForbiddenError(missing=missing)
        else:
            has_any = any(p in effective for p in perms)
            if perms and not has_any:
                raise ForbiddenError(missing=list(perms))

        return user
    return _dep


def rol_gerektir(*allowed_roles: Any):
    """
    Role-checking dependency factory (RBAC).

    Usage:
        @router.get("/admin/system-stats")
        async def stats(user: User = Depends(rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN))):
            ...
    """
    async def _dep(user: User = Depends(aktif_kullanici)) -> User:
        from app.core.permissions import Role

        valid_roles = []
        for r in allowed_roles:
            if isinstance(r, Role):
                valid_roles.append(r.value)
            elif isinstance(r, str):
                valid_roles.append(r)

        user_role_str = user.role.value if isinstance(user.role, Role) else str(user.role)

        if user_role_str not in valid_roles:
            raise ForbiddenError(detail="Bu işlem için rol yetkiniz yetersiz.")

        return user
    return _dep


def kurum_izolasyonu_kontrolu(user: User, resource_org_id: uuid.UUID | str) -> None:
    """
    ABAC Organization / Tenant Isolation check helper.

    Validates that user.organization_id matches resource_org_id.
    SUPER_ADMIN bypasses organization restrictions.
    Raises ForbiddenError (HTTP 403) on mismatch.
    """
    from app.core.permissions import verify_organization_access, is_super_admin

    if not verify_organization_access(
        user_org_id=user.organization_id,
        resource_org_id=resource_org_id,
        is_super=is_super_admin(user.role),
    ):
        raise ForbiddenError(detail="Farklı kuruma ait kaynağa erişim yetkiniz yoktur.")


def sahip_veya_admin_kontrolu(
    user: User,
    resource_owner_id: uuid.UUID | str,
    resource_org_id: uuid.UUID | str | None = None,
) -> None:
    """
    ABAC Resource Ownership & Privilege check helper.

    Validates that:
    1. Organization boundary is matched (if resource_org_id is provided).
    2. User is the resource owner OR holds SUPER_ADMIN or HOSPITAL_ADMIN privilege within same org.
    Raises ForbiddenError (HTTP 403) if checks fail.
    """
    from app.core.permissions import check_abac_access

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

