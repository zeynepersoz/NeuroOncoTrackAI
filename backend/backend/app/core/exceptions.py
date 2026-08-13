"""
NeuroOncoTrack-AI — Exception Types & Error Codes

Ortak error envelope ve authentication error kodları.
Tüm API hataları bu modüldeki sınıflar üzerinden fırlatılır.

Error Envelope:
{
  "error": {
    "code": "AUTH_001",
    "message": "...",
    "detail": "...",
    "request_id": "...",
    "timestamp": "ISO-8601"
  }
}
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


# ── Error Codes ──────────────────────────────────────────────

class ErrorCode:
    """Authentication and system error codes."""

    # Authentication — 401
    AUTH_001 = "AUTH_001"  # E-posta veya parola hatalı
    AUTH_002 = "AUTH_002"  # Jeton süresi dolmuş veya geçersiz

    # Authorization — 403
    AUTH_003 = "AUTH_003"  # Yetersiz izin

    # Account — 423
    AUTH_004 = "AUTH_004"  # Hesap kilitli

    # MFA — 401
    AUTH_005 = "AUTH_005"  # MFA gerekli veya hatalı

    # Password — 403
    AUTH_006 = "AUTH_006"  # Parola değişimi zorunlu

    # Validation — 422
    VAL_001 = "VAL_001"  # Doğrulama hatası

    # Rate Limit — 429
    RATE_001 = "RATE_001"  # İstek limiti aşıldı


ERROR_STATUS_MAP: dict[str, int] = {
    ErrorCode.AUTH_001: 401,
    ErrorCode.AUTH_002: 401,
    ErrorCode.AUTH_003: 403,
    ErrorCode.AUTH_004: 423,
    ErrorCode.AUTH_005: 401,
    ErrorCode.AUTH_006: 403,
    ErrorCode.VAL_001: 422,
    ErrorCode.RATE_001: 429,
}

ERROR_MESSAGE_MAP: dict[str, str] = {
    ErrorCode.AUTH_001: "E-posta veya parola hatalı.",
    ErrorCode.AUTH_002: "Jeton süresi dolmuş veya geçersiz.",
    ErrorCode.AUTH_003: "Bu işlem için yetkiniz bulunmamaktadır.",
    ErrorCode.AUTH_004: "Hesap kilitli. Lütfen daha sonra tekrar deneyin.",
    ErrorCode.AUTH_005: "Çok faktörlü doğrulama gerekli veya kod hatalı.",
    ErrorCode.AUTH_006: "Parola değişimi zorunludur.",
    ErrorCode.VAL_001: "İstek doğrulama hatası.",
    ErrorCode.RATE_001: "Çok fazla istek. Lütfen daha sonra tekrar deneyin.",
}


# ── Base Exception ───────────────────────────────────────────

class AppError(Exception):
    """Base application error with error code and structured output."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        detail: str | None = None,
        status_code: int | None = None,
    ):
        self.code = code
        self.message = message or ERROR_MESSAGE_MAP.get(code, "Bilinmeyen hata.")
        self.detail = detail
        self.status_code = status_code or ERROR_STATUS_MAP.get(code, 500)
        super().__init__(self.message)

    def to_dict(self, request_id: str | None = None) -> dict[str, Any]:
        """Build the standard error envelope."""
        body: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "details": self.detail if self.detail is not None else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if self.detail:
            body["detail"] = self.detail
        if request_id:
            body["request_id"] = request_id
        return {"error": body}


# ── Specific Exceptions ─────────────────────────────────────

class AuthenticationError(AppError):
    """AUTH_001 — Geçersiz kimlik bilgileri."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.AUTH_001, detail=detail)


class InvalidTokenError(AppError):
    """AUTH_002 — Geçersiz veya süresi dolmuş jeton."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.AUTH_002, detail=detail)


class ForbiddenError(AppError):
    """AUTH_003 — Yetersiz izin."""

    def __init__(self, detail: str | None = None, missing: list[str] | None = None):
        _detail = detail
        if missing:
            _detail = f"Gerekli izin: {', '.join(missing)}"
        super().__init__(code=ErrorCode.AUTH_003, detail=_detail)


class AccountLockedError(AppError):
    """AUTH_004 — Hesap kilitli."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.AUTH_004, detail=detail)


class MFARequiredError(AppError):
    """AUTH_005 — MFA doğrulaması gerekli veya MFA kodu hatalı."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.AUTH_005, detail=detail)


class PasswordChangeRequiredError(AppError):
    """AUTH_006 — Parola değişimi zorunlu."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.AUTH_006, detail=detail)


class ValidationError(AppError):
    """VAL_001 — Doğrulama hatası."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.VAL_001, detail=detail)


class RateLimitError(AppError):
    """RATE_001 — İstek limiti aşıldı."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.RATE_001, detail=detail)


# ── FastAPI Exception Handlers ───────────────────────────────

def _get_request_id(request: Request) -> str | None:
    """Extract request ID from request state if available."""
    return getattr(request.state, "request_id", None)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Global handler for all AppError subclasses."""
    request_id = _get_request_id(request)
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(request_id=request_id),
    )


async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Global handler for FastAPI RequestValidationError -> VAL_001 standard envelope."""
    request_id = _get_request_id(request)
    cleaned_errors = []
    for err in exc.errors():
        cleaned_errors.append({
            "loc": [str(x) for x in err.get("loc", [])],
            "msg": str(err.get("msg", "")),
            "type": str(err.get("type", "")),
        })

    detail_str = "; ".join([f"{'.'.join(e['loc'])}: {e['msg']}" for e in cleaned_errors])
    body: dict[str, Any] = {
        "code": ErrorCode.VAL_001,
        "message": ERROR_MESSAGE_MAP[ErrorCode.VAL_001],
        "detail": detail_str,
        "details": cleaned_errors,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(status_code=422, content={"error": body})


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Global handler for Starlette/FastAPI HTTPException -> standard envelope."""
    request_id = _get_request_id(request)
    code = ErrorCode.AUTH_002 if exc.status_code == 401 else (ErrorCode.VAL_001 if exc.status_code == 422 else "HTTP_ERROR")
    detail_msg = str(exc.detail) if exc.detail else "İşlem başarısız."
    body: dict[str, Any] = {
        "code": code,
        "message": ERROR_MESSAGE_MAP.get(code, detail_msg),
        "detail": detail_msg,
        "details": detail_msg,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(status_code=exc.status_code, content={"error": body})


def register_exception_handlers(app: Any) -> None:
    """Register all custom exception handlers on the FastAPI app."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
