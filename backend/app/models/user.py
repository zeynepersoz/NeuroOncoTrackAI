"""
NeuroOncoTrack-AI — User Model

Full User entity with all authentication-related fields.
Sensitive fields (mfa_secret) are stored encrypted.
Backup codes are stored as hashed values.
Password hash and sensitive data must NEVER be logged.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    """
    User (Kullanıcı) entity.

    Contains all fields needed for authentication, authorization,
    MFA, account locking, and password policy enforcement.
    """

    __tablename__ = "users"

    # ── Organization Scope ───────────────────────────────────
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── Identity ─────────────────────────────────────────────
    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Role & Permissions ───────────────────────────────────
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    extra_permissions: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True, default=list
    )
    revoked_permissions: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True, default=list
    )

    # ── Account Status ───────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # ── MFA ──────────────────────────────────────────────────
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Fernet-encrypted TOTP secret
    backup_codes: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )  # SHA-256 hashed backup codes

    # ── Password Policy ──────────────────────────────────────
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Audit Trail ──────────────────────────────────────────
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ────────────────────────────────────────
    organization = relationship("Organization", back_populates="users", lazy="joined")
    sessions = relationship(
        "Session", back_populates="user", lazy="selectin", cascade="all, delete-orphan"
    )
    password_history = relationship(
        "PasswordHistory",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="PasswordHistory.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email!r}, role={self.role})>"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def is_effectively_locked(self) -> bool:
        """Check if account is currently locked (including time-based locks)."""
        if not self.is_locked:
            return False
        if self.locked_until is None:
            return True  # Permanently locked
        from datetime import timezone as tz
        return datetime.now(tz.utc) < self.locked_until
