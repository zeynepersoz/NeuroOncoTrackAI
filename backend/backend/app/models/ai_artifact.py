"""
NeuroOncoTrack-AI — AI Artifact Entity

Tracks files and generated binary assets (segmentation masks, NIfTI files, overlay images, heatmaps)
associated with AI analysis jobs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.ai_analysis import AIAnalysis


class AIArtifact(Base, UUIDMixin):
    """
    Metadata for AI generated file artifacts (e.g. segmentation masks, overlays).
    Stored paths reference secure multi-tenant object storage or local media vaults.
    """

    __tablename__ = "ai_artifacts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # e.g. "mask", "segmentation_nifti", "overlay", "report_pdf"
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/octet-stream")
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    # ── Relationships ───────────────────────────────────────
    analysis: Mapped[AIAnalysis] = relationship("AIAnalysis", back_populates="artifacts")

    def __repr__(self) -> str:
        return f"<AIArtifact(id={self.id}, type='{self.artifact_type}', path='{self.file_path}')>"
