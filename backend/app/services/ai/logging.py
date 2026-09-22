"""
NeuroOncoTrack-AI — AI Structured Logging & Sanitization

Ensures production-grade structured logging for all AI inference operations.
Strictly enforces privacy & security invariants:
- NEVER logs medical images, base64 data, full prompt, raw AI outputs
- NEVER logs passwords, JWTs, API keys, secrets, or raw PHI
- Only logs safe operational telemetry: provider, model, operation, duration_ms, request_id, status, error_type
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.ai")

# Blacklist of fields that must NEVER be recorded in AI logs
RESTRICTED_AI_KEYS = {
    "image",
    "image_bytes",
    "image_base64",
    "b64",
    "base64",
    "file",
    "files",
    "raw_image",
    "prompt",
    "full_prompt",
    "full_output",
    "raw_output",
    "token",
    "password",
    "password_hash",
    "secret",
    "key",
    "api_key",
    "groq_api_key",
    "openai_api_key",
    "access_token",
    "refresh_token",
    "authorization",
    "jwt",
    "phi",
    "patient_name",
    "ssn",
    "mrn",
}


def sanitize_ai_payload(payload: Any) -> Any:
    """Recursively sanitize sensitive attributes, binaries, and PHI from log payloads."""
    if not payload:
        return {}
    if isinstance(payload, dict):
        safe_dict = {}
        for k, v in payload.items():
            if str(k).lower() in RESTRICTED_AI_KEYS:
                safe_dict[k] = "[REDACTED]"
                continue
            if isinstance(v, (dict, list)):
                safe_dict[k] = sanitize_ai_payload(v)
            elif isinstance(v, (bytes, bytearray)):
                safe_dict[k] = f"[BYTES_LEN_{len(v)}]"
            elif isinstance(v, str) and len(v) > 500:
                safe_dict[k] = f"[TRUNCATED_STR_LEN_{len(v)}]"
            else:
                safe_dict[k] = v
        return safe_dict
    elif isinstance(payload, list):
        return [sanitize_ai_payload(item) for item in payload]
    elif isinstance(payload, (bytes, bytearray)):
        return f"[BYTES_LEN_{len(payload)}]"
    elif isinstance(payload, str) and len(payload) > 500:
        return f"[TRUNCATED_STR_LEN_{len(payload)}]"
    return payload


def log_ai_telemetry(
    provider: str,
    operation: str,
    model: str,
    request_id: str,
    duration_ms: float,
    status: str,
    http_status: int | None = None,
    error_type: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Record structured AI telemetry event without leaking sensitive data.
    """
    safe_extra = sanitize_ai_payload(extra) if extra else {}

    record = {
        "event": "AI_INFERENCE_OPERATION",
        "provider": provider,
        "operation": operation,
        "model": model,
        "request_id": request_id,
        "duration_ms": round(duration_ms, 2),
        "status": status,
        "http_status": http_status,
        "error_type": error_type,
        "details": safe_extra,
    }

    if status == "SUCCESS":
        logger.info(
            "AI CALL: %s | provider=%s | model=%s | duration=%.2fms | req_id=%s",
            operation,
            provider,
            model,
            duration_ms,
            request_id,
            extra=record,
        )
    else:
        logger.warning(
            "AI CALL FAILED: %s | provider=%s | model=%s | error=%s | req_id=%s",
            operation,
            provider,
            model,
            error_type or "UNKNOWN",
            request_id,
            extra=record,
        )
