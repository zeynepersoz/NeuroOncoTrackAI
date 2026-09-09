"""
NeuroOncoTrack-AI — Config Unit Tests

Tests for app.core.config:
  - Settings loading from environment
  - Environment variable overrides
  - RSA private & public key loading from files
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings


def test_settings_loading():
    assert settings.APP_NAME == "neurooncotrack-api"
    assert settings.APP_ENV == "test"
    assert settings.JWT_ALGORITHM == "RS256"
    assert settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 15
    assert settings.REFRESH_TOKEN_EXPIRE_DAYS == 7


def test_rsa_key_loading():
    private_key = settings.load_jwt_private_key()
    public_key = settings.load_jwt_public_key()

    assert private_key is not None
    assert "BEGIN PRIVATE KEY" in private_key or "BEGIN RSA PRIVATE KEY" in private_key
    assert public_key is not None
    assert "BEGIN PUBLIC KEY" in public_key or "BEGIN RSA PUBLIC KEY" in public_key


def test_missing_rsa_key_raises_file_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "JWT_PRIVATE_KEY_PATH", str(tmp_path / "non_existent.pem"))

    with pytest.raises(FileNotFoundError, match="JWT private key not found"):
        settings.load_jwt_private_key()


def test_cors_origins_parsing():
    from app.core.config import Settings

    s1 = Settings(CORS_ORIGINS='["http://localhost:3000", "http://localhost:8000"]')
    assert s1.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:8000"]

    s2 = Settings(CORS_ORIGINS="http://localhost:3000, http://localhost:8000")
    assert s2.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:8000"]
