"""
NeuroOncoTrack-AI — Patient Entity

Represents a patient record scoped to an organization.
Enforces multi-tenant data isolation and audit tracking.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.ai_analysis import AIAnalysis
    from app.models.clinical_report import ClinicalReport


class Patient(Base, UUIDMixin, TimestampMixin):
    """
    Patient demographic and clinical identifier record.
    Strictly scoped to an organization to prevent cross-tenant data leakage.
    """

    __tablename__ = "patients"

    # ── Multi-Tenant Scope ──────────────────────────────────
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Clinical Identifier ─────────────────────────────────
    patient_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    birth_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── Ownership & Status ──────────────────────────────────
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "patient_id", name="uq_patients_org_patient_id"),
    )

    # ── Relationships ───────────────────────────────────────
    cases: Mapped[list[Case]] = relationship(
        "Case",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    analyses: Mapped[list[AIAnalysis]] = relationship(
        "AIAnalysis",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    reports: Mapped[list[ClinicalReport]] = relationship(
        "ClinicalReport",
        back_populates="patient",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Patient(id={self.id}, patient_id='{self.patient_id}', org_id={self.organization_id})>"
