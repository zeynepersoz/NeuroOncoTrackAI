"""
NeuroOncoTrack-AI — AI Contracts & Schemas

Pydantic v2 schemas for AI service integration.
Enforces strict DTO input/output validation (extra="forbid") to ensure
unvalidated raw dicts are never propagated through the system.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AIStatus(str, Enum):
    """Execution status of an AI inference or pipeline task."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AITaskType(str, Enum):
    """High-level AI task classifications."""
    CLASSIFICATION_2D = "classification_2d"
    SEGMENTATION_3D = "segmentation_3d"
    REPORT = "report"
    GENERIC = "generic"


class AIOperation(str, Enum):
    """Canonical AI operations supported by the platform."""
    CLASSIFICATION = "classification"
    SEGMENTATION = "segmentation"
    REPORT_GENERATION = "report_generation"


class AITimeoutProfile(BaseModel):
    """Timeout configuration profile for a specific AI service operation."""
    connect_timeout: float = Field(default=10.0, ge=0.1, description="TCP/SSL connect timeout in seconds")
    read_timeout: float = Field(default=60.0, ge=0.1, description="HTTP read/streaming timeout in seconds")
    write_timeout: float = Field(default=30.0, ge=0.1, description="HTTP write timeout in seconds")
    pool_timeout: float = Field(default=10.0, ge=0.1, description="Connection pool acquisition timeout in seconds")
    total_timeout: float = Field(default=120.0, ge=0.1, description="Maximum total request timeout in seconds")

    model_config = ConfigDict(extra="forbid")


class AIRetryProfile(BaseModel):
    """Retry policy configuration for an AI service operation."""
    max_retries: int = Field(default=3, ge=0, le=10, description="Max retry attempts for retryable transient errors")
    backoff_factor: float = Field(default=0.5, ge=0.0, le=60.0, description="Exponential backoff factor in seconds")
    retry_on_timeout: bool = Field(default=False, description="Whether to retry on read timeout (avoids retry storms when False)")

    model_config = ConfigDict(extra="forbid")


class AIServiceDefinition(BaseModel):
    """
    Central specification of an AI service registered for an operation.
    
    Encapsulates endpoint resolution, provider binding, model name,
    activation state, timeout, and retry profiles.
    """
    operation: AIOperation | str = Field(..., description="Target AI operation")
    service_name: str = Field(..., min_length=1, description="Human-readable unique service name")
    base_url: str | None = Field(None, description="Base URL of target service (required in production)")
    endpoint: str = Field(default="/", description="Relative path endpoint on the service")
    provider_type: str = Field(default="internal_service", description="Provider identifier (e.g. internal_service, mock_provider)")
    model: str | None = Field(None, description="Default model identifier/version")
    enabled: bool = Field(default=True, description="Whether this AI operation is active and callable")
    timeout_profile: AITimeoutProfile = Field(default_factory=AITimeoutProfile, description="Timeout configuration")
    retry_profile: AIRetryProfile = Field(default_factory=AIRetryProfile, description="Retry configuration")
    api_key: str | None = Field(default=None, description="Optional scoped API key / Bearer token")

    model_config = ConfigDict(extra="forbid")

    def __repr__(self) -> str:
        # Never leak api_key or credentials in string representations
        return (
            f"AIServiceDefinition(operation={self.operation!r}, "
            f"service_name={self.service_name!r}, base_url={self.base_url!r}, "
            f"endpoint={self.endpoint!r}, enabled={self.enabled!r}, "
            f"model={self.model!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


class AIHealthResponse(BaseModel):
    """Standardized health and connectivity status of an AI service provider."""
    status: str = Field(..., description="'up', 'down', or 'degraded'")
    provider: str = Field(..., description="Provider name or identifier")
    latency_ms: float = Field(..., ge=0.0, description="Ping roundtrip latency in milliseconds")
    details: dict[str, Any] = Field(default_factory=dict, description="Diagnostic connectivity details")

    model_config = ConfigDict(extra="forbid")


class AIResponse(BaseModel):
    """
    Standardized response contract for all AI model inference operations.
    
    Guarantees consistent structure regardless of the underlying concrete
    AI provider (Internal FastAPI, GPU cluster, external LLM, etc.).
    """
    provider: str = Field(..., min_length=1, description="AI provider identifier")
    model: str = Field(..., min_length=1, description="Model identifier and version")
    request_id: str = Field(..., min_length=1, description="Correlation / Request ID for tracing")
    status: AIStatus | str = Field(default=AIStatus.COMPLETED, description="Task execution status")
    output: dict[str, Any] = Field(..., description="Structured model inference results")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Auxiliary execution metadata")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Response generation UTC timestamp",
    )

    model_config = ConfigDict(extra="forbid")


class AIRequestPayload(BaseModel):
    """Generic structured request payload dispatched to AI providers."""
    task_type: AITaskType | str = Field(..., description="Target AI operation task type")
    inputs: dict[str, Any] = Field(..., description="Input parameters and feature maps")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Inference parameters (e.g. mode, device)")
    correlation_id: str | None = Field(None, description="Optional correlation / request tracing ID")

    model_config = ConfigDict(extra="forbid")


class AIExecutionRequest(BaseModel):
    """
    Contract representing an AI inference execution request.
    
    Contains operation, input payload, execution parameters, and correlation tracing.
    Infrastructure and routing parameters (provider, base_url, endpoint, api_key, model)
    are strictly managed by the server-side registry.
    """
    operation: AIOperation | str = Field(..., description="Target AI operation")
    inputs: dict[str, Any] = Field(..., description="Payload / feature maps / patient data")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Inference parameters (e.g. mode, device)")
    correlation_id: str | None = Field(None, description="Optional correlation / request tracing ID")

    model_config = ConfigDict(extra="forbid")


class AIExecutionResult(BaseModel):
    """
    Standardized, safe result returned by AI execution core.
    
    Internal service-level result holding normalized inference results and metadata.
    Guarantees no internal secrets, credentials, or internal endpoints are exposed.
    """
    operation: str = Field(..., min_length=1, description="Executed AI operation")
    status: AIStatus | str = Field(default=AIStatus.COMPLETED, description="Execution status")
    provider: str = Field(..., min_length=1, description="AI provider identifier")
    model: str = Field(..., min_length=1, description="Model identifier and version")
    request_id: str = Field(..., min_length=1, description="Correlation / Request ID")
    output: dict[str, Any] = Field(..., description="Structured, validated inference results")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Safe auxiliary execution metadata")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Response generation UTC timestamp",
    )
    error: str | None = Field(default=None, description="Provider-independent safe error description")

    model_config = ConfigDict(extra="forbid")

    def to_response(self) -> AIResponse:
        """Convert internal execution result to standard AIResponse."""
        return AIResponse(
            provider=self.provider,
            model=self.model,
            request_id=self.request_id,
            status=self.status,
            output=self.output,
            metadata=self.metadata,
            created_at=self.created_at,
        )

    def to_public_dict(self) -> dict[str, Any]:
        """
        Produce a safe dictionary suitable for public/client responses.
        Shields internal provider, internal URLs, and internal metadata.
        """
        return {
            "status": self.status.value if isinstance(self.status, AIStatus) else str(self.status),
            "operation": self.operation,
            "request_id": self.request_id,
            "output": self.output,
            "created_at": self.created_at.isoformat(),
        }


# Authoritative classification label set defined by existing model architecture
KNOWN_CLASSIFICATION_LABELS = frozenset({"glioma", "meningioma", "notumor", "pituitary"})


class ClassificationInput(BaseModel):
    """
    Strict input schema for AI classification operation (TASK-048).
    
    Guarantees:
    - Non-empty, sanitized patient identifier
    - Valid modality paths map requiring at least t1c
    - No path traversal or null bytes in input paths
    - Controlled inference mode, device, and predictor parameters
    - Extra fields strictly forbidden to prevent parameter tampering
    """
    patient_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Sanitized patient or case identifier",
        examples=["BRATS-GLI-00123-000"],
    )
    modality_paths: dict[str, str] = Field(
        ...,
        description="Modality path mapping (e.g. {'t1c': 'path/to/t1c.nii.gz'}). At least t1c is required.",
    )
    mode: str = Field(
        default="fast",
        description="Inference execution mode: 'full', 'fast', or 'classify_only'",
    )
    device: str = Field(
        default="auto",
        description="Target compute device: 'auto', 'cuda', 'mps', or 'cpu'",
    )
    predictor: str = Field(
        default="v3",
        description="Authoritative model predictor: 'v3' or 'v2'",
    )
    extra_features: dict[str, float] | None = Field(
        default=None,
        description="Optional numeric clinical/segmentation metrics (e.g. tumor_volume_cm3)",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("patient_id cannot be empty or whitespace only")
        if "\0" in cleaned:
            raise ValueError("patient_id contains invalid null bytes")
        if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
            raise ValueError("patient_id contains illegal path traversal characters")
        if not re.match(r"^[A-Za-z0-9_\-]+$", cleaned):
            raise ValueError("patient_id contains invalid characters (allowed: alphanumeric, hyphen, underscore)")
        return cleaned

    @field_validator("modality_paths")
    @classmethod
    def validate_modality_paths(cls, paths: dict[str, str]) -> dict[str, str]:
        if not paths:
            raise ValueError("modality_paths cannot be empty")
        
        normalized: dict[str, str] = {}
        allowed_modalities = {"t1", "t1c", "t2", "flair"}

        for mod, path_str in paths.items():
            mod_clean = str(mod).strip().lower()
            if mod_clean not in allowed_modalities:
                raise ValueError(f"Unknown modality '{mod}'. Allowed: {sorted(allowed_modalities)}")
            if not isinstance(path_str, str):
                raise ValueError(f"Path for modality '{mod}' must be a string")
            val_clean = path_str.strip()
            if not val_clean:
                raise ValueError(f"Path for modality '{mod}' cannot be empty")
            if "\0" in val_clean:
                raise ValueError(f"Path for modality '{mod}' contains null bytes")
            if ".." in val_clean:
                raise ValueError(f"Path for modality '{mod}' contains directory traversal ('..')")
            normalized[mod_clean] = val_clean

        if "t1c" not in normalized:
            raise ValueError("At least 't1c' modality path is required for classification")

        return normalized

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in {"full", "fast", "classify_only"}:
            raise ValueError("mode must be one of: 'full', 'fast', 'classify_only'")
        return clean

    @field_validator("device")
    @classmethod
    def validate_device(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in {"auto", "cuda", "mps", "cpu"}:
            raise ValueError("device must be one of: 'auto', 'cuda', 'mps', 'cpu'")
        return clean

    @field_validator("predictor")
    @classmethod
    def validate_predictor(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in {"v3", "v2"}:
            raise ValueError("predictor must be one of: 'v3', 'v2'")
        return clean

    @field_validator("extra_features")
    @classmethod
    def validate_extra_features(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is None:
            return None
        cleaned: dict[str, float] = {}
        for k, val in v.items():
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ValueError(f"extra_feature '{k}' must be a numeric float/int")
            f_val = float(val)
            if math.isnan(f_val) or math.isinf(f_val):
                raise ValueError(f"extra_feature '{k}' cannot be NaN or Infinity")
            cleaned[str(k).strip()] = f_val
        return cleaned


class ClassificationOutput(BaseModel):
    """
    Strict, normalized output schema for classification operation (TASK-048).
    
    Guarantees:
    - Valid, authoritative tumor prediction class
    - Strictly finite confidence score normalized within [0.0, 1.0]
    - Normalized probabilities map for all classes
    - Request correlation tracing
    - Shields all internal provider URLs, file paths, and raw debug dumps
    """
    prediction: str = Field(..., description="Authoritative predicted tumor class")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score in [0.0, 1.0]")
    probabilities: dict[str, float] = Field(..., description="Class probability distribution")
    who_grade_hint: str | None = Field(None, description="Clinical WHO grade advisory information")
    tumor_area_ratio_2d: float | None = Field(None, description="Estimated 2D slice tumor area ratio")
    tumor_volume_cm3: float | None = Field(None, description="3D tumor volume in cm3 if available")
    et_wt_ratio: float | None = Field(None, description="Enhancing to whole tumor ratio if available")
    request_id: str = Field(..., min_length=1, description="Correlation / Request tracing ID")
    model: str = Field(..., min_length=1, description="Model identifier used for inference")
    status: str = Field(default="COMPLETED", description="Execution status")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Inference completion timestamp",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("confidence must be a numeric value")
        val = float(v)
        if math.isnan(val):
            raise ValueError("confidence cannot be NaN")
        if math.isinf(val):
            raise ValueError("confidence cannot be Infinity")
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"confidence must be in range [0.0, 1.0], got {val}")
        return val

    @field_validator("prediction")
    @classmethod
    def validate_prediction(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean:
            raise ValueError("prediction label cannot be empty")
        if clean not in KNOWN_CLASSIFICATION_LABELS:
            raise ValueError(
                f"Unknown classification label '{clean}'. Expected one of: {sorted(KNOWN_CLASSIFICATION_LABELS)}"
            )
        return clean

    @field_validator("probabilities")
    @classmethod
    def validate_probabilities(cls, v: dict[str, float]) -> dict[str, float]:
        if not isinstance(v, dict):
            raise ValueError("probabilities must be a dictionary")
        validated: dict[str, float] = {}
        for k, prob in v.items():
            if not isinstance(prob, (int, float)) or isinstance(prob, bool):
                raise ValueError(f"probability for '{k}' must be numeric")
            f_prob = float(prob)
            if math.isnan(f_prob) or math.isinf(f_prob):
                raise ValueError(f"probability for '{k}' cannot be NaN or Infinity")
            if not (0.0 <= f_prob <= 1.0):
                raise ValueError(f"probability for '{k}' must be within [0.0, 1.0]")
            validated[str(k).strip().lower()] = f_prob
        return validated


class SegmentationInput(BaseModel):
    """
    Strict input schema for AI segmentation operation (TASK-049).
    
    Guarantees:
    - Non-empty, sanitized patient identifier (alphanumeric, hyphen, underscore; no traversal or null bytes)
    - Valid modality paths map requiring at least t1c
    - No path traversal or null bytes in input paths
    - Controlled inference mode, device, and predictor parameters
    - Extra fields strictly forbidden to prevent parameter tampering
    """
    patient_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Sanitized patient or case identifier",
        examples=["BRATS-GLI-00123-000"],
    )
    modality_paths: dict[str, str] = Field(
        ...,
        description="Modality path mapping (e.g. {'t1c': 'scans/t1c.nii.gz'}). At least t1c is required.",
    )
    mode: str = Field(
        default="fast",
        description="Inference execution mode: 'full', 'fast', or 'classify_only'",
    )
    device: str = Field(
        default="auto",
        description="Target compute device: 'auto', 'cuda', 'mps', or 'cpu'",
    )
    predictor: str = Field(
        default="v3",
        description="Authoritative model predictor: 'v3' or 'v2'",
    )
    extra_features: dict[str, float] | None = Field(
        default=None,
        description="Optional numeric clinical/segmentation metrics (e.g. tumor_volume_cm3)",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("patient_id cannot be empty or whitespace only")
        if "\0" in cleaned:
            raise ValueError("patient_id contains invalid null bytes")
        if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
            raise ValueError("patient_id contains illegal path traversal characters")
        if not re.match(r"^[A-Za-z0-9_\-]+$", cleaned):
            raise ValueError("patient_id contains invalid characters (allowed: alphanumeric, hyphen, underscore)")
        return cleaned

    @field_validator("modality_paths")
    @classmethod
    def validate_modality_paths(cls, paths: dict[str, str]) -> dict[str, str]:
        if not paths:
            raise ValueError("modality_paths cannot be empty")
        
        normalized: dict[str, str] = {}
        allowed_modalities = {"t1", "t1c", "t2", "flair"}

        for mod, path_str in paths.items():
            mod_clean = str(mod).strip().lower()
            if mod_clean not in allowed_modalities:
                raise ValueError(f"Unknown modality '{mod}'. Allowed: {sorted(allowed_modalities)}")
            if not isinstance(path_str, str):
                raise ValueError(f"Path for modality '{mod}' must be a string")
            val_clean = path_str.strip()
            if not val_clean:
                raise ValueError(f"Path for modality '{mod}' cannot be empty")
            if "\0" in val_clean:
                raise ValueError(f"Path for modality '{mod}' contains null bytes")
            if ".." in val_clean:
                raise ValueError(f"Path for modality '{mod}' contains directory traversal ('..')")
            normalized[mod_clean] = val_clean

        if "t1c" not in normalized:
            raise ValueError("At least 't1c' modality path is required for segmentation")

        return normalized

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in {"full", "fast", "classify_only"}:
            raise ValueError("mode must be one of: 'full', 'fast', 'classify_only'")
        return clean

    @field_validator("device")
    @classmethod
    def validate_device(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in {"auto", "cuda", "mps", "cpu"}:
            raise ValueError("device must be one of: 'auto', 'cuda', 'mps', 'cpu'")
        return clean

    @field_validator("predictor")
    @classmethod
    def validate_predictor(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in {"v3", "v2"}:
            raise ValueError("predictor must be one of: 'v3', 'v2'")
        return clean

    @field_validator("extra_features")
    @classmethod
    def validate_extra_features(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is None:
            return None
        cleaned: dict[str, float] = {}
        for k, val in v.items():
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ValueError(f"extra_feature '{k}' must be a numeric float/int")
            f_val = float(val)
            if math.isnan(f_val) or math.isinf(f_val):
                raise ValueError(f"extra_feature '{k}' cannot be NaN or Infinity")
            cleaned[str(k).strip()] = f_val
        return cleaned


class SegmentationOutput(BaseModel):
    """
    Strict, normalized output schema for segmentation operation (TASK-049).
    
    Guarantees:
    - Safe execution status and mask metadata
    - Shields internal server filesystem paths (only safe relative artifact IDs allowed)
    - Validated numerical values (finite, non-NaN, non-Inf, bounded domain values)
    - Request correlation tracing
    - Shields all internal provider URLs, credentials, and debug dumps
    """
    status: str = Field(default="COMPLETED", description="Execution status")
    mask_status: str | None = Field(default=None, description="Status of mask generation")
    mask_artifact_id: str | None = Field(default=None, description="Safe relative artifact identifier or filename")
    tumor_area_ratio_2d: float | None = Field(default=None, description="Estimated 2D slice tumor area ratio in [0.0, 1.0]")
    tumor_volume_cm3: float | None = Field(default=None, description="Tumor volume in cm3")
    et_wt_ratio: float | None = Field(default=None, description="Enhancing to whole tumor volume ratio in [0.0, 1.0]")
    volumes_cm3: dict[str, float] | None = Field(default=None, description="Sub-region volumetric breakdown")
    slices_count: int | None = Field(default=None, description="Total slices analyzed")
    num_tumor_slices: int | None = Field(default=None, description="Number of tumor-bearing slices")
    best_slice: int | None = Field(default=None, description="Representative/maximum tumor slice index")
    request_id: str = Field(..., min_length=1, description="Correlation / Request tracing ID")
    model: str = Field(..., min_length=1, description="Model identifier used for segmentation")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Segmentation completion UTC timestamp",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("mask_artifact_id")
    @classmethod
    def validate_mask_artifact_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        if "\0" in clean or ".." in clean:
            raise ValueError("mask_artifact_id contains illegal path traversal or null bytes")
        # Ensure no absolute paths (e.g. C:\ or /var) leak through
        if clean.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", clean):
            raise ValueError("mask_artifact_id must not be an absolute filesystem path")
        return clean

    @field_validator("tumor_area_ratio_2d")
    @classmethod
    def validate_tumor_area_ratio_2d(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("tumor_area_ratio_2d must be numeric")
        val = float(v)
        if math.isnan(val) or math.isinf(val):
            raise ValueError("tumor_area_ratio_2d cannot be NaN or Infinity")
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"tumor_area_ratio_2d must be in range [0.0, 1.0], got {val}")
        return val

    @field_validator("tumor_volume_cm3")
    @classmethod
    def validate_tumor_volume_cm3(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("tumor_volume_cm3 must be numeric")
        val = float(v)
        if math.isnan(val) or math.isinf(val):
            raise ValueError("tumor_volume_cm3 cannot be NaN or Infinity")
        if val < 0.0:
            raise ValueError(f"tumor_volume_cm3 cannot be negative, got {val}")
        return val

    @field_validator("et_wt_ratio")
    @classmethod
    def validate_et_wt_ratio(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("et_wt_ratio must be numeric")
        val = float(v)
        if math.isnan(val) or math.isinf(val):
            raise ValueError("et_wt_ratio cannot be NaN or Infinity")
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"et_wt_ratio must be in range [0.0, 1.0], got {val}")
        return val

    @field_validator("volumes_cm3")
    @classmethod
    def validate_volumes_cm3(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("volumes_cm3 must be a dictionary")
        validated: dict[str, float] = {}
        for k, vol in v.items():
            if not isinstance(vol, (int, float)) or isinstance(vol, bool):
                raise ValueError(f"volume for '{k}' must be numeric")
            f_vol = float(vol)
            if math.isnan(f_vol) or math.isinf(f_vol):
                raise ValueError(f"volume for '{k}' cannot be NaN or Infinity")
            if f_vol < 0.0:
                raise ValueError(f"volume for '{k}' cannot be negative, got {f_vol}")
            validated[str(k).strip()] = f_vol
        return validated

    @field_validator("slices_count", "num_tumor_slices", "best_slice")
    @classmethod
    def validate_slice_counts(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("Slice count values must be integers")
        if v < 0:
            raise ValueError("Slice count values cannot be negative")
        return v


# ─────────────────────────────────────────────────────────────
# REPORT GENERATION SCHEMAS (TASK-050)
# ─────────────────────────────────────────────────────────────

DATA_INSUFFICIENT_STR = "Data insufficient"


class ReportClassificationData(BaseModel):
    """
    Structured classification section for report generation input/output.
    Reuses the authoritative classification output contract without requiring
    server-internal metadata like request_id/model if provided independently.
    """
    prediction: str = Field(..., description="Authoritative predicted tumor class")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score in [0.0, 1.0]")
    probabilities: dict[str, float] = Field(..., description="Class probability distribution")
    who_grade_hint: str | None = Field(default=None, description="Clinical WHO grade advisory information")
    tumor_area_ratio_2d: float | None = Field(default=None, description="Estimated 2D slice tumor area ratio")
    tumor_volume_cm3: float | None = Field(default=None, description="3D tumor volume in cm3 if available")
    et_wt_ratio: float | None = Field(default=None, description="Enhancing to whole tumor ratio if available")
    request_id: str | None = Field(default=None, description="Optional source request ID")
    model: str | None = Field(default=None, description="Optional model identifier")
    status: str | None = Field(default="COMPLETED", description="Execution status")
    created_at: datetime | None = Field(default=None, description="Inference timestamp")

    model_config = ConfigDict(extra="forbid")

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("confidence must be a numeric value")
        val = float(v)
        if math.isnan(val):
            raise ValueError("confidence cannot be NaN")
        if math.isinf(val):
            raise ValueError("confidence cannot be Infinity")
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"confidence must be in range [0.0, 1.0], got {val}")
        return val

    @field_validator("prediction")
    @classmethod
    def validate_prediction(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean:
            raise ValueError("prediction label cannot be empty")
        if clean not in KNOWN_CLASSIFICATION_LABELS:
            raise ValueError(
                f"Unknown classification label '{clean}'. Expected one of: {sorted(KNOWN_CLASSIFICATION_LABELS)}"
            )
        return clean

    @field_validator("probabilities")
    @classmethod
    def validate_probabilities(cls, v: dict[str, float]) -> dict[str, float]:
        if not isinstance(v, dict):
            raise ValueError("probabilities must be a dictionary")
        validated: dict[str, float] = {}
        for k, prob in v.items():
            if not isinstance(prob, (int, float)) or isinstance(prob, bool):
                raise ValueError(f"probability for '{k}' must be numeric")
            f_prob = float(prob)
            if math.isnan(f_prob) or math.isinf(f_prob):
                raise ValueError(f"probability for '{k}' cannot be NaN or Infinity")
            if not (0.0 <= f_prob <= 1.0):
                raise ValueError(f"probability for '{k}' must be within [0.0, 1.0]")
            validated[str(k).strip().lower()] = f_prob
        return validated

    @field_validator("tumor_volume_cm3")
    @classmethod
    def validate_tumor_volume(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("tumor_volume_cm3 must be numeric")
        f_val = float(v)
        if math.isnan(f_val) or math.isinf(f_val):
            raise ValueError("tumor_volume_cm3 cannot be NaN or Infinity")
        if f_val < 0.0:
            raise ValueError(f"tumor_volume_cm3 cannot be negative, got {f_val}")
        return f_val

    @field_validator("tumor_area_ratio_2d", "et_wt_ratio")
    @classmethod
    def validate_ratios(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("ratio value must be numeric")
        f_val = float(v)
        if math.isnan(f_val) or math.isinf(f_val):
            raise ValueError("ratio value cannot be NaN or Infinity")
        if not (0.0 <= f_val <= 1.0):
            raise ValueError(f"ratio value must be within [0.0, 1.0], got {f_val}")
        return f_val


class ReportSegmentationData(BaseModel):
    """
    Structured segmentation section for report generation input/output.
    Reuses the authoritative segmentation output contract.
    """
    status: str = Field(default="COMPLETED", description="Execution status")
    mask_status: str | None = Field(default=None, description="Status of mask generation")
    mask_artifact_id: str | None = Field(default=None, description="Safe relative artifact identifier or filename")
    tumor_area_ratio_2d: float | None = Field(default=None, description="Estimated 2D slice tumor area ratio in [0.0, 1.0]")
    tumor_volume_cm3: float | None = Field(default=None, description="Tumor volume in cm3")
    et_wt_ratio: float | None = Field(default=None, description="Enhancing to whole tumor volume ratio in [0.0, 1.0]")
    volumes_cm3: dict[str, float] | None = Field(default=None, description="Sub-region volumetric breakdown")
    slices_count: int | None = Field(default=None, description="Total slices analyzed")
    num_tumor_slices: int | None = Field(default=None, description="Number of tumor-bearing slices")
    best_slice: int | None = Field(default=None, description="Representative/maximum tumor slice index")
    request_id: str | None = Field(default=None, description="Optional source request ID")
    model: str | None = Field(default=None, description="Optional model identifier")
    created_at: datetime | None = Field(default=None, description="Inference timestamp")

    model_config = ConfigDict(extra="forbid")

    @field_validator("mask_artifact_id")
    @classmethod
    def validate_mask_artifact_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        if "\0" in clean or ".." in clean:
            raise ValueError("mask_artifact_id contains illegal path traversal or null bytes")
        if clean.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", clean):
            raise ValueError("mask_artifact_id must not be an absolute filesystem path")
        return clean

    @field_validator("tumor_area_ratio_2d")
    @classmethod
    def validate_tumor_area_ratio_2d(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("tumor_area_ratio_2d must be numeric")
        val = float(v)
        if math.isnan(val) or math.isinf(val):
            raise ValueError("tumor_area_ratio_2d cannot be NaN or Infinity")
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"tumor_area_ratio_2d must be in range [0.0, 1.0], got {val}")
        return val

    @field_validator("tumor_volume_cm3")
    @classmethod
    def validate_tumor_volume_cm3(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("tumor_volume_cm3 must be numeric")
        val = float(v)
        if math.isnan(val) or math.isinf(val):
            raise ValueError("tumor_volume_cm3 cannot be NaN or Infinity")
        if val < 0.0:
            raise ValueError(f"tumor_volume_cm3 cannot be negative, got {val}")
        return val

    @field_validator("et_wt_ratio")
    @classmethod
    def validate_et_wt_ratio(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError("et_wt_ratio must be numeric")
        val = float(v)
        if math.isnan(val) or math.isinf(val):
            raise ValueError("et_wt_ratio cannot be NaN or Infinity")
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"et_wt_ratio must be in range [0.0, 1.0], got {val}")
        return val

    @field_validator("volumes_cm3")
    @classmethod
    def validate_volumes_cm3(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("volumes_cm3 must be a dictionary")
        validated: dict[str, float] = {}
        for k, vol in v.items():
            if not isinstance(vol, (int, float)) or isinstance(vol, bool):
                raise ValueError(f"volume for '{k}' must be numeric")
            f_vol = float(vol)
            if math.isnan(f_vol) or math.isinf(f_vol):
                raise ValueError(f"volume for '{k}' cannot be NaN or Infinity")
            if f_vol < 0.0:
                raise ValueError(f"volume for '{k}' cannot be negative, got {f_vol}")
            validated[str(k).strip()] = f_vol
        return validated

    @field_validator("slices_count", "num_tumor_slices", "best_slice")
    @classmethod
    def validate_slice_counts(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("Slice count values must be integers")
        if v < 0:
            raise ValueError("Slice count values cannot be negative")
        return v


class ReportGenerationInput(BaseModel):
    """
    Strict input schema for structured AI report generation (TASK-050).
    
    Consumes already-produced classification and segmentation results.
    Guarantees:
    - Sanitized patient identifier
    - Preserves data integrity: never converts None or missing data into 0 or plausible medical values
    - Extra fields strictly forbidden (extra="forbid")
    - Parameter tampering prevented (no user-selectable base_url, model, or provider)
    - At least one structured analysis result (classification or segmentation) is required
    """
    patient_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Sanitized patient or case identifier",
        examples=["BRATS-GLI-00123-000"],
    )
    classification: ReportClassificationData | ClassificationOutput | None = Field(
        default=None,
        description="Authoritative classification analysis result",
    )
    segmentation: ReportSegmentationData | SegmentationOutput | None = Field(
        default=None,
        description="Authoritative segmentation analysis result",
    )
    extra_clinical_context: dict[str, Any] | None = Field(
        default=None,
        description="Optional clinical metadata (age, sex, clinical indication)",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("patient_id cannot be empty or whitespace only")
        if "\0" in cleaned:
            raise ValueError("patient_id contains invalid null bytes")
        if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
            raise ValueError("patient_id contains illegal path traversal characters")
        if not re.match(r"^[A-Za-z0-9_\-]+$", cleaned):
            raise ValueError("patient_id contains invalid characters (allowed: alphanumeric, hyphen, underscore)")
        return cleaned

    @field_validator("extra_clinical_context")
    @classmethod
    def validate_extra_clinical_context(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("extra_clinical_context must be a dictionary")
        cleaned: dict[str, Any] = {}
        for key, val in v.items():
            s_key = str(key).strip()
            if not s_key or "\0" in s_key or ".." in s_key:
                raise ValueError("Invalid key in extra_clinical_context")
            # Only primitives allowed
            if not isinstance(val, (str, int, float, bool)):
                raise ValueError(f"Value for '{s_key}' must be primitive (string, number, boolean)")
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                f_val = float(val)
                if math.isnan(f_val) or math.isinf(f_val):
                    raise ValueError(f"Numeric value for '{s_key}' cannot be NaN or Infinity")
            if isinstance(val, str):
                if "\0" in val:
                    raise ValueError(f"String value for '{s_key}' contains null bytes")
                # Basic prompt injection guard: block instruction delimiter sequences
                for forbidden in ("<|im_start|>", "<|im_end|>", "[INST]", "[/INST]", "### System:", "### Instruction:"):
                    if forbidden in val:
                        raise ValueError(f"Illegal instruction injection sequence detected in '{s_key}'")
            cleaned[s_key] = val
        return cleaned

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        if self.classification is None and self.segmentation is None:
            raise ValueError("At least one analysis result (classification or segmentation) must be provided for report generation")


FORBIDDEN_RECOMMENDATION_PHRASES = frozenset({
    "kesin tanı",
    "kesinlikle",
    "teşhis edilmiştir",
    "tanısı konulmuştur",
    "şüphesiz",
    "kuşkusuz",
    "tartışmasız",
    "definitively diagnosed",
    "definitive diagnosis",
    "confirmed diagnosis",
})


class ReportGenerationOutput(BaseModel):
    """
    Strict, normalized output schema for structured AI report generation (TASK-050).
    
    Guarantees:
    - Structured clinical report sections (summary, findings, limitations, recommendations)
    - Distinguishes AI findings from definitive clinical diagnosis (recommendations cannot contain definitive claims)
    - Preserves data integrity and uncertainty without inventing missing values
    - Shields all internal provider URLs, filesystem paths, credentials, and debug tracebacks
    - Correlates with request tracing
    """
    report_id: str = Field(..., min_length=1, description="Unique report identifier")
    request_id: str = Field(..., min_length=1, description="Correlation / Request tracing ID")
    status: str = Field(default="COMPLETED", description="Execution status")
    summary: str = Field(..., min_length=1, description="Structured clinical summary")
    classification: dict[str, Any] | None = Field(default=None, description="Source classification data")
    segmentation: dict[str, Any] | None = Field(default=None, description="Source segmentation data")
    findings: str = Field(..., min_length=1, description="Detailed radiological findings")
    limitations: str = Field(..., min_length=1, description="Safety limitations and medical disclaimers")
    recommendations: str = Field(..., min_length=1, description="Advisory clinical recommendations")
    model: str = Field(..., min_length=1, description="Model identifier used for report generation")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Report generation UTC timestamp",
    )
    fhir: dict[str, Any] | None = Field(default=None, description="Preliminary FHIR DiagnosticReport resource")

    model_config = ConfigDict(extra="forbid")

    @field_validator("recommendations")
    @classmethod
    def validate_recommendations(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("recommendations section cannot be empty")
        v_lower = clean.lower()
        for phrase in FORBIDDEN_RECOMMENDATION_PHRASES:
            if phrase in v_lower:
                raise ValueError(
                    f"recommendations section contains forbidden definitive medical claim phrase: '{phrase}'"
                )
        return clean

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("limitations section cannot be empty")
        v_lower = clean.lower()
        required_elements = ("uzman hekim", "kesin tanı niteliği taşımaz", "yapay zeka", "klinik karar destek")
        if not any(req in v_lower for req in required_elements):
            clean += "\n\nNot: Bu rapor yapay zeka destekli bir sistem tarafından üretilmiştir. Kesin tanı niteliği taşımaz ve uzman hekim değerlendirmesi gerektirir."
        return clean

    @field_validator("summary", "findings")
    @classmethod
    def validate_non_empty_sections(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Report section cannot be empty")
        # Check against path leakage
        if re.search(r"[A-Za-z]:\\[^ \n]+|/home/[^ \n]+|/var/[^ \n]+", clean):
            raise ValueError("Report section contains leaked internal filesystem paths")

# ── Persistence & Retrieval DTOs ───────────────────────────────

class AIAnalysisHistoryItem(BaseModel):
    """Summarized view of an AI analysis for history listings."""
    id: str
    organization_id: str
    patient_id: str
    case_id: str | None = None
    request_id: str
    operation: str
    status: str
    model: str
    prediction: str | None = None
    confidence: float | None = None
    tumor_volume_cm3: float | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AIAnalysisHistoryResponse(BaseModel):
    """Paginated response for AI analysis history queries."""
    items: list[AIAnalysisHistoryItem]
    total: int


class AIAnalysisDetailResponse(BaseModel):
    """Comprehensive detail of a single AI analysis execution."""
    id: str
    organization_id: str
    patient_id: str
    case_id: str | None = None
    request_id: str
    operation: str
    status: str
    model: str
    model_version: str | None = None
    inputs: dict[str, Any] | None = None
    prediction: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    who_grade_hint: str | None = None
    tumor_volume_cm3: float | None = None
    tumor_area_ratio_2d: float | None = None
    et_wt_ratio: float | None = None
    mask_artifact_id: str | None = None
    raw_output: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ClinicalReportHistoryItem(BaseModel):
    """Summarized view of a generated clinical report."""
    id: str
    report_id: str
    patient_id: str
    case_id: str | None = None
    status: str
    summary: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClinicalReportHistoryResponse(BaseModel):
    """Paginated list of clinical reports."""
    items: list[ClinicalReportHistoryItem]
    total: int


class ClinicalReportDetailResponse(BaseModel):
    """Full detail view of an immutable clinical report."""
    id: str
    report_id: str
    patient_id: str
    case_id: str | None = None
    status: str
    model: str
    summary: str
    classification_snapshot: dict[str, Any] | None = None
    segmentation_snapshot: dict[str, Any] | None = None
    findings: str
    limitations: str
    recommendations: str
    fhir_resource: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
