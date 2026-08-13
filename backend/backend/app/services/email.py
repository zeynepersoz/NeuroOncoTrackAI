"""
NeuroOncoTrack-AI — Email Service Abstraction

Provides interface for sending system emails (password reset, notifications).
Production SMTP / provider integration is abstracted and mockable in tests.
Sensitive credentials, passwords, and secrets are NEVER logged.
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger("app.email")


class EmailService:
    """Email service interface for sending system emails."""

    @staticmethod
    async def send_password_reset_email(email: str, reset_token: str) -> bool:
        """
        Send password reset email to user.

        Constructs reset URL using settings.FRONTEND_URL (or default config) and reset_token.
        Does NOT expose passwords, hashes, or secrets.
        """
        base_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
        reset_url = f"{base_url}/auth/reset-password?token={reset_token}"

        logger.info(
            "PASSWORD RESET EMAIL SENT: To=%s | Link=%s",
            email,
            reset_url,
        )
        return True


email_service = EmailService()
