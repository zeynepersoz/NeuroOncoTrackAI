"""Create clinical and AI persistence tables (patients, cases, ai_analyses, clinical_reports, ai_artifacts)

Revision ID: 004_clinical_ai_persistence
Revises: 003_password_reset_tokens
Create Date: 2026-09-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_clinical_ai_persistence"
down_revision: Union[str, None] = "003_password_reset_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Patients ──────────────────────────────────────────────
    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("patient_id", sa.String(64), nullable=False, index=True),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("birth_date", sa.String(20), nullable=True),
        sa.Column("gender", sa.String(20), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "patient_id", name="uq_patients_org_patient_id"),
    )

    # ── Cases ─────────────────────────────────────────────────
    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("case_number", sa.String(64), nullable=False, index=True),
        sa.Column("modality", sa.String(20), nullable=False, server_default="MR"),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN", index=True),
        sa.Column("physician_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("clinical_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "case_number", name="uq_cases_org_case_number"),
    )

    # ── AI Analyses ───────────────────────────────────────────
    op.create_table(
        "ai_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("request_id", sa.String(128), nullable=False, index=True),
        sa.Column("operation", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False, default="PROCESSING", index=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("inputs", postgresql.JSONB(), nullable=True),
        sa.Column("prediction", sa.String(50), nullable=True, index=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("probabilities", postgresql.JSONB(), nullable=True),
        sa.Column("who_grade_hint", sa.String(100), nullable=True),
        sa.Column("tumor_volume_cm3", sa.Float(), nullable=True),
        sa.Column("tumor_area_ratio_2d", sa.Float(), nullable=True),
        sa.Column("et_wt_ratio", sa.Float(), nullable=True),
        sa.Column("mask_artifact_id", sa.String(256), nullable=True),
        sa.Column("raw_output", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Clinical Reports ──────────────────────────────────────
    op.create_table(
        "clinical_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_analyses.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("report_id", sa.String(128), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False, default="DRAFT", index=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("classification_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("segmentation_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("findings", sa.Text(), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=False),
        sa.Column("recommendations", sa.Text(), nullable=False),
        sa.Column("fhir_resource", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("report_id", name="uq_clinical_reports_report_id"),
    )

    # ── AI Artifacts ──────────────────────────────────────────
    op.create_table(
        "ai_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_analyses.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("artifact_type", sa.String(50), nullable=False, index=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ai_artifacts")
    op.drop_table("clinical_reports")
    op.drop_table("ai_analyses")
    op.drop_table("cases")
    op.drop_table("patients")
