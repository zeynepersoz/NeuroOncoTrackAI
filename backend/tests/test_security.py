"""
NeuroOncoTrack-AI — Security Unit Tests

Tests for app.core.security:
  - Argon2id password hashing & verification
  - RS256 JWT access token creation, decoding & claim validation
  - Expired, tampered, wrong issuer / audience tokens
  - MFA Fernet secret encryption & decryption
  - Backup code generation & verification
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core import security
from app.core.config import settings


# ── Argon2id Password Hashing & Verification Tests (003-B) ──

def test_argon2id_valid_password_hashing():
    """1. Valid password can be hashed."""
    password = "ComplexPassword123!"
    hashed = security.hash_password(password)

    assert hashed is not None
    assert isinstance(hashed, str)


def test_argon2id_hash_does_not_contain_plaintext_password():
    """2. Hash does not contain plaintext password."""
    password = "ComplexPassword123!"
    hashed = security.hash_password(password)

    assert password not in hashed


def test_argon2id_hash_format():
    """3. Hash is in Argon2id format."""
    password = "ComplexPassword123!"
    hashed = security.hash_password(password)

    assert "$argon2id$" in hashed
    assert "m=65536" in hashed or f"m={settings.ARGON2_MEMORY_COST}" in hashed
    assert "t=3" in hashed or f"t={settings.ARGON2_TIME_COST}" in hashed
    assert "p=4" in hashed or f"p={settings.ARGON2_PARALLELISM}" in hashed


def test_argon2id_unique_salts_produce_different_hashes():
    """4. Same password hashed twice produces two different hashes due to random salt."""
    password = "ComplexPassword123!"
    hash1 = security.hash_password(password)
    hash2 = security.hash_password(password)

    assert hash1 != hash2
    assert security.verify_password(password, hash1) is True
    assert security.verify_password(password, hash2) is True


def test_argon2id_password_verification_success():
    """5. First hash verifies with correct password."""
    password = "ComplexPassword123!"
    hashed = security.hash_password(password)

    assert security.verify_password(password, hashed) is True


def test_argon2id_password_verification_failure():
    """6. Incorrect password fails verification."""
    password = "ComplexPassword123!"
    wrong_password = "WrongPassword123!"
    hashed = security.hash_password(password)

    assert security.verify_password(wrong_password, hashed) is False


def test_argon2id_empty_and_invalid_inputs_handled():
    """7. Empty/invalid password input handles correctly."""
    assert security.verify_password("", "sample_hash") is False
    assert security.verify_password("ComplexPass1!", "") is False
    assert security.verify_password(None, "sample_hash") is False  # type: ignore[arg-type]
    assert security.verify_password("ComplexPass1!", None) is False  # type: ignore[arg-type]


def test_argon2id_malformed_hash_does_not_crash_application():
    """8. Malformed password hash does not cause application crash during verification."""
    password = "ComplexPassword123!"
    malformed_hashes = [
        "invalid_hash_string",
        "$argon2id$v=19$m=65536,t=3,p=4$invalidbase64salt$invalidbase64hash",
        "$argon2i$v=19$m=4096,t=3,p=1$c2FsdHNhbHQ$hash",
        "12345",
        "!!!corrupted!!!",
    ]

    for bad_hash in malformed_hashes:
        assert security.verify_password(password, bad_hash) is False


def test_argon2id_hash_output_is_string():
    """9. Hash output is string."""
    hashed = security.hash_password("ComplexPassword123!")
    assert type(hashed) is str


def test_argon2id_hashing_does_not_log_plaintext_password(caplog):
    """10. Password hash operation does not log the plaintext password."""
    import logging
    caplog.set_level(logging.DEBUG)

    secret_password = "SuperSecretPassword123!"
    security.hash_password(secret_password)

    captured_logs = caplog.text
    assert secret_password not in captured_logs


def test_password_needs_rehash():
    password = "ComplexPassword123!"
    hashed = security.hash_password(password)

    # Hashes created with current parameters should not need rehash
    assert security.password_needs_rehash(hashed) is False


# ── RS256 JWT Access Token Tests ─────────────────────────────

def test_rs256_access_token_creation_and_decoding():
    subject = "user_123"
    org_id = "org_456"
    role = "PHYSICIAN"
    perms = ["patient:read", "report:approve"]

    token, jti, expires = security.create_access_token(
        subject,
        organization_id=org_id,
        role=role,
        permissions=perms,
        mfa_verified=True,
    )

    assert token is not None
    assert isinstance(token, str)
    assert jti is not None
    assert expires > datetime.now(timezone.utc)

    # Decode token
    payload = security.decode_access_token(token)

    assert payload["sub"] == subject
    assert payload["jti"] == jti
    assert payload["org"] == org_id
    assert payload["role"] == role
    assert payload["perms"] == perms
    assert payload["mfa"] is True
    assert payload["iss"] == settings.JWT_ISSUER
    assert payload["aud"] == settings.JWT_AUDIENCE


def test_jwt_expired_token():
    # Artificially create token that expired 5 minutes ago
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": "user_123",
        "jti": "test_jti",
        "org": "org_456",
        "role": "PHYSICIAN",
        "perms": [],
        "mfa": True,
        "iat": now - timedelta(minutes=20),
        "nbf": now - timedelta(minutes=20),
        "exp": now - timedelta(minutes=5),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }
    private_key = settings.load_jwt_private_key()
    token = jwt.encode(expired_payload, private_key, algorithm="RS256")

    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_access_token(token)


def test_jwt_invalid_signature():
    token, _, _ = security.create_access_token(
        "user_123",
        organization_id="org_456",
        role="PHYSICIAN",
        permissions=[],
    )

    # Tamper with token header/payload
    tampered_token = token[:-10] + "0000000000"

    with pytest.raises(jwt.PyJWTError):
        security.decode_access_token(tampered_token)


def test_jwt_invalid_issuer():
    now = datetime.now(timezone.utc)
    bad_issuer_payload = {
        "sub": "user_123",
        "jti": "test_jti",
        "org": "org_456",
        "role": "PHYSICIAN",
        "perms": [],
        "mfa": True,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=15),
        "iss": "invalid-issuer-api",
        "aud": settings.JWT_AUDIENCE,
    }
    private_key = settings.load_jwt_private_key()
    token = jwt.encode(bad_issuer_payload, private_key, algorithm="RS256")

    with pytest.raises(jwt.InvalidIssuerError):
        security.decode_access_token(token)


def test_jwt_invalid_audience():
    now = datetime.now(timezone.utc)
    bad_aud_payload = {
        "sub": "user_123",
        "jti": "test_jti",
        "org": "org_456",
        "role": "PHYSICIAN",
        "perms": [],
        "mfa": True,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=15),
        "iss": settings.JWT_ISSUER,
        "aud": "wrong-web-client",
    }
    private_key = settings.load_jwt_private_key()
    token = jwt.encode(bad_aud_payload, private_key, algorithm="RS256")

    with pytest.raises(jwt.InvalidAudienceError):
        security.decode_access_token(token)


# ── MFA Fernet Secret Encryption Tests ──────────────────────

def test_mfa_secret_encryption_and_decryption():
    secret = "JBSWY3DPEHPK3PXP"  # Sample Base32 TOTP secret

    encrypted = security.encrypt_mfa_secret(secret)
    assert encrypted is not None
    assert encrypted != secret

    decrypted = security.decrypt_mfa_secret(encrypted)
    assert decrypted == secret


def test_mfa_secret_decryption_failure():
    with pytest.raises(ValueError, match="Failed to decrypt MFA secret"):
        security.decrypt_mfa_secret("invalid_encrypted_data")


# ── Backup Code Generation and Verification Tests ─────────────

def test_backup_code_generation_and_verification():
    codes = security.generate_backup_codes(count=10)

    assert len(codes) == 10
    assert all(len(c) == 8 for c in codes)
    assert len(set(codes)) == 10  # All unique

    sample_code = codes[0]
    hashed_code = security.hash_backup_code(sample_code)

    assert security.verify_backup_code(sample_code, hashed_code) is True
    assert security.verify_backup_code("WRONGCOD", hashed_code) is False
