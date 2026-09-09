"""
NeuroOncoTrack-AI — Security Module

Centralised security utilities:
  - Argon2id password hashing & verification
  - RS256 JWT creation & decoding
  - Opaque refresh token generation & hashing
  - MFA secret encryption / decryption
  - Backup code hashing
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
import pyotp
from argon2 import PasswordHasher, Type
from argon2.exceptions import HashingError, InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.exceptions import ValidationError


# ── Password Validation & Security ──────────────────────────

def validate_password(password: str) -> None:
    """
    Validate password against security policy requirements:
      - Must not be None or non-string
      - Must not be empty or whitespace only
      - Minimum length (12 characters)
      - Must contain at least one uppercase letter (A-Z)
      - Must contain at least one lowercase letter (a-z)
      - Must contain at least one digit (0-9)
      - Must contain at least one special character

    Raises ValidationError (VAL_001) if validation fails.
    Plaintext password is NEVER included in the exception message or detail.
    """
    if not isinstance(password, str) or not password:
        raise ValidationError(detail="Parola boş bırakılamaz.")

    if not password.strip():
        raise ValidationError(detail="Parola yalnızca boşluklardan oluşamaz.")

    if len(password) < settings.PASSWORD_MIN_LENGTH:
        raise ValidationError(
            detail=f"Parola en az {settings.PASSWORD_MIN_LENGTH} karakter uzunluğunda olmalıdır."
        )

    errors: list[str] = []
    if not any(c.isupper() for c in password):
        errors.append("en az bir büyük harf")
    if not any(c.islower() for c in password):
        errors.append("en az bir küçük harf")
    if not any(c.isdigit() for c in password):
        errors.append("en az bir rakam")
    if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?`~" for c in password):
        errors.append("en az bir özel karakter")

    if errors:
        raise ValidationError(
            detail=f"Parola şunları içermelidir: {', '.join(errors)}."
        )


# ── Argon2id Password Hashing ────────────────────────────────

_password_hasher = PasswordHasher(
    time_cost=settings.ARGON2_TIME_COST,
    memory_cost=settings.ARGON2_MEMORY_COST,
    parallelism=settings.ARGON2_PARALLELISM,
    hash_len=32,
    salt_len=16,
    type=Type.ID,  # Argon2id
)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    if not isinstance(plain_password, str):
        raise TypeError("Plaintext password must be a string")
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against an Argon2id hash.

    Returns True if the password matches, False otherwise.
    Never raises for incorrect or malformed passwords/hashes — prevents timing enumeration and crashes.
    """
    if not isinstance(plain_password, str) or not isinstance(hashed_password, str):
        return False
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, HashingError, InvalidHashError, ValueError):
        return False


def password_needs_rehash(hashed_password: str) -> bool:
    """Check if a password hash needs to be rehashed due to parameter changes."""
    return _password_hasher.check_needs_rehash(hashed_password)


# ── Password History & Reuse Prevention (003-C) ─────────────

def is_password_reused(
    plain_password: str,
    historical_hashes: list[str],
    limit: int = settings.PASSWORD_HISTORY_COUNT,
) -> bool:
    """
    Check if a plaintext password matches any of the last N historical password hashes.

    Parameters:
        plain_password: The new plaintext password to check.
        historical_hashes: List of previous Argon2id password hashes (ordered newest to oldest).
        limit: Number of recent history records to check (default: settings.PASSWORD_HISTORY_COUNT = 5).

    Returns:
        True if the password matches any hash in the recent history limit; False otherwise.

    Note:
        Uses verify_password() for each entry. Argon2id uses unique random salts,
        so direct string equality (==) cannot be used.
        Malformed or invalid hashes safely return False without raising uncaught exceptions.
    """
    if not isinstance(plain_password, str) or not plain_password:
        return False

    if not historical_hashes:
        return False

    # Check only up to the specified limit of recent hashes
    hashes_to_check = historical_hashes[:limit]

    for old_hash in hashes_to_check:
        if verify_password(plain_password, old_hash):
            return True

    return False


def validate_password_not_reused(
    plain_password: str,
    current_password_hash: str | None = None,
    historical_hashes: list[str] | None = None,
    limit: int = settings.PASSWORD_HISTORY_COUNT,
) -> None:
    """
    Validate that a plaintext password is not currently in use and has not been used
    in the last N (default: 5) historical passwords.

    Raises:
        ValidationError (VAL_001) if the password was previously used.
        Plaintext password is NEVER included in the exception detail or log.
    """
    all_hashes: list[str] = []
    if current_password_hash:
        all_hashes.append(current_password_hash)
    if historical_hashes:
        all_hashes.extend(historical_hashes)

    if is_password_reused(plain_password, all_hashes, limit=limit):
        raise ValidationError(
            detail=f"Yeni parola son kullanılan {limit} parola ile aynı olamaz."
        )


# ── RS256 JWT ────────────────────────────────────────────────

def create_access_token(
    subject: str,
    *,
    organization_id: str,
    role: str,
    permissions: list[str],
    mfa_verified: bool = False,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    """
    Create a signed RS256 JWT access token.

    Returns:
        tuple of (encoded_token, jti, expiration_datetime)
    """
    now = datetime.now(timezone.utc)
    jti = uuid4().hex
    expires = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "jti": jti,
        "org": str(organization_id),
        "role": role,
        "perms": permissions,
        "mfa": mfa_verified,
        "iat": now,
        "nbf": now,
        "exp": expires,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }

    if extra_claims:
        payload.update(extra_claims)

    private_key = settings.load_jwt_private_key()
    token = jwt.encode(payload, private_key, algorithm=settings.JWT_ALGORITHM)

    return token, jti, expires


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate an RS256 JWT access token.

    Validates: signature, expiration, not-before, issuer, audience, required claims.
    Strictly restricts allowed algorithms to ["RS256"] to prevent algorithm confusion attacks.
    Raises jwt.PyJWTError subtypes on any failure.
    """
    if not isinstance(token, str) or not token or token.count(".") != 2:
        raise jwt.InvalidTokenError("Invalid JWT token format")

    public_key = settings.load_jwt_public_key()
    return jwt.decode(
        token,
        public_key,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
        options={
            "require": ["sub", "jti", "org", "role", "perms", "mfa", "exp", "iss", "aud", "iat", "nbf"],
        },
    )


def create_mfa_temp_token(user_id: str) -> tuple[str, datetime]:
    """
    Create a short-lived temporary token for MFA verification flow.

    This is a JWT with a 5-minute expiration and a special purpose claim.
    Returns (token, expiration).
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=5)

    payload = {
        "sub": user_id,
        "jti": uuid4().hex,
        "purpose": "mfa_verification",
        "iat": now,
        "exp": expires,
        "iss": settings.JWT_ISSUER,
    }

    private_key = settings.load_jwt_private_key()
    token = jwt.encode(payload, private_key, algorithm=settings.JWT_ALGORITHM)

    return token, expires


def decode_mfa_temp_token(token: str) -> dict[str, Any]:
    """
    Decode a temporary MFA verification token.

    Validates purpose claim to ensure it's a legitimate MFA flow token.
    """
    public_key = settings.load_jwt_public_key()
    payload = jwt.decode(
        token,
        public_key,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        options={
            "require": ["sub", "jti", "purpose", "exp", "iss"],
            "verify_aud": False,  # MFA temp tokens have no audience
        },
    )

    if payload.get("purpose") != "mfa_verification":
        raise jwt.InvalidTokenError("Token is not an MFA verification token")

    return payload


# ── Refresh Token ────────────────────────────────────────────

def generate_refresh_token() -> str:
    """Generate a cryptographically secure opaque 256-bit refresh token."""
    return secrets.token_urlsafe(32)  # 256 bits of entropy


def hash_token(token: str) -> str:
    """
    Hash an opaque token (refresh token, reset token) using SHA-256.

    Database stores the hash, never the plaintext token.
    Raises ValueError if token is empty or non-string.
    """
    if not isinstance(token, str) or not token:
        raise ValueError("Token must be a non-empty string")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token_hash(plain_token: str, expected_hash: str) -> bool:
    """
    Verify an opaque token against its expected SHA-256 hash using constant-time comparison.

    Returns True if the token hash matches expected_hash; False otherwise.
    Never exposes plaintext token in exception messages or logs.
    """
    if not isinstance(plain_token, str) or not isinstance(expected_hash, str):
        return False
    if not plain_token or not expected_hash:
        return False
    try:
        computed_hash = hash_token(plain_token)
        return hmac.compare_digest(computed_hash, expected_hash)
    except ValueError:
        return False


# ── Secure Random Tokens ────────────────────────────────────

def generate_password_reset_token() -> str:
    """Generate a secure random token for password reset."""
    return secrets.token_urlsafe(32)


def generate_backup_codes(count: int = 10) -> list[str]:
    """
    Generate a list of MFA backup codes.

    Each code is 8 alphanumeric characters for ease of typing.
    """
    return [secrets.token_hex(4).upper() for _ in range(count)]


def hash_backup_code(code: str) -> str:
    """Hash a single backup code for safe storage."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def verify_backup_code(plain_code: str, hashed_code: str) -> bool:
    """Verify a backup code against its hash."""
    return secrets.compare_digest(
        hashlib.sha256(plain_code.encode("utf-8")).hexdigest(),
        hashed_code,
    )


# ── MFA Secret Encryption ───────────────────────────────────

def _get_fernet() -> Fernet:
    """Get Fernet instance for MFA secret encryption."""
    key = settings.MFA_ENCRYPTION_KEY
    if not key:
        raise ValueError(
            "MFA_ENCRYPTION_KEY is not configured. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_mfa_secret(secret: str) -> str:
    """Encrypt an MFA TOTP secret for database storage."""
    fernet = _get_fernet()
    return fernet.encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_mfa_secret(encrypted_secret: str) -> str:
    """Decrypt an MFA TOTP secret from database storage."""
    try:
        fernet = _get_fernet()
        return fernet.decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("Failed to decrypt MFA secret — invalid key or corrupted data")


# ── TOTP Operations ──────────────────────────────────────────

def generate_totp_secret() -> str:
    """Generate a base32 random TOTP secret."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str, issuer_name: str = "NeuroOncoTrack-AI") -> str:
    """
    Generate an otpauth:// provisioning URI for QR code generation in authenticator apps.
    """
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer_name)


def verify_totp_code(secret: str, code: str, valid_window: int = 1) -> bool:
    """
    Verify a 6-digit TOTP code against secret.

    valid_window=1 allows 30-second clock drift (checks current, previous, next 30s step).
    Returns True if valid; False otherwise.
    """
    if not isinstance(secret, str) or not isinstance(code, str):
        return False
    clean_code = code.strip()
    if not clean_code.isdigit() or len(clean_code) != 6:
        return False
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(clean_code, valid_window=valid_window)
    except Exception:
        return False

