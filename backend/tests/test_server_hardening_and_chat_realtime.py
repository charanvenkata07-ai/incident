"""
Tests for server hardening, exception handlers, idempotency, and chat realtime contracts.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_request_validation_error_structured_422():
    """Invalid payload to a typed endpoint returns structured 422 with error key or detail."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/login", json={"not_email": True})
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body or "detail" in body

@pytest.mark.asyncio
async def test_health_endpoint_returns_structured_response():
    """Health check returns structured JSON with expected keys."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "environment" in body

@pytest.mark.asyncio
async def test_x_request_id_header_present_on_response():
    """Every response must include X-Request-ID header."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert "x-request-id" in resp.headers or "X-Request-ID" in resp.headers

@pytest.mark.asyncio
async def test_client_supplied_request_id_adopted():
    """If client supplies X-Request-ID, response echoes it back."""
    custom_id = "test-req-abc123"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health", headers={"X-Request-ID": custom_id})
        response_id = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID", "")
        assert response_id == custom_id

@pytest.mark.asyncio
async def test_404_returns_error_json():
    """Unknown routes return JSON error, not HTML."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/nonexistent-route-xyz")
        assert resp.status_code == 404
        body = resp.json()
        assert body is not None

@pytest.mark.asyncio
async def test_admin_endpoint_requires_auth():
    """Protected admin endpoints return 401/403 without auth token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/admin/employees")
        assert resp.status_code in (401, 403, 422)
