"""
NeuroOncoTrack-AI — Application Entrypoint

FastAPI application instance with middleware, exception handlers,
and lifecycle management.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis
from app.db.session import close_db


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


# ── Exception Handlers ───────────────────────────────────────
register_exception_handlers(app)


# ── Health Check ─────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "service": settings.APP_NAME}


# ── Router Registration ─────────────────────────────────────
from app.api.v1.auth import router as auth_router

app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
