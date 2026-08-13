"""
NeuroOncoTrack-AI — Password History Model

Tracks previous password hashes to enforce the "last 5 passwords
cannot be reused" policy defined in the architecture.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin


class PasswordHistory(Base, UUIDMixin):
    """
    Password history record.

    Stores Argon2id hashes of previous passwords.
    When a user changes their password, the old hash is recorded here.
    The system checks the last N entries to prevent password reuse.
    """

    __tablename__ = "password_history"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # ── Relationship ─────────────────────────────────────────
    user = relationship("User", back_populates="password_history")

    def __repr__(self) -> str:
        return f"<PasswordHistory(id={self.id}, user_id={self.user_id})>"
