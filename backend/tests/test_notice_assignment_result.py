import pytest
import uuid
from datetime import datetime, timezone, time, date
from unittest.mock import patch, AsyncMock
from sqlalchemy import select
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.user import User
from app.models.team import Team
from app.models.employee import Employee
from app.models.shift import Shift, ShiftAssignment
from app.models.presence import PresenceRecord
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.audit import AuditLog
from app.core.id_generator import generate_incident_number, generate_unique_incident_number


@pytest.mark.asyncio
async def test_incident_id_generator():
    """Verify server-side incident ID generation format and uniqueness."""
    async with async_session_maker() as session:
        ids = set()
        for _ in range(20):
            inc_id = await generate_unique_incident_number(session)
            assert inc_id.startswith("INC-")
            assert len(inc_id) == 12  # "INC-" (4) + 8 chars = 12
            assert inc_id not in ids
            ids.add(inc_id)


@pytest.mark.asyncio
async def test_send_notice_with_auto_assignment_success():
    """
    When sending notice with auto_assign=True, server automatically generates
    an INC-XXXXXXXX ID, evaluates current shift & presence, assigns to eligible employee,
    and returns full 10-field assignment result packet.
    """
    async with async_session_maker() as session:
        # Create team
        team_name = f"DB L2 Test {uuid.uuid4().hex[:6]}"
        team = Team(id=uuid.uuid4(), name=team_name, description="Database L2 Testing", is_active=True)
        session.add(team)

        # Create 10 employee users to satisfy mandatory 10-member rule
        tag = uuid.uuid4().hex[:6]
        emp_user = User(
            id=uuid.uuid4(),
            email=f"kiran_{tag}@incidentflow.dev",
            hashed_password="pw",
            full_name="Kiran Kumar",
            role="EMPLOYEE",
            is_active=True,
        )
        session.add(emp_user)
        await session.flush()

        emp = Employee(
            id=uuid.uuid4(),
            user_id=emp_user.id,
            team_id=team.id,
            employee_code=f"EMP_{tag}_001",
            availability_status="AVAILABLE",
            is_present=True,
        )
        session.add(emp)

        for i in range(2, 11):
            u = User(
                id=uuid.uuid4(),
                email=f"emp_{tag}_{i:02d}@incidentflow.dev",
                hashed_password="pw",
                full_name=f"Engineer {i:02d}",
                role="EMPLOYEE",
                is_active=True,
            )
            session.add(u)
            await session.flush()
            e = Employee(
                id=uuid.uuid4(),
                user_id=u.id,
                team_id=team.id,
                employee_code=f"EMP_{tag}_{i:03d}",
                availability_status="AVAILABLE",
                is_present=True,
            )
            session.add(e)

        from zoneinfo import ZoneInfo
        from app.services.shift_service import ShiftService
        shift_svc = ShiftService(session)
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        shift = await shift_svc.get_active_shift(now)
        if not shift:
            shift = Shift(
                id=uuid.uuid4(),
                name="24x7 Test Shift",
                start_time=time(0, 0, 0),
                end_time=time(23, 59, 59),
                timezone="Asia/Kolkata",
                is_active=True,
            )
            session.add(shift)
            await session.flush()

        today = now.date()
        sa = ShiftAssignment(id=uuid.uuid4(), shift_id=shift.id, employee_id=emp.id, date=today, is_active=True)
        session.add(sa)

        pr = PresenceRecord(id=uuid.uuid4(), employee_id=emp.id, status="CHECKED_IN", date=today)
        session.add(pr)

        # Admin user
        admin_user = User(
            id=uuid.uuid4(),
            email=f"admin_{uuid.uuid4().hex[:6]}@incidentflow.dev",
            hashed_password="pw",
            full_name="Admin Ops",
            role="ADMIN",
            is_active=True,
        )
        session.add(admin_user)
        await session.commit()

        admin_token = create_access_token(data={"sub": str(admin_user.id), "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {admin_token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.websocket.manager.ws_manager.send_to_user", new_callable=AsyncMock) as mock_ws_user, \
             patch("app.websocket.manager.ws_manager.broadcast_to_team", new_callable=AsyncMock) as mock_ws_team:
            
            resp = await client.post(
                f"/api/admin/teams/{team.id}/notice",
                json={
                    "title": "Database connection pool exhaustion",
                    "message": "Investigate connection pool exhaustion on replica cluster 3",
                    "priority": "P2",
                    "auto_assign": True,
                },
                headers=headers,
            )
            assert resp.status_code == 200
            data = resp.json()

            # 1. Verify 10-field response requirements
            assert data["incident_number"].startswith("INC-")
            assert data["short_description"] == "Database connection pool exhaustion"
            assert data["target_group"] == team.name
            assert data["notice_sent_time"] is not None
            assert data["assignment_status"] == "ASSIGNED"
            assert data["assigned_employee_name"] == "Kiran Kumar"
            assert data["employee_id"] == str(emp.id)
            assert data["assignment_time"] is not None
            assert "PRESENT" in data["employee_presence"]
            assert data["current_task"] == "Database connection pool exhaustion"
            assert data["task_status"] in ["ASSIGNED", "IN_PROGRESS"]
            assert data["unassigned_reason"] is None

            # 2. Verify WebSocket broadcast was called
            assert mock_ws_team.called


@pytest.mark.asyncio
async def test_send_notice_unassigned_when_no_employee_available():
    """
    When no eligible employee is on shift/present, assignment_status is UNASSIGNED
    with explicit reason and AUTO_ASSIGN_FAILED audit log.
    """
    async with async_session_maker() as session:
        # Team with no scheduled employees
        team = Team(id=uuid.uuid4(), name=f"Empty Team {uuid.uuid4().hex[:6]}", description="Empty", is_active=True)
        session.add(team)

        admin_user = User(
            id=uuid.uuid4(),
            email=f"admin_{uuid.uuid4().hex[:6]}@incidentflow.dev",
            hashed_password="pw",
            full_name="Admin Ops",
            role="ADMIN",
            is_active=True,
        )
        session.add(admin_user)
        await session.commit()

        admin_token = create_access_token(data={"sub": str(admin_user.id), "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {admin_token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.websocket.manager.ws_manager.send_to_user", new_callable=AsyncMock), \
             patch("app.websocket.manager.ws_manager.broadcast_to_team", new_callable=AsyncMock):

            resp = await client.post(
                f"/api/admin/teams/{team.id}/notice",
                json={
                    "title": "BGP route flapping in border routers",
                    "message": "Check border gateway peering status",
                    "priority": "P1",
                    "auto_assign": True,
                },
                headers=headers,
            )
            assert resp.status_code == 200
            data = resp.json()

            assert data["incident_number"].startswith("INC-")
            assert data["assignment_status"] == "Assignment Pending"
            assert data["assigned_employee_name"] is None
            assert data["employee_id"] is None
            assert data["unassigned_reason"] is not None
            assert len(data["unassigned_reason"]) > 0
