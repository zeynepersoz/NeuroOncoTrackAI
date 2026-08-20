"""
NeuroOncoTrack-AI — TASK-043 Production Security Headers Test Suite

Tests cover:
- Verification of production security headers on API responses:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Referrer-Policy: strict-origin-when-cross-origin
  - Content-Security-Policy: default-src 'self'; frame-ancestors 'none';
- HSTS behavior: Strict-Transport-Security enabled when HTTPS, skipped for HTTP local development.
- Path-scoped CSP for /docs: Allows Swagger UI CDN assets & inline scripts on /docs without relaxing global API CSP.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def async_https_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        yield client


@pytest.mark.anyio
async def test_production_security_headers_present(async_client: AsyncClient):
    """Verify security headers are returned on API endpoints."""
    res = await async_client.get("/health/liveness")
    assert res.status_code == 200

    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert headers.get("Content-Security-Policy") == "default-src 'self'; frame-ancestors 'none';"


@pytest.mark.anyio
async def test_docs_endpoint_has_path_scoped_csp(async_client: AsyncClient):
    """Verify GET /docs returns HTTP 200 and permits Swagger UI CDN assets and inline script in CSP."""
    res = await async_client.get("/docs")
    assert res.status_code == 200

    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    csp = headers.get("Content-Security-Policy", "")
    assert "https://cdn.jsdelivr.net" in csp
    assert "'unsafe-inline'" in csp
    assert "https://fastapi.tiangolo.com" in csp
    assert "frame-ancestors 'none'" in csp


@pytest.mark.anyio
async def test_standard_api_maintains_strict_csp(async_client: AsyncClient):
    """Verify standard API endpoints maintain strict default-src 'self' CSP without external origins."""
    res = await async_client.get("/health")
    assert res.status_code in (200, 503)

    csp = res.headers.get("Content-Security-Policy", "")
    assert csp == "default-src 'self'; frame-ancestors 'none';"
    assert "cdn.jsdelivr.net" not in csp
    assert "unsafe-inline" not in csp


@pytest.mark.anyio
async def test_hsts_header_on_https_request(async_https_client: AsyncClient):
    """Verify Strict-Transport-Security is present on HTTPS requests."""
    res = await async_https_client.get("/health/liveness")
    assert res.status_code == 200

    headers = res.headers
    assert "Strict-Transport-Security" in headers
    assert "max-age=31536000" in headers["Strict-Transport-Security"]


@pytest.mark.anyio
async def test_hsts_skipped_on_local_http(async_client: AsyncClient):
    """Verify HSTS does not break local HTTP dev testing."""
    res = await async_client.get("/health/liveness")
    assert res.status_code == 200
    assert "Strict-Transport-Security" not in res.headers
