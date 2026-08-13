"""
NeuroOncoTrack-AI — User Schemas

Pydantic v2 schemas for user profile responses and updates.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserProfileResponse(BaseModel):
    """User profile returned in login response and GET /auth/me."""

    id: str
    email: str
    first_name: str
    last_name: str
    full_name: str
    title: str | None = None
    role: str
    permissions: list[str] = []
    organization_id: str
    organization_name: str | None = None
    mfa_enabled: bool = False
    must_change_password: bool = False
    last_login_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    """PATCH /api/v1/auth/me — only allowed self-update fields."""

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    title: str | None = Field(None, max_length=100)
    email: EmailStr | None = Field(None)

    model_config = {"from_attributes": True, "extra": "ignore"}
