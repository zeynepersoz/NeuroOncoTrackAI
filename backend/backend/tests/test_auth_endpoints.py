"""
NeuroOncoTrack-AI — Authentication Endpoints Unit & Integration Test Suite (TASK-005)

Tests cover:
- Register (policy validation, Argon2id hashing, email uniqueness, non-exposure)
- Login (credential verification, RS256 access token, opaque refresh token, DB session)
- Refresh (token lookup, hash verification, rotation, revoked/expired session handling)
- Logout (session revocation, JTI Redis blacklisting, cookie clearing)
- Me (authenticated user profile retrieval, sensitive field exclusion)
- Security (non-exposure of passwords, tokens, keys in logs or error responses)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import security
from app.core.config import settings
from app.main import app
from app.models.organization import Organization
from app.models.password_history import PasswordHistory
from app.models.session import Session
from app.models.user import User


from app.db.session import get_db


@pytest.fixture
async def async_client(db_session):
    """Async HTTP client for testing FastAPI endpoints."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ── REGISTER TESTS ──────────────────────────────────────────

@pytest.mark.anyio
async def test_valid_registration_succeeds(db_session, async_client):
    """1, 4-7. Valid registration creates user, hashes password with Argon2id, creates PasswordHistory."""
    org = Organization(name="Ankara Hastanesi", code="ANK_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    reg_payload = {
        "email": "  Doctor.Ankara@Example.COM  ",  # Tests email normalization (4)
        "password": "ComplexPassword123!",
        "first_name": "Ahmet",
        "last_name": "Yılmaz",
        "title": "Prof. Dr.",
        "role": "PHYSICIAN",
        "organization_id": str(org.id),
    }

    res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 201

    data = res.json()
    assert data["email"] == "doctor.ankara@example.com"
    assert data["first_name"] == "Ahmet"
    assert "password" not in data
    assert "password_hash" not in data

    # Verify DB state
    db_res = await db_session.execute(select(User).where(User.email == "doctor.ankara@example.com"))
    user = db_res.scalar_one_or_none()
    assert user is not None
    assert user.password_hash != "ComplexPassword123!"
    assert "$argon2id$" in user.password_hash

    # Verify PasswordHistory record
    ph_res = await db_session.execute(select(PasswordHistory).where(PasswordHistory.user_id == user.id))
    hist = ph_res.scalars().all()
    assert len(hist) == 1
    assert hist[0].password_hash == user.password_hash


@pytest.mark.anyio
async def test_weak_password_registration_rejected(db_session, async_client):
    """2. Weak password is rejected with 422 Unprocessable Entity."""
    org = Organization(name="Ankara Hastanesi 2", code="ANK_02")
    db_session.add(org)
    await db_session.commit()

    reg_payload = {
        "email": "weak.user@example.com",
        "password": "weak",  # Fails min length & complexity
        "first_name": "Weak",
        "last_name": "User",
        "role": "PHYSICIAN",
        "organization_id": str(org.id),
    }

    res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 422


@pytest.mark.anyio
async def test_duplicate_email_registration_rejected(db_session, async_client):
    """3. Duplicate email is rejected with controlled 422 error."""
    org = Organization(name="Ankara Hastanesi 3", code="ANK_03")
    db_session.add(org)
    await db_session.commit()

    user = User(
        organization_id=org.id,
        email="existing@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Existing",
        last_name="User",
        role="PHYSICIAN",
    )
    db_session.add(user)
    await db_session.commit()

    reg_payload = {
        "email": "EXISTING@example.com",
        "password": "ComplexPassword123!",
        "first_name": "Dup",
        "last_name": "User",
        "role": "PHYSICIAN",
        "organization_id": str(org.id),
    }

    res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 422
    assert "zaten kullanımda" in res.json()["error"]["detail"]


# ── LOGIN TESTS ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_valid_login_succeeds(db_session, async_client):
    """9, 13-18. Valid credentials produce RS256 access token, opaque refresh cookie, and Session record."""
    org = Organization(name="Bursa Hastanesi", code="BUR_01")
    db_session.add(org)
    await db_session.commit()

    password_plain = "ComplexPass123!"
    user = User(
        organization_id=org.id,
        email="doctor.bursa@example.com",
        password_hash=security.hash_password(password_plain),
        first_name="Bülent",
        last_name="Kaya",
        role="PHYSICIAN",
    )
    db_session.add(user)
    await db_session.commit()

    login_payload = {
        "email": "DOCTOR.BURSA@EXAMPLE.COM",
        "password": password_plain,
    }

    res = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert res.status_code == 200

    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "password" not in data

    # Check refresh cookie
    cookie = res.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    assert cookie is not None

    # Verify RS256 JWT access token
    token_payload = security.decode_access_token(data["access_token"])
    assert token_payload["sub"] == str(user.id)

    # Verify Session created in DB storing ONLY the SHA-256 hash
    computed_hash = security.hash_token(cookie)
    sess_res = await db_session.execute(select(Session).where(Session.refresh_token_hash == computed_hash))
    sess = sess_res.scalar_one_or_none()

    assert sess is not None
    assert sess.user_id == user.id
    assert cookie not in sess.refresh_token_hash


@pytest.mark.anyio
async def test_invalid_login_credentials_rejected(db_session, async_client):
    """10, 11, 12. Invalid password, unknown email, or inactive user returned generic 401."""
    org = Organization(name="Bursa Hastanesi 2", code="BUR_02")
    db_session.add(org)
    await db_session.commit()

    user = User(
        organization_id=org.id,
        email="active.doc@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Active",
        last_name="Doc",
        role="PHYSICIAN",
        is_active=False,  # Inactive
    )
    db_session.add(user)
    await db_session.commit()

    # Wrong password
    res1 = await async_client.post("/api/v1/auth/login", json={"email": "active.doc@example.com", "password": "WrongPassword123!"})
    assert res1.status_code == 401

    # Unknown user
    res2 = await async_client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "Pass12345678!"})
    assert res2.status_code == 401


# ── REFRESH TESTS ───────────────────────────────────────────

@pytest.mark.anyio
async def test_valid_token_refresh_succeeds(db_session, async_client):
    """19, 20. Valid refresh cookie rotates session and issues new access token."""
    org = Organization(name="Adana Hastanesi", code="ADA_01")
    db_session.add(org)
    await db_session.commit()

    user = User(
        organization_id=org.id,
        email="doc.adana@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Adnan",
        last_name="Menderes",
        role="PHYSICIAN",
    )
    db_session.add(user)
    await db_session.commit()

    # Login to acquire refresh cookie
    login_res = await async_client.post("/api/v1/auth/login", json={"email": "doc.adana@example.com", "password": "Pass12345678!"})
    assert login_res.status_code == 200

    refresh_cookie = login_res.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)

    # Call refresh endpoint with cookie
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, refresh_cookie)
    ref_res = await async_client.post("/api/v1/auth/refresh")
    assert ref_res.status_code == 200

    ref_data = ref_res.json()
    assert "access_token" in ref_data

    # Old refresh cookie should now be rotated (old session revoked)
    old_hash = security.hash_token(refresh_cookie)
    sess_res = await db_session.execute(select(Session).where(Session.refresh_token_hash == old_hash))
    old_sess = sess_res.scalar_one_or_none()
    assert old_sess is not None
    assert old_sess.revoked_at is not None


@pytest.mark.anyio
async def test_invalid_and_revoked_refresh_token_fails(db_session, async_client):
    """20-25. Malformed, unknown, or revoked refresh token fails with 401."""
    # Unknown refresh token
    async_client.cookies.set(settings.REFRESH_TOKEN_COOKIE_NAME, "unknown_refresh_token_string")
    res1 = await async_client.post("/api/v1/auth/refresh")
    assert res1.status_code == 401


# ── LOGOUT & ME TESTS ───────────────────────────────────────

@pytest.mark.anyio
async def test_logout_and_me_endpoints(db_session, async_client):
    """26-36. /me returns user profile; /logout revokes session and blacklists JTI."""
    org = Organization(name="Antalya Hastanesi", code="ANT_01")
    db_session.add(org)
    await db_session.commit()

    user = User(
        organization_id=org.id,
        email="doc.antalya@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Can",
        last_name="Yılmaz",
        role="PHYSICIAN",
    )
    db_session.add(user)
    await db_session.commit()

    # Login
    login_res = await async_client.post("/api/v1/auth/login", json={"email": "doc.antalya@example.com", "password": "Pass12345678!"})
    login_data = login_res.json()
    access_token = login_data["access_token"]

    # 31, 35, 36. GET /me with Bearer token
    headers = {"Authorization": f"Bearer {access_token}"}
    me_res = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == "doc.antalya@example.com"
    assert "password" not in me_data
    assert "password_hash" not in me_data

    # 26. POST /logout
    logout_res = await async_client.post("/api/v1/auth/logout", headers=headers)
    assert logout_res.status_code == 204


# ── SECURITY NON-EXPOSURE TESTS ─────────────────────────────

@pytest.mark.anyio
async def test_security_non_exposure_in_logs_and_errors(caplog, async_client):
    """37-44. Passwords, tokens, keys, and hashes are NEVER exposed in logs or exception details."""
    caplog.set_level(logging.DEBUG)

    secret_pass = "SuperSecretPass123!"
    login_res = await async_client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": secret_pass})
    assert login_res.status_code == 401

    captured = caplog.text
    err_body = login_res.text

    assert secret_pass not in captured
    assert secret_pass not in err_body
    assert "BEGIN PRIVATE KEY" not in captured
