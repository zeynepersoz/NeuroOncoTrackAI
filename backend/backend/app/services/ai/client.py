"""
NeuroOncoTrack-AI — Central AI HTTP Client

Production-grade asynchronous HTTP client for AI services.
Centralizes network communication, timeouts, retry with exponential backoff,
structured exceptions, and secure telemetry.
Direct httpx calls in routers are forbidden.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import (
    AIProviderError,
    AIServiceBadResponse,
    AIServiceInvalidResponse,
    AIServiceTimeout,
    AIServiceUnavailable,
)
from app.services.ai.logging import log_ai_telemetry


class AIServiceClient:
    """
    Central async HTTP client for AI microservices and external inference providers.
    
    Provides:
    - Fine-grained connection/read/write/pool timeout management
    - Automatic exponential backoff retry for transient network/server failures
    - Deterministic error fast-fail (no retries for 4xx client errors)
    - Full response parsing and schema error trapping
    - Zero sensitive credential / host information leakage
    """

    RETRYABLE_STATUS_CODES = {502, 503, 504}
    _UNSET = object()

    def __init__(
        self,
        base_url: Any = _UNSET,
        api_key: str | None = None,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        write_timeout: float | None = None,
        pool_timeout: float | None = None,
        total_timeout: float | None = None,
        max_retries: int | None = None,
        retry_backoff_factor: float | None = None,
        retry_on_timeout: bool = False,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = settings.AI_SERVICE_URL if base_url is self._UNSET else base_url
        raw_key = api_key if api_key is not None else settings.AI_API_KEY
        self.api_key = (
            raw_key.strip()
            if (raw_key and isinstance(raw_key, str) and raw_key.strip())
            else None
        )
        self.connect_timeout = (
            connect_timeout
            if connect_timeout is not None
            else settings.AI_CONNECT_TIMEOUT_SECONDS
        )
        self.read_timeout = (
            read_timeout
            if read_timeout is not None
            else settings.AI_READ_TIMEOUT_SECONDS
        )
        self.write_timeout = (
            write_timeout
            if write_timeout is not None
            else settings.AI_WRITE_TIMEOUT_SECONDS
        )
        self.pool_timeout = (
            pool_timeout
            if pool_timeout is not None
            else settings.AI_POOL_TIMEOUT_SECONDS
        )
        self.total_timeout = (
            total_timeout
            if total_timeout is not None
            else settings.AI_TOTAL_TIMEOUT_SECONDS
        )
        self.max_retries = (
            max_retries if max_retries is not None else settings.AI_MAX_RETRIES
        )
        self.retry_backoff_factor = (
            retry_backoff_factor
            if retry_backoff_factor is not None
            else settings.AI_RETRY_BACKOFF_FACTOR
        )
        self.retry_on_timeout = retry_on_timeout

        # Explicit bounds validation
        if self.connect_timeout <= 0:
            raise ValueError("connect_timeout must be greater than 0")
        if self.read_timeout <= 0:
            raise ValueError("read_timeout must be greater than 0")
        if self.write_timeout <= 0:
            raise ValueError("write_timeout must be greater than 0")
        if self.pool_timeout <= 0:
            raise ValueError("pool_timeout must be greater than 0")
        if self.total_timeout <= 0:
            raise ValueError("total_timeout must be greater than 0")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.retry_backoff_factor < 0:
            raise ValueError("retry_backoff_factor must be non-negative")

        self._timeout = httpx.Timeout(
            timeout=self.total_timeout,
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=self.write_timeout,
            pool=self.pool_timeout,
        )
        self._external_client = client
        self._client: httpx.AsyncClient | None = client

    def __repr__(self) -> str:
        # Never leak api_key or credentials in string representations
        return (
            f"AIServiceClient(base_url={self.base_url!r}, "
            f"connect_timeout={self.connect_timeout}, "
            f"read_timeout={self.read_timeout}, "
            f"write_timeout={self.write_timeout}, "
            f"pool_timeout={self.pool_timeout}, "
            f"total_timeout={self.total_timeout}, "
            f"max_retries={self.max_retries}, "
            f"retry_on_timeout={self.retry_on_timeout})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily initialize or return active httpx AsyncClient."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        """Close client session and release connection pool."""
        if self._client is not None and self._external_client is None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> AIServiceClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def _build_url(self, endpoint_or_url: str) -> str:
        """Resolve full target URL safely."""
        if endpoint_or_url.startswith(("http://", "https://")):
            return endpoint_or_url
        if not self.base_url:
            raise AIServiceUnavailable(
                detail="AI servis URL yapılandırması eksik veya tanımlanmamış."
            )
        return f"{self.base_url.rstrip('/')}/{endpoint_or_url.lstrip('/')}"

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
        operation: str = "inference",
        provider_name: str = "internal",
        model_name: str = "neuroonco-v3",
    ) -> dict[str, Any]:
        """
        Execute an async HTTP request to an AI service with timeout and retry logic.
        """
        req_id = request_id or uuid.uuid4().hex
        url = self._build_url(endpoint)

        req_headers = {
            "Accept": "application/json",
            "X-Request-ID": req_id,
            "X-Correlation-ID": req_id,
        }
        if self.api_key:
            req_headers["Authorization"] = f"Bearer {self.api_key}"
        if headers:
            req_headers.update(headers)

        client = self._get_client()
        attempts = 0
        last_exception: Exception | None = None
        last_response: httpx.Response | None = None

        while attempts <= self.max_retries:
            attempts += 1
            t0 = time.perf_counter()
            try:
                response = await client.request(
                    method=method.upper(),
                    url=url,
                    json=json_data,
                    headers=req_headers,
                    timeout=self._timeout,
                )
                duration_ms = (time.perf_counter() - t0) * 1000.0
                last_response = response

                # Non-retryable Client Errors (4xx) -> Fail fast immediately
                if 400 <= response.status_code < 500:
                    log_ai_telemetry(
                        provider=provider_name,
                        operation=operation,
                        model=model_name,
                        request_id=req_id,
                        duration_ms=duration_ms,
                        status="FAILED",
                        http_status=response.status_code,
                        error_type=f"HTTP_{response.status_code}",
                    )
                    if response.status_code == 401 or response.status_code == 403:
                        raise AIProviderError(
                            detail="AI servisi kimlik doğrulama veya yetkilendirme reddedildi."
                        )
                    if response.status_code == 404:
                        raise AIProviderError(
                            detail="AI servisinde istenen model veya kaynak bulunamadı."
                        )
                    if response.status_code == 422:
                        raise AIServiceInvalidResponse(
                            detail="AI servisi istek parametreleri doğrulanamadı."
                        )
                    raise AIProviderError(
                        detail=f"AI servisi istemci hatası döndürdü (HTTP {response.status_code})."
                    )

                # Retryable Server Errors (502, 503, 504)
                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    log_ai_telemetry(
                        provider=provider_name,
                        operation=operation,
                        model=model_name,
                        request_id=req_id,
                        duration_ms=duration_ms,
                        status="RETRYING" if attempts <= self.max_retries else "FAILED",
                        http_status=response.status_code,
                        error_type=f"HTTP_{response.status_code}",
                        extra={"attempt": attempts, "max_retries": self.max_retries},
                    )
                    if attempts <= self.max_retries:
                        backoff = self.retry_backoff_factor * (2 ** (attempts - 1))
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        if response.status_code == 503:
                            raise AIServiceUnavailable(
                                detail="AI servisi geçici olarak kullanım dışı (503)."
                            )
                        if response.status_code == 504:
                            raise AIServiceTimeout(
                                detail="AI servisi ağ geçidi zaman aşımı (504)."
                            )
                        raise AIServiceBadResponse(
                            detail="AI servisinden geçersiz ağ geçidi yanıtı alındı (502)."
                        )

                # Any other unexpected 5xx status code
                if response.status_code >= 500:
                    log_ai_telemetry(
                        provider=provider_name,
                        operation=operation,
                        model=model_name,
                        request_id=req_id,
                        duration_ms=duration_ms,
                        status="FAILED",
                        http_status=response.status_code,
                        error_type=f"HTTP_{response.status_code}",
                    )
                    raise AIServiceBadResponse(
                        detail="AI servisi beklenmeyen bir sunucu hatası döndürdü."
                    )

                # Parse JSON payload
                try:
                    data = response.json()
                except Exception as json_exc:
                    log_ai_telemetry(
                        provider=provider_name,
                        operation=operation,
                        model=model_name,
                        request_id=req_id,
                        duration_ms=duration_ms,
                        status="FAILED",
                        http_status=response.status_code,
                        error_type="MALFORMED_JSON",
                    )
                    raise AIServiceInvalidResponse(
                        detail="AI servisinden gelen yanıt geçerli bir JSON formatında değil."
                    ) from json_exc

                # Successful call
                log_ai_telemetry(
                    provider=provider_name,
                    operation=operation,
                    model=model_name,
                    request_id=req_id,
                    duration_ms=duration_ms,
                    status="SUCCESS",
                    http_status=response.status_code,
                )
                return data

            except (httpx.ConnectError, httpx.NetworkError) as conn_exc:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                last_exception = conn_exc
                log_ai_telemetry(
                    provider=provider_name,
                    operation=operation,
                    model=model_name,
                    request_id=req_id,
                    duration_ms=duration_ms,
                    status="RETRYING" if attempts <= self.max_retries else "FAILED",
                    error_type="CONNECTION_ERROR",
                    extra={"attempt": attempts, "max_retries": self.max_retries},
                )
                if attempts <= self.max_retries:
                    backoff = self.retry_backoff_factor * (2 ** (attempts - 1))
                    await asyncio.sleep(backoff)
                    continue
                raise AIServiceUnavailable(
                    detail="AI servisine bağlanılamadı. Bağlantı reddedildi veya servis kapalı."
                ) from conn_exc

            except httpx.TimeoutException as timeout_exc:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                last_exception = timeout_exc
                should_retry = self.retry_on_timeout and (attempts <= self.max_retries)
                log_ai_telemetry(
                    provider=provider_name,
                    operation=operation,
                    model=model_name,
                    request_id=req_id,
                    duration_ms=duration_ms,
                    status="RETRYING" if should_retry else "FAILED",
                    error_type="TIMEOUT",
                    extra={"attempt": attempts, "max_retries": self.max_retries},
                )
                if should_retry:
                    backoff = self.retry_backoff_factor * (2 ** (attempts - 1))
                    await asyncio.sleep(backoff)
                    continue
                raise AIServiceTimeout(
                    detail="AI servisi yanıt süresi zaman aşımına uğradı."
                ) from timeout_exc

        # Fallback if loop finishes unexpectedly
        if last_exception:
            raise AIServiceUnavailable(detail="AI servisi çağrısı başarısız oldu.")
        raise AIServiceBadResponse(detail="AI servisinden geçerli bir yanıt alınamadı.")

    async def get(
        self,
        endpoint: str,
        *,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
        operation: str = "get",
        provider_name: str = "internal",
        model_name: str = "neuroonco-v3",
    ) -> dict[str, Any]:
        return await self.request(
            method="GET",
            endpoint=endpoint,
            headers=headers,
            request_id=request_id,
            operation=operation,
            provider_name=provider_name,
            model_name=model_name,
        )

    async def post(
        self,
        endpoint: str,
        *,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
        operation: str = "post",
        provider_name: str = "internal",
        model_name: str = "neuroonco-v3",
    ) -> dict[str, Any]:
        return await self.request(
            method="POST",
            endpoint=endpoint,
            json_data=json_data,
            headers=headers,
            request_id=request_id,
            operation=operation,
            provider_name=provider_name,
            model_name=model_name,
        )
