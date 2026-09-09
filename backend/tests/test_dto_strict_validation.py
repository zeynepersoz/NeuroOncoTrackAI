"""
NeuroOncoTrack-AI — TASK-044 DTO Strict Validation Test Suite

Tests cover:
- Extra/unwhitelisted payload fields triggering HTTP 422 Unprocessable Entity.
- Legitimate request payloads succeeding cleanly.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import security
from app.api.deps import get_db
from app.main import app
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture
async def async_client(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def active_user(db_session):
    org = Organization(name="DTO Test Org", code="DTO_ORG_01")
    db_session.add(org)
    await db_session.commit()

    user = User(
        organization_id=org.id,
        email="dto.test@example.com",
        password_hash=security.hash_password("ValidPass123!"),
        first_name="DTO",
        last_name="Tester",
        role="PHYSICIAN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.anyio
async def test_extra_field_triggers_422_error(async_client: AsyncClient, active_user):
    """Extra unwhitelisted fields (role, is_superuser, organization_id) return HTTP 422."""
    token, _, _ = security.create_access_token(
        subject=str(active_user.id),
        role=active_user.role,
        organization_id=str(active_user.organization_id),
        permissions=["*"],
    )

    headers = {"Authorization": f"Bearer {token}"}
    extra_payload = {
        "first_name": "UpdatedName",
        "role": "SUPER_ADMIN",
        "is_superuser": True,
        "organization_id": str(uuid.uuid4()),
    }

    res = await async_client.patch("/api/v1/auth/me", json=extra_payload, headers=headers)
    assert res.status_code == 422


@pytest.mark.anyio
async def test_legitimate_payload_succeeds(async_client: AsyncClient, active_user):
    """Valid legitimate request payload succeeds (200 OK)."""
    token, _, _ = security.create_access_token(
        subject=str(active_user.id),
        role=active_user.role,
        organization_id=str(active_user.organization_id),
        permissions=["*"],
    )

    headers = {"Authorization": f"Bearer {token}"}
    valid_payload = {
        "first_name": "ValidFirst",
        "last_name": "ValidLast",
    }

    res = await async_client.patch("/api/v1/auth/me", json=valid_payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["first_name"] == "ValidFirst"
    assert res.json()["last_name"] == "ValidLast"
