"""
NeuroOncoTrack-AI — AI Dependency Injection

FastAPI dependency providers for AI components:
- get_ai_client() -> AIServiceClient
- get_ai_registry() -> AIServiceRegistry
- get_ai_provider() -> AIProvider
- get_ai_service() -> AIOrchestrationService

Ensures testability, clean lifecycle cleanup, and seamless mock injection.
"""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends

from app.core.config import settings
from app.services.ai.client import AIServiceClient
from app.services.ai.orchestrator import AIOrchestrationService
from app.services.ai.provider import AIProvider
from app.services.ai.providers.internal_service import InternalAIServiceProvider
from app.services.ai.registry import AIServiceRegistry


async def get_ai_client() -> AsyncGenerator[AIServiceClient, None]:
    """
    FastAPI dependency yielding a configured AIServiceClient.
    Closes the connection pool on request completion.
    """
    client = AIServiceClient(
        base_url=settings.AI_SERVICE_URL,
        api_key=settings.AI_API_KEY,
        connect_timeout=settings.AI_CONNECT_TIMEOUT_SECONDS,
        read_timeout=settings.AI_READ_TIMEOUT_SECONDS,
        write_timeout=settings.AI_WRITE_TIMEOUT_SECONDS,
        pool_timeout=settings.AI_POOL_TIMEOUT_SECONDS,
        total_timeout=settings.AI_TOTAL_TIMEOUT_SECONDS,
        max_retries=settings.AI_MAX_RETRIES,
        retry_backoff_factor=settings.AI_RETRY_BACKOFF_FACTOR,
    )
    try:
        yield client
    finally:
        await client.close()


async def get_ai_registry() -> AsyncGenerator[AIServiceRegistry, None]:
    """
    FastAPI dependency yielding the central AIServiceRegistry.
    Cleans up all initialized providers upon completion.
    """
    registry = AIServiceRegistry.from_settings(settings)
    try:
        yield registry
    finally:
        await registry.close()


def get_ai_provider(
    client: AIServiceClient = Depends(get_ai_client),
) -> AIProvider:
    """
    FastAPI dependency providing a default fallback AIProvider.
    """
    return InternalAIServiceProvider(client=client)


def get_ai_service(
    registry: AIServiceRegistry = Depends(get_ai_registry),
) -> AIOrchestrationService:
    """
    FastAPI dependency providing the AIOrchestrationService backed by the registry.
    """
    return AIOrchestrationService(registry=registry)
