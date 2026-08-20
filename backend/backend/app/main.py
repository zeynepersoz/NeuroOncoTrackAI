"""
NeuroOncoTrack-AI — Application Entrypoint

FastAPI application instance with middleware, exception handlers,
and lifecycle management.
"""

import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis_client
from app.core import redis as redis_core
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis
from app.db.session import close_db, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown hooks."""
    # Startup
    yield
    # Shutdown
    await close_db()
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    description="NeuroOncoTrack-AI Backend API — Beyin tümörü segmentasyonu ve klinik karar destek platformu",
    version="0.1.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request ID Middleware ────────────────────────────────────
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Assign a unique request ID to every request for tracing."""
    request_id = request.headers.get("X-Request-ID", uuid4().hex)
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Production Security Headers Middleware ───────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Inject production-grade security headers into HTTP responses with path-scoped CSP for docs."""
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Path-scoped CSP: Allow CDN assets & inline init script exclusively for /docs and /redoc
    path = request.url.path
    if path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net; "
            "frame-ancestors 'none';"
        )
    else:
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"

    # Enforce HSTS only on HTTPS or production forwarded HTTPS requests to avoid breaking local dev
    is_https = (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto") == "https"
        or (not settings.is_development and request.url.scheme != "http")
    )
    if is_https:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


# ── Exception Handlers ───────────────────────────────────────
register_exception_handlers(app)


# ── Health Check ─────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: redis_core.Redis | None = Depends(get_redis_client),
) -> dict[str, Any]:
    """
    Active Readiness Probe & Health Check Endpoint.

    Actively checks PostgreSQL database (`SELECT 1`) and Redis (`PING`),
    calculates component latencies, and returns structured status diagnostics.

    Status logic:
    - 200 OK (status: "healthy"): All components up
    - 200 OK (status: "degraded"): Database up, Redis down
    - 503 Service Unavailable (status: "unhealthy"): Database down
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    components: dict[str, dict[str, Any]] = {}
    is_db_up = False
    is_redis_up = False

    # 1. Check Database
    t0 = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latency_db = round((time.perf_counter() - t0) * 1000, 2)
        components["database"] = {
            "status": "up",
            "latency_ms": latency_db,
        }
        is_db_up = True
    except Exception as exc:
        latency_db = round((time.perf_counter() - t0) * 1000, 2)
        components["database"] = {
            "status": "down",
            "latency_ms": latency_db,
            "error": str(exc),
        }

    # 2. Check Redis
    t0 = time.perf_counter()
    if redis is not None:
        try:
            await redis.ping()
            latency_redis = round((time.perf_counter() - t0) * 1000, 2)
            components["redis"] = {
                "status": "up",
                "latency_ms": latency_redis,
            }
            is_redis_up = True
        except Exception as exc:
            latency_redis = round((time.perf_counter() - t0) * 1000, 2)
            components["redis"] = {
                "status": "down",
                "latency_ms": latency_redis,
                "error": str(exc),
            }
    else:
        components["redis"] = {
            "status": "down",
            "latency_ms": 0.0,
            "error": "Redis client unavailable",
        }

    # 3. Determine Overall Status & Response Status Code
    if is_db_up and is_redis_up:
        overall_status = "healthy"
        response.status_code = status.HTTP_200_OK
    elif is_db_up:
        overall_status = "degraded"
        response.status_code = status.HTTP_200_OK
    else:
        overall_status = "unhealthy"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": overall_status,
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "timestamp": now_iso,
        "components": components,
    }


@app.get("/health/liveness", tags=["system"])
async def liveness_check() -> dict[str, str]:
    """Fast liveness probe for container orchestrators."""
    return {"status": "alive", "service": settings.APP_NAME}


# ── Router Registration ─────────────────────────────────────
from app.api.v1.auth import router as auth_router
from app.api.v1.admin import router as admin_router

app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_router, prefix=settings.API_V1_PREFIX)

