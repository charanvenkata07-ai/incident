import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.core.database import async_session_maker
from app.core.security import hash_password, create_access_token
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team

@pytest.mark.asyncio
async def test_admin_account_canonical_record():
    """Verify that pvcharan975@gmail.com exists ONLY as an active ADMIN account."""
    async with async_session_maker() as session:
        res = await session.execute(select(User).where(User.email == "pvcharan975@gmail.com"))
        users = res.scalars().all()
        assert len(users) == 1, "Exactly one account must exist for pvcharan975@gmail.com"

        admin = users[0]
        assert admin.role == "ADMIN", "Role must be ADMIN"
        assert admin.is_active is True, "Admin account must be active"

        # Verify no active employee record is attached to pvcharan975@gmail.com
        emp_res = await session.execute(select(Employee).where(Employee.user_id == admin.id))
        emp = emp_res.scalar_one_or_none()
        assert emp is None, "pvcharan975@gmail.com must not be linked to any employee record"

@pytest.mark.asyncio
async def test_admin_login_success():
    """Verify Admin login succeeds with pvcharan975@gmail.com and password pvcharan12345PV."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/auth/login", json={
            "email": "pvcharan975@gmail.com",
            "password": "pvcharan12345PV"
        })
        assert res.status_code == 200, f"Login failed: {res.text}"
        data = res.json()
        assert data["role"] == "ADMIN"
        assert "access_token" in data
        assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_admin_login_invalid_password():
    """Verify Admin login fails with wrong password."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/auth/login", json={
            "email": "pvcharan975@gmail.com",
            "password": "wrongpassword123"
        })
        assert res.status_code == 401

@pytest.mark.asyncio
async def test_employee_login_roster_excludes_admin():
    """Verify that public employee group rosters NEVER list pvcharan975@gmail.com."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Get all groups
        groups_res = await ac.get("/api/auth/groups")
        assert groups_res.status_code == 200
        groups = groups_res.json()

        for g in groups:
            emp_res = await ac.get(f"/api/auth/groups/{g['id']}/employees")
            assert emp_res.status_code == 200
            employees = emp_res.json()
            for emp in employees:
                assert emp["email"] != "pvcharan975@gmail.com", f"Admin email found in group {g['name']} employee roster!"

@pytest.mark.asyncio
async def test_admin_endpoints_exclude_admin_from_employee_lists():
    """Verify that /api/admin/employees and /api/admin/teams/{id}/members exclude pvcharan975@gmail.com."""
    async with async_session_maker() as session:
        admin_res = await session.execute(select(User).where(User.email == "pvcharan975@gmail.com"))
        admin = admin_res.scalar_one()

    token = create_access_token(data={"sub": str(admin.id), "role": "ADMIN"})
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        emp_res = await ac.get("/api/admin/employees", headers=headers)
        assert emp_res.status_code == 200
        emp_list = emp_res.json()
        for emp in emp_list:
            assert emp["email"] != "pvcharan975@gmail.com", "Admin email returned in employee list!"

        # Check teams
        teams_res = await ac.get("/api/admin/teams", headers=headers)
        assert teams_res.status_code == 200
        teams = teams_res.json()["teams"]
        for t in teams[:3]:
            members_res = await ac.get(f"/api/admin/teams/{t['id']}/members", headers=headers)
            assert members_res.status_code == 200
            members = members_res.json().get("members", [])
            for m in members:
                assert m["email"] != "pvcharan975@gmail.com", f"Admin email returned in team {t['name']} members!"
