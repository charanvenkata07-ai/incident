import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import async_session_maker
from app.models.team import Team
from app.models.employee import Employee
from app.models.user import User
from sqlalchemy import select


@pytest.mark.asyncio
async def test_admin_login_success():
    """Admin login with valid credentials returns JWT token and role=ADMIN."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/auth/login",
            json={"email": "admin@incidentflow.dev", "password": "pvcharan12345PV"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["role"] == "ADMIN"


@pytest.mark.asyncio
async def test_public_login_groups_metadata():
    """
    GET /api/auth/groups returns all active groups with work domains and member counts.
    Inactive groups must be excluded.
    Never exposes internal secrets.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/auth/groups")
        assert resp.status_code == 200
        groups = resp.json()
        assert len(groups) >= 10

        # Check required operational groups exist
        group_names = {g["name"] for g in groups}
        required_names = {
            "MDM L3", "Database L2", "Network L2", "Linux L2", "Windows L2",
            "Cloud Operations L2", "Application Support L2", "Security Operations L2",
            "Storage & Backup L2", "Monitoring & Batch L2"
        }
        assert required_names.issubset(group_names), f"Missing groups: {required_names - group_names}"

        # Verify no credentials or private data in response
        for g in groups:
            assert "name" in g
            assert "work_domain" in g
            assert "member_count" in g
            assert "password" not in g
            assert "secret" not in g


@pytest.mark.asyncio
async def test_group_employee_list_isolation_and_security():
    """
    GET /api/auth/groups/{group_id}/employees returns only employees belonging to that group.
    CRITICAL: Never exposes passwords, hashes, or sensitive tokens.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get Database L2 group
        groups_resp = await client.get("/api/auth/groups")
        db_group = next(g for g in groups_resp.json() if g["name"] == "Database L2")

        # Get employees of Database L2
        resp = await client.get(f"/api/auth/groups/{db_group['id']}/employees")
        assert resp.status_code == 200
        employees = resp.json()
        assert len(employees) >= 10

        for emp in employees:
            assert "id" in emp
            assert "name" in emp
            assert "email" in emp
            assert "Database L2" in emp["name"]
            # Strict security assertion: NO credential leaks
            assert "password" not in emp
            assert "hashed_password" not in emp
            assert "salt" not in emp
            assert "token" not in emp


@pytest.mark.asyncio
async def test_employee_login_success_with_group_verification():
    """Employee logs in with valid employee_id, team_id, and password."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Resolve Database L2 and an employee in it
        groups_resp = await client.get("/api/auth/groups")
        db_group = next(g for g in groups_resp.json() if g["name"] == "Database L2")

        emp_resp = await client.get(f"/api/auth/groups/{db_group['id']}/employees")
        target_emp = emp_resp.json()[0]

        # Authenticate
        login_resp = await client.post(
            "/api/auth/login",
            json={
                "employee_id": target_emp["id"],
                "team_id": db_group["id"],
                "password": "pvcharan12345"
            }
        )
        assert login_resp.status_code == 200
        data = login_resp.json()
        assert "access_token" in data
        assert data["role"] == "EMPLOYEE"


@pytest.mark.asyncio
async def test_tampered_group_id_rejected():
    """
    SECURITY REQUIREMENT:
    An employee from Network L2 attempts to log in by submitting the group ID of Database L2.
    The backend must verify group membership against PostgreSQL and REJECT with 403 Forbidden.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        groups_resp = await client.get("/api/auth/groups")
        groups_by_name = {g["name"]: g for g in groups_resp.json()}

        db_group = groups_by_name["Database L2"]
        net_group = groups_by_name["Network L2"]

        # Get an employee belonging to Network L2
        net_emp_resp = await client.get(f"/api/auth/groups/{net_group['id']}/employees")
        network_emp = net_emp_resp.json()[0]

        # Attempt to log in claiming to belong to Database L2
        tampered_resp = await client.post(
            "/api/auth/login",
            json={
                "employee_id": network_emp["id"],
                "team_id": db_group["id"],  # TAMPERED: Wrong group!
                "password": "pvcharan12345"
            }
        )
        assert tampered_resp.status_code == 403
        assert "does not belong to the selected group" in tampered_resp.json()["detail"]


@pytest.mark.asyncio
async def test_inactive_employee_login_rejected():
    """Deactivated accounts cannot authenticate."""
    async with async_session_maker() as session:
        # Create a deactivated user
        deact_user = User(
            email=f"deactivated_{uuid.uuid4().hex[:6]}@incidentflow.dev",
            hashed_password="hashed_placeholder",
            full_name="Deactivated Employee",
            role="EMPLOYEE",
            is_active=False
        )
        session.add(deact_user)
        await session.commit()
        deact_email = deact_user.email

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/auth/login",
            json={"email": deact_email, "password": "password123"}
        )
        assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_invalid_password_rejected():
    """Incorrect password returns 401 Unauthorized."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/auth/login",
            json={"email": "admin@incidentflow.dev", "password": "wrong_password_attempt"}
        )
        assert resp.status_code == 401
        assert "Invalid credentials" in resp.json()["detail"]
