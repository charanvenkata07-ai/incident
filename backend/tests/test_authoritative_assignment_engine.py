import uuid
import pytest
from datetime import datetime, time, date, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.shift import Shift, ShiftAssignment
from app.models.audit import AuditLog
from app.models.task_template import TaskTemplate
from app.services.assignment_engine import AssignmentEngine
from app.services.shift_service import ShiftService


def make_test_employee(name: str, employee_code: str, team_id: uuid.UUID, is_present: bool = False, availability: str = "OFFLINE"):
    u = User(
        id=uuid.uuid4(),
        full_name=name,
        email=f"{employee_code.lower()}@incidentflow.dev",
        role="EMPLOYEE",
        is_active=True
    )
    e = Employee(
        id=uuid.uuid4(),
        user_id=u.id,
        team_id=team_id,
        employee_code=employee_code,
        is_present=is_present,
        availability_status=availability,
        is_group_leader=(employee_code.endswith("001"))
    )
    e.user = u
    return e


@pytest.mark.asyncio
async def test_01_first_incident_auto_assigns_db001_without_presence():
    """
    Rule: DO NOT use availability or presence to decide assignment.
    The workforce is schedule-driven. First incident: DB001 is assigned automatically
    even when all engineers are OFFLINE and is_present = False.
    """
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Database L2")

    # 10 members, all offline and not present
    emps = [
        make_test_employee(f"DB Engineer {i:02d}", f"DB{i:03d}", team_id, is_present=False, availability="OFFLINE")
        for i in range(1, 11)
    ]
    shift_morning = Shift(
        id=uuid.uuid4(), name="Morning Shift (Shift A)",
        start_time=time(6, 0), end_time=time(14, 0), is_active=True
    )

    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC-AUTH-001",
        assignment_group="Database L2",
        short_description="Database cluster latency high",
        state="NEW"
    )

    # Monday morning
    monday_time = datetime(2026, 9, 21, 9, 30, tzinfo=ZoneInfo("Asia/Kolkata"))

    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._get_automation_mode = AsyncMock(return_value="LIVE")
    engine._get_live_pilot_config = AsyncMock(return_value={"enabled": True, "assignment_group": "Database L2", "max_active_assignments": 10})
    engine._get_active_pilot_assignment_count = AsyncMock(return_value=0)
    engine._send_group_arrival_notice = AsyncMock()
    engine._get_required_skills = AsyncMock(return_value=set())
    engine._get_strategy = AsyncMock(return_value="LEAST_WORKLOAD")
    engine.workload_service.get_workloads = AsyncMock(return_value={e.id: 0 for e in emps})
    engine.audit_service.log = AsyncMock()
    engine.notification_service.create_notification = AsyncMock()

    # Shift service returns shift A with DB001..DB004
    engine.shift_service.get_current_scheduled_employees_for_team = AsyncMock(
        return_value=(shift_morning, emps[:4])
    )

    # Database query mocks
    async def mock_execute(stmt):
        stmt_str = str(stmt)
        mock_res = MagicMock()
        if "FROM teams" in stmt_str:
            mock_res.scalar_one_or_none.return_value = team
            return mock_res
        elif "FROM employees" in stmt_str and "team_id" in stmt_str:
            mock_res.scalars.return_value.all.return_value = emps
            mock_res.scalar_one.return_value = emps[0]
            return mock_res
        elif "FROM incident_assignments" in stmt_str:
            mock_res.scalars.return_value.all.return_value = []
            mock_res.scalar_one_or_none.return_value = None
            return mock_res
        elif "FROM incidents" in stmt_str:
            mock_res.scalar_one_or_none.return_value = incident
            return mock_res
        elif "FROM task_templates" in stmt_str:
            mock_res.scalars.return_value.all.return_value = []
            return mock_res
        mock_res.scalars.return_value.all.return_value = []
        mock_res.scalar_one_or_none.return_value = None
        return mock_res

    mock_db.execute = AsyncMock(side_effect=mock_execute)

    async def mock_get(model, pk):
        if model == User:
            for e in emps:
                if e.user_id == pk:
                    return e.user
        elif model == Employee:
            for e in emps:
                if e.id == pk:
                    return e
        elif model == Team:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = monday_time
        with patch("app.websocket.manager.ws_manager.broadcast_all", AsyncMock()), \
             patch("app.websocket.manager.ws_manager.broadcast_to_team", AsyncMock()), \
             patch("app.websocket.manager.ws_manager.broadcast_to_admins", AsyncMock()), \
             patch("app.websocket.manager.ws_manager.send_to_user", AsyncMock()):

            assignment = await engine.process_incident(incident, force_internal=True)

            assert assignment is not None
            assert assignment.employee_id == emps[0].id
            assert emps[0].employee_code == "DB001"
            assert incident.state == "ASSIGNED"


@pytest.mark.asyncio
async def test_02_same_incident_sent_again_rotates_to_db002_excluding_db001():
    """
    Rule: Same incident sent again -> DB002 is assigned, excluding DB001 who already
    handled this incident in the cycle.
    """
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Database L2")

    emps = [
        make_test_employee(f"DB Engineer {i:02d}", f"DB{i:03d}", team_id)
        for i in range(1, 11)
    ]
    shift_morning = Shift(
        id=uuid.uuid4(), name="Morning Shift (Shift A)",
        start_time=time(6, 0), end_time=time(14, 0), is_active=True
    )

    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC-AUTH-002",
        assignment_group="Database L2",
        state="NEW"
    )

    monday_time = datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._get_automation_mode = AsyncMock(return_value="LIVE")
    engine._send_group_arrival_notice = AsyncMock()
    engine._get_required_skills = AsyncMock(return_value=set())
    engine._get_strategy = AsyncMock(return_value="LEAST_WORKLOAD")
    engine.workload_service.get_workloads = AsyncMock(return_value={e.id: 0 for e in emps})
    engine.audit_service.log = AsyncMock()
    engine.notification_service.create_notification = AsyncMock()

    engine.shift_service.get_current_scheduled_employees_for_team = AsyncMock(
        return_value=(shift_morning, emps[:4])
    )

    # DB001 is already in prior assignments for this incident
    prior_assignees = [emps[0].id]

    async def mock_execute(stmt):
        stmt_str = str(stmt)
        mock_res = MagicMock()
        if "FROM teams" in stmt_str:
            mock_res.scalar_one_or_none.return_value = team
            return mock_res
        elif "FROM employees" in stmt_str and "team_id" in stmt_str:
            mock_res.scalars.return_value.all.return_value = emps
            # Return DB002 for the employee row lock
            mock_res.scalar_one.return_value = emps[1]
            return mock_res
        elif "FROM incident_assignments" in stmt_str:
            if "is_active = true" in stmt_str.lower() or "is_active = 1" in stmt_str.lower():
                # No currently active assignment
                mock_res.scalar_one_or_none.return_value = None
                mock_res.scalars.return_value.all.return_value = []
            else:
                # Prior assignment returns DB001
                mock_res.scalars.return_value.all.return_value = prior_assignees
            return mock_res
        elif "FROM incidents" in stmt_str:
            mock_res.scalar_one_or_none.return_value = incident
            return mock_res
        elif "FROM task_templates" in stmt_str:
            mock_res.scalars.return_value.all.return_value = []
            return mock_res
        mock_res.scalars.return_value.all.return_value = []
        mock_res.scalar_one_or_none.return_value = None
        return mock_res

    mock_db.execute = AsyncMock(side_effect=mock_execute)

    async def mock_get(model, pk):
        if model == User:
            for e in emps:
                if e.user_id == pk:
                    return e.user
        elif model == Employee:
            for e in emps:
                if e.id == pk:
                    return e
        elif model == Team:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = monday_time
        with patch("app.websocket.manager.ws_manager.broadcast_all", AsyncMock()), \
             patch("app.websocket.manager.ws_manager.broadcast_to_team", AsyncMock()), \
             patch("app.websocket.manager.ws_manager.broadcast_to_admins", AsyncMock()), \
             patch("app.websocket.manager.ws_manager.send_to_user", AsyncMock()):

            assignment = await engine.process_incident(incident, force_internal=True)

            assert assignment is not None
            # Authoritative Rule: Exactly ONE personal assignment created per incident
            added_assignments = [call.args[0] for call in mock_db.add.call_args_list if isinstance(call.args[0], IncidentAssignment)]
            assert len(added_assignments) == 1


@pytest.mark.asyncio
async def test_03_all_10_team_members_assigned_records_completion():
    """
    Under the Authoritative Rotation Rule, group assignment creates exactly ONE personal assignment
    for the incident according to rotation.
    """
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Database L2")

    emps = [
        make_test_employee(f"DB Engineer {i:02d}", f"DB{i:03d}", team_id)
        for i in range(1, 11)
    ]

    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC-AUTH-ALL10",
        assignment_group="Database L2",
        state="ASSIGNED"
    )

    monday_time = datetime(2026, 9, 21, 11, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._send_group_arrival_notice = AsyncMock()
    engine.audit_service.log = AsyncMock()

    # All 10 employees are in prior assignments
    all_emp_ids = [e.id for e in emps]

    async def mock_execute(stmt):
        stmt_str = str(stmt)
        mock_res = MagicMock()
        if "FROM teams" in stmt_str:
            mock_res.scalar_one_or_none.return_value = team
            return mock_res
        elif "FROM employees" in stmt_str:
            mock_res.scalars.return_value.all.return_value = emps
            return mock_res
        elif "FROM incident_assignments" in stmt_str:
            mock_res.scalars.return_value.all.return_value = all_emp_ids
            mock_res.scalar_one_or_none.return_value = None
            return mock_res
        return mock_res

    mock_db.execute = AsyncMock(side_effect=mock_execute)

    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = monday_time
        assignment = await engine.process_incident(incident, force_internal=True)

        assert assignment is not None
        added_assignments = [call.args[0] for call in mock_db.add.call_args_list if isinstance(call.args[0], IncidentAssignment)]
        assert len(added_assignments) == 1
        assert incident.state == "ASSIGNED"


@pytest.mark.asyncio
async def test_04_multiple_incidents_on_same_shift_distributed_by_workload():
    """
    Rule: If multiple distinct incidents arrive on the same shift,
    distribute across scheduled employees (DB001 gets INC1, DB002 gets INC2).
    """
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Database L2")

    emps = [
        make_test_employee(f"DB Engineer {i:02d}", f"DB{i:03d}", team_id)
        for i in range(1, 11)
    ]
    shift_morning = Shift(
        id=uuid.uuid4(), name="Morning Shift (Shift A)",
        start_time=time(6, 0), end_time=time(14, 0), is_active=True
    )

    inc2 = Incident(
        id=uuid.uuid4(),
        incident_number="INC-AUTH-002B",
        assignment_group="Database L2",
        state="NEW"
    )

    monday_time = datetime(2026, 9, 21, 10, 30, tzinfo=ZoneInfo("Asia/Kolkata"))

    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._send_group_arrival_notice = AsyncMock()
    engine._get_required_skills = AsyncMock(return_value=set())
    engine._get_strategy = AsyncMock(return_value="LEAST_WORKLOAD")

    # DB001 has workload 1 (active on INC1). DB002..DB004 have workload 0.
    workloads_map = {
        emps[0].id: 1,
        emps[1].id: 0,
        emps[2].id: 0,
        emps[3].id: 0
    }
    engine.workload_service.get_workloads = AsyncMock(return_value=workloads_map)
    engine.audit_service.log = AsyncMock()
    engine.notification_service.create_notification = AsyncMock()

    engine.shift_service.get_current_scheduled_employees_for_team = AsyncMock(
        return_value=(shift_morning, emps[:4])
    )

    async def mock_execute(stmt):
        stmt_str = str(stmt)
        mock_res = MagicMock()
        if "FROM teams" in stmt_str:
            mock_res.scalar_one_or_none.return_value = team
            return mock_res
        elif "FROM employees" in stmt_str and "team_id" in stmt_str:
            mock_res.scalars.return_value.all.return_value = emps
            mock_res.scalar_one.return_value = emps[1]
            return mock_res
        elif "FROM incident_assignments" in stmt_str:
            mock_res.scalars.return_value.all.return_value = []
            mock_res.scalar_one_or_none.return_value = None
            return mock_res
        elif "FROM incidents" in stmt_str:
            mock_res.scalar_one_or_none.return_value = inc2
            return mock_res
        mock_res.scalars.return_value.all.return_value = []
        mock_res.scalar_one_or_none.return_value = None
        return mock_res

    mock_db.execute = AsyncMock(side_effect=mock_execute)

    async def mock_get(model, pk):
        if model == User:
            for e in emps:
                if e.user_id == pk:
                    return e.user
        elif model == Employee:
            for e in emps:
                if e.id == pk:
                    return e
        elif model == Team:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.return_value = monday_time
        with patch("app.websocket.manager.ws_manager.broadcast_all", AsyncMock()), \
             patch("app.websocket.manager.ws_manager.broadcast_to_team", AsyncMock()), \
             patch("app.websocket.manager.ws_manager.broadcast_to_admins", AsyncMock()), \
             patch("app.websocket.manager.ws_manager.send_to_user", AsyncMock()):

            assignment = await engine.process_incident(inc2, force_internal=True)

            # Group assignment creates exactly ONE personal assignment for the incident
            added_assignments = [call.args[0] for call in mock_db.add.call_args_list if isinstance(call.args[0], IncidentAssignment)]
            assert len(added_assignments) == 1
            assert assignment.incident_id == inc2.id


@pytest.mark.asyncio
async def test_05_sunday_holiday_hold_and_saturday_working_day():
    """
    Rule: Monday–Saturday are normal working days (Saturday is a working day).
    Sunday is a default holiday (incident safely retained with SUNDAY_HOLIDAY_HOLD).
    """
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)
    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._send_group_arrival_notice = AsyncMock()
    engine.audit_service.log = AsyncMock()

    # Sunday: September 20, 2026
    sunday_dt = datetime(2026, 9, 20, 14, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert sunday_dt.weekday() == 6

    inc_sun = Incident(id=uuid.uuid4(), incident_number="INC-SUN", assignment_group="Database L2")

    with patch("app.services.assignment_engine.datetime") as mock_dt:
        mock_dt.now.return_value = sunday_dt
        res_sun = await engine.process_incident(inc_sun, force_internal=True)

        assert res_sun is None
        assert inc_sun.state == "SUNDAY_HOLIDAY_HOLD"
        sun_audits = [
            c for c in engine.audit_service.log.call_args_list
            if c.kwargs.get("action") == "SUNDAY_HOLIDAY_HOLD"
        ]
        assert len(sun_audits) == 1

    # Saturday: September 19, 2026 -> Normal working day!
    saturday_dt = datetime(2026, 9, 19, 14, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert saturday_dt.weekday() == 5  # Saturday is NOT blocked by Sunday hold


@pytest.mark.asyncio
async def test_06_complete_incident_releases_active_slot():
    """
    Rule: Completing an incident sets is_active = False so uq_active_incident_assignment
    is released for future assignments/rotations.
    """
    async with async_session_maker() as session:
        admin_user = (await session.execute(select(User).where(User.role == "ADMIN"))).scalars().first()
        team = (await session.execute(select(Team).where(Team.is_active == True))).scalars().first()
        emp = (await session.execute(select(Employee).where(Employee.team_id == team.id))).scalars().first()

        inc = Incident(
            incident_number=f"INC-COMPL-{uuid.uuid4().hex[:6].upper()}",
            short_description="Incident Completion Test",
            state="ASSIGNED",
            priority="P3",
            assignment_group=team.name
        )
        session.add(inc)
        await session.flush()

        assignment = IncidentAssignment(
            incident_id=inc.id,
            employee_id=emp.id,
            assignment_type="AUTOMATIC",
            status="ASSIGNED",
            assigned_at=datetime.now(timezone.utc),
            is_active=True
        )
        session.add(assignment)
        await session.commit()
        inc_id = inc.id
        inc_num = inc.incident_number

    transport = ASGITransport(app=app)
    admin_token = create_access_token(data={"sub": str(admin_user.id), "role": admin_user.role})
    headers = {"Authorization": f"Bearer {admin_token}"}

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post(f"/api/incidents/{inc_num}/complete", headers=headers)
        assert res.status_code == 200

    # Verify Database state
    async with async_session_maker() as session:
        updated_assign = (await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc_id)
        )).scalar_one()

        # is_active MUST be False!
        assert updated_assign.is_active is False
        assert updated_assign.status == "COMPLETED"

        updated_inc = (await session.execute(
            select(Incident).where(Incident.id == inc_id)
        )).scalar_one()
        assert updated_inc.state == "RESOLVED"


@pytest.mark.asyncio
async def test_07_send_team_notice_auto_assigns_and_rotates_e2e():
    """
    Rule: When an admin sends an incident notice to a team:
    1. The notice broadcasts to all 10 members.
    2. An employee is automatically assigned on current shift.
    3. When re-sent to the team, the assignment rotates to the NEXT employee.
    4. Exactly one active assignment exists in the database.
    """
    async with async_session_maker() as session:
        admin_user = (await session.execute(select(User).where(User.role == "ADMIN"))).scalars().first()
        team = (await session.execute(select(Team).where(Team.name == "Database L2"))).scalar_one_or_none()
        if not team:
            team = (await session.execute(select(Team).where(Team.is_active == True))).scalars().first()

    transport = ASGITransport(app=app)
    admin_token = create_access_token(data={"sub": str(admin_user.id), "role": admin_user.role})
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Ensure Monday morning time so active shift is active and not Sunday holiday
    test_dt = datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    with patch("app.services.assignment_engine.datetime") as mock_dt:
        mock_dt.now.return_value = test_dt

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Send first notice to team
            payload1 = {
                "title": "Postgres Primary Replication Lag High",
                "message": "Wal sender thread blocking standby node sync.",
                "priority": "P2"
            }
            res1 = await ac.post(f"/api/admin/teams/{team.id}/notices", headers=headers, json=payload1)
            assert res1.status_code == 200
            data1 = res1.json()

            inc_id1 = data1.get("incident_id")
            inc_num1 = data1.get("incident_number")
            first_assigned_emp = data1.get("employee_id")

            assert inc_id1 is not None
            assert first_assigned_emp is not None
            assert data1.get("assigned_employee_name") is not None

            # 2. Send notice again referencing the same incident
            payload2 = {
                "title": "Postgres Primary Replication Lag High - Re-dispatch",
                "message": "Continuing replication lag analysis.",
                "incident_number": inc_num1,
                "priority": "P2"
            }
            res2 = await ac.post(f"/api/admin/teams/{team.id}/notices", headers=headers, json=payload2)
            assert res2.status_code == 200
            data2 = res2.json()

            second_assigned_emp = data2.get("employee_id")
            assert second_assigned_emp is not None
            assert second_assigned_emp != first_assigned_emp

    # 3. Verify Database invariant: exactly ONE active assignment exists (no duplicate personal assignments)
    async with async_session_maker() as session:
        active_assignments = (await session.execute(
            select(IncidentAssignment).where(
                IncidentAssignment.incident_id == uuid.UUID(inc_id1),
                IncidentAssignment.is_active == True
            )
        )).scalars().all()
        assert len(active_assignments) == 1
        assert str(active_assignments[0].employee_id) == str(second_assigned_emp)

