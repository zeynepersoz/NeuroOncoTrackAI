"""
NeuroOncoTrack-AI — TASK-041 Persistent Database Audit Logging Test Suite

Tests cover:
- Audit event creation and database persistence in AuditLog table.
- Sensitive credential/token sanitization in AuditLog.details JSON.
- Audit inspection endpoints reading directly from DB.
- Tenant isolation enforcement on audit log endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import audit, security
from app.api.deps import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture
async def async_client(db_session):
    """Async HTTP client for testing FastAPI endpoints."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def org_a(db_session):
    org = Organization(name="Hospital Alpha", code="ALPHA_01")
    db_session.add(org)
    await db_session.commit()
    return org


@pytest.fixture
async def org_b(db_session):
    org = Organization(name="Hospital Beta", code="BETA_01")
    db_session.add(org)
    await db_session.commit()
    return org


@pytest.fixture
async def super_admin(db_session, org_a):
    user = User(
        organization_id=org_a.id,
        email="super.audit@example.com",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Super",
        last_name="Admin",
        role="SUPER_ADMIN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def hospital_admin_a(db_session, org_a):
    user = User(
        organization_id=org_a.id,
        email="admin.alpha@example.com",
        password_hash=security.hash_password("SuperSecret123!"),
        first_name="Alpha",
        last_name="Admin",
        role="HOSPITAL_ADMIN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.anyio
async def test_audit_event_database_persistence(db_session):
    """Test 1: Logging an audit event persists an AuditLog row to the database."""
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    audit.log_audit_event(
        event="TEST_PERSIST_EVENT",
        user_id=user_id,
        ip_address="192.168.1.100",
        user_agent="TestRunner/1.0",
        details={"action": "test_persistence", "organization_id": str(org_id)},
        db=db_session,
    )
    await db_session.commit()

    res = await db_session.execute(select(AuditLog).where(AuditLog.event == "TEST_PERSIST_EVENT"))
    log_record = res.scalar_one_or_none()

    assert log_record is not None
    assert log_record.event == "TEST_PERSIST_EVENT"
    assert str(log_record.actor_id) == str(user_id)
    assert str(log_record.organization_id) == str(org_id)
    assert log_record.ip_address == "192.168.1.100"
    assert log_record.user_agent == "TestRunner/1.0"
    assert log_record.details["action"] == "test_persistence"


@pytest.mark.anyio
async def test_sensitive_data_sanitization_in_db(db_session):
    """Test 2: Sensitive keys (password, token, mfa_secret, etc.) are stripped before DB persistence."""
    sensitive_payload = {
        "password": "plain_password_123",
        "password_hash": "argon2_hash",
        "access_token": "jwt.access.token",
        "refresh_token": "opaque_refresh",
        "mfa_secret": "JBSWY3DPEHPK3PXP",
        "totp_secret": "secret123",
        "safe_field": "visible_metadata",
    }

    audit.log_audit_event(
        event="SENSITIVE_TEST_EVENT",
        details=sensitive_payload,
        db=db_session,
    )
    await db_session.commit()

    res = await db_session.execute(select(AuditLog).where(AuditLog.event == "SENSITIVE_TEST_EVENT"))
    log_record = res.scalar_one_or_none()

    assert log_record is not None
    stored_details = log_record.details or {}

    assert "safe_field" in stored_details
    assert stored_details["safe_field"] == "visible_metadata"

    for sensitive_key in ("password", "password_hash", "access_token", "refresh_token", "mfa_secret", "totp_secret"):
        assert sensitive_key not in stored_details


@pytest.mark.anyio
async def test_audit_api_reads_from_database(async_client, db_session, super_admin):
    """Test 3: /api/v1/admin/audit-logs reads directly from DB entries."""
    audit_uuid = uuid.uuid4()
    audit_log = AuditLog(
        id=audit_uuid,
        event="DB_READ_TEST_EVENT",
        actor_id=super_admin.id,
        organization_id=super_admin.organization_id,
        result="SUCCESS",
        ip_address="10.0.0.1",
        details={"module": "forensics"},
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(audit_log)
    await db_session.commit()

    token, _, _ = security.create_access_token(
        subject=str(super_admin.id),
        role=super_admin.role,
        organization_id=str(super_admin.organization_id),
        permissions=["*"],
    )

    headers = {"Authorization": f"Bearer {token}"}
    res = await async_client.get("/api/v1/admin/audit-logs?search=DB_READ_TEST_EVENT", headers=headers)
    assert res.status_code == 200

    data = res.json()
    assert data["total"] >= 1
    found_events = [item["event"] for item in data["items"]]
    assert "DB_READ_TEST_EVENT" in found_events


@pytest.mark.anyio
async def test_audit_tenant_isolation(async_client, db_session, hospital_admin_a, org_b):
    """Test 4: HOSPITAL_ADMIN cannot view audit logs belonging to another organization."""
    # Log event for Org B
    audit_log_b = AuditLog(
        id=uuid.uuid4(),
        event="ORG_B_CONFIDENTIAL_EVENT",
        organization_id=org_b.id,
        result="SUCCESS",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(audit_log_b)
    await db_session.commit()

    # HOSPITAL_ADMIN A token
    token_a, _, _ = security.create_access_token(
        subject=str(hospital_admin_a.id),
        role=hospital_admin_a.role,
        organization_id=str(hospital_admin_a.organization_id),
        permissions=["user:read", "audit:read"],
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Query audit logs as Hospital Admin A
    res = await async_client.get("/api/v1/admin/audit-logs", headers=headers_a)
    assert res.status_code == 200

    data = res.json()
    for item in data["items"]:
        if item.get("organization_id"):
            assert str(item["organization_id"]) == str(hospital_admin_a.organization_id)
        assert item["event"] != "ORG_B_CONFIDENTIAL_EVENT"
