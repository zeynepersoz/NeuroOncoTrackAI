"""
NeuroOncoTrack-AI — AI Integration Services Package
"""

from app.services.ai.client import AIServiceClient
from app.services.ai.deps import (
    get_ai_client,
    get_ai_provider,
    get_ai_registry,
    get_ai_service,
)
from app.services.ai.orchestrator import AIOrchestrationService
from app.services.ai.provider import AIProvider
from app.services.ai.providers.internal_service import InternalAIServiceProvider
from app.services.ai.providers.mock_provider import MockAIProvider
from app.services.ai.registry import AIServiceRegistry

__all__ = [
    "AIServiceClient",
    "AIServiceRegistry",
    "AIProvider",
    "InternalAIServiceProvider",
    "MockAIProvider",
    "AIOrchestrationService",
    "get_ai_client",
    "get_ai_registry",
    "get_ai_provider",
    "get_ai_service",
]
