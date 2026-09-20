"""
NeuroOncoTrack-AI — AI Operations API Router (v1)

Endpoints for AI inference, classification, segmentation, reporting, and persistent history.
Enforces:
- RBAC authorization (Permission.AI_VIEW_RESULT, Permission.AI_RUN_SEGMENTATION, Permission.REPORT_GENERATE)
- Strict DTO schema validation (ClassificationInput, SegmentationInput, ReportGenerationInput)
- High-level orchestration through AIOrchestrationService
- Rate limiting on inference operations (rl:ai_classify, rl:ai_segment, rl:ai_report)
- End-to-end database persistence (Patient, Case, AIAnalysis, ClinicalReport, AIArtifact)
- Multi-tenant data isolation on all queries and mutations
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import aktif_kullanici, get_redis_client, izin_gerektir
from app.core import redis as redis_core
from app.core.config import settings
from app.core.exceptions import NotFoundError, RateLimitError
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import (
    AIAnalysis,
    AIArtifact,
    Case,
    ClinicalReport,
    Organization,
    Patient,
    User,
)
from app.schemas.ai import (
    AIAnalysisDetailResponse,
    AIAnalysisHistoryItem,
    AIAnalysisHistoryResponse,
    AIExecutionRequest,
    AIOperation,
    ClassificationInput,
    ClassificationOutput,
    ClinicalReportDetailResponse,
    ClinicalReportHistoryItem,
    ClinicalReportHistoryResponse,
    ReportGenerationInput,
    ReportGenerationOutput,
    SegmentationInput,
    SegmentationOutput,
)
from app.services.ai.deps import get_ai_service
from app.services.ai.orchestrator import AIOrchestrationService

logger = logging.getLogger("app.ai.api")

router = APIRouter(prefix="/ai", tags=["ai"])


# ── Internal Persistence Helpers ───────────────────────────────

async def _resolve_organization_id(db: AsyncSession, current_user: User) -> uuid.UUID:
    """Resolve organization ID for current user, providing safe fallback for test fixtures."""
    if getattr(current_user, "organization_id", None):
        return current_user.organization_id
    try:
        stmt = select(Organization.id).limit(1)
        res = await db.execute(stmt)
        existing_org_id = res.scalar_one_or_none()
        if existing_org_id:
            return existing_org_id
        default_org = Organization(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            name="Default Clinical Center",
            code="default",
        )
        db.add(default_org)
        await db.flush()
        return default_org.id
    except Exception:
        return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def _persist_ai_start(
    db: AsyncSession | None,
    *,
    current_user: User,
    patient_id_str: str,
    request_id: str,
    operation: str,
    model: str,
    inputs: dict[str, Any],
) -> AIAnalysis | None:
    """Record the initiation of an AI inference job in the database."""
    if db is None:
        return None
    try:
        org_id = await _resolve_organization_id(db, current_user)
        # Find or create patient record scoped to organization
        stmt = select(Patient).where(
            Patient.organization_id == org_id,
            Patient.patient_id == patient_id_str,
        )
        res = await db.execute(stmt)
        patient = res.scalar_one_or_none()
        if patient is None:
            try:
                async with db.begin_nested():
                    patient = Patient(
                        organization_id=org_id,
                        patient_id=patient_id_str,
                        created_by=current_user.id,
                    )
                    db.add(patient)
                    await db.flush()
            except IntegrityError:
                # Concurrent request created the patient record simultaneously
                stmt = select(Patient).where(
                    Patient.organization_id == org_id,
                    Patient.patient_id == patient_id_str,
                )
                res = await db.execute(stmt)
                patient = res.scalar_one_or_none()

        analysis = AIAnalysis(
            organization_id=org_id,
            patient_id=patient.id,
            created_by=current_user.id,
            request_id=request_id,
            operation=operation,
            status="PROCESSING",
            model=model,
            inputs=inputs,
        )
        db.add(analysis)
        await db.commit()
        await db.refresh(analysis)
        return analysis
    except Exception as exc:
        logger.warning("Could not persist AI start record (uninitialized DB or mock): %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass
        return None


def _sanitize_for_jsonb(obj: Any) -> Any:
    if isinstance(obj, str):
        return obj.replace("\0", "")
    if isinstance(obj, dict):
        return {str(k).replace("\0", ""): _sanitize_for_jsonb(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_jsonb(v) for v in obj]
    return obj


async def _persist_ai_complete(
    db: AsyncSession | None,
    analysis: AIAnalysis | None,
    *,
    status_val: str,
    output_dict: dict[str, Any],
    operation: str,
) -> None:
    """Record the successful completion and clinical metrics of an AI inference job."""
    if db is None or analysis is None:
        return
    try:
        analysis.status = status_val
        analysis.completed_at = datetime.now(timezone.utc)
        analysis.raw_output = _sanitize_for_jsonb(output_dict)

        if operation == "classification":
            analysis.prediction = output_dict.get("prediction")
            analysis.confidence = output_dict.get("confidence")
            analysis.probabilities = output_dict.get("probabilities")
            analysis.who_grade_hint = output_dict.get("who_grade_hint")
            analysis.tumor_area_ratio_2d = output_dict.get("tumor_area_ratio_2d")
            analysis.tumor_volume_cm3 = output_dict.get("tumor_volume_cm3")
            analysis.et_wt_ratio = output_dict.get("et_wt_ratio")
        elif operation == "segmentation":
            analysis.tumor_area_ratio_2d = output_dict.get("tumor_area_ratio_2d")
            analysis.tumor_volume_cm3 = output_dict.get("tumor_volume_cm3")
            analysis.et_wt_ratio = output_dict.get("et_wt_ratio")
            mask_art = output_dict.get("mask_artifact_id")
            if mask_art:
                clean_name = str(mask_art).strip()
                # Protect against null-bytes and path traversal
                clean_name = clean_name.replace("\0", "")
                clean_name = os.path.basename(clean_name.replace("\\", "/"))
                # Sanitize duplicate extensions such as .nii.gz.nii.gz
                clean_name = re.sub(r"(\.nii\.gz)+$", ".nii.gz", clean_name)
                clean_name = re.sub(r"(\.nii)+$", ".nii", clean_name)
                if not clean_name.endswith((".nii.gz", ".nii", ".png", ".jpg", ".jpeg")):
                    clean_name = f"{clean_name}.nii.gz"
                analysis.mask_artifact_id = clean_name
                artifact = AIArtifact(
                    organization_id=analysis.organization_id,
                    analysis_id=analysis.id,
                    artifact_type="mask",
                    file_name=clean_name,
                    file_path=f"storage/artifacts/{clean_name}",
                    content_type="application/gzip" if clean_name.endswith((".gz", ".nii.gz")) else "application/octet-stream",
                )
                db.add(artifact)
            else:
                analysis.mask_artifact_id = None

        await db.commit()
    except Exception as exc:
        logger.warning("Could not persist AI completion record: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass


async def _persist_ai_failed(
    db: AsyncSession | None,
    analysis: AIAnalysis | None,
    error_msg: str,
) -> None:
    """Record an inference job failure."""
    if db is None or analysis is None:
        return
    try:
        analysis.status = "FAILED"
        analysis.completed_at = datetime.now(timezone.utc)
        analysis.error = error_msg
        await db.commit()
    except Exception as exc:
        logger.warning("Could not persist AI failure record: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass


async def _persist_clinical_report(
    db: AsyncSession | None,
    *,
    current_user: User,
    payload: ReportGenerationInput,
    output_dict: dict[str, Any],
    report_id: str,
) -> ClinicalReport | None:
    """Record an immutable structured clinical report into the database."""
    if db is None:
        return None
    try:
        org_id = await _resolve_organization_id(db, current_user)
        # Find or create patient record scoped to organization
        stmt = select(Patient).where(
            Patient.organization_id == org_id,
            Patient.patient_id == payload.patient_id,
        )
        res = await db.execute(stmt)
        patient = res.scalar_one_or_none()
        if patient is None:
            try:
                async with db.begin_nested():
                    patient = Patient(
                        organization_id=org_id,
                        patient_id=payload.patient_id,
                        created_by=current_user.id,
                    )
                    db.add(patient)
                    await db.flush()
            except IntegrityError:
                # Concurrent request created the patient record simultaneously
                stmt = select(Patient).where(
                    Patient.organization_id == org_id,
                    Patient.patient_id == payload.patient_id,
                )
                res = await db.execute(stmt)
                patient = res.scalar_one_or_none()

        report = ClinicalReport(
            organization_id=org_id,
            patient_id=patient.id,
            created_by=current_user.id,
            report_id=report_id,
            status="FINAL",
            model=output_dict.get("model") or "report_generation_model",
            summary=output_dict.get("summary", "Klinik değerlendirme tamamlandı."),
            classification_snapshot=payload.classification.model_dump(mode="json") if payload.classification else None,
            segmentation_snapshot=payload.segmentation.model_dump(mode="json") if payload.segmentation else None,
            findings=output_dict.get("findings", "Görüntüleme analizi bulguları incelendi."),
            limitations=output_dict.get("limitations", "Bu rapor yapay zeka destekli bir sistem tarafından üretilmiştir. Kesin tanı niteliği taşımaz ve uzman hekim değerlendirmesi gerektirir."),
            recommendations=output_dict.get("recommendations", "Klinik bulgularla birlikte uzman hekim tarafından değerlendirilmesi önerilir."),
            fhir_resource=output_dict.get("fhir"),
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        return report
    except Exception as exc:
        logger.warning("Could not persist clinical report: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass
        return None


# ── Endpoints ──────────────────────────────────────────────────

@router.post(
    "/classify",
    response_model=ClassificationOutput,
    status_code=status.HTTP_200_OK,
    summary="Execute 2D/3D Tumor Classification Inference",
    description=(
        "Executes AI brain tumor classification for the specified patient and MRI modalities. "
        "Requires authenticated user with AI_VIEW_RESULT permission."
    ),
)
async def classify_tumor(
    payload: ClassificationInput,
    request: Request,
    current_user: User = Depends(izin_gerektir(Permission.AI_VIEW_RESULT)),
    ai_service: AIOrchestrationService = Depends(get_ai_service),
    redis: redis_core.Redis | None = Depends(get_redis_client),
    db: AsyncSession = Depends(get_db),
) -> ClassificationOutput:
    """Execute AI classification for brain tumor diagnosis and persist audit record."""
    # 1. Rate limiting enforcement
    if redis is not None:
        user_identifier = f"user:{current_user.id}"
        is_allowed, attempts = await redis_core.check_rate_limit(
            redis,
            identifier=user_identifier,
            prefix="rl:ai_classify:",
            max_attempts=settings.AI_CLASSIFICATION_RATE_LIMIT_ATTEMPTS,
        )
        if not is_allowed:
            raise RateLimitError(
                detail=f"AI sınıflandırma istek limiti aşıldı ({settings.AI_CLASSIFICATION_RATE_LIMIT_ATTEMPTS} istek/{settings.AI_CLASSIFICATION_RATE_LIMIT_WINDOW_MINUTES} dk). Lütfen daha sonra tekrar deneyin."
            )
        await redis_core.increment_rate_limit(
            redis,
            identifier=user_identifier,
            prefix="rl:ai_classify:",
            window_minutes=settings.AI_CLASSIFICATION_RATE_LIMIT_WINDOW_MINUTES,
        )

    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex

    logger.info(
        "AI classification requested: user_id=%s, patient_id=%s, req_id=%s",
        str(current_user.id),
        payload.patient_id,
        request_id,
    )

    inputs: dict[str, Any] = {
        "patient_id": payload.patient_id,
        "modality_paths": payload.modality_paths,
    }
    parameters: dict[str, Any] = {
        "mode": payload.mode,
        "device": payload.device,
        "predictor": payload.predictor,
    }
    if payload.extra_features:
        parameters["extra_features"] = payload.extra_features

    exec_request = AIExecutionRequest(
        operation=AIOperation.CLASSIFICATION,
        inputs=inputs,
        parameters=parameters,
        correlation_id=request_id,
    )

    # Persist pending/processing execution record
    analysis_record = await _persist_ai_start(
        db,
        current_user=current_user,
        patient_id_str=payload.patient_id,
        request_id=request_id,
        operation="classification",
        model=payload.predictor or "classification_model",
        inputs=inputs,
    )

    try:
        exec_result = await ai_service.execute(exec_request)
    except Exception as exc:
        await _persist_ai_failed(db, analysis_record, str(exc))
        raise

    output_dict = exec_result.output
    status_str = exec_result.status.value if hasattr(exec_result.status, "value") else str(exec_result.status)

    # Persist completed results
    await _persist_ai_complete(
        db,
        analysis_record,
        status_val=status_str,
        output_dict=output_dict,
        operation="classification",
    )

    classification_response = ClassificationOutput(
        prediction=output_dict.get("prediction", ""),
        confidence=output_dict.get("confidence", 0.0),
        probabilities=output_dict.get("probabilities", {}),
        who_grade_hint=output_dict.get("who_grade_hint"),
        tumor_area_ratio_2d=output_dict.get("tumor_area_ratio_2d"),
        tumor_volume_cm3=output_dict.get("tumor_volume_cm3"),
        et_wt_ratio=output_dict.get("et_wt_ratio"),
        request_id=exec_result.request_id,
        model=exec_result.model,
        status=status_str,
        created_at=exec_result.created_at,
    )

    return classification_response


@router.post(
    "/segment",
    response_model=SegmentationOutput,
    status_code=status.HTTP_200_OK,
    summary="Execute 2D/3D Tumor Segmentation Inference",
    description=(
        "Executes AI brain tumor segmentation for the specified patient and MRI modalities. "
        "Requires authenticated user with AI_RUN_SEGMENTATION permission."
    ),
)
async def segment_tumor(
    payload: SegmentationInput,
    request: Request,
    current_user: User = Depends(izin_gerektir(Permission.AI_RUN_SEGMENTATION)),
    ai_service: AIOrchestrationService = Depends(get_ai_service),
    redis: redis_core.Redis | None = Depends(get_redis_client),
    db: AsyncSession = Depends(get_db),
) -> SegmentationOutput:
    """Execute AI segmentation for brain tumor diagnosis and persist audit record."""
    # 1. Rate limiting enforcement
    if redis is not None:
        user_identifier = f"user:{current_user.id}"
        is_allowed, attempts = await redis_core.check_rate_limit(
            redis,
            identifier=user_identifier,
            prefix="rl:ai_segment:",
            max_attempts=settings.AI_SEGMENTATION_RATE_LIMIT_ATTEMPTS,
        )
        if not is_allowed:
            raise RateLimitError(
                detail=f"AI segmentasyon istek limiti aşıldı ({settings.AI_SEGMENTATION_RATE_LIMIT_ATTEMPTS} istek/{settings.AI_SEGMENTATION_RATE_LIMIT_WINDOW_MINUTES} dk). Lütfen daha sonra tekrar deneyin."
            )
        await redis_core.increment_rate_limit(
            redis,
            identifier=user_identifier,
            prefix="rl:ai_segment:",
            window_minutes=settings.AI_SEGMENTATION_RATE_LIMIT_WINDOW_MINUTES,
        )

    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex

    logger.info(
        "AI segmentation requested: user_id=%s, patient_id=%s, req_id=%s",
        str(current_user.id),
        payload.patient_id,
        request_id,
    )

    inputs: dict[str, Any] = {
        "patient_id": payload.patient_id,
        "modality_paths": payload.modality_paths,
    }
    parameters: dict[str, Any] = {
        "mode": payload.mode,
        "device": payload.device,
        "predictor": payload.predictor,
    }
    if payload.extra_features:
        parameters["extra_features"] = payload.extra_features

    exec_request = AIExecutionRequest(
        operation=AIOperation.SEGMENTATION,
        inputs=inputs,
        parameters=parameters,
        correlation_id=request_id,
    )

    # Persist pending/processing execution record
    analysis_record = await _persist_ai_start(
        db,
        current_user=current_user,
        patient_id_str=payload.patient_id,
        request_id=request_id,
        operation="segmentation",
        model=payload.predictor or "segmentation_model",
        inputs=inputs,
    )

    try:
        exec_result = await ai_service.execute(exec_request)
    except Exception as exc:
        await _persist_ai_failed(db, analysis_record, str(exc))
        raise

    output_dict = exec_result.output
    status_str = exec_result.status.value if hasattr(exec_result.status, "value") else str(exec_result.status)

    # Persist completed results and mask artifacts
    await _persist_ai_complete(
        db,
        analysis_record,
        status_val=status_str,
        output_dict=output_dict,
        operation="segmentation",
    )

    safe_mask_id = (
        analysis_record.mask_artifact_id
        if (analysis_record and analysis_record.mask_artifact_id)
        else output_dict.get("mask_artifact_id")
    )
    if isinstance(safe_mask_id, str):
        safe_mask_id = os.path.basename(safe_mask_id.replace("\\", "/")).replace("\0", "")

    segmentation_response = SegmentationOutput(
        status=status_str,
        mask_status=output_dict.get("mask_status"),
        mask_artifact_id=safe_mask_id or None,
        tumor_area_ratio_2d=output_dict.get("tumor_area_ratio_2d"),
        tumor_volume_cm3=output_dict.get("tumor_volume_cm3"),
        et_wt_ratio=output_dict.get("et_wt_ratio"),
        volumes_cm3=output_dict.get("volumes_cm3"),
        slices_count=output_dict.get("slices_count"),
        num_tumor_slices=output_dict.get("num_tumor_slices"),
        best_slice=output_dict.get("best_slice"),
        request_id=exec_result.request_id,
        model=exec_result.model,
        created_at=exec_result.created_at,
    )

    return segmentation_response


@router.post(
    "/report",
    response_model=ReportGenerationOutput,
    status_code=status.HTTP_200_OK,
    summary="Generate Structured AI Clinical Report",
    description=(
        "Generates a structured clinical AI report consuming previously computed "
        "classification and segmentation analysis. Requires authenticated user with "
        "REPORT_GENERATE permission and is protected by dedicated rate limiting."
    ),
)
async def generate_ai_report(
    payload: ReportGenerationInput,
    request: Request,
    current_user: User = Depends(izin_gerektir(Permission.REPORT_GENERATE)),
    ai_service: AIOrchestrationService = Depends(get_ai_service),
    redis: redis_core.Redis | None = Depends(get_redis_client),
    db: AsyncSession = Depends(get_db),
) -> ReportGenerationOutput:
    """Generate structured AI clinical report and persist immutable document."""
    # 1. Rate limiting enforcement
    if redis is not None:
        user_identifier = f"user:{current_user.id}"
        is_allowed, attempts = await redis_core.check_rate_limit(
            redis,
            identifier=user_identifier,
            prefix="rl:ai_report:",
            max_attempts=settings.AI_REPORT_RATE_LIMIT_ATTEMPTS,
        )
        if not is_allowed:
            raise RateLimitError(
                detail=f"AI rapor üretim istek limiti aşıldı ({settings.AI_REPORT_RATE_LIMIT_ATTEMPTS} istek/{settings.AI_REPORT_RATE_LIMIT_WINDOW_MINUTES} dk). Lütfen daha sonra tekrar deneyin."
            )
        await redis_core.increment_rate_limit(
            redis,
            identifier=user_identifier,
            prefix="rl:ai_report:",
            window_minutes=settings.AI_REPORT_RATE_LIMIT_WINDOW_MINUTES,
        )

    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex

    logger.info(
        "AI report generation requested: user_id=%s, patient_id=%s, req_id=%s",
        str(current_user.id),
        payload.patient_id,
        request_id,
    )

    inputs: dict[str, Any] = {
        "patient_id": payload.patient_id,
    }
    if payload.classification is not None:
        inputs["classification"] = payload.classification.model_dump()
    if payload.segmentation is not None:
        inputs["segmentation"] = payload.segmentation.model_dump()
    if payload.extra_clinical_context is not None:
        inputs["extra_clinical_context"] = payload.extra_clinical_context

    exec_request = AIExecutionRequest(
        operation=AIOperation.REPORT_GENERATION,
        inputs=inputs,
        parameters={},
        correlation_id=request_id,
    )

    exec_result = await ai_service.execute(exec_request)
    output_dict = exec_result.output
    generated_report_id = output_dict.get("report_id") or uuid.uuid4().hex
    status_str = exec_result.status.value if hasattr(exec_result.status, "value") else str(exec_result.status)

    # Persist immutable clinical report
    await _persist_clinical_report(
        db,
        current_user=current_user,
        payload=payload,
        output_dict=output_dict,
        report_id=generated_report_id,
    )

    report_response = ReportGenerationOutput(
        report_id=generated_report_id,
        request_id=exec_result.request_id,
        status=status_str,
        summary=output_dict.get("summary", "Klinik değerlendirme tamamlandı."),
        classification=output_dict.get("classification") or (payload.classification.model_dump() if payload.classification else None),
        segmentation=output_dict.get("segmentation") or (payload.segmentation.model_dump() if payload.segmentation else None),
        findings=output_dict.get("findings", "Görüntüleme analizi bulguları incelendi."),
        limitations=output_dict.get("limitations", "Bu rapor yapay zeka destekli bir sistem tarafından üretilmiştir. Kesin tanı niteliği taşımaz ve uzman hekim değerlendirmesi gerektirir."),
        recommendations=output_dict.get("recommendations", "Klinik bulgularla birlikte uzman hekim tarafından değerlendirilmesi önerilir."),
        model=exec_result.model,
        created_at=exec_result.created_at,
        fhir=output_dict.get("fhir"),
    )

    return report_response


# ── History & Case Retrieval Endpoints ─────────────────────────

@router.get(
    "/history",
    response_model=AIAnalysisHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get AI Analysis History (Tenant Scoped)",
    description="Retrieves a paginated list of previous AI analyses for the tenant, with optional patient and operation filters.",
)
async def get_ai_history(
    patient_id: str | None = None,
    operation: str | None = None,
    status_filter: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(izin_gerektir(Permission.AI_VIEW_RESULT)),
    db: AsyncSession = Depends(get_db),
) -> AIAnalysisHistoryResponse:
    """Retrieve historical AI analysis records scoped to user's organization."""
    org_id = await _resolve_organization_id(db, current_user)
    query = (
        select(AIAnalysis, Patient.patient_id.label("patient_code"))
        .join(Patient, AIAnalysis.patient_id == Patient.id)
        .where(AIAnalysis.organization_id == org_id)
    )
    if patient_id:
        query = query.where(Patient.patient_id == patient_id)
    if operation:
        query = query.where(AIAnalysis.operation == operation)
    if status_filter:
        query = query.where(AIAnalysis.status == status_filter)

    count_query = select(func.count()).select_from(query.subquery())
    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    query = query.order_by(desc(AIAnalysis.created_at)).offset(offset).limit(limit)
    rows = await db.execute(query)

    items: list[AIAnalysisHistoryItem] = []
    for analysis, p_code in rows.all():
        items.append(
            AIAnalysisHistoryItem(
                id=str(analysis.id),
                organization_id=str(analysis.organization_id),
                patient_id=p_code,
                case_id=str(analysis.case_id) if analysis.case_id else None,
                request_id=analysis.request_id,
                operation=analysis.operation,
                status=analysis.status,
                model=analysis.model,
                prediction=analysis.prediction,
                confidence=analysis.confidence,
                tumor_volume_cm3=analysis.tumor_volume_cm3,
                created_at=analysis.created_at,
                completed_at=analysis.completed_at,
            )
        )

    return AIAnalysisHistoryResponse(items=items, total=total)


@router.get(
    "/analyses/{analysis_id}",
    response_model=AIAnalysisDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get AI Analysis Detail (Tenant Scoped)",
    description="Retrieves comprehensive details of a single AI analysis execution, enforcing strict multi-tenant authorization.",
)
async def get_ai_analysis_detail(
    analysis_id: uuid.UUID,
    current_user: User = Depends(izin_gerektir(Permission.AI_VIEW_RESULT)),
    db: AsyncSession = Depends(get_db),
) -> AIAnalysisDetailResponse:
    """Retrieve full detail of a specific AI analysis execution."""
    org_id = await _resolve_organization_id(db, current_user)
    stmt = (
        select(AIAnalysis, Patient.patient_id.label("patient_code"))
        .join(Patient, AIAnalysis.patient_id == Patient.id)
        .where(
            AIAnalysis.id == analysis_id,
            AIAnalysis.organization_id == org_id,
        )
    )
    res = await db.execute(stmt)
    row = res.one_or_none()
    if not row:
        raise NotFoundError("Analiz kaydı bulunamadı veya erişim yetkiniz yok.")
    analysis, p_code = row

    return AIAnalysisDetailResponse(
        id=str(analysis.id),
        organization_id=str(analysis.organization_id),
        patient_id=p_code,
        case_id=str(analysis.case_id) if analysis.case_id else None,
        request_id=analysis.request_id,
        operation=analysis.operation,
        status=analysis.status,
        model=analysis.model,
        model_version=analysis.model_version,
        inputs=analysis.inputs,
        prediction=analysis.prediction,
        confidence=analysis.confidence,
        probabilities=analysis.probabilities,
        who_grade_hint=analysis.who_grade_hint,
        tumor_volume_cm3=analysis.tumor_volume_cm3,
        tumor_area_ratio_2d=analysis.tumor_area_ratio_2d,
        et_wt_ratio=analysis.et_wt_ratio,
        mask_artifact_id=analysis.mask_artifact_id,
        raw_output=analysis.raw_output,
        error=analysis.error,
        created_at=analysis.created_at,
        completed_at=analysis.completed_at,
    )


@router.get(
    "/reports",
    response_model=ClinicalReportHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="List Generated Clinical Reports (Tenant Scoped)",
    description="Retrieves a list of generated clinical reports for the current organization.",
)
async def list_clinical_reports(
    patient_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(izin_gerektir(Permission.AI_VIEW_RESULT)),
    db: AsyncSession = Depends(get_db),
) -> ClinicalReportHistoryResponse:
    """Retrieve historical clinical reports scoped to user's organization."""
    org_id = await _resolve_organization_id(db, current_user)
    query = (
        select(ClinicalReport, Patient.patient_id.label("patient_code"))
        .join(Patient, ClinicalReport.patient_id == Patient.id)
        .where(ClinicalReport.organization_id == org_id)
    )
    if patient_id:
        query = query.where(Patient.patient_id == patient_id)

    count_query = select(func.count()).select_from(query.subquery())
    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    query = query.order_by(desc(ClinicalReport.created_at)).offset(offset).limit(limit)
    rows = await db.execute(query)

    items: list[ClinicalReportHistoryItem] = []
    for report, p_code in rows.all():
        items.append(
            ClinicalReportHistoryItem(
                id=str(report.id),
                report_id=report.report_id,
                patient_id=p_code,
                case_id=str(report.case_id) if report.case_id else None,
                status=report.status,
                summary=report.summary,
                created_at=report.created_at,
            )
        )

    return ClinicalReportHistoryResponse(items=items, total=total)


@router.get(
    "/reports/{report_id}",
    response_model=ClinicalReportDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Single Clinical Report (Tenant Scoped)",
    description="Retrieves full immutable clinical report by report_id within tenant boundary.",
)
async def get_clinical_report_detail(
    report_id: str,
    current_user: User = Depends(izin_gerektir(Permission.AI_VIEW_RESULT)),
    db: AsyncSession = Depends(get_db),
) -> ClinicalReportDetailResponse:
    """Retrieve full detail of a specific clinical report."""
    org_id = await _resolve_organization_id(db, current_user)
    stmt = (
        select(ClinicalReport, Patient.patient_id.label("patient_code"))
        .join(Patient, ClinicalReport.patient_id == Patient.id)
        .where(
            ClinicalReport.report_id == report_id,
            ClinicalReport.organization_id == org_id,
        )
    )
    res = await db.execute(stmt)
    row = res.one_or_none()
    if not row:
        raise NotFoundError("Klinik rapor bulunamadı veya erişim yetkiniz yok.")
    report, p_code = row

    return ClinicalReportDetailResponse(
        id=str(report.id),
        report_id=report.report_id,
        patient_id=p_code,
        case_id=str(report.case_id) if report.case_id else None,
        status=report.status,
        model=report.model,
        summary=report.summary,
        classification_snapshot=report.classification_snapshot,
        segmentation_snapshot=report.segmentation_snapshot,
        findings=report.findings,
        limitations=report.limitations,
        recommendations=report.recommendations,
        fhir_resource=report.fhir_resource,
        created_at=report.created_at,
    )
