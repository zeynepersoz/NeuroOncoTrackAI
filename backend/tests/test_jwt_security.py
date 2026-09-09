"""
NeuroOncoTrack-AI — Comprehensive JWT / Access Token Security Test Suite (TASK-004)

Tests cover RS256 signing, verification, claim enforcement (sub, iss, aud, exp, iat, nbf, jti),
algorithm confusion prevention (none, HS256, ES256), auth dependency validation,
and non-exposure of private keys/tokens.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select

from app.api import deps
from app.core import security
from app.core.config import settings
from app.core.exceptions import InvalidTokenError
from app.models.organization import Organization
from app.models.password_history import PasswordHistory
from app.models.session import Session
from app.models.user import User


# Helper: Generate RSA 2048 key pair for testing signature forgery
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

_fake_private_key_obj = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_fake_private_pem = _fake_private_key_obj.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode("utf-8")


# ── POSITIVE TESTS ──────────────────────────────────────────

def test_valid_user_access_token_creation():
    """1, 2, 4-10. Valid access token created with RS256 and standard claims."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    token, jti, expires = security.create_access_token(
        subject=user_id,
        organization_id=org_id,
        role="PHYSICIAN",
        permissions=["report:read", "patient:read"],
    )

    assert token is not None
    assert isinstance(token, str)
    assert jti is not None
    assert expires > datetime.now(timezone.utc)

    # Verify header algorithm is strictly RS256
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"


def test_valid_access_token_decoding():
    """3. Token can be decoded and validated successfully."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    token, jti, expires = security.create_access_token(
        subject=user_id,
        organization_id=org_id,
        role="PHYSICIAN",
        permissions=["report:read"],
    )

    payload = security.decode_access_token(token)

    assert payload["sub"] == user_id
    assert payload["org"] == org_id
    assert payload["role"] == "PHYSICIAN"
    assert payload["perms"] == ["report:read"]
    assert payload["iss"] == settings.JWT_ISSUER
    assert payload["aud"] == settings.JWT_AUDIENCE
    assert payload["jti"] == jti
    assert "iat" in payload
    assert "nbf" in payload
    assert "exp" in payload


# ── NEGATIVE TESTS ──────────────────────────────────────────

def test_expired_token_rejected():
    """12. Expired token is rejected."""
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=10)

    payload = {
        "sub": str(uuid.uuid4()),
        "jti": uuid.uuid4().hex,
        "org": str(uuid.uuid4()),
        "role": "PHYSICIAN",
        "perms": [],
        "mfa": False,
        "iat": past - timedelta(minutes=15),
        "nbf": past - timedelta(minutes=15),
        "exp": past,  # Expired 10 minutes ago
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }

    private_key = settings.load_jwt_private_key()
    expired_token = jwt.encode(payload, private_key, algorithm="RS256")

    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_access_token(expired_token)


def test_invalid_signature_rejected():
    """13. Invalid signature (signed with different RSA key) is rejected."""
    payload = {
        "sub": str(uuid.uuid4()),
        "jti": uuid.uuid4().hex,
        "org": str(uuid.uuid4()),
        "role": "PHYSICIAN",
        "perms": [],
        "mfa": False,
        "iat": datetime.now(timezone.utc),
        "nbf": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }

    # Sign with a fake untrusted private key
    forged_token = jwt.encode(payload, _fake_private_pem, algorithm="RS256")

    with pytest.raises(jwt.InvalidSignatureError):
        security.decode_access_token(forged_token)


def test_wrong_issuer_rejected():
    """14. Wrong issuer is rejected."""
    payload = {
        "sub": str(uuid.uuid4()),
        "jti": uuid.uuid4().hex,
        "org": str(uuid.uuid4()),
        "role": "PHYSICIAN",
        "perms": [],
        "mfa": False,
        "iat": datetime.now(timezone.utc),
        "nbf": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "iss": "untrusted-issuer-attacker",
        "aud": settings.JWT_AUDIENCE,
    }

    private_key = settings.load_jwt_private_key()
    wrong_iss_token = jwt.encode(payload, private_key, algorithm="RS256")

    with pytest.raises(jwt.InvalidIssuerError):
        security.decode_access_token(wrong_iss_token)


def test_wrong_audience_rejected():
    """15. Wrong audience is rejected."""
    payload = {
        "sub": str(uuid.uuid4()),
        "jti": uuid.uuid4().hex,
        "org": str(uuid.uuid4()),
        "role": "PHYSICIAN",
        "perms": [],
        "mfa": False,
        "iat": datetime.now(timezone.utc),
        "nbf": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "iss": settings.JWT_ISSUER,
        "aud": "wrong-audience-app",
    }

    private_key = settings.load_jwt_private_key()
    wrong_aud_token = jwt.encode(payload, private_key, algorithm="RS256")

    with pytest.raises(jwt.InvalidAudienceError):
        security.decode_access_token(wrong_aud_token)


def test_missing_required_claims_rejected():
    """16-20. Missing required claims (sub, exp, iss, aud, jti, nbf) are rejected."""
    required_claims = ["sub", "jti", "org", "role", "perms", "mfa", "exp", "iss", "aud", "iat", "nbf"]

    base_payload = {
        "sub": str(uuid.uuid4()),
        "jti": uuid.uuid4().hex,
        "org": str(uuid.uuid4()),
        "role": "PHYSICIAN",
        "perms": [],
        "mfa": False,
        "iat": datetime.now(timezone.utc),
        "nbf": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }

    private_key = settings.load_jwt_private_key()

    for claim_to_remove in ["sub", "jti", "exp", "iss", "aud", "nbf"]:
        incomplete_payload = base_payload.copy()
        incomplete_payload.pop(claim_to_remove)

        incomplete_token = jwt.encode(incomplete_payload, private_key, algorithm="RS256")

        with pytest.raises(jwt.MissingRequiredClaimError):
            security.decode_access_token(incomplete_token)


def test_malformed_and_empty_tokens_rejected():
    """21, 22, 26. Malformed, empty, or random strings are safely rejected."""
    invalid_tokens = [
        "",
        "not-a-jwt",
        "header.payload",
        "a.b.c.d",
        "12345",
        "!!!invalid!!!",
    ]

    for bad_token in invalid_tokens:
        with pytest.raises(jwt.InvalidTokenError):
            security.decode_access_token(bad_token)


# ── ALGORITHM CONFUSION TESTS ───────────────────────────────

def test_none_algorithm_token_rejected():
    """23, 31. 'none' algorithm token attack is strictly rejected."""
    payload = {
        "sub": str(uuid.uuid4()),
        "jti": uuid.uuid4().hex,
        "org": str(uuid.uuid4()),
        "role": "PHYSICIAN",
        "perms": [],
        "mfa": False,
        "iat": datetime.now(timezone.utc),
        "nbf": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }

    # Encode with 'none' algorithm (unassigned/unsigned token)
    none_token = jwt.encode(payload, key=None, algorithm="none")

    with pytest.raises((jwt.InvalidAlgorithmError, jwt.InvalidTokenError)):
        security.decode_access_token(none_token)


def test_hs256_algorithm_token_rejected():
    """24, 31. HS256 algorithm confusion attack is strictly rejected."""
    payload = {
        "sub": str(uuid.uuid4()),
        "jti": uuid.uuid4().hex,
        "org": str(uuid.uuid4()),
        "role": "PHYSICIAN",
        "perms": [],
        "mfa": False,
        "iat": datetime.now(timezone.utc),
        "nbf": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }

    # Attacker attempts HMAC symmetric signing using a secret key
    hs256_token = jwt.encode(payload, key="shared_secret_key_1234567890123456", algorithm="HS256")

    with pytest.raises((jwt.InvalidAlgorithmError, jwt.InvalidTokenError)):
        security.decode_access_token(hs256_token)


def test_unsupported_algorithm_rejected():
    """25. Unsupported algorithms like ES256 are rejected."""
    # We pass a fake header algorithm ES256 token
    raw_token = "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.signature"

    with pytest.raises((jwt.InvalidAlgorithmError, jwt.InvalidTokenError)):
        security.decode_access_token(raw_token)


# ── SECURITY & CONFIG TESTS ─────────────────────────────────

def test_private_key_not_logged(caplog):
    """27. Private key is never logged during token creation or decoding."""
    caplog.set_level(logging.DEBUG)

    user_id = str(uuid.uuid4())
    token, jti, _ = security.create_access_token(
        subject=user_id, organization_id=str(uuid.uuid4()), role="ADMIN", permissions=[]
    )
    security.decode_access_token(token)

    captured = caplog.text
    assert "BEGIN PRIVATE KEY" not in captured
    assert "-----BEGIN RSA PRIVATE KEY-----" not in captured


def test_jti_is_unique_per_token():
    """10, 32. JTI is unique and unpredictable across token generations."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    _, jti1, _ = security.create_access_token(subject=user_id, organization_id=org_id, role="USER", permissions=[])
    _, jti2, _ = security.create_access_token(subject=user_id, organization_id=org_id, role="USER", permissions=[])

    assert jti1 != jti2
    assert len(jti1) == 32  # hex 16 bytes uuid4


def test_config_values_applied():
    """33-36. Expiration, issuer, audience, and RSA keys are loaded from settings."""
    assert settings.JWT_ALGORITHM == "RS256"
    assert settings.JWT_ISSUER is not None
    assert settings.JWT_AUDIENCE is not None
    assert settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES > 0


# ── AUTH DEPENDENCY INTEGRATION TESTS ────────────────────────

@pytest.mark.anyio
async def test_aktif_kullanici_dependency_pass(db_session):
    """11. Valid token passes aktif_kullanici dependency."""
    org = Organization(name="İzmir Hastanesi", code="IZM_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    user = User(
        organization_id=org.id,
        email="doctor.izmir@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Mehmet",
        last_name="Demir",
        role="PHYSICIAN",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Create valid access token for this user
    token, _, _ = security.create_access_token(
        subject=str(user.id),
        organization_id=str(org.id),
        role=user.role,
        permissions=["report:read"],
    )

    # Call dependency
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    mock_request = Request(scope={"type": "http", "app": None})

    resolved_user = await deps.aktif_kullanici(request=mock_request, credentials=creds, db=db_session)

    assert resolved_user.id == user.id
    assert resolved_user.email == "doctor.izmir@example.com"


@pytest.mark.anyio
async def test_aktif_kullanici_dependency_expired_token_rejected(db_session):
    """11. Expired token in aktif_kullanici dependency raises InvalidTokenError."""
    now = datetime.now(timezone.utc)
    past = now - timedelta(minutes=10)

    payload = {
        "sub": str(uuid.uuid4()),
        "jti": uuid.uuid4().hex,
        "org": str(uuid.uuid4()),
        "role": "PHYSICIAN",
        "perms": [],
        "mfa": False,
        "iat": past - timedelta(minutes=15),
        "nbf": past - timedelta(minutes=15),
        "exp": past,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }

    private_key = settings.load_jwt_private_key()
    expired_token = jwt.encode(payload, private_key, algorithm="RS256")

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired_token)
    mock_request = Request(scope={"type": "http", "app": None})

    with pytest.raises(InvalidTokenError) as exc_info:
        await deps.aktif_kullanici(request=mock_request, credentials=creds, db=db_session)

    assert "Geçersiz veya süresi dolmuş" in exc_info.value.detail
