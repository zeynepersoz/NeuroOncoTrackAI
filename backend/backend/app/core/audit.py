"""
NeuroOncoTrack-AI — Audit Logging Abstraction

Provides lightweight audit event recording abstraction for security events.
Events (e.g., CIKIS, GIRIS_BASARILI, GIRIS_BASARISIZ) are logged cleanly and persisted to the AuditLog database table.
Plaintext passwords, access tokens, refresh tokens, and keys are NEVER logged.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger("app.audit")

# Persistent structured in-memory audit store for inspection and query APIs / tests
_AUDIT_LOG_STORE: list[dict[str, Any]] = []

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "secret",
    "access_token",
    "refresh_token",
    "jwt",
    "mfa_secret",
    "totp_secret",
    "backup_code",
    "backup_codes",
    "api_key",
    "session_secret",
    "reset_token",
    "setup_token",
    "credentials",
    "key",
}


def sanitize_audit_details(details: dict[str, Any] | None) -> dict[str, Any]:
    """Recursively sanitize any sensitive credential or token keys from details dict."""
    if not details:
        return {}
    safe_details = {}
    for k, v in details.items():
        if k.lower() in SENSITIVE_KEYS:
            continue
        if isinstance(v, dict):
            safe_details[k] = sanitize_audit_details(v)
        elif isinstance(v, list):
            safe_details[k] = [
                sanitize_audit_details(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            safe_details[k] = v
    return safe_details


async def _persist_audit_log_to_db(audit_obj: AuditLog) -> None:
    """Helper to persist audit log object to DB via session maker when no active DB session was passed."""
    try:
        from app.db.session import async_session_maker
        if async_session_maker:
            async with async_session_maker() as session:
                session.add(audit_obj)
                await session.commit()
    except Exception as exc:
        logger.error("Failed to persist audit log to database: %s", exc)


def log_audit_event(
    event: str,
    user_id: uuid.UUID | str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
) -> None:
    """
    Record an audit event into logger, in-memory store, and database.
    Guarantees zero sensitive credentials or tokens are included.
    """
    safe_details = sanitize_audit_details(details)
    timestamp = datetime.now(timezone.utc)
    entry_uuid = uuid.uuid4()
    entry_id = str(entry_uuid)

    actor_str = str(user_id) if user_id else (str(safe_details.get("actor_user_id")) if safe_details.get("actor_user_id") else None)
    target_str = str(safe_details.get("target_user_id")) if safe_details.get("target_user_id") else None
    org_str = str(safe_details.get("organization_id")) if safe_details.get("organization_id") else None
    result_str = str(safe_details.get("result", "SUCCESS"))

    actor_uuid: uuid.UUID | None = None
    if actor_str:
        try:
            actor_uuid = uuid.UUID(actor_str)
        except (ValueError, TypeError):
            pass

    target_uuid: uuid.UUID | None = None
    if target_str:
        try:
            target_uuid = uuid.UUID(target_str)
        except (ValueError, TypeError):
            pass

    org_uuid: uuid.UUID | None = None
    if org_str:
        try:
            org_uuid = uuid.UUID(org_str)
        except (ValueError, TypeError):
            pass

    entry = {
        "id": entry_id,
        "event": event,
        "actor_id": actor_str,
        "target_user_id": target_str,
        "organization_id": org_str,
        "result": result_str,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "details": safe_details,
        "timestamp": timestamp,
    }

    _AUDIT_LOG_STORE.append(entry)

    logger.info(
        "AUDIT EVENT: %s | User: %s | IP: %s | UA: %s | Details: %s",
        event,
        actor_str or "anonymous",
        ip_address or "unknown",
        user_agent or "unknown",
        safe_details,
    )

    audit_obj = AuditLog(
        id=entry_uuid,
        event=event,
        actor_id=actor_uuid,
        target_user_id=target_uuid,
        organization_id=org_uuid,
        result=result_str,
        ip_address=ip_address,
        user_agent=user_agent,
        details=safe_details,
        timestamp=timestamp,
    )

    if db is not None:
        db.add(audit_obj)
    else:
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(_persist_audit_log_to_db(audit_obj))
        except RuntimeError:
            pass


async def log_audit_event_async(
    db: AsyncSession,
    event: str,
    user_id: uuid.UUID | str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Async helper to log and immediately persist audit log to DB session."""
    log_audit_event(
        event=event,
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
        db=db,
    )


def log_authorization_event(
    event: str,
    actor_id: uuid.UUID | str | None,
    target_user_id: uuid.UUID | str | None = None,
    organization_id: uuid.UUID | str | None = None,
    permission: str | None = None,
    role: str | None = None,
    result: str = "DENIED",
    ip_address: str | None = None,
    user_agent: str | None = None,
    extra_details: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
) -> None:
    """
    Standardized audit event recorder for authorization, privilege, and access control events.
    """
    details: dict[str, Any] = {
        "actor_user_id": str(actor_id) if actor_id else None,
        "target_user_id": str(target_user_id) if target_user_id else None,
        "organization_id": str(organization_id) if organization_id else None,
        "result": result,
    }
    if permission:
        details["permission"] = permission
    if role:
        details["role"] = role
    if extra_details:
        details.update(extra_details)

    log_audit_event(
        event=event,
        user_id=actor_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
        db=db,
    )


def clear_audit_log_store() -> None:
    """Utility function for clearing audit store in unit tests."""
    global _AUDIT_LOG_STORE
    _AUDIT_LOG_STORE = []


def get_audit_store() -> list[dict[str, Any]]:
    """Retrieve raw immutable list of audit entries."""
    return list(_AUDIT_LOG_STORE)
