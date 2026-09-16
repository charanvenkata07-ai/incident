import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.security import get_current_user
from app.models.user import User
from uuid import uuid4

@pytest.mark.asyncio
async def test_health_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "HEALTHY"
        assert "environment" in resp.json()


@pytest.mark.asyncio
async def test_admin_authorization_rejected_for_employee():
    # Mock current user dependency with EMPLOYEE role (avoids network/DB call)
    employee_user = User(
        id=uuid4(),
        email="employee@test.com",
        full_name="Employee Test",
        role="EMPLOYEE",
        is_active=True
    )
    
    app.dependency_overrides[get_current_user] = lambda: employee_user
    
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/dashboard", headers={"Authorization": "Bearer fake_token"})
            # EMPLOYEE user accessing ADMIN-required route must get 403 Forbidden
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Not enough permissions"
    finally:
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_unauthenticated_requests_fail():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/admin/dashboard")
        # No bearer token -> 401 Unauthorized
        assert resp.status_code == 401

@pytest.mark.asyncio
async def test_employee_cannot_access_settings():
    employee_user = User(
        id=uuid4(),
        email="employee@test.com",
        full_name="Employee Test",
        role="EMPLOYEE",
        is_active=True
    )
    app.dependency_overrides[get_current_user] = lambda: employee_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/settings", headers={"Authorization": "Bearer token"})
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Not enough permissions"
    finally:
        app.dependency_overrides.clear()

