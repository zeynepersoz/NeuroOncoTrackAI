"""
NeuroOncoTrack-AI — Session Model

Tracks refresh token sessions with device metadata.
Refresh token is NEVER stored as plaintext — only SHA-256 hash.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin


class Session(Base, UUIDMixin):
    """
    Session (Oturum) entity.

    Each login creates a session record. The refresh token hash
    links the opaque token in the cookie to this database record.
    """

    __tablename__ = "sessions"

    # ── User Reference ───────────────────────────────────────
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Token ────────────────────────────────────────────────
    refresh_token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # SHA-256 hex digest — plaintext NEVER stored

    # ── Device Metadata ──────────────────────────────────────
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Timestamps ───────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # ── Revocation ───────────────────────────────────────────
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    # ── Relationships ────────────────────────────────────────
    user = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        status = "revoked" if self.revoked_at else "active"
        return f"<Session(id={self.id}, user_id={self.user_id}, {status})>"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        from datetime import timezone as tz
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=tz.utc)
        return datetime.now(tz.utc) > expires

    @property
    def is_valid(self) -> bool:
        """Session is valid if not revoked and not expired."""
        return not self.is_revoked and not self.is_expired
