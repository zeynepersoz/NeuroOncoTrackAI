"""
NeuroOncoTrack-AI — AI Provider Interface Abstraction

Defines the abstract interface contract that all concrete AI inference providers
must satisfy (Internal FastAPI AI service, GPU clusters, Cloud APIs, Mock providers).
Shields upper-layer routers and business logic from provider-specific implementation details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.ai import (
    AIExecutionRequest,
    AIExecutionResult,
    AIHealthResponse,
    AIOperation,
    AIResponse,
    AIServiceDefinition,
)


class AIProvider(ABC):
    """
    Abstract AI Provider interface contract.
    
    All concrete inference engines (internal, cloud, mock) implement this interface.
    Upper application layers interact strictly with this contract.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier name of this provider."""
        ...

    @abstractmethod
    async def execute(
        self,
        request: AIExecutionRequest,
        service: AIServiceDefinition,
    ) -> AIExecutionResult:
        """
        Execute an AI inference operation against target service definition.
        
        Normalizes provider-specific response to standardized AIExecutionResult.
        Shields internal network and infrastructure details.
        """
        ...


    @abstractmethod
    async def classify(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        """
        Execute 2D / volumetric classification (e.g. tumor subtype / grade).
        """
        ...

    @abstractmethod
    async def segment(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        """
        Execute 3D multi-sequence MRI segmentation (e.g. BraTS sub-regions: WT, TC, ET).
        """
        ...

    @abstractmethod
    async def generate_report(
        self,
        inputs: dict[str, Any],
        *,
        correlation_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> AIResponse:
        """
        Generate structured clinical / radiology AI report.
        """
        ...

    @abstractmethod
    async def check_health(self) -> AIHealthResponse:
        """
        Check provider connectivity without executing heavy inference.
        """
        ...

    async def close(self) -> None:
        """Cleanup and release underlying network/client resources."""
        pass
