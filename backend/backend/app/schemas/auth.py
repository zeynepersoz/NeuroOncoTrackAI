"""
NeuroOncoTrack-AI — Auth Request/Response Schemas

Pydantic v2 schemas for authentication endpoints.
Enforces strict DTO input validation (extra="forbid").
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ── Register ─────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    """POST /api/v1/auth/register"""
    email: EmailStr
    password: str
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    title: str | None = Field(None, max_length=100)
    role: str = "PHYSICIAN"
    organization_id: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Enforce password policy via core security validator."""
        from app.core.exceptions import ValidationError
        from app.core.security import validate_password
        try:
            validate_password(v)
        except ValidationError as e:
            raise ValueError(e.detail or e.message) from e
        return v


# ── Login ────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """POST /api/v1/auth/login"""
    email: EmailStr
    password: str = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")


class LoginResponse(BaseModel):
    """Successful login response (HTTP 200)."""
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserProfileResponse
    must_change_password: bool = False


class MFARequiredResponse(BaseModel):
    """Login response when MFA is required (HTTP 202)."""
    mfa_required: bool = True
    mfa_temp_token: str
    message: str = "Çok faktörlü doğrulama gerekli."


# ── MFA Flow Schemas ─────────────────────────────────────────

class MFASetupResponse(BaseModel):
    """POST /api/v1/auth/mfa/setup response."""
    secret: str
    provisioning_uri: str
    backup_codes: list[str]
    message: str = "Authenticator uygulamanızla QR kodunu tarayın ve aktivasyon için doğrulama kodunu gönderin."


class MFAEnableRequest(BaseModel):
    """POST /api/v1/auth/mfa/enable request."""
    code: str = Field(..., min_length=6, max_length=6)

    model_config = ConfigDict(extra="forbid")


class MFAVerifyRequest(BaseModel):
    """POST /api/v1/auth/mfa/verify"""
    mfa_temp_token: str
    code: str = Field(..., min_length=6, max_length=8)
    is_backup_code: bool = False

    model_config = ConfigDict(extra="forbid")


class MFADisableRequest(BaseModel):
    """POST /api/v1/auth/mfa/disable request."""
    current_password: str = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")


# ── Token Refresh ────────────────────────────────────────────

class TokenRefreshResponse(BaseModel):
    """POST /api/v1/auth/refresh response."""
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


# ── Password Change ──────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    """POST /api/v1/auth/change-password"""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=12)

    model_config = ConfigDict(extra="forbid")

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        """Enforce password policy via core security validator."""
        from app.core.exceptions import ValidationError
        from app.core.security import validate_password
        try:
            validate_password(v)
        except ValidationError as e:
            raise ValueError(e.detail or e.message) from e
        return v


# ── Forgot Password ──────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    """POST /api/v1/auth/forgot-password"""
    email: EmailStr

    model_config = ConfigDict(extra="forbid")


class ForgotPasswordResponse(BaseModel):
    """Generic response — same for existing and non-existing emails."""
    message: str = "Eğer bu e-posta adresi kayıtlıysa, parola sıfırlama bağlantısı gönderilmiştir."


# ── Reset Password ───────────────────────────────────────────

class ResetPasswordRequest(BaseModel):
    """POST /api/v1/auth/reset-password"""
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=12)

    model_config = ConfigDict(extra="forbid")

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        """Enforce password policy via core security validator."""
        from app.core.exceptions import ValidationError
        from app.core.security import validate_password
        try:
            validate_password(v)
        except ValidationError as e:
            raise ValueError(e.detail or e.message) from e
        return v


# ── Session Management ───────────────────────────────────────

class SessionResponse(BaseModel):
    """GET /api/v1/auth/sessions item."""
    id: str | uuid.UUID
    device: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    current: bool = False
    is_current: bool = False

    model_config = ConfigDict(from_attributes=True)


# ── Generic ──────────────────────────────────────────────────

class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


# ── Forward Reference Resolution ────────────────────────────
from app.schemas.user import UserProfileResponse  # noqa: E402

LoginResponse.model_rebuild()
