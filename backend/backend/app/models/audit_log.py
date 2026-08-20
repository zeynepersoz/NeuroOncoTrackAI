"""
NeuroOncoTrack-AI — AuditLog Model

Persistent audit log entity for security forensic tracking.
Stores event action, actor, target user, organization, result status,
client IP, user agent, and sanitized details JSON.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class AuditLog(Base, UUIDMixin):
    """
    AuditLog entity.

    Tracks immutable security audit events in database.
    """

    __tablename__ = "audit_logs"

    event: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    result: Mapped[str] = mapped_column(String(50), nullable=False, default="SUCCESS", index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        index=True,
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, event='{self.event}', actor_id={self.actor_id}, timestamp={self.timestamp})>"
