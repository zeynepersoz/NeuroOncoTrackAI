"""
NeuroOncoTrack-AI — Organization Model

Minimum Organization entity required for authentication scope.
All users belong to an organization; login checks organization status.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Organization(Base, UUIDMixin, TimestampMixin):
    """
    Organization (Kurum) entity.

    Defines the data scope boundary — all user and patient records
    are scoped to an organization.
    """

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    org_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    users = relationship("User", back_populates="organization", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, code={self.code!r}, active={self.is_active})>"
