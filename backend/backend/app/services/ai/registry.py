"""
NeuroOncoTrack-AI — AI Service Registry

Centralized, typed registry for managing and routing AI services by operation.
Encapsulates:
- Operation-based lookup (CLASSIFICATION, SEGMENTATION, REPORT_GENERATION)
- Independent activation toggles (enabled/disabled)
- Fail-closed production enforcement (no silent fallbacks)
- Operation-scoped timeout & retry profiles
- Safe error handling without leaking internal URLs, hostnames, or credentials
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from app.core.config import Settings, settings as global_settings
from app.core.exceptions import AIServiceUnavailable
from app.schemas.ai import (
    AIHealthResponse,
    AIOperation,
    AIRetryProfile,
    AIServiceDefinition,
    AITimeoutProfile,
)
from app.services.ai.client import AIServiceClient
from app.services.ai.provider import AIProvider
from app.services.ai.providers.internal_service import InternalAIServiceProvider

logger = logging.getLogger("app.ai.registry")


class AIServiceRegistry:
    """
    Central repository of registered AI services and provider routing.
    
    Provides:
    - Operation-to-service definition lookup
    - Safe fail-closed routing in production environments
    - Independent enable/disable gating
    - Connectivity health abstraction across all registered operations
    """

    def __init__(self, is_production: bool = False):
        self._services: dict[AIOperation, AIServiceDefinition] = {}
        self._providers: dict[AIOperation, AIProvider] = {}
        self._is_production = is_production

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

    def _validate_url_security(self, url: str | None) -> None:
        """Validate URL to prevent SSRF and non-HTTP protocol schemes."""
        if not url:
            return
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise AIServiceUnavailable(
                detail="Yapay zeka servis protokolü geçersiz (yalnızca HTTP/HTTPS desteklenir)."
            )
        if not parsed.netloc:
            raise AIServiceUnavailable(
                detail="Yapay zeka servis adresi geçersiz."
            )

    def register(
        self,
        definition: AIServiceDefinition,
        provider: AIProvider | None = None,
    ) -> None:
        """Register an AI service definition and optional bound provider."""
        op = self._normalize_operation(definition.operation)
        self._validate_url_security(definition.base_url)
        self._services[op] = definition
        if provider is not None:
            self._providers[op] = provider
        elif op in self._providers:
            del self._providers[op]

    def get_service(self, operation: AIOperation | str) -> AIServiceDefinition:
        """
        Lookup active service definition for target operation.
        
        Enforces:
        - Operation existence check
        - Feature toggle check (enabled / disabled)
        - Production fail-closed check (missing base_url rejected)
        """
        op = self._normalize_operation(operation)

        if op not in self._services:
            raise AIServiceUnavailable(
                detail="İstenen yapay zeka operasyonu için servis kaydı bulunamadı."
            )

        definition = self._services[op]

        # 1. Feature activation toggle
        if not definition.enabled:
            raise AIServiceUnavailable(
                detail=f"'{definition.service_name}' yapay zeka servisi geçici olarak devre dışı bırakılmıştır."
            )

        # 2. Production fail-closed enforcement
        if self._is_production:
            if not definition.base_url or not definition.base_url.strip():
                raise AIServiceUnavailable(
                    detail=f"'{definition.service_name}' yapay zeka servisi yapılandırması eksik."
                )

        return definition

    def get(self, operation: AIOperation | str) -> AIServiceDefinition:
        """Convenience alias for get_service."""
        return self.get_service(operation)

    def get_provider(self, operation: AIOperation | str) -> AIProvider:
        """
        Resolve or lazily construct the AIProvider for an operation.
        """
        definition = self.get_service(operation)
        op = self._normalize_operation(operation)

        if op in self._providers:
            return self._providers[op]

        # Lazily instantiate concrete client and provider based on definition
        if definition.provider_type != "internal_service":
            raise AIServiceUnavailable(
                detail=f"Desteklenmeyen yapay zeka sağlayıcı türü: '{definition.provider_type}'."
            )

        client = AIServiceClient(
            base_url=definition.base_url,
            api_key=definition.api_key,
            connect_timeout=definition.timeout_profile.connect_timeout,
            read_timeout=definition.timeout_profile.read_timeout,
            write_timeout=definition.timeout_profile.write_timeout,
            pool_timeout=definition.timeout_profile.pool_timeout,
            total_timeout=definition.timeout_profile.total_timeout,
            max_retries=definition.retry_profile.max_retries,
            retry_backoff_factor=definition.retry_profile.backoff_factor,
            retry_on_timeout=definition.retry_profile.retry_on_timeout,
        )
        provider = InternalAIServiceProvider(client=client)
        self._providers[op] = provider
        return provider

    def list_operations(self) -> list[str]:
        """Return list of all registered operations."""
        return [op.value for op in self._services.keys()]

    def is_enabled(self, operation: AIOperation | str) -> bool:
        """Check if an operation is currently registered and enabled."""
        try:
            definition = self.get_service(operation)
            return definition.enabled
        except AIServiceUnavailable:
            return False

    async def check_health(
        self, operation: AIOperation | str | None = None
    ) -> dict[str, AIHealthResponse]:
        """
        Inspect health and connectivity for registered operations.
        Does not execute heavy inference workloads.
        """
        results: dict[str, AIHealthResponse] = {}

        if operation is not None:
            op = self._normalize_operation(operation)
            targets = [op] if op in self._services else []
        else:
            targets = list(self._services.keys())

        for op in targets:
            definition = self._services[op]
            if not definition.enabled:
                results[op.value] = AIHealthResponse(
                    status="disabled",
                    provider=definition.service_name,
                    latency_ms=0.0,
                    details={"status": "disabled", "reason": "Operation disabled by policy"},
                )
                continue

            try:
                provider = self.get_provider(op)
                health = await provider.check_health()
                results[op.value] = health
            except Exception as exc:
                results[op.value] = AIHealthResponse(
                    status="down",
                    provider=definition.service_name,
                    latency_ms=0.0,
                    details={"error": "Connectivity failed"},
                )

        return results

    async def close(self) -> None:
        """Release all active provider resources."""
        for provider in self._providers.values():
            try:
                await provider.close()
            except Exception as exc:
                logger.warning("Error closing AI provider: %s", exc)
        self._providers.clear()

    @classmethod
    def from_settings(
        cls,
        app_settings: Settings | None = None,
        custom_providers: dict[AIOperation, AIProvider] | None = None,
    ) -> AIServiceRegistry:
        """
        Construct a fully configured AIServiceRegistry from application settings.
        """
        cfg = app_settings or global_settings
        registry = cls(is_production=cfg.is_production)

        # 1. Classification Definition
        cls_def = AIServiceDefinition(
            operation=AIOperation.CLASSIFICATION,
            service_name="internal-classification",
            base_url=cfg.AI_SERVICE_URL,
            endpoint="/infer",
            provider_type="internal_service",
            model=cfg.AI_CLASSIFICATION_MODEL,
            enabled=cfg.AI_CLASSIFICATION_ENABLED,
            api_key=cfg.AI_API_KEY,
            timeout_profile=AITimeoutProfile(
                connect_timeout=cfg.AI_CONNECT_TIMEOUT_SECONDS,
                read_timeout=cfg.AI_CLASSIFICATION_READ_TIMEOUT_SECONDS,
                write_timeout=cfg.AI_WRITE_TIMEOUT_SECONDS,
                pool_timeout=cfg.AI_POOL_TIMEOUT_SECONDS,
                total_timeout=cfg.AI_TOTAL_TIMEOUT_SECONDS,
            ),
            retry_profile=AIRetryProfile(
                max_retries=cfg.AI_MAX_RETRIES,
                backoff_factor=cfg.AI_RETRY_BACKOFF_FACTOR,
                retry_on_timeout=False,
            ),
        )
        registry.register(cls_def)

        # 2. Segmentation Definition (longer compute timeout, guarded retry)
        seg_def = AIServiceDefinition(
            operation=AIOperation.SEGMENTATION,
            service_name="internal-segmentation",
            base_url=cfg.AI_SEGMENTATION_URL or cfg.AI_SERVICE_URL,
            endpoint="/infer" if not cfg.AI_SEGMENTATION_URL else "/segment",
            provider_type="internal_service",
            model=cfg.AI_SEGMENTATION_MODEL,
            enabled=cfg.AI_SEGMENTATION_ENABLED,
            api_key=cfg.AI_API_KEY,
            timeout_profile=AITimeoutProfile(
                connect_timeout=cfg.AI_CONNECT_TIMEOUT_SECONDS,
                read_timeout=cfg.AI_SEGMENTATION_READ_TIMEOUT_SECONDS,
                write_timeout=cfg.AI_WRITE_TIMEOUT_SECONDS,
                pool_timeout=cfg.AI_POOL_TIMEOUT_SECONDS,
                total_timeout=max(cfg.AI_TOTAL_TIMEOUT_SECONDS, cfg.AI_SEGMENTATION_READ_TIMEOUT_SECONDS + 10.0),
            ),
            retry_profile=AIRetryProfile(
                max_retries=1,  # Guarded: avoid GPU retry storms on heavy 3D segmentation
                backoff_factor=cfg.AI_RETRY_BACKOFF_FACTOR,
                retry_on_timeout=False,
            ),
        )
        registry.register(seg_def)

        # 3. Report Generation Definition
        rep_def = AIServiceDefinition(
            operation=AIOperation.REPORT_GENERATION,
            service_name="internal-report",
            base_url=cfg.AI_REPORT_URL or cfg.AI_SERVICE_URL,
            endpoint="/report",
            provider_type="internal_service",
            model=cfg.AI_REPORT_MODEL,
            enabled=cfg.AI_REPORT_ENABLED,
            api_key=cfg.AI_API_KEY,
            timeout_profile=AITimeoutProfile(
                connect_timeout=cfg.AI_CONNECT_TIMEOUT_SECONDS,
                read_timeout=cfg.AI_REPORT_READ_TIMEOUT_SECONDS,
                write_timeout=cfg.AI_WRITE_TIMEOUT_SECONDS,
                pool_timeout=cfg.AI_POOL_TIMEOUT_SECONDS,
                total_timeout=cfg.AI_TOTAL_TIMEOUT_SECONDS,
            ),
            retry_profile=AIRetryProfile(
                max_retries=cfg.AI_MAX_RETRIES,
                backoff_factor=cfg.AI_RETRY_BACKOFF_FACTOR,
                retry_on_timeout=False,
            ),
        )
        registry.register(rep_def)

        # Bind custom/mock providers if provided
        if custom_providers:
            for op, p in custom_providers.items():
                if op in registry._services:
                    registry.register(registry._services[op], provider=p)

        return registry
