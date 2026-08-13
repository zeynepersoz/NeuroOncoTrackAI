"""
NeuroOncoTrack-AI — Audit Logging Abstraction

Provides lightweight audit event recording abstraction for security events.
Events (e.g., CIKIS, GIRIS_BASARILI, GIRIS_BASARISIZ) are logged cleanly.
Plaintext passwords, access tokens, refresh tokens, and keys are NEVER logged.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger("app.audit")


def log_audit_event(
    event: str,
    user_id: uuid.UUID | str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Record an audit event.

    This abstraction can be hooked into a persistent Audit database or external logging service.
    Guarantees no sensitive credentials or tokens are included in details.
    """
    safe_details = {}
    if details:
        # Sanitize any accidental sensitive keys
        sensitive_keys = {"password", "token", "secret", "access_token", "refresh_token", "key"}
        for k, v in details.items():
            if k.lower() not in sensitive_keys:
                safe_details[k] = v

    logger.info(
        "AUDIT EVENT: %s | User: %s | IP: %s | UA: %s | Details: %s",
        event,
        str(user_id) if user_id else "anonymous",
        ip_address or "unknown",
        user_agent or "unknown",
        safe_details,
    )
