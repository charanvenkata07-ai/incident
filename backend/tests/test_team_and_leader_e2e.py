import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.audit import AuditLog

@pytest.mark.asyncio
async def test_get_my_team_operational_endpoint():
    """Verify GET /api/me/team and GET /api/employees/team return real DB structured team details."""
    async with async_session_maker() as session:
        ravi_user = (await session.execute(
            select(User).where(User.email == "ravi@incidentflow.dev")
        )).scalar_one_or_none()
        assert ravi_user is not None, "ravi@incidentflow.dev must exist"

        emp = (await session.execute(
            select(Employee).where(Employee.user_id == ravi_user.id)
        )).scalar_one_or_none()
        assert emp is not None and emp.team_id is not None

        team = await session.get(Team, emp.team_id)
        assert team is not None

    token = create_access_token(data={"sub": str(ravi_user.id), "role": ravi_user.role})
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Test /api/me/team
        res = await ac.get("/api/me/team", headers=headers)
        assert res.status_code == 200, f"Failed /api/me/team: {res.text}"
        data = res.json()

        assert data["id"] == str(team.id)
        assert data["name"] == team.name
        assert data["member_count"] >= 1
        assert "online_count" in data
        assert "available_count" in data
        assert "members" in data
        assert len(data["members"]) > 0

        # Verify members schema structure
        first_member = data["members"][0]
        assert "employee_id" in first_member
        assert "full_name" in first_member
        assert "is_present" in first_member
        assert "availability_status" in first_member

        # Test synonym /api/employees/team
        res_syn = await ac.get("/api/employees/team", headers=headers)
        assert res_syn.status_code == 200
        assert res_syn.json()["id"] == str(team.id)


@pytest.mark.asyncio
async def test_admin_teams_and_group_leader_flow():
    """
    Verify:
    1. GET /api/admin/teams contains group_leader_id and group_leader_name
    2. GET /api/admin/teams/{team_id}/group-leader returns current leader and eligible members
    3. POST /api/admin/teams/{team_id}/group-leader atomically changes leader and logs audit
    """
    async with async_session_maker() as session:
        admin_user = (await session.execute(
            select(User).where(User.role == "ADMIN")
        )).scalars().first()
        assert admin_user is not None

        # Pick active team with >= 2 members
        teams = (await session.execute(
            select(Team).where(Team.is_active == True)
        )).scalars().all()
        assert len(teams) > 0

        target_team = None
        target_members = []
        for t in teams:
            m_res = await session.execute(
                select(Employee, User).join(User, Employee.user_id == User.id).where(
                    Employee.team_id == t.id,
                    User.is_active == True,
                    User.role == "EMPLOYEE"
                )
            )
            members = m_res.all()
            if len(members) >= 2:
                target_team = t
                target_members = members
                break

        assert target_team is not None, "Need at least one team with >= 2 employees"

    admin_token = create_access_token(data={"sub": str(admin_user.id), "role": admin_user.role})
    headers = {"Authorization": f"Bearer {admin_token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. GET /api/admin/teams
        res_list = await ac.get("/api/admin/teams", headers=headers)
        assert res_list.status_code == 200
        teams_data = res_list.json()["teams"]
        matching_team = next((t for t in teams_data if t["id"] == str(target_team.id)), None)
        assert matching_team is not None
        assert "group_leader_id" in matching_team
        assert "group_leader_name" in matching_team

        # 2. GET /api/admin/teams/{team_id}/group-leader
        res_gl = await ac.get(f"/api/admin/teams/{target_team.id}/group-leader", headers=headers)
        assert res_gl.status_code == 200
        gl_data = res_gl.json()
        assert gl_data["team_id"] == str(target_team.id)
        assert "eligible_members" in gl_data
        assert len(gl_data["eligible_members"]) >= 2

        # 3. Pick a member who is NOT currently the leader, or the other member
        cur_leader_emp_id = gl_data["current_leader"]["employee_id"] if gl_data["current_leader"] else None
        new_leader_candidate = next(
            (m for m in gl_data["eligible_members"] if m["employee_id"] != cur_leader_emp_id),
            gl_data["eligible_members"][0]
        )

        # 4. POST /api/admin/teams/{team_id}/group-leader
        assign_res = await ac.post(
            f"/api/admin/teams/{target_team.id}/group-leader",
            headers=headers,
            json={
                "employee_id": new_leader_candidate["employee_id"],
                "reason": "Automated E2E shift leadership assignment"
            }
        )
        assert assign_res.status_code == 200, f"Failed assign leader: {assign_res.text}"
        assign_data = assign_res.json()
        assert assign_data["status"] == "success"
        assert assign_data["group_leader"]["employee_id"] == new_leader_candidate["employee_id"]

    # 5. Verify database invariant: exactly ONE leader for this team
    async with async_session_maker() as session:
        leaders_in_team = (await session.execute(
            select(Employee).where(
                Employee.team_id == target_team.id,
                Employee.is_group_leader == True
            )
        )).scalars().all()
        assert len(leaders_in_team) == 1, f"Expected exactly 1 leader, got {len(leaders_in_team)}"
        assert str(leaders_in_team[0].id) == new_leader_candidate["employee_id"]

        # Verify audit log
        audit = (await session.execute(
            select(AuditLog).where(
                AuditLog.action == "GROUP_LEADER_CHANGED",
                AuditLog.entity_id == target_team.id
            ).order_by(AuditLog.created_at.desc())
        )).scalars().first()
        assert audit is not None
        assert audit.new_value["group_leader_id"] == new_leader_candidate["employee_id"]


@pytest.mark.asyncio
async def test_group_leader_dm_authorization():
    """
    Verify:
    1. Normal employee messaging Admin is denied with 403 Forbidden.
    2. Group Leader messaging Admin succeeds with 200 OK.
    """
    async with async_session_maker() as session:
        admin_user = (await session.execute(
            select(User).where(User.role == "ADMIN")
        )).scalars().first()
        assert admin_user is not None

        # Find or create a non-leader employee and a group-leader employee
        leader_emp_row = (await session.execute(
            select(Employee, User).join(User, Employee.user_id == User.id).where(
                Employee.is_group_leader == True,
                User.is_active == True,
                User.role == "EMPLOYEE"
            )
        )).first()
        assert leader_emp_row is not None, "Need at least one Group Leader"
        leader_emp, leader_user = leader_emp_row

        non_leader_emp_row = (await session.execute(
            select(Employee, User).join(User, Employee.user_id == User.id).where(
                Employee.is_group_leader == False,
                User.is_active == True,
                User.role == "EMPLOYEE"
            )
        )).first()
        assert non_leader_emp_row is not None, "Need at least one non-leader Employee"
        non_leader_emp, non_leader_user = non_leader_emp_row

    transport = ASGITransport(app=app)

    # 1. Non-leader employee attempts to DM Admin
    non_leader_token = create_access_token(data={"sub": str(non_leader_user.id), "role": non_leader_user.role})
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res_denied = await ac.post(
            "/api/chat/conversations/direct",
            headers={"Authorization": f"Bearer {non_leader_token}"},
            json={"other_user_id": str(admin_user.id)}
        )
        assert res_denied.status_code == 403, f"Expected 403 Forbidden for non-leader DM to admin, got {res_denied.status_code}"

    # 2. Group Leader attempts to DM Admin
    leader_token = create_access_token(data={"sub": str(leader_user.id), "role": leader_user.role})
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res_allowed = await ac.post(
            "/api/chat/conversations/direct",
            headers={"Authorization": f"Bearer {leader_token}"},
            json={"other_user_id": str(admin_user.id)}
        )
        assert res_allowed.status_code == 200, f"Expected 200 OK for Group Leader DM to admin, got {res_allowed.status_code}"
        conv_data = res_allowed.json()
        assert conv_data["type"] == "DIRECT"


@pytest.mark.asyncio
async def test_admin_diagnostics_endpoint():
    """Verify GET /api/admin/diagnostics returns 200 OK with runtime health and CORS origins."""
    async with async_session_maker() as session:
        admin_user = (await session.execute(
            select(User).where(User.role == "ADMIN")
        )).scalars().first()
        assert admin_user is not None

    admin_token = create_access_token(data={"sub": str(admin_user.id), "role": admin_user.role})
    headers = {"Authorization": f"Bearer {admin_token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/admin/diagnostics", headers=headers)
        assert res.status_code == 200, f"Failed diagnostics: {res.text}"
        data = res.json()

        assert "backend_status" in data
        assert "database_status" in data
        assert "redis_status" in data
        assert "websocket_status" in data
        assert "active_websocket_connections" in data
        assert "cors_origins" in data
        assert isinstance(data["cors_origins"], list)
        assert len(data["cors_origins"]) >= 1
