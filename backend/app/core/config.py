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
    AI_CLASSIFICATION_RATE_LIMIT_ATTEMPTS: int = 30
    AI_CLASSIFICATION_RATE_LIMIT_WINDOW_MINUTES: int = 1
    AI_SEGMENTATION_RATE_LIMIT_ATTEMPTS: int = 10
    AI_SEGMENTATION_RATE_LIMIT_WINDOW_MINUTES: int = 1
    AI_REPORT_RATE_LIMIT_ATTEMPTS: int = 10
    AI_REPORT_RATE_LIMIT_WINDOW_MINUTES: int = 1

    # ── MFA ──────────────────────────────────────────────────
    MFA_ISSUER_NAME: str = "NeuroOncoTrack"
    MFA_ENCRYPTION_KEY: str = ""

    # ── CORS ─────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # ── AI Services ──────────────────────────────────────────
    AI_SERVICE_URL: str | None = None
    AI_SEGMENTATION_URL: str | None = None
    AI_REPORT_URL: str | None = None
    AI_API_KEY: str | None = None
    AI_CONNECT_TIMEOUT_SECONDS: float = 10.0
    AI_READ_TIMEOUT_SECONDS: float = 60.0
    AI_WRITE_TIMEOUT_SECONDS: float = 30.0
    AI_POOL_TIMEOUT_SECONDS: float = 10.0
    AI_TOTAL_TIMEOUT_SECONDS: float = 120.0
    AI_MAX_RETRIES: int = 3
    AI_RETRY_BACKOFF_FACTOR: float = 0.5

    # AI Operation Toggles
    AI_CLASSIFICATION_ENABLED: bool = True
    AI_SEGMENTATION_ENABLED: bool = True
    AI_REPORT_ENABLED: bool = True

    # AI Model Configurations
    AI_CLASSIFICATION_MODEL: str = "neuroonco-v3"
    AI_SEGMENTATION_MODEL: str = "segmentation-3d"
    AI_REPORT_MODEL: str = "report-rag"

    # Operation-specific Read Timeouts
    AI_CLASSIFICATION_READ_TIMEOUT_SECONDS: float = 30.0
    AI_SEGMENTATION_READ_TIMEOUT_SECONDS: float = 120.0
    AI_REPORT_READ_TIMEOUT_SECONDS: float = 60.0

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
