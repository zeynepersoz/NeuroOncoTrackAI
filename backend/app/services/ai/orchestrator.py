"""
NeuroOncoTrack-AI — AI Application Orchestration Service

High-level application service layer coordinating AI inference tasks.
Routes operations through the centralized AIServiceRegistry:
Router → AIOrchestrationService → AIServiceRegistry → AIProvider → AIServiceClient → AI Service
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.core.exceptions import AIServiceUnavailable
from app.schemas.ai import (
    AIExecutionRequest,
    AIExecutionResult,
    AIHealthResponse,
    AIOperation,
    AIResponse,
    AIServiceDefinition,
)
from app.services.ai.logging import log_ai_telemetry
from app.services.ai.provider import AIProvider
from app.services.ai.registry import AIServiceRegistry


class AIOrchestrationService:
    """
    Application service that orchestrates AI operations.
    
    Routes high-level business workflows via the AIServiceRegistry,
    ensuring operation validation, feature gating, correlation tracing,
    and provider dispatch for classification, segmentation, and report generation.
    """

    RESTRICTED_PARAMETER_KEYS = {
        "provider", "provider_type", "provider_name", "service",
        "service_name", "adapter", "implementation", "class", "module",
        "url", "base_url", "endpoint", "service_url", "callback_url",
        "webhook_url", "host", "target", "destination", "api_key",
        "groq_api_key", "secret", "token", "password", "timeout",
        "retries", "retry", "max_retries",
    }

    def __init__(
        self,
        registry: AIServiceRegistry | None = None,
        provider: AIProvider | None = None,
    ):
        if registry is None and provider is None:
            raise ValueError("Either registry or provider must be provided.")
        self.registry = registry
        self.provider = provider

    def _ensure_correlation_id(self, correlation_id: str | None) -> str:
        return correlation_id or uuid.uuid4().hex

    def _normalize_operation(self, operation: AIOperation | str) -> AIOperation:
        """Normalize operation string or enum safely to AIOperation."""
        if isinstance(operation, AIOperation):
            return operation
        if isinstance(operation, str):
            clean_str = operation.strip().lower()
            for op in AIOperation:
                if op.value.lower() == clean_str:
                    return op
        raise AIServiceUnavailable(
            detail="Bilinmeyen veya desteklenmeyen yapay zeka operasyonu."
        )

    def _resolve_service_and_provider(
        self,
        operation: AIOperation,
    ) -> tuple[AIServiceDefinition, AIProvider]:
        """Resolve service definition and provider from registry or direct fallback."""
        if self.registry is not None:
            service_def = self.registry.get_service(operation)
            provider = self.registry.get_provider(operation)
            return service_def, provider

        # Fallback to direct single provider (TASK-045 compatibility)
        dummy_service = AIServiceDefinition(
            operation=operation,
            service_name=self.provider.provider_name if self.provider else "direct-provider",
            model="neuroonco-v3",
        )
        return dummy_service, self.provider  # type: ignore[return-value]

    def _resolve_provider_and_params(
        self,
        operation: AIOperation,
        parameters: dict[str, Any] | None,
    ) -> tuple[AIProvider, dict[str, Any]]:
        """Resolve target provider and sanitize parameters."""
        service_def, provider = self._resolve_service_and_provider(operation)
        merged_params = dict(parameters or {})

        # Server-side registered model is authoritative; user input cannot override it
        if service_def.model:
            merged_params["model"] = service_def.model

        # Strip restricted routing, credential, and infrastructure keys
        for k in self.RESTRICTED_PARAMETER_KEYS:
            merged_params.pop(k, None)

        return provider, merged_params

    async def execute(self, request: AIExecutionRequest) -> AIExecutionResult:
        """
        Execute an AI inference operation against the centralized registry.
        Enforces authoritative model resolution, correlation tracing, parameter sanitization,
        and telemetry recording.
        """
        t0 = time.perf_counter()
        op = self._normalize_operation(request.operation)
        cid = self._ensure_correlation_id(request.correlation_id)

        service_def, provider = self._resolve_service_and_provider(op)

        # Sanitize parameters
        clean_params = dict(request.parameters or {})
        if service_def.model:
            clean_params["model"] = service_def.model
        for k in self.RESTRICTED_PARAMETER_KEYS:
            clean_params.pop(k, None)

        clean_request = AIExecutionRequest(
            operation=op,
            inputs=request.inputs,
            parameters=clean_params,
            correlation_id=cid,
        )

        try:
            result = await provider.execute(clean_request, service_def)
            duration_ms = (time.perf_counter() - t0) * 1000.0
            log_ai_telemetry(
                provider=provider.provider_name,
                operation=op.value,
                model=result.model,
                request_id=cid,
                duration_ms=duration_ms,
                status="SUCCESS",
            )
            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            log_ai_telemetry(
                provider=provider.provider_name if provider else "unknown",
                operation=op.value,
                model=service_def.model or "unknown",
                request_id=cid,
                duration_ms=duration_ms,
                status="FAILED",
                error_type=type(exc).__name__,
            )
            raise

    async def classify(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        """Orchestrate 2D image classification returning AIResponse."""
        cid = self._ensure_correlation_id(correlation_id)
        provider, params = self._resolve_provider_and_params(
            AIOperation.CLASSIFICATION, parameters
        )
        return await provider.classify(inputs, correlation_id=cid, parameters=params)

    async def segment(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        """Orchestrate 3D multi-sequence MRI segmentation returning AIResponse."""
        cid = self._ensure_correlation_id(correlation_id)
        provider, params = self._resolve_provider_and_params(
            AIOperation.SEGMENTATION, parameters
        )
        return await provider.segment(inputs, correlation_id=cid, parameters=params)

    async def generate_report(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        """Orchestrate clinical AI diagnostic report generation returning AIResponse."""
        cid = self._ensure_correlation_id(correlation_id)
        provider, params = self._resolve_provider_and_params(
            AIOperation.REPORT_GENERATION, parameters
        )
        return await provider.generate_report(inputs, correlation_id=cid, parameters=params)

    async def check_health(
        self, operation: AIOperation | str | None = None
    ) -> AIHealthResponse:
        """
        Check availability of configured AI services.
        If specific operation provided, inspects that operation; otherwise checks overall connectivity.
        """
        if self.registry is not None:
            results = await self.registry.check_health(operation)
            if operation is not None:
                op_key = operation.value if isinstance(operation, AIOperation) else str(operation)
                if op_key in results:
                    return results[op_key]

            # Aggregate health across all registered services
            all_up = all(r.status == "up" for r in results.values() if r.status != "disabled")
            any_down = any(r.status == "down" for r in results.values())
            overall_status = "down" if any_down else ("up" if all_up else "degraded")
            max_latency = max((r.latency_ms for r in results.values()), default=0.0)

            return AIHealthResponse(
                status=overall_status,
                provider="service_registry",
                latency_ms=max_latency,
                details={k: v.model_dump() for k, v in results.items()},
            )

        return await self.provider.check_health()  # type: ignore[union-attr]

    async def close(self) -> None:
        """Release underlying registry and provider resources."""
        if self.registry is not None:
            await self.registry.close()
        if self.provider is not None:
            await self.provider.close()
