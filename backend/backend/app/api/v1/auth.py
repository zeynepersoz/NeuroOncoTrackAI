"""
NeuroOncoTrack-AI — Authentication API Endpoints (v1)

Implements:
- POST /api/v1/auth/register — Register new user
- POST /api/v1/auth/login    — Authenticate & receive access token + refresh session
- POST /api/v1/auth/refresh  — Rotate refresh token & receive new access token
- POST /api/v1/auth/logout   — Revoke refresh session & blacklist access token JTI
- GET  /api/v1/auth/me       — Fetch current user profile
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import aktif_kullanici, bearer_scheme
from app.core import permissions as perms_core, redis as redis_core, security
from app.core.config import settings
from app.core.exceptions import (
    AccountLockedError,
    AuthenticationError,
    InvalidTokenError,
    MFARequiredError,
    ValidationError,
)
from app.db.session import get_db
from app.models.organization import Organization
from app.models.password_history import PasswordHistory
from app.models.session import Session
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MFADisableRequest,
    MFAEnableRequest,
    MFARequiredResponse,
    MFASetupResponse,
    MFAVerifyRequest,
    MessageResponse,
    RegisterRequest,
    TokenRefreshResponse,
)
from app.schemas.user import UserProfileResponse, UserProfileUpdate

router = APIRouter(prefix="/auth", tags=["auth"])


def build_user_profile_response(user: User) -> UserProfileResponse:
    """Build UserProfileResponse from User ORM model safely converting UUIDs and sets."""
    effective_perms = perms_core.get_effective_permissions(
        user.role, user.extra_permissions, user.revoked_permissions
    )
    org_name = user.organization.name if user.organization else None

    return UserProfileResponse(
        id=str(user.id),
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        title=user.title,
        role=user.role,
        permissions=sorted(list(effective_perms)),
        organization_id=str(user.organization_id),
        organization_name=org_name,
        mfa_enabled=user.mfa_enabled,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


@router.post("/register", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """
    Register a new user profile.

    Validates password strength policy, enforces email uniqueness,
    hashes password with Argon2id, and creates initial password history record.
    """
    email_clean = payload.email.strip().lower()

    # Check if email is already registered
    existing_res = await db.execute(select(User).where(User.email == email_clean))
    if existing_res.scalar_one_or_none():
        raise ValidationError(detail="Bu e-posta adresi zaten kullanımda.")

    # Validate organization
    try:
        org_uuid = uuid.UUID(payload.organization_id)
    except (ValueError, TypeError):
        raise ValidationError(detail="Geçersiz organizasyon kimliği.")

    org_res = await db.execute(select(Organization).where(Organization.id == org_uuid))
    org = org_res.scalar_one_or_none()
    if not org or not org.is_active:
        raise ValidationError(detail="Geçersiz veya pasif organizasyon.")

    # Validate and hash password
    security.validate_password(payload.password)
    hashed_password = security.hash_password(payload.password)

    now = datetime.now(timezone.utc)
    new_user = User(
        organization_id=org.id,
        email=email_clean,
        password_hash=hashed_password,
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        title=payload.title.strip() if payload.title else None,
        role=payload.role,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Initial PasswordHistory record
    pw_hist = PasswordHistory(
        user_id=new_user.id,
        password_hash=hashed_password,
        created_at=now,
    )
    db.add(pw_hist)
    await db.commit()
    await db.refresh(new_user)

    return build_user_profile_response(new_user)


@router.post("/login", response_model=LoginResponse | MFARequiredResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse | MFARequiredResponse:
    """
    Authenticate user with email and password.

    Returns access_token (RS256 JWT) and sets HTTP-only cookie with refresh_token.
    """
    email_clean = payload.email.strip().lower()

    # Generic authentication failure to prevent user enumeration
    user_res = await db.execute(select(User).where(User.email == email_clean))
    user = user_res.scalar_one_or_none()

    if not user or not security.verify_password(payload.password, user.password_hash):
        raise AuthenticationError(detail="E-posta veya parola hatalı.")

    if not user.is_active:
        raise AuthenticationError(detail="Kullanıcı hesabı pasif durumda.")

    if user.is_effectively_locked:
        raise AccountLockedError(detail="Kullanıcı hesabı kilitli.")

    if user.organization and not user.organization.is_active:
        raise AuthenticationError(detail="Kullanıcının bağlı olduğu kurum pasif durumda.")

    # MFA Flow check
    if user.mfa_enabled:
        temp_token, _ = security.create_mfa_temp_token(str(user.id))
        response.status_code = status.HTTP_202_ACCEPTED
        return MFARequiredResponse(mfa_temp_token=temp_token)

    # Calculate effective permissions (convert set to sorted list for JSON serialization)
    effective_perms = perms_core.get_effective_permissions(
        user.role, user.extra_permissions, user.revoked_permissions
    )
    effective_list = sorted(list(effective_perms))

    # Create RS256 JWT Access Token
    access_token, jti, exp = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
        permissions=effective_list,
    )

    # Create Opaque Refresh Token & Session
    now = datetime.now(timezone.utc)
    refresh_token = security.generate_refresh_token()
    refresh_hash = security.hash_token(refresh_token)

    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    sess = Session(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        ip_address=ip_addr,
        user_agent=user_agent,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(sess)

    user.last_login_at = now
    await db.commit()
    await db.refresh(user)

    # Set HTTP-only Refresh Token cookie
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_at=exp,
        user=build_user_profile_response(user),
    )


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenRefreshResponse:
    """
    Refresh access token using HTTP-only refresh token cookie.

    Rotates refresh token and returns new RS256 JWT access token.
    """
    refresh_token = request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    if not refresh_token:
        # Check header if passed in request body/header
        auth_header = request.headers.get("X-Refresh-Token")
        if auth_header:
            refresh_token = auth_header

    if not refresh_token:
        raise InvalidTokenError(detail="Yenileme jetonu bulunamadı.")

    try:
        computed_hash = security.hash_token(refresh_token)
    except ValueError:
        raise InvalidTokenError(detail="Geçersiz yenileme jetonu.")

    sess_res = await db.execute(select(Session).where(Session.refresh_token_hash == computed_hash))
    sess = sess_res.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if not sess:
        raise InvalidTokenError(detail="Geçersiz veya bulunamayan oturum.")

    if not sess.is_valid or sess.revoked_at is not None:
        raise InvalidTokenError(detail="Oturum sonlandırılmış.")

    if sess.expires_at < now:
        raise InvalidTokenError(detail="Oturum süresi dolmuş.")

    # Fetch User
    user_res = await db.execute(select(User).where(User.id == sess.user_id))
    user = user_res.scalar_one_or_none()

    if not user or not user.is_active or user.is_effectively_locked:
        raise InvalidTokenError(detail="Kullanıcı hesabı geçersiz veya kilitli.")

    # Refresh Token Rotation — Revoke old session and issue new one
    sess.revoked_at = now

    new_refresh_token = security.generate_refresh_token()
    new_refresh_hash = security.hash_token(new_refresh_token)

    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    new_sess = Session(
        user_id=user.id,
        refresh_token_hash=new_refresh_hash,
        ip_address=ip_addr,
        user_agent=user_agent,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_sess)

    # Issue new Access Token
    effective_perms = perms_core.get_effective_permissions(
        user.role, user.extra_permissions, user.revoked_permissions
    )
    access_token, _, exp = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
        permissions=sorted(list(effective_perms)),
    )

    await db.commit()

    # Update HTTP-only Cookie
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=new_refresh_token,
        httponly=True,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    return TokenRefreshResponse(
        access_token=access_token,
        token_type="bearer",
        expires_at=exp,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(aktif_kullanici),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Log out user.

    Revokes active refresh session (user isolated), adds current access token JTI to Redis blacklist,
    clears refresh cookie, logs audit event 'CIKIS', and returns 204 No Content.
    """
    from app.core.audit import log_audit_event

    now = datetime.now(timezone.utc)
    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    # Revoke Session from Cookie if present (user isolated)
    refresh_token = request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    if refresh_token:
        try:
            computed_hash = security.hash_token(refresh_token)
            sess_res = await db.execute(
                select(Session).where(
                    Session.refresh_token_hash == computed_hash,
                    Session.user_id == current_user.id,
                )
            )
            sess = sess_res.scalar_one_or_none()
            if sess and sess.revoked_at is None:
                sess.revoked_at = now
                await db.commit()
        except ValueError:
            pass

    # Blacklist current access token JTI in Redis
    if credentials and credentials.credentials:
        try:
            payload = security.decode_access_token(credentials.credentials)
            jti = payload.get("jti")
            exp_ts = payload.get("exp")

            if jti and exp_ts:
                ttl = int(exp_ts.timestamp() - now.timestamp()) if isinstance(exp_ts, datetime) else int(exp_ts - now.timestamp())
                if ttl > 0:
                    app_obj = getattr(request, "app", None)
                    app_state = getattr(app_obj, "state", None) if app_obj else None
                    redis_client = getattr(app_state, "redis", None) if app_state else None

                    if redis_client:
                        await redis_core.blacklist_token(redis_client, jti, ttl)
        except Exception:
            pass

    # Clear refresh cookie
    response.delete_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
    )
    response.status_code = status.HTTP_204_NO_CONTENT

    # Record Audit Event
    log_audit_event(
        event="CIKIS",
        user_id=current_user.id,
        ip_address=ip_addr,
        user_agent=user_agent,
    )

    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    request: Request,
    response: Response,
    current_user: User = Depends(aktif_kullanici),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Log out user from all active sessions.

    Revokes ALL active refresh sessions belonging to current_user, adds current access token JTI
    to Redis blacklist, clears refresh cookie, logs audit event 'CIKIS_TUM_OTURUMLAR', and returns 204 No Content.
    """
    from app.core.audit import log_audit_event

    now = datetime.now(timezone.utc)
    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    # Revoke ALL active sessions for this user (user isolated)
    sess_res = await db.execute(
        select(Session).where(
            Session.user_id == current_user.id,
            Session.revoked_at.is_(None),
        )
    )
    active_sessions = sess_res.scalars().all()
    for sess in active_sessions:
        sess.revoked_at = now
    if active_sessions:
        await db.commit()

    # Blacklist current access token JTI in Redis
    if credentials and credentials.credentials:
        try:
            payload = security.decode_access_token(credentials.credentials)
            jti = payload.get("jti")
            exp_ts = payload.get("exp")

            if jti and exp_ts:
                ttl = int(exp_ts.timestamp() - now.timestamp()) if isinstance(exp_ts, datetime) else int(exp_ts - now.timestamp())
                if ttl > 0:
                    app_obj = getattr(request, "app", None)
                    app_state = getattr(app_obj, "state", None) if app_obj else None
                    redis_client = getattr(app_state, "redis", None) if app_state else None

                    if redis_client:
                        await redis_core.blacklist_token(redis_client, jti, ttl)
        except Exception:
            pass

    # Clear refresh cookie
    response.delete_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
    )
    response.status_code = status.HTTP_204_NO_CONTENT

    # Record Audit Event
    log_audit_event(
        event="CIKIS_TUM_OTURUMLAR",
        user_id=current_user.id,
        ip_address=ip_addr,
        user_agent=user_agent,
    )

    return response


@router.get("/me", response_model=UserProfileResponse)
async def me(
    current_user: User = Depends(aktif_kullanici),
) -> UserProfileResponse:
    """Fetch profile of currently authenticated user."""
    return build_user_profile_response(current_user)


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(aktif_kullanici),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """
    Update profile of currently authenticated user.

    Only allows modifying permitted self-update fields (first_name, last_name, title, email).
    Protected security & authorization fields (role, permissions, organization_id, is_active, etc.) cannot be changed.
    Enforces email uniqueness validation and email case-normalization.
    """
    update_data = payload.model_dump(exclude_unset=True)

    if not update_data:
        return build_user_profile_response(current_user)

    # Email Uniqueness & Normalization Check
    if "email" in update_data and update_data["email"]:
        new_email = update_data["email"].strip().lower()
        if new_email != current_user.email.lower():
            email_check = await db.execute(
                select(User).where(
                    func.lower(User.email) == new_email,
                    User.id != current_user.id,
                )
            )
            if email_check.scalar_one_or_none():
                raise ValidationError(detail="Bu e-posta adresi başka bir kullanıcı tarafından kullanılıyor.")
            update_data["email"] = new_email
        else:
            update_data["email"] = new_email

    for field, value in update_data.items():
        if hasattr(current_user, field):
            setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return build_user_profile_response(current_user)


# ── MFA Endpoints (TASK-007) ─────────────────────────────────

@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup(
    current_user: User = Depends(aktif_kullanici),
    db: AsyncSession = Depends(get_db),
) -> MFASetupResponse:
    """
    Initialize MFA setup for authenticated user.

    Generates a TOTP secret (encrypted at rest), provisioning URI, and 10 single-use backup codes.
    MFA is not enabled until verified via /mfa/enable.
    """
    if current_user.mfa_enabled:
        raise ValidationError(detail="Çok faktörlü doğrulama zaten aktif durumda.")

    totp_secret = security.generate_totp_secret()
    provisioning_uri = security.get_totp_uri(totp_secret, current_user.email)
    encrypted_secret = security.encrypt_mfa_secret(totp_secret)

    plaintext_backup_codes = security.generate_backup_codes(10)
    hashed_backup_codes = [security.hash_backup_code(c) for c in plaintext_backup_codes]

    current_user.mfa_secret = encrypted_secret
    current_user.backup_codes = hashed_backup_codes
    current_user.mfa_enabled = False

    await db.commit()

    return MFASetupResponse(
        secret=totp_secret,
        provisioning_uri=provisioning_uri,
        backup_codes=plaintext_backup_codes,
    )


@router.post("/mfa/enable", response_model=MessageResponse)
async def mfa_enable(
    payload: MFAEnableRequest,
    current_user: User = Depends(aktif_kullanici),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Confirm setup and enable MFA by verifying initial 6-digit TOTP code.
    """
    if current_user.mfa_enabled:
        raise ValidationError(detail="Çok faktörlü doğrulama zaten aktif durumda.")

    if not current_user.mfa_secret:
        raise ValidationError(detail="Önce MFA kurulumu (/mfa/setup) yapılmalıdır.")

    plain_secret = security.decrypt_mfa_secret(current_user.mfa_secret)
    if not security.verify_totp_code(plain_secret, payload.code):
        raise MFARequiredError(detail="Geçersiz MFA doğrulama kodu.")

    current_user.mfa_enabled = True
    await db.commit()

    return MessageResponse(message="Çok faktörlü doğrulama başarıyla etkinleştirildi.")


@router.post("/mfa/verify", response_model=LoginResponse)
async def mfa_verify(
    payload: MFAVerifyRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    Verify MFA login challenge with temporary token and TOTP or backup code.
    """
    try:
        temp_payload = security.decode_mfa_temp_token(payload.mfa_temp_token)
    except Exception as e:
        raise MFARequiredError(detail="Geçersiz veya süresi dolmuş geçici doğrulama jetonu.") from e

    user_id_str = temp_payload.get("sub")
    temp_jti = temp_payload.get("jti")
    try:
        user_uuid = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise MFARequiredError(detail="Geçersiz geçici doğrulama jetonu.")

    app_obj = getattr(request, "app", None)
    app_state = getattr(app_obj, "state", None) if app_obj else None
    redis_client = getattr(app_state, "redis", None) if app_state else None

    # Verify temp token hasn't been used yet (one-time semantics)
    if redis_client and temp_jti:
        used_temp_key = f"mfa:used_temp:{temp_jti}"
        if await redis_client.exists(used_temp_key):
            raise MFARequiredError(detail="Bu geçici doğrulama jetonu zaten kullanıldı.")

    user_res = await db.execute(select(User).where(User.id == user_uuid))
    user = user_res.scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthenticationError(detail="Kullanıcı hesabı geçersiz veya pasif.")

    if user.is_effectively_locked:
        raise AccountLockedError(detail="Kullanıcı hesabı kilitli.")

    if user.organization and not user.organization.is_active:
        raise AuthenticationError(detail="Kullanıcının bağlı olduğu kurum pasif durumda.")

    if not user.mfa_enabled or not user.mfa_secret:
        raise ValidationError(detail="Çok faktörlü doğrulama bu kullanıcı için aktif değil.")

    code_clean = payload.code.strip()

    if payload.is_backup_code or len(code_clean) == 8:
        # Verify Backup Code
        found_idx: int | None = None
        raw_codes = user.backup_codes or []
        if isinstance(raw_codes, str):
            import json
            try:
                raw_codes = json.loads(raw_codes)
            except Exception:
                raw_codes = []
        elif isinstance(raw_codes, list) and raw_codes and all(isinstance(x, str) and len(x) == 1 for x in raw_codes):
            import json
            try:
                raw_codes = json.loads("".join(raw_codes))
            except Exception:
                raw_codes = []

        for idx, h_code in enumerate(raw_codes):
            if security.verify_backup_code(code_clean, h_code):
                found_idx = idx
                break

        if found_idx is None:
            raise MFARequiredError(detail="Geçersiz yedek kod.")

        # Single-use consumption
        from sqlalchemy.orm.attributes import flag_modified
        updated_codes = list(raw_codes)
        updated_codes.pop(found_idx)
        user.backup_codes = updated_codes
        flag_modified(user, "backup_codes")
    else:
        # Verify TOTP Code
        plain_secret = security.decrypt_mfa_secret(user.mfa_secret)
        if not security.verify_totp_code(plain_secret, code_clean):
            raise MFARequiredError(detail="Geçersiz MFA doğrulama kodu.")

        # Replay Protection via Redis
        if redis_client:
            replay_key = f"mfa:replay:{user.id}:{code_clean}"
            if await redis_client.exists(replay_key):
                raise MFARequiredError(detail="Bu doğrulama kodu zaten kullanıldı.")
            await redis_client.set(replay_key, "1", ex=60)

    # Mark temporary token as consumed in Redis
    if redis_client and temp_jti:
        used_temp_key = f"mfa:used_temp:{temp_jti}"
        await redis_client.set(used_temp_key, "1", ex=300)

    # Finalize Authentication
    effective_perms = perms_core.get_effective_permissions(
        user.role, user.extra_permissions, user.revoked_permissions
    )
    effective_list = sorted(list(effective_perms))

    access_token, _, exp = security.create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role,
        permissions=effective_list,
        mfa_verified=True,
    )

    now = datetime.now(timezone.utc)
    refresh_token = security.generate_refresh_token()
    refresh_hash = security.hash_token(refresh_token)

    ip_addr = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    sess = Session(
        user_id=user.id,
        refresh_token_hash=refresh_hash,
        ip_address=ip_addr,
        user_agent=user_agent,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(sess)

    user.last_login_at = now
    await db.commit()

    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_at=exp,
        user=build_user_profile_response(user),
    )


@router.post("/mfa/disable", response_model=MessageResponse)
async def mfa_disable(
    payload: MFADisableRequest,
    current_user: User = Depends(aktif_kullanici),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Disable MFA for current user. Requires password verification.
    """
    if not current_user.mfa_enabled:
        raise ValidationError(detail="Çok faktörlü doğrulama zaten pasif durumda.")

    if not security.verify_password(payload.current_password, current_user.password_hash):
        raise AuthenticationError(detail="Mevcut parola hatalı.")

    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.backup_codes = None

    await db.commit()

    return MessageResponse(message="Çok faktörlü doğrulama başarıyla devre dışı bırakıldı.")

