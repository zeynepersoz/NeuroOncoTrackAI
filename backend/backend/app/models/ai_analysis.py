"""
NeuroOncoTrack-AI — AI Analysis Entity

Tracks immutable executions of AI inference (classification, segmentation, report generation).
Maintains execution lifecycle: PENDING -> PROCESSING -> COMPLETED / FAILED.
Stores inputs and normalized numerical outputs without data loss.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.case import Case
    from app.models.ai_artifact import AIArtifact


class AIAnalysis(Base, UUIDMixin):
    """
    Persistent record of an AI analysis job.
    Never overwritten; maintains historical audit trail of inference tasks.
    """

    __tablename__ = "ai_analyses"

    # ── Tenant & Association ─────────────────────────────────
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
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Execution Metadata ───────────────────────────────────
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # classification, segmentation, report_generation
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PROCESSING", index=True)  # PENDING, PROCESSING, COMPLETED, FAILED
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── Structured Inputs (Safe, sanitized) ──────────────────
    inputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # ── Classification Results ───────────────────────────────
    prediction: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    probabilities: Mapped[dict[str, float] | None] = mapped_column(JSONB, nullable=True)
    who_grade_hint: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Volumetric & Segmentation Results ────────────────────
    tumor_volume_cm3: Mapped[float | None] = mapped_column(Float, nullable=True)
    tumor_area_ratio_2d: Mapped[float | None] = mapped_column(Float, nullable=True)
    et_wt_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    mask_artifact_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # ── Complete Normalized Output & Errors ───────────────────
    raw_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Timestamps ───────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Relationships ───────────────────────────────────────
    patient: Mapped[Patient] = relationship("Patient", back_populates="analyses")
    case: Mapped[Case | None] = relationship("Case", back_populates="analyses")
    artifacts: Mapped[list[AIArtifact]] = relationship(
        "AIArtifact",
        back_populates="analysis",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AIAnalysis(id={self.id}, op='{self.operation}', status='{self.status}', pred='{self.prediction}')>"
