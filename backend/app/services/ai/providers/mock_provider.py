"""
NeuroOncoTrack-AI — Mock AI Provider

In-memory mock provider implementation for unit tests, local verification,
and offline CI testing environments.
Produces deterministic, schema-valid AIExecutionResult and AIResponse outputs.
Supports failure injection (timeouts, connection errors, malformed responses)
without network dependencies.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.exceptions import (
    AIProviderError,
    AIServiceBadResponse,
    AIServiceInvalidResponse,
    AIServiceTimeout,
    AIServiceUnavailable,
)
from app.schemas.ai import (
    AIExecutionRequest,
    AIExecutionResult,
    AIHealthResponse,
    AIOperation,
    AIResponse,
    AIServiceDefinition,
    AIStatus,
)
from app.services.ai.provider import AIProvider


class MockAIProvider(AIProvider):
    """
    Mock AI Provider returning deterministic results without making network calls.
    Supports failure injection for rigorous testing.
    """

    def __init__(
        self,
        provider_name: str = "mock_provider",
        healthy: bool = True,
        latency_ms: float = 12.5,
        simulate_timeout: bool = False,
        simulate_connection_error: bool = False,
        simulate_http_error: int | None = None,
        simulate_malformed: bool = False,
        simulate_invalid_response: bool = False,
    ):
        self._provider_name = provider_name
        self.healthy = healthy
        self.latency_ms = latency_ms
        self.simulate_timeout = simulate_timeout
        self.simulate_connection_error = simulate_connection_error
        self.simulate_http_error = simulate_http_error
        self.simulate_malformed = simulate_malformed
        self.simulate_invalid_response = simulate_invalid_response
        self.calls: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def _check_simulated_failures(self) -> None:
        """Trigger configured failure injection if any."""
        if self.simulate_timeout:
            raise AIServiceTimeout(detail="Simulated mock timeout occurred.")
        if self.simulate_connection_error:
            raise AIServiceUnavailable(detail="Simulated mock connection failure.")
        if self.simulate_http_error:
            if self.simulate_http_error == 503:
                raise AIServiceUnavailable(detail="Simulated 503 service unavailable.")
            if self.simulate_http_error == 504:
                raise AIServiceTimeout(detail="Simulated 504 gateway timeout.")
            if self.simulate_http_error >= 500:
                raise AIServiceBadResponse(detail=f"Simulated {self.simulate_http_error} error.")
            raise AIProviderError(detail=f"Simulated {self.simulate_http_error} client error.")
        if self.simulate_malformed or self.simulate_invalid_response:
            raise AIServiceInvalidResponse(detail="Simulated invalid/malformed response.")

    async def execute(
        self,
        request: AIExecutionRequest,
        service: AIServiceDefinition,
    ) -> AIExecutionResult:
        """Execute mock inference and return deterministic AIExecutionResult."""
        self._check_simulated_failures()

        req_id = request.correlation_id or uuid.uuid4().hex
        op_val = request.operation.value if isinstance(request.operation, AIOperation) else str(request.operation)
        resolved_model = service.model or "mock-default-model"

        self.calls.append({
            "op": op_val,
            "inputs": request.inputs,
            "parameters": request.parameters,
            "req_id": req_id,
            "service": service,
        })

        if op_val == AIOperation.CLASSIFICATION.value or op_val == "classify":
            return AIExecutionResult(
                operation=op_val,
                status=AIStatus.COMPLETED,
                provider=self.provider_name,
                model=resolved_model,
                request_id=req_id,
                output={
                    "prediction": "glioma",
                    "confidence": 0.94,
                    "probabilities": {
                        "glioma": 0.94,
                        "meningioma": 0.04,
                        "notumor": 0.01,
                        "pituitary": 0.01,
                    },
                    "who_grade_hint": "III-IV (agresif alt tip beklenir)",
                },
                metadata={"simulated": True, "mode": request.parameters.get("mode", "fast")},
            )

        if op_val == AIOperation.SEGMENTATION.value or op_val == "segment":
            return AIExecutionResult(
                operation=op_val,
                status=AIStatus.COMPLETED,
                provider=self.provider_name,
                model=resolved_model,
                request_id=req_id,
                output={
                    "volumes_cm3": {"whole_tumor": 42.1, "tumor_core": 28.3, "enhancing_tumor": 14.2},
                    "tumor_volume_cm3": 42.1,
                    "tumor_area_ratio_2d": 0.18,
                    "et_wt_ratio": 0.34,
                    "slices_count": 155,
                    "num_tumor_slices": 42,
                    "best_slice": 78,
                    "mask_status": "generated",
                    "mask_artifact_id": "mask_tumor_gtv.nii.gz",
                },
                metadata={"simulated": True},
            )

        if op_val == AIOperation.REPORT_GENERATION.value or op_val == "generate_report":
            return AIExecutionResult(
                operation=op_val,
                status=AIStatus.COMPLETED,
                provider=self.provider_name,
                model=resolved_model,
                request_id=req_id,
                output={
                    "report": "Sol frontal lobda kitle lezyonu izlenmektedir.",
                    "sections": {
                        "findings": "Sol frontal lobda kitle lezyonu izlenmektedir.",
                        "impression": "Yüksek dereceli glial tümör (WHO Grade IV) ile uyumludur.",
                    },
                    "fhir": {
                        "resourceType": "DiagnosticReport",
                        "status": "preliminary",
                    },
                    "is_valid": True,
                },
                metadata={"simulated": True},
            )

        # Fallback generic operation
        return AIExecutionResult(
            operation=op_val,
            status=AIStatus.COMPLETED,
            provider=self.provider_name,
            model=resolved_model,
            request_id=req_id,
            output={"result": "generic_mock_output"},
            metadata={"simulated": True},
        )

    async def classify(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        self._check_simulated_failures()
        req_id = correlation_id or uuid.uuid4().hex
        self.calls.append({"op": "classify", "inputs": inputs, "req_id": req_id})
        return AIResponse(
            provider=self.provider_name,
            model="mock-classifier-v1",
            request_id=req_id,
            status=AIStatus.COMPLETED,
            output={
                "prediction": "glioblastoma",
                "confidence": 0.94,
                "probabilities": {
                    "glioblastoma": 0.94,
                    "astrocytoma": 0.04,
                    "oligodendroglioma": 0.02,
                },
            },
            metadata={"simulated": True, "mode": parameters.get("mode", "full") if parameters else "full"},
        )

    async def segment(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        self._check_simulated_failures()
        req_id = correlation_id or uuid.uuid4().hex
        self.calls.append({"op": "segment", "inputs": inputs, "req_id": req_id})
        return AIResponse(
            provider=self.provider_name,
            model="mock-segmentor-3d-v1",
            request_id=req_id,
            status=AIStatus.COMPLETED,
            output={
                "volumes_cm3": {"whole_tumor": 42.1, "tumor_core": 28.3, "enhancing_tumor": 14.2},
                "slices_count": 155,
                "mask_status": "generated",
            },
            metadata={"simulated": True},
        )

    async def generate_report(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        self._check_simulated_failures()
        req_id = correlation_id or uuid.uuid4().hex
        self.calls.append({"op": "generate_report", "inputs": inputs, "req_id": req_id})
        return AIResponse(
            provider=self.provider_name,
            model="mock-report-llm-v1",
            request_id=req_id,
            status=AIStatus.COMPLETED,
            output={
                "findings": "Sol frontal lobda kitle lezyonu izlenmektedir.",
                "impression": "Yüksek dereceli glial tümör (WHO Grade IV) ile uyumludur.",
                "recommendations": ["Multidisipliner tümör konseyi değerlendirmesi önerilir."],
            },
            metadata={"simulated": True},
        )

    async def check_health(self) -> AIHealthResponse:
        if self.healthy:
            return AIHealthResponse(
                status="up",
                provider=self.provider_name,
                latency_ms=self.latency_ms,
                details={"mode": "mock", "state": "operational"},
            )
        return AIHealthResponse(
            status="down",
            provider=self.provider_name,
            latency_ms=self.latency_ms,
            details={"mode": "mock", "state": "unhealthy"},
        )
