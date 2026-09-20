"""
NeuroOncoTrack-AI — Case / Clinical Study Entity

Represents a medical examination or imaging study episode tied to a patient.
Tracks attending physician, clinical indication, and modality.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.ai_analysis import AIAnalysis
    from app.models.clinical_report import ClinicalReport


class Case(Base, UUIDMixin, TimestampMixin):
    """
    Clinical case or imaging examination study record.
    """

    __tablename__ = "cases"

    # ── Multi-Tenant Scope ──────────────────────────────────
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Case Metadata ───────────────────────────────────────
    case_number: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    modality: Mapped[str] = mapped_column(String(20), nullable=False, default="MR")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN", index=True)

    # ── Physician & Ownership ───────────────────────────────
    physician_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clinical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "case_number", name="uq_cases_org_case_number"),
    )

    # ── Relationships ───────────────────────────────────────
    patient: Mapped[Patient] = relationship("Patient", back_populates="cases")
    analyses: Mapped[list[AIAnalysis]] = relationship(
        "AIAnalysis",
        back_populates="case",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    reports: Mapped[list[ClinicalReport]] = relationship(
        "ClinicalReport",
        back_populates="case",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Case(id={self.id}, case_number='{self.case_number}', status='{self.status}')>"
