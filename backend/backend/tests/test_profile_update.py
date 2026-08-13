"""
NeuroOncoTrack-AI — Profile Update API Endpoints & Authorization Tests (TASK-011)

Tests cover:
- Test 1: Update first_name successfully
- Test 2: Update multiple permitted profile fields (first_name, last_name, title) preserving untouched fields
- Test 3: Update email to unused normalized email
- Test 4: Invalid email format rejection (422 Unprocessable Entity)
- Test 5: Empty PATCH payload handling (200 OK with unchanged profile)
- Test 6: Profile update unauthorized rejection (no Auth header -> 401)
- Test 7: Profile update invalid Bearer token rejection (401)
- Test 8: Forbidden field protection: cannot update role
- Test 9: Forbidden field protection: cannot update permissions
- Test 10: Forbidden field protection: cannot update organization_id
- Test 11: Forbidden field protection: cannot update account status (is_active)
- Test 12: Forbidden field protection: cannot update MFA status (mfa_enabled)
- Test 13: Forbidden field protection: cannot update system fields (id)
- Test 14: Email uniqueness conflict rejection when using another user's email
- Test 15: Same email update succeeds without conflict
- Test 16: Email case normalization (converted to lowercase)
- Test 17: IDOR protection (cannot target or modify another user's profile)
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import security
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture
async def async_client(db_session, mock_redis):
    """Async HTTP client for testing FastAPI endpoints with DB session and FakeRedis."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.state.redis = mock_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    if hasattr(app.state, "redis"):
        delattr(app.state, "redis")


@pytest.fixture
async def test_org(db_session):
    org = Organization(name="Profile Test Hastanesi", code="PROFILE_ORG_01")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def user_main(db_session, test_org):
    user = User(
        organization_id=test_org.id,
        email="profile.main@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Ahmet",
        last_name="Yılmaz",
        title="Dr.",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def user_other(db_session, test_org):
    user = User(
        organization_id=test_org.id,
        email="profile.other@example.com",
        password_hash=security.hash_password("Pass12345678!"),
        first_name="Mehmet",
        last_name="Kaya",
        title="Doç. Dr.",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ── TEST 1: UPDATE FIRST NAME ──────────────────────────────────

@pytest.mark.anyio
async def test_update_first_name(db_session, async_client, user_main):
    """PATCH /api/v1/auth/me updates first_name and persists change to DB."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"first_name": "Ali"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["first_name"] == "Ali"

    await db_session.refresh(user_main)
    assert user_main.first_name == "Ali"


# ── TEST 2: UPDATE MULTIPLE PROFILE FIELDS ────────────────────

@pytest.mark.anyio
async def test_update_multiple_profile_fields(db_session, async_client, user_main):
    """PATCH /api/v1/auth/me updates multiple fields while preserving untouched fields."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"first_name": "Kemal", "last_name": "Demir", "title": "Prof. Dr."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["first_name"] == "Kemal"
    assert data["last_name"] == "Demir"
    assert data["title"] == "Prof. Dr."
    assert data["email"] == "profile.main@example.com"  # Untouched
    assert data["role"] == "PHYSICIAN"                  # Untouched


# ── TEST 3: UPDATE EMAIL ──────────────────────────────────────

@pytest.mark.anyio
async def test_update_email(db_session, async_client, user_main):
    """PATCH /api/v1/auth/me updates email to an unused normalized email."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"email": "new.email@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["email"] == "new.email@example.com"

    await db_session.refresh(user_main)
    assert user_main.email == "new.email@example.com"


# ── TEST 4: INVALID PROFILE FIELDS ────────────────────────────

@pytest.mark.anyio
async def test_invalid_profile_fields(async_client, user_main):
    """Invalid email format in payload returns 422 Unprocessable Entity."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"email": "not-an-email"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


# ── TEST 5: EMPTY PATCH ───────────────────────────────────────

@pytest.mark.anyio
async def test_empty_patch(async_client, user_main):
    """PATCH /api/v1/auth/me with empty json payload returns 200 OK with unchanged profile."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["email"] == "profile.main@example.com"


# ── TEST 6 & 7: AUTHENTICATION FAILURES ───────────────────────

@pytest.mark.anyio
async def test_profile_update_unauthorized(async_client):
    """PATCH /api/v1/auth/me without Authorization header returns 401 Unauthorized."""
    res = await async_client.patch("/api/v1/auth/me", json={"first_name": "Test"})
    assert res.status_code == 401


@pytest.mark.anyio
async def test_profile_update_invalid_token(async_client):
    """PATCH /api/v1/auth/me with invalid Bearer token returns 401 Unauthorized."""
    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"first_name": "Test"},
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    assert res.status_code == 401


# ── TESTS 8-13: FORBIDDEN FIELDS PROTECTION ───────────────────

@pytest.mark.anyio
async def test_cannot_update_role(db_session, async_client, user_main):
    """Attempting to update 'role' through /auth/me is ignored and does not alter role."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"role": "SUPER_ADMIN", "first_name": "Hakki"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "PHYSICIAN"
    assert res.json()["first_name"] == "Hakki"

    await db_session.refresh(user_main)
    assert user_main.role == "PHYSICIAN"


@pytest.mark.anyio
async def test_cannot_update_permissions(db_session, async_client, user_main):
    """Attempting to update 'extra_permissions' or 'permissions' is ignored."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"permissions": ["system:all"], "extra_permissions": ["system:all"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert "system:all" not in res.json()["permissions"]


@pytest.mark.anyio
async def test_cannot_update_organization(db_session, async_client, user_main):
    """Attempting to update 'organization_id' is ignored and org remains unchanged."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"organization_id": "00000000-0000-0000-0000-000000000000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["organization_id"] == str(user_main.organization_id)


@pytest.mark.anyio
async def test_cannot_update_account_status(db_session, async_client, user_main):
    """Attempting to update 'is_active' is ignored."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    await db_session.refresh(user_main)
    assert user_main.is_active is True


@pytest.mark.anyio
async def test_cannot_update_mfa_fields(db_session, async_client, user_main):
    """Attempting to update 'mfa_enabled' or 'mfa_secret' is ignored."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"mfa_enabled": True, "mfa_secret": "fake_secret"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    await db_session.refresh(user_main)
    assert user_main.mfa_enabled is False


@pytest.mark.anyio
async def test_cannot_update_system_fields(db_session, async_client, user_main):
    """Attempting to update 'id' is ignored."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"id": "00000000-0000-0000-0000-000000000000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["id"] == str(user_main.id)


# ── TEST 14: EMAIL UNIQUENESS CONFLICT ────────────────────────

@pytest.mark.anyio
async def test_email_uniqueness_conflict(async_client, user_main, user_other):
    """Attempting to update email to another existing user's email fails with validation error."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"email": "profile.other@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422
    assert "başka bir kullanıcı" in res.json()["error"]["detail"]


# ── TEST 15: SAME EMAIL DOES NOT CONFLICT ─────────────────────

@pytest.mark.anyio
async def test_same_email_does_not_conflict(async_client, user_main):
    """Updating to user's own email succeeds without a false uniqueness conflict."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"email": "profile.main@example.com", "first_name": "Can"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["first_name"] == "Can"
    assert res.json()["email"] == "profile.main@example.com"


# ── TEST 16: EMAIL CASE NORMALIZATION ─────────────────────────

@pytest.mark.anyio
async def test_email_case_normalization(db_session, async_client, user_main):
    """Updating email with mixed uppercase letters normalizes email to lowercase."""
    token, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"email": "PROFILE.MAIN.UPDATED@EXAMPLE.COM"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["email"] == "profile.main.updated@example.com"

    await db_session.refresh(user_main)
    assert user_main.email == "profile.main.updated@example.com"


# ── TEST 17: IDOR PROTECTION ─────────────────────────────────

@pytest.mark.anyio
async def test_profile_update_cannot_target_another_user(db_session, async_client, user_main, user_other):
    """Client cannot submit another user ID to modify another user's profile (IDOR protection)."""
    token_main, _, _ = security.create_access_token(
        subject=str(user_main.id),
        organization_id=str(user_main.organization_id),
        role=user_main.role,
        permissions=[],
    )

    # Attempt to send user_other.id in payload
    res = await async_client.patch(
        "/api/v1/auth/me",
        json={"user_id": str(user_other.id), "id": str(user_other.id), "first_name": "HackedName"},
        headers={"Authorization": f"Bearer {token_main}"},
    )
    assert res.status_code == 200

    # User main is updated
    await db_session.refresh(user_main)
    assert user_main.first_name == "HackedName"

    # User other remains untouched
    await db_session.refresh(user_other)
    assert user_other.first_name == "Mehmet"
