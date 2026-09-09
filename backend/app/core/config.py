"""
NeuroOncoTrack-AI — Application Configuration

Environment variable based configuration using Pydantic Settings.
All secrets and infrastructure settings are loaded from environment variables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    APP_NAME: str = "neurooncotrack-api"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ── Database ─────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/neurooncotrack"
    DATABASE_ECHO: bool = False

    # ── Redis ────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT (RS256) ──────────────────────────────────────────
    JWT_PRIVATE_KEY_PATH: str = "keys/private.pem"
    JWT_PUBLIC_KEY_PATH: str = "keys/public.pem"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_ISSUER: str = "neurooncotrack-api"
    JWT_AUDIENCE: str = "neurooncotrack-web"
    JWT_ALGORITHM: str = "RS256"

    # ── Refresh Token ────────────────────────────────────────
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_TOKEN_COOKIE_NAME: str = "refresh_token"
    REFRESH_TOKEN_COOKIE_SECURE: bool = True
    REFRESH_TOKEN_COOKIE_SAMESITE: str = "lax"

    # ── Password Policy ──────────────────────────────────────
    PASSWORD_MIN_LENGTH: int = 12
    PASSWORD_HISTORY_COUNT: int = 5
    ARGON2_MEMORY_COST: int = 65536  # 64 MB
    ARGON2_TIME_COST: int = 3
    ARGON2_PARALLELISM: int = 4

    # ── Rate Limiting ────────────────────────────────────────
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_MINUTES: int = 15
    ACCOUNT_LOCK_DURATION_MINUTES: int = 30

    # ── MFA ──────────────────────────────────────────────────
    MFA_ISSUER_NAME: str = "NeuroOncoTrack"
    MFA_ENCRYPTION_KEY: str = ""

    # ── CORS ─────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # ── Computed Properties ──────────────────────────────────

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() in ("development", "test", "testing", "local", "dev")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    def load_jwt_private_key(self) -> str:
        """Load RSA private key from file for JWT signing."""
        path = Path(self.JWT_PRIVATE_KEY_PATH)
        if not path.exists():
            raise FileNotFoundError(
                f"JWT private key not found at {path.absolute()}. "
                "Generate with: openssl genrsa -out keys/private.pem 2048"
            )
        return path.read_text()

    def load_jwt_public_key(self) -> str:
        """Load RSA public key from file for JWT verification."""
        path = Path(self.JWT_PUBLIC_KEY_PATH)
        if not path.exists():
            raise FileNotFoundError(
                f"JWT public key not found at {path.absolute()}. "
                "Generate with: openssl rsa -in keys/private.pem -pubout -out keys/public.pem"
            )
        return path.read_text()

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v


# Singleton settings instance
settings = Settings()
