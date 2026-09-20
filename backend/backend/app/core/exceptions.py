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

from app.core.config import settings


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

    # AI Services — 502 / 503 / 504
    AI_001 = "AI_001"  # AI servisi kullanılamıyor (503)
    AI_002 = "AI_002"  # AI servisi zaman aşımı (504)
    AI_003 = "AI_003"  # AI servisi hatalı yanıt (502)
    AI_004 = "AI_004"  # AI servisi geçersiz yanıt formatı (502)
    AI_005 = "AI_005"  # AI sağlayıcı hatası (502)


ERROR_STATUS_MAP: dict[str, int] = {
    ErrorCode.AUTH_001: 401,
    ErrorCode.AUTH_002: 401,
    ErrorCode.AUTH_003: 403,
    ErrorCode.AUTH_004: 423,
    ErrorCode.AUTH_005: 401,
    ErrorCode.AUTH_006: 403,
    ErrorCode.VAL_001: 422,
    ErrorCode.RATE_001: 429,
    ErrorCode.AI_001: 503,
    ErrorCode.AI_002: 504,
    ErrorCode.AI_003: 502,
    ErrorCode.AI_004: 502,
    ErrorCode.AI_005: 502,
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
    ErrorCode.AI_001: "Yapay zeka servisine erişilemiyor. Lütfen daha sonra tekrar deneyin.",
    ErrorCode.AI_002: "Yapay zeka servisi yanıt süresi aşıldı.",
    ErrorCode.AI_003: "Yapay zeka servisinden beklenmeyen bir yanıt alındı.",
    ErrorCode.AI_004: "Yapay zeka servisi yanıt formatı doğrulanamadı.",
    ErrorCode.AI_005: "Yapay zeka sağlayıcı işlemi sırasında hata oluştu.",
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


class NotFoundError(AppError):
    """NOT_FOUND — İstenen kaynak bulunamadı."""

    def __init__(self, message: str = "Kaynak bulunamadı.", detail: str | None = None):
        super().__init__(code="NOT_FOUND", message=message, detail=detail, status_code=404)


# ── AI Exceptions ───────────────────────────────────────────

class AIError(AppError):
    """Base exception for all AI integration errors."""

    def __init__(
        self,
        code: str = ErrorCode.AI_005,
        message: str | None = None,
        detail: str | None = None,
        status_code: int | None = None,
    ):
        safe_detail = self._sanitize_detail(detail)
        super().__init__(code=code, message=message, detail=safe_detail, status_code=status_code)

    @staticmethod
    def _sanitize_detail(detail: str | None) -> str | None:
        if not detail:
            return None
        import re
        # Strip URLs (e.g. http://localhost:8100, http://ai-service:8100/infer)
        cleaned = re.sub(r"https?://[^\s/$.?#].[^\s]*", "[REDACTED_URL]", detail)
        # Strip API keys/secrets
        cleaned = re.sub(r"(?:api[_-]?key|secret|token)[:=]\s*[\w\-.]+", "[REDACTED_CREDENTIAL]", cleaned, flags=re.IGNORECASE)
        # Mask hostnames with ports (e.g. ai-service:8100)
        cleaned = re.sub(r"\b[\w\-]+:\d{2,5}\b", "[REDACTED_ENDPOINT]", cleaned)
        return cleaned


class AIServiceUnavailable(AIError):
    """AI_001 — AI servisi kullanılamıyor veya bağlantı kurulamadı (503)."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.AI_001, detail=detail)


class AIServiceTimeout(AIError):
    """AI_002 — AI servisi yanıt süresi zaman aşımına uğradı (504)."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.AI_002, detail=detail)


class AIServiceBadResponse(AIError):
    """AI_003 — AI servisinden geçersiz/hatalı HTTP yanıtı alındı (502)."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.AI_003, detail=detail)


class AIServiceInvalidResponse(AIError):
    """AI_004 — AI servisinden gelen veri doğrulanamadı veya şemaya uymuyor (502)."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.AI_004, detail=detail)


class AIProviderError(AIError):
    """AI_005 — AI sağlayıcısı seviyesinde hata oluştu (502)."""

    def __init__(self, detail: str | None = None):
        super().__init__(code=ErrorCode.AI_005, detail=detail)


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


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global fallback handler for unhandled 500 internal server exceptions."""
    request_id = _get_request_id(request)
    # Mask internal traceback/credentials in production environments
    detail_msg = (
        str(exc)
        if getattr(settings, "is_development", True)
        else "Sunucu işlemi sırasında beklenmeyen bir hata meydana geldi."
    )
    body: dict[str, Any] = {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Sunucu içi bir hata oluştu.",
        "detail": detail_msg,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(status_code=500, content={"error": body})


def register_exception_handlers(app: Any) -> None:
    """Register all custom exception handlers on the FastAPI app."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
