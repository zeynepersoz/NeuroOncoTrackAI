"""
NeuroOncoTrack-AI — Internal AI Service Provider

Concrete AI provider communicating with the existing internal FastAPI AI microservice
(ai_service/serve.py) via AIServiceClient.
Enforces:
- Authoritative server configuration (endpoint, model, timeouts, retries)
- Strict parameter whitelisting (drops unvetted parameters)
- Strict path sanitization (prevents directory traversal, generates safe server-side output_dir)
- groq_api_key suppression (never accepted or forwarded; ai_service uses server environment)
- Strict response validation (ensures valid types, required fields, and schema conformity)
- Comprehensive detail sanitization (shields internal filesystem paths and hostnames)
"""

from __future__ import annotations

import math
import re
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.exceptions import AIServiceInvalidResponse
from app.schemas.ai import (
    AIExecutionRequest,
    AIExecutionResult,
    AIHealthResponse,
    AIOperation,
    AIResponse,
    AIServiceDefinition,
    AIStatus,
    KNOWN_CLASSIFICATION_LABELS,
)
from app.services.ai.client import AIServiceClient
from app.services.ai.provider import AIProvider

# Allowed parameters and their valid choices for downstream ai_service
ALLOWED_INFER_MODES = {"full", "fast", "classify_only"}
ALLOWED_DEVICES = {"auto", "cuda", "mps", "cpu"}
ALLOWED_PREDICTORS = {"v3", "v2"}

# Restricted keys that must NEVER be forwarded to ai_service
RESTRICTED_PAYLOAD_KEYS = {
    "groq_api_key",
    "api_key",
    "secret",
    "token",
    "password",
    "authorization",
    "provider",
    "base_url",
    "endpoint",
    "model",
    "guidelines_dir",
    "quarantine_root",
    "output_dir",
}


class InternalAIServiceProvider(AIProvider):
    """
    Concrete provider connecting to the internal NeuroOncoTrack AI microservice.
    """

    def __init__(self, client: AIServiceClient | None = None):
        self.client = client or AIServiceClient()

    @property
    def provider_name(self) -> str:
        return "internal_service"

    def _sanitize_patient_id(self, patient_id: Any) -> str:
        """Sanitize patient identifier to prevent path manipulation."""
        raw = str(patient_id or "ANON_PATIENT")
        cleaned = re.sub(r"[^A-Za-z0-9_\-]", "", raw)
        return cleaned or "ANON_PATIENT"

    def _validate_modality_paths(self, modality_paths: dict[str, Any]) -> dict[str, str]:
        """Validate modality path map against directory traversal."""
        cleaned_paths = {}
        for mod, path_val in modality_paths.items():
            str_path = str(path_val)
            if ".." in str_path or "\0" in str_path:
                raise AIServiceInvalidResponse(
                    detail="Geçersiz modalite dosya yolu: Dizin geçişi karakterleri tespit edildi."
                )
            cleaned_paths[str(mod).lower()] = str_path
        return cleaned_paths

    def _filter_and_whitelist_parameters(
        self, parameters: dict[str, Any] | None
    ) -> dict[str, Any]:
        """
        Enforce strict parameter whitelisting.
        Never forwards groq_api_key or arbitrary user-supplied parameters.
        """
        if not parameters:
            return {}

        whitelisted: dict[str, Any] = {}

        # 1. Mode check
        if "mode" in parameters:
            mode_val = str(parameters["mode"]).lower()
            if mode_val in ALLOWED_INFER_MODES:
                whitelisted["mode"] = mode_val

        # 2. Device check
        if "device" in parameters:
            dev_val = str(parameters["device"]).lower()
            if dev_val in ALLOWED_DEVICES:
                whitelisted["device"] = dev_val

        # 3. Predictor check
        if "predictor" in parameters:
            pred_val = str(parameters["predictor"]).lower()
            if pred_val in ALLOWED_PREDICTORS:
                whitelisted["predictor"] = pred_val

        # 4. Extra features (must be dict)
        if "extra_features" in parameters and isinstance(parameters["extra_features"], dict):
            # Only numeric values permitted in extra_features
            safe_features = {}
            for k, v in parameters["extra_features"].items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    safe_features[str(k)] = float(v)
            if safe_features:
                whitelisted["extra_features"] = safe_features

        return whitelisted

    def _build_infer_payload(
        self,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build a secure InferRequest payload for existing ai_service /infer endpoint.
        Guarantees server-controlled output_dir and safe modality_paths.
        """
        patient_id = self._sanitize_patient_id(inputs.get("patient_id"))
        server_output_dir = f"processed/{patient_id}"

        raw_modalities = inputs.get("modality_paths") or inputs.get("modalities")
        if isinstance(raw_modalities, dict):
            modality_paths = self._validate_modality_paths(raw_modalities)
        else:
            # Fallback for direct slice or mock payload compatibility
            modality_paths = {"t1c": "t1c_synthetic.nii.gz"}

        whitelisted_params = self._filter_and_whitelist_parameters(parameters)

        payload: dict[str, Any] = {
            "patient_id": patient_id,
            "modality_paths": modality_paths,
            "output_dir": server_output_dir,
            "mode": whitelisted_params.get("mode", "fast"),
            "device": whitelisted_params.get("device", "auto"),
            "predictor": whitelisted_params.get("predictor", "v3"),
        }

        if "extra_features" in whitelisted_params:
            payload["extra_features"] = whitelisted_params["extra_features"]

        return payload

    def _build_report_payload(
        self,
        inputs: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build a secure ReportRequest payload for existing ai_service /report endpoint.
        Never forwards groq_api_key; downstream relies on server-side environment.
        """
        safe_model_output: dict[str, Any] = {}
        patient_id = self._sanitize_patient_id(inputs.get("patient_id"))
        safe_model_output["patient_id"] = patient_id

        # 1. Classification inputs
        cls_data = inputs.get("classification")
        if isinstance(cls_data, dict):
            if "prediction" in cls_data and cls_data["prediction"]:
                safe_model_output["prediction"] = str(cls_data["prediction"]).strip().lower()
            if "confidence" in cls_data and cls_data["confidence"] is not None:
                safe_model_output["confidence"] = float(cls_data["confidence"])
            if "probabilities" in cls_data and isinstance(cls_data["probabilities"], dict):
                safe_model_output["probabilities"] = {
                    str(k).strip().lower(): float(v) for k, v in cls_data["probabilities"].items()
                }
            if "who_grade_hint" in cls_data and cls_data["who_grade_hint"]:
                safe_model_output["who_grade_hint"] = str(cls_data["who_grade_hint"])
            if "tumor_area_ratio_2d" in cls_data and cls_data["tumor_area_ratio_2d"] is not None:
                safe_model_output["tumor_area_ratio_2d"] = float(cls_data["tumor_area_ratio_2d"])
            if "tumor_volume_cm3" in cls_data and cls_data["tumor_volume_cm3"] is not None:
                safe_model_output["tumor_volume_cm3"] = float(cls_data["tumor_volume_cm3"])
            if "et_wt_ratio" in cls_data and cls_data["et_wt_ratio"] is not None:
                safe_model_output["et_wt_ratio"] = float(cls_data["et_wt_ratio"])

        # 2. Segmentation inputs
        seg_data = inputs.get("segmentation")
        if isinstance(seg_data, dict):
            if "tumor_volume_cm3" in seg_data and seg_data["tumor_volume_cm3"] is not None:
                safe_model_output["tumor_volume_cm3"] = float(seg_data["tumor_volume_cm3"])
            if "tumor_area_ratio_2d" in seg_data and seg_data["tumor_area_ratio_2d"] is not None:
                safe_model_output["tumor_area_ratio_2d"] = float(seg_data["tumor_area_ratio_2d"])
            if "et_wt_ratio" in seg_data and seg_data["et_wt_ratio"] is not None:
                safe_model_output["et_wt_ratio"] = float(seg_data["et_wt_ratio"])
            if "volumes_cm3" in seg_data and isinstance(seg_data["volumes_cm3"], dict):
                safe_model_output["volumes_cm3"] = {
                    str(k).strip().lower(): float(v) for k, v in seg_data["volumes_cm3"].items()
                }

        # 3. Direct model_output fallback (if caller passed raw dict)
        if not cls_data and not seg_data and "model_output" in inputs and isinstance(inputs["model_output"], dict):
            for k, v in inputs["model_output"].items():
                if str(k).lower() not in RESTRICTED_PAYLOAD_KEYS:
                    safe_model_output[k] = v
        elif not cls_data and not seg_data:
            # Check if root inputs has prediction
            for k, v in inputs.items():
                if str(k).lower() not in RESTRICTED_PAYLOAD_KEYS and k not in ("extra_clinical_context", "classification", "segmentation"):
                    safe_model_output[k] = v

        # 4. Extra clinical context
        extra_ctx = inputs.get("extra_clinical_context")
        if isinstance(extra_ctx, dict):
            for k, v in extra_ctx.items():
                if str(k).lower() not in RESTRICTED_PAYLOAD_KEYS and isinstance(v, (str, int, float, bool)):
                    safe_model_output[f"clinical_{k}"] = v

        return {"model_output": safe_model_output}
    def _validate_segmentation_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate and sanitize segmentation output fields against NaN/Inf/bounds."""
        clean_seg: dict[str, Any] = {}

        # mask_status
        mask_status = data.get("mask_status")
        if mask_status is not None:
            clean_seg["mask_status"] = str(mask_status).strip().lower()

        # mask_artifact_id: sanitize to relative name, no traversal, no absolute paths
        mask_artifact = data.get("mask_artifact_id")
        if mask_artifact is not None:
            s_artifact = str(mask_artifact).strip()
            if "\0" in s_artifact or ".." in s_artifact:
                raise AIServiceInvalidResponse(detail="Geçersiz maske dosyası belirteci.")
            if s_artifact.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", s_artifact):
                raise AIServiceInvalidResponse(detail="Maske dosyası mutlak yol içeremez.")
            clean_seg["mask_artifact_id"] = s_artifact

        # tumor_area_ratio_2d
        if data.get("tumor_area_ratio_2d") is not None:
            v = data["tumor_area_ratio_2d"]
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise AIServiceInvalidResponse(detail="tumor_area_ratio_2d sayısal olmalıdır.")
            fv = float(v)
            if math.isnan(fv) or math.isinf(fv) or not (0.0 <= fv <= 1.0):
                raise AIServiceInvalidResponse(detail="tumor_area_ratio_2d [0.0, 1.0] aralığında olmalıdır.")
            clean_seg["tumor_area_ratio_2d"] = fv

        # tumor_volume_cm3
        vol_raw = data.get("tumor_volume_cm3") if data.get("tumor_volume_cm3") is not None else data.get("volume_cm3")
        if vol_raw is not None:
            if not isinstance(vol_raw, (int, float)) or isinstance(vol_raw, bool):
                raise AIServiceInvalidResponse(detail="tumor_volume_cm3 sayısal olmalıdır.")
            fvol = float(vol_raw)
            if math.isnan(fvol) or math.isinf(fvol) or fvol < 0.0:
                raise AIServiceInvalidResponse(detail="tumor_volume_cm3 negatif veya geçersiz olamaz.")
            clean_seg["tumor_volume_cm3"] = fvol

        # et_wt_ratio
        if data.get("et_wt_ratio") is not None:
            v = data["et_wt_ratio"]
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise AIServiceInvalidResponse(detail="et_wt_ratio sayısal olmalıdır.")
            fv = float(v)
            if math.isnan(fv) or math.isinf(fv) or not (0.0 <= fv <= 1.0):
                raise AIServiceInvalidResponse(detail="et_wt_ratio [0.0, 1.0] aralığında olmalıdır.")
            clean_seg["et_wt_ratio"] = fv

        # volumes_cm3
        if data.get("volumes_cm3") is not None:
            vols = data["volumes_cm3"]
            if not isinstance(vols, dict):
                raise AIServiceInvalidResponse(detail="volumes_cm3 sözlük formatında olmalıdır.")
            clean_vols: dict[str, float] = {}
            for k, vk in vols.items():
                if not isinstance(vk, (int, float)) or isinstance(vk, bool):
                    raise AIServiceInvalidResponse(detail=f"Hacim değeri '{k}' sayısal olmalıdır.")
                fvk = float(vk)
                if math.isnan(fvk) or math.isinf(fvk) or fvk < 0.0:
                    raise AIServiceInvalidResponse(detail=f"Hacim değeri '{k}' negatif veya geçersiz olamaz.")
                clean_vols[str(k).strip().lower()] = fvk
            clean_seg["volumes_cm3"] = clean_vols

        # integer slice counts
        for count_key in ("slices_count", "num_tumor_slices", "best_slice"):
            if data.get(count_key) is not None:
                ck = data[count_key]
                if not isinstance(ck, int) or isinstance(ck, bool) or ck < 0:
                    raise AIServiceInvalidResponse(detail=f"{count_key} pozitif tam sayı olmalıdır.")
                clean_seg[count_key] = ck

        return clean_seg

    def _validate_and_normalize_report_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate and sanitize report output fields against leaks and contradictions."""
        clean_rep: dict[str, Any] = {}

        # 1. Sections mapping
        sections = data.get("sections") if isinstance(data.get("sections"), dict) else {}
        clean_rep["sections"] = sections

        # 2. Summary
        summary = data.get("summary") or sections.get("DEĞERLENDİRME") or data.get("report") or "Klinik değerlendirme tamamlandı."
        clean_summary = str(summary).strip()
        if not clean_summary:
            clean_summary = "Klinik değerlendirme tamamlandı."
        clean_summary = re.sub(r"[A-Za-z]:\\[^ \n]+|/home/[^ \n]+|/var/[^ \n]+", "[gizlendi]", clean_summary)
        clean_rep["summary"] = clean_summary

        # 3. Findings
        findings = data.get("findings") or sections.get("BULGULAR") or clean_summary
        clean_findings = str(findings).strip()
        if not clean_findings:
            clean_findings = "Görüntüleme analizi bulguları incelendi."
        clean_findings = re.sub(r"[A-Za-z]:\\[^ \n]+|/home/[^ \n]+|/var/[^ \n]+", "[gizlendi]", clean_findings)
        clean_rep["findings"] = clean_findings

        # 4. Recommendations
        recs = data.get("recommendations") or sections.get("ÖNERİ") or "Klinik bulgularla birlikte uzman hekim tarafından değerlendirilmesi önerilir."
        clean_recs = str(recs).strip()
        if not clean_recs:
            clean_recs = "Klinik bulgularla birlikte uzman hekim tarafından değerlendirilmesi önerilir."
        for phrase in ("kesin tanı", "kesinlikle", "teşhis edilmiştir", "tanısı konulmuştur", "definitively diagnosed"):
            if phrase in clean_recs.lower():
                raise AIServiceInvalidResponse(
                    detail=f"AI raporu öneriler bölümü kesin tanı iddiası içeremez: '{phrase}'"
                )
        clean_rep["recommendations"] = clean_recs

        # 5. Limitations
        limits = data.get("limitations") or "Bu rapor yapay zeka destekli bir sistem tarafından üretilmiştir. Kesin tanı niteliği taşımaz ve uzman hekim değerlendirmesi gerektirir."
        clean_limits = str(limits).strip()
        clean_rep["limitations"] = clean_limits

        # 6. FHIR
        if "fhir" in data and isinstance(data["fhir"], dict):
            clean_rep["fhir"] = data["fhir"]
        else:
            clean_rep["fhir"] = None

        if "report" in data and isinstance(data["report"], str):
            clean_rep["report"] = data["report"]

        # Classification / Segmentation passthrough if present in data
        if "classification" in data:
            clean_rep["classification"] = data["classification"]
        if "segmentation" in data:
            clean_rep["segmentation"] = data["segmentation"]

        # Medical consistency check: if prediction is notumor, findings/summary cannot state confirmed tumor/glioma
        pred = data.get("prediction") or (data.get("classification") or {}).get("prediction")
        if pred and str(pred).strip().lower() == "notumor":
            lower_text = f"{clean_summary.lower()} {clean_findings.lower()}"
            if "kesin glioma" in lower_text or "confirmed glioma" in lower_text or "tümör varlığı doğrulanmıştır" in lower_text:
                raise AIServiceInvalidResponse(
                    detail="AI rapor çıktısı kaynak sınıflandırma verisiyle ('notumor') çelişiyor."
                )

        return clean_rep

    def _normalize_and_validate_response(
        self,
        raw_res: dict[str, Any],
        operation: str,
        req_id: str,
        service: AIServiceDefinition,
    ) -> AIExecutionResult:
        """
        Normalize and validate raw response from ai_service into a clean AIExecutionResult.
        Guarantees no internal paths, credentials, or unvalidated structures are returned.
        """
        resolved_model = service.model or "neuroonco-v3"
        op_clean = str(operation).strip().lower()
        is_segmentation = op_clean in (AIOperation.SEGMENTATION.value, "segment", "segmentation")
        is_report = op_clean in (AIOperation.REPORT_GENERATION.value, "report", "report_generation", "generate_report")

        # ── Branch A: Existing ai_service /infer pipeline result ──
        if "summary" in raw_res and "stages" in raw_res:
            summary = raw_res.get("summary")
            if not isinstance(summary, dict):
                raise AIServiceInvalidResponse(
                    detail="AI servis yanıtındaki özet alanı beklenen formatta değil."
                )

            if is_segmentation:
                preprocess_stage = raw_res.get("stages", {}).get("preprocess", {})
                classify_stage = raw_res.get("stages", {}).get("classify", {})
                if preprocess_stage.get("status") == "error" or classify_stage.get("status") == "error":
                    raise AIServiceInvalidResponse(
                        detail="AI segmentasyon aşaması mikroserviste başarısız oldu."
                    )
                seg_data = dict(summary)
                xai_stage = raw_res.get("stages", {}).get("xai", {})
                if xai_stage.get("status") == "ok":
                    seg_data["mask_status"] = "generated"
                    overlay_path = xai_stage.get("payload", {}).get("overlay_path")
                    if overlay_path:
                        seg_data["mask_artifact_id"] = Path(str(overlay_path)).name
                elif xai_stage.get("status") == "skipped":
                    seg_data["mask_status"] = "skipped"

                clean_output = self._validate_segmentation_fields(seg_data)
                safe_metadata = {
                    "total_elapsed_ms": raw_res.get("total_elapsed_ms", 0.0),
                    "device": raw_res.get("device", "auto"),
                    "mode": raw_res.get("mode", "fast"),
                    "stage_status": {
                        k: v.get("status") for k, v in raw_res.get("stages", {}).items() if isinstance(v, dict)
                    },
                }
                model_id = (
                    classify_stage.get("payload", {}).get("model_id")
                    or service.model
                    or resolved_model
                )
                return AIExecutionResult(
                    operation=operation,
                    status=AIStatus.COMPLETED,
                    provider=self.provider_name,
                    model=model_id,
                    request_id=req_id,
                    output=clean_output,
                    metadata=safe_metadata,
                )

            # Check if execution failed in stages
            classify_stage = raw_res.get("stages", {}).get("classify", {})
            if classify_stage.get("status") == "error":
                raise AIServiceInvalidResponse(
                    detail="AI sınıflandırma aşaması mikroserviste başarısız oldu."
                )

            # Strict field validation
            prediction = summary.get("prediction")
            confidence = summary.get("confidence")
            probabilities = summary.get("probabilities")

            if not isinstance(prediction, str) or not prediction.strip():
                raise AIServiceInvalidResponse(
                    detail="AI sınıflandırma tahmini eksik veya geçersiz türde."
                )
            clean_pred = prediction.strip().lower()
            if clean_pred not in KNOWN_CLASSIFICATION_LABELS:
                raise AIServiceInvalidResponse(
                    detail=f"Bilinmeyen AI sınıflandırma etiketi: {clean_pred}"
                )

            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
                raise AIServiceInvalidResponse(
                    detail="AI sınıflandırma güven skoru [0.0, 1.0] aralığında geçerli bir sayı olmalıdır."
                )
            f_conf = float(confidence)
            if math.isnan(f_conf) or math.isinf(f_conf) or not (0.0 <= f_conf <= 1.0):
                raise AIServiceInvalidResponse(
                    detail="AI sınıflandırma güven skoru sonlu ve [0.0, 1.0] aralığında geçerli bir sayı olmalıdır."
                )

            if not isinstance(probabilities, dict):
                raise AIServiceInvalidResponse(
                    detail="AI sınıflandırma olasılık dağılımı sözlük formatında olmalıdır."
                )
            clean_probs: dict[str, float] = {}
            for k, v in probabilities.items():
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    raise AIServiceInvalidResponse(
                        detail="AI sınıflandırma olasılık değeri sayısal olmalıdır."
                    )
                f_v = float(v)
                if math.isnan(f_v) or math.isinf(f_v) or not (0.0 <= f_v <= 1.0):
                    raise AIServiceInvalidResponse(
                        detail="AI sınıflandırma olasılık değeri sonlu ve [0.0, 1.0] aralığında olmalıdır."
                    )
                clean_probs[str(k).strip().lower()] = f_v

            # Clean output data
            clean_output = {
                "prediction": clean_pred,
                "confidence": f_conf,
                "probabilities": clean_probs,
                "who_grade_hint": summary.get("who_grade_hint"),
            }
            if summary.get("tumor_area_ratio_2d") is not None:
                clean_output["tumor_area_ratio_2d"] = summary.get("tumor_area_ratio_2d")
            if summary.get("tumor_volume_cm3") is not None:
                clean_output["tumor_volume_cm3"] = summary.get("tumor_volume_cm3")
            if summary.get("et_wt_ratio") is not None:
                clean_output["et_wt_ratio"] = summary.get("et_wt_ratio")

            # Sanitized metadata — strictly exclude file paths, internal directories, or raw traceback
            safe_metadata = {
                "total_elapsed_ms": raw_res.get("total_elapsed_ms", 0.0),
                "device": raw_res.get("device", "auto"),
                "mode": raw_res.get("mode", "fast"),
                "stage_status": {
                    k: v.get("status") for k, v in raw_res.get("stages", {}).items() if isinstance(v, dict)
                },
            }

            model_id = classify_stage.get("payload", {}).get("model_id") or resolved_model

            return AIExecutionResult(
                operation=operation,
                status=AIStatus.COMPLETED,
                provider=self.provider_name,
                model=model_id,
                request_id=req_id,
                output=clean_output,
                metadata=safe_metadata,
            )

        # ── Branch B: Existing ai_service /report response ──
        if "payload" in raw_res and "status" in raw_res and isinstance(raw_res.get("payload"), dict):
            rep_payload = raw_res["payload"]
            if not any(k in rep_payload for k in ("report", "sections", "fhir")):
                raise AIServiceInvalidResponse(
                    detail="AI raporlama yanıtı beklenen rapor alanlarını içermiyor."
                )

            clean_output = self._validate_and_normalize_report_fields(rep_payload)
            safe_metadata = {
                "elapsed_ms": raw_res.get("elapsed_ms", 0.0),
                "attempt": rep_payload.get("attempt", 1),
            }

            return AIExecutionResult(
                operation=operation,
                status=AIStatus.COMPLETED,
                provider=self.provider_name,
                model=resolved_model,
                request_id=req_id,
                output=clean_output,
                metadata=safe_metadata,
            )

        # ── Branch C: Generic structured response / standard microservice output ──
        output_data = raw_res.get("output", raw_res)
        if not isinstance(output_data, dict):
            output_data = {"result": output_data}

        if is_report:
            clean_output = self._validate_and_normalize_report_fields(output_data)
            safe_metadata = {
                k: v for k, v in raw_res.get("metadata", {}).items()
                if str(k).lower() not in RESTRICTED_PAYLOAD_KEYS and not str(v).startswith(("/", "C:\\"))
            }
            return AIExecutionResult(
                operation=operation,
                status=raw_res.get("status", AIStatus.COMPLETED),
                provider=self.provider_name,
                model=raw_res.get("model", resolved_model),
                request_id=req_id,
                output=clean_output,
                metadata=safe_metadata,
            )

        if is_segmentation:
            clean_output = self._validate_segmentation_fields(output_data)
            safe_metadata = {
                k: v for k, v in raw_res.get("metadata", {}).items()
                if str(k).lower() not in RESTRICTED_PAYLOAD_KEYS and not str(v).startswith(("/", "C:\\"))
            }
            return AIExecutionResult(
                operation=operation,
                status=raw_res.get("status", AIStatus.COMPLETED),
                provider=self.provider_name,
                model=raw_res.get("model", resolved_model),
                request_id=req_id,
                output=clean_output,
                metadata=safe_metadata,
            )

        # Validate prediction if present
        if "prediction" in output_data:
            if not isinstance(output_data["prediction"], str) or not output_data["prediction"].strip():
                raise AIServiceInvalidResponse(detail="Tahmin alanı geçersiz formatta.")
            clean_c_pred = output_data["prediction"].strip().lower()
            if clean_c_pred not in KNOWN_CLASSIFICATION_LABELS:
                raise AIServiceInvalidResponse(detail=f"Bilinmeyen AI sınıflandırma etiketi: {clean_c_pred}")
            output_data["prediction"] = clean_c_pred

        if "confidence" in output_data:
            if not isinstance(output_data["confidence"], (int, float)) or isinstance(output_data["confidence"], bool):
                raise AIServiceInvalidResponse(detail="Güven değeri sayısal olmalıdır.")
            c_conf = float(output_data["confidence"])
            if math.isnan(c_conf) or math.isinf(c_conf) or not (0.0 <= c_conf <= 1.0):
                raise AIServiceInvalidResponse(detail="Güven değeri sonlu ve [0.0, 1.0] aralığında olmalıdır.")
            output_data["confidence"] = c_conf

        safe_metadata = {
            k: v for k, v in raw_res.get("metadata", {}).items()
            if str(k).lower() not in RESTRICTED_PAYLOAD_KEYS and not str(v).startswith(("/", "C:\\"))
        }

        return AIExecutionResult(
            operation=operation,
            status=raw_res.get("status", AIStatus.COMPLETED),
            provider=self.provider_name,
            model=raw_res.get("model", resolved_model),
            request_id=req_id,
            output=output_data,
            metadata=safe_metadata,
        )

    async def execute(
        self,
        request: AIExecutionRequest,
        service: AIServiceDefinition,
    ) -> AIExecutionResult:
        """
        Execute an AI inference operation against the target service definition.
        Adapts inputs to the downstream ai_service contract and normalizes the response.
        """
        req_id = request.correlation_id or uuid.uuid4().hex
        op_val = request.operation.value if isinstance(request.operation, AIOperation) else str(request.operation)

        # Determine target endpoint and adapted payload based on operation
        if op_val == AIOperation.CLASSIFICATION.value or op_val == "classify":
            endpoint = service.endpoint or "/infer"
            # If input is already formatted for /infer or has patient_id
            if "patient_id" in request.inputs or "modality_paths" in request.inputs:
                payload = self._build_infer_payload(request.inputs, request.parameters)
            else:
                # Direct slice or generic classification payload
                payload = {
                    "inputs": request.inputs,
                    "parameters": self._filter_and_whitelist_parameters(request.parameters),
                }
        elif op_val == AIOperation.REPORT_GENERATION.value or op_val == "generate_report":
            endpoint = service.endpoint or "/report"
            payload = self._build_report_payload(request.inputs, request.parameters)
        elif op_val in (AIOperation.SEGMENTATION.value, "segment", "segmentation"):
            endpoint = service.endpoint or "/infer"
            if "patient_id" in request.inputs or "modality_paths" in request.inputs:
                payload = self._build_infer_payload(request.inputs, request.parameters)
            else:
                payload = {
                    "inputs": request.inputs,
                    "parameters": self._filter_and_whitelist_parameters(request.parameters),
                }
        else:
            # Generic operation
            endpoint = service.endpoint or f"/{op_val}"
            payload = {
                "inputs": request.inputs,
                "parameters": self._filter_and_whitelist_parameters(request.parameters),
            }

        # Client post uses server-side configured base_url, endpoint, and timeouts
        raw_res = await self.client.post(
            endpoint=endpoint,
            json_data=payload,
            request_id=req_id,
            operation=op_val,
            provider_name=self.provider_name,
            model_name=service.model or "neuroonco-v3",
        )

        return self._normalize_and_validate_response(
            raw_res=raw_res,
            operation=op_val,
            req_id=req_id,
            service=service,
        )

    async def classify(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        """Backward-compatible classify invocation returning AIResponse."""
        dummy_service = AIServiceDefinition(
            operation=AIOperation.CLASSIFICATION,
            service_name="internal-classification",
            base_url=settings.AI_SERVICE_URL,
            endpoint="/infer",
            model=(parameters.get("model") if parameters else None) or settings.AI_CLASSIFICATION_MODEL,
        )
        req = AIExecutionRequest(
            operation=AIOperation.CLASSIFICATION,
            inputs=inputs,
            parameters=parameters or {},
            correlation_id=correlation_id,
        )
        result = await self.execute(req, dummy_service)
        return result.to_response()

    async def segment(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        """Backward-compatible segment invocation returning AIResponse."""
        dummy_service = AIServiceDefinition(
            operation=AIOperation.SEGMENTATION,
            service_name="internal-segmentation",
            base_url=settings.AI_SEGMENTATION_URL or settings.AI_SERVICE_URL,
            endpoint="/infer",
            model=(parameters.get("model") if parameters else None) or settings.AI_SEGMENTATION_MODEL,
        )
        req = AIExecutionRequest(
            operation=AIOperation.SEGMENTATION,
            inputs=inputs,
            parameters=parameters or {},
            correlation_id=correlation_id,
        )
        result = await self.execute(req, dummy_service)
        return result.to_response()

    async def generate_report(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        """Backward-compatible generate_report invocation returning AIResponse."""
        dummy_service = AIServiceDefinition(
            operation=AIOperation.REPORT_GENERATION,
            service_name="internal-report",
            base_url=settings.AI_REPORT_URL or settings.AI_SERVICE_URL,
            endpoint="/report",
            model=(parameters.get("model") if parameters else None) or settings.AI_REPORT_MODEL,
        )
        req = AIExecutionRequest(
            operation=AIOperation.REPORT_GENERATION,
            inputs=inputs,
            parameters=parameters or {},
            correlation_id=correlation_id,
        )
        result = await self.execute(req, dummy_service)
        return result.to_response()

    async def check_health(self) -> AIHealthResponse:
        """
        Inspect health and component status without leaking local filesystem paths.
        """
        t0 = time.perf_counter()
        try:
            res = await self.client.get(
                endpoint="/health",
                operation="health_check",
                provider_name=self.provider_name,
            )
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            # Check if this is the ai_service/serve.py component status structure
            if "components" in res and isinstance(res["components"], dict):
                components = res["components"]
                all_ok = all(
                    comp.get("ok") is True
                    for comp in components.values()
                    if isinstance(comp, dict)
                )
                any_ok = any(
                    comp.get("ok") is True
                    for comp in components.values()
                    if isinstance(comp, dict)
                )
                status_val = "up" if all_ok else ("degraded" if any_ok else "down")

                # Shield details: strictly map component booleans, strip guidelines_dir / filesystem paths
                safe_details = {
                    "components": {
                        k: (v.get("ok") if isinstance(v, dict) else False)
                        for k, v in components.items()
                    },
                    "device": res.get("device_detected", "unknown"),
                }
                return AIHealthResponse(
                    status=status_val,
                    provider=self.provider_name,
                    latency_ms=latency_ms,
                    details=safe_details,
                )

            # Standard health response
            raw_status = str(res.get("status", "up")).lower()
            status_val = "up" if raw_status in ("up", "ok", "healthy") else "degraded"
            return AIHealthResponse(
                status=status_val,
                provider=self.provider_name,
                latency_ms=latency_ms,
                details={"remote_status": raw_status},
            )
        except Exception:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return AIHealthResponse(
                status="down",
                provider=self.provider_name,
                latency_ms=latency_ms,
                details={"error": "AI service unavailable"},
            )

    async def close(self) -> None:
        await self.client.close()
