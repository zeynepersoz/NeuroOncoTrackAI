"""
NeuroOncoTrack-AI — Clinical Report Entity

Persistent clinical report record preserving structured sections,
immutable snapshots of classification and segmentation,
and physician signing state.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.case import Case


class ClinicalReport(Base, UUIDMixin, TimestampMixin):
    """
    Persistent AI-assisted clinical report.
    Freezes analysis snapshots to guarantee historical immutability.
    """

    __tablename__ = "clinical_reports"

    # ── Business Identifiers & Tenant Scope ──────────────────
    report_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )
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
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_analyses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Author & Lifecycle ───────────────────────────────────
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="DRAFT",
        index=True,
    )  # DRAFT, APPROVED, SIGNED

    # ── Immutable Analysis Snapshots ─────────────────────────
    classification_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    segmentation_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # ── Structured Clinical Report Sections ──────────────────
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    findings: Mapped[str] = mapped_column(Text, nullable=False)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    recommendations: Mapped[str] = mapped_column(Text, nullable=False)

    # ── FHIR DiagnosticReport Resource ───────────────────────
    fhir_resource: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    # ── Physician Signature / Approval ───────────────────────
    signed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Relationships ───────────────────────────────────────
    patient: Mapped[Patient] = relationship("Patient", back_populates="reports")
    case: Mapped[Case | None] = relationship("Case", back_populates="reports")

    def __repr__(self) -> str:
        return f"<ClinicalReport(id={self.id}, report_id='{self.report_id}', status='{self.status}')>"
