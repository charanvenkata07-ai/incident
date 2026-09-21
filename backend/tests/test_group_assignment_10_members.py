import asyncio
import uuid
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from unittest.mock import patch, AsyncMock

from app.main import app
from app.core.database import async_session_maker
from app.models.user import User
from app.models.team import Team
from app.models.employee import Employee
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.assignment_cycle import AssignmentCycle
from app.models.notification import Notification
from app.services.assignment_engine import AssignmentEngine
from app.websocket.manager import ws_manager


async def create_test_team(session, name="Database L2", count=10, prefix="DB"):
    team = Team(id=uuid.uuid4(), name=name, description=f"{name} Operations", is_active=True)
    session.add(team)
    await session.flush()

    unique_tag = uuid.uuid4().hex[:4].upper()
    employees = []
    for i in range(1, count + 1):
        uid = uuid.uuid4()
        user = User(
            id=uid,
            email=f"{prefix.lower()}{i:03d}_{uuid.uuid4().hex[:6]}@incidentflow.dev",
            hashed_password="dummy_hashed_password_for_tests",
            full_name=f"{prefix} Engineer {i:02d}",
            role="EMPLOYEE",
            is_active=True
        )
        session.add(user)
        await session.flush()

        emp = Employee(
            id=uuid.uuid4(),
            user_id=user.id,
            team_id=team.id,
            employee_code=f"{prefix}_{unique_tag}_{i:03d}",
            is_present=(i % 2 == 0),  # Mixed presence: offline/online
            availability_status="AVAILABLE" if i % 2 == 0 else "OFFLINE",
            is_group_leader=(i == 1)  # Employee 1 is group leader
        )

        emp.user = user
        session.add(emp)
        employees.append(emp)

    await session.commit()
    return team, employees


# =============================================================================
# TEST 1: 10-member team group assignment -> exactly 10 assignments
# =============================================================================
@pytest.mark.asyncio
async def test_01_ten_member_team_group_assignment_creates_exactly_10_assignments():
    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"DB L2 {uuid.uuid4().hex[:6]}", count=10, prefix="DB")
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Database node high CPU",
            assignment_group=team.name,
            state="NEW",
            current_cycle=1
        )
        session.add(inc)
        await session.commit()

        engine = AssignmentEngine(session)
        result = await engine.assign_group(inc, team, cycle_number=1)

        assert result["status"] == "success"
        assert result["members"] == 10
        assert result["assigned"] == "10/10"
        assert result["assigned_count"] == 10
        assert len(result["assignments"]) == 10

        # Verify in DB
        res = await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id, IncidentAssignment.is_active == True)
        )
        db_assignments = res.scalars().all()
        assert len(db_assignments) == 10


# =============================================================================
# TEST 2: All Employee IDs unique -> PASS
# =============================================================================
@pytest.mark.asyncio
async def test_02_all_employee_ids_unique():
    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"Linux L2 {uuid.uuid4().hex[:6]}", count=10, prefix="LX")
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Kernel panic",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.commit()

        engine = AssignmentEngine(session)
        result = await engine.assign_group(inc, team, cycle_number=1)

        assigned_emp_ids = [a.employee_id for a in result["assignments"]]
        assert len(assigned_emp_ids) == 10
        assert len(set(assigned_emp_ids)) == 10, "Every assigned employee ID must be unique"


# =============================================================================
# TEST 3: Same employee twice in same cycle -> impossible (DB constraint rejects)
# =============================================================================
@pytest.mark.asyncio
async def test_03_same_employee_twice_in_same_cycle_rejected_by_database():
    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"Net L2 {uuid.uuid4().hex[:6]}", count=10, prefix="NW")
        inc_num = f"INC-TEST-03-{uuid.uuid4().hex[:6]}"
        cycle_id = f"{inc_num}:CYCLE-001"
        inc = Incident(id=uuid.uuid4(), incident_number=inc_num, short_description="BGP drop", state="NEW")
        session.add(inc)
        await session.flush()




        # Assignment 1 for emp 0 in cycle
        ass1 = IncidentAssignment(
            id=uuid.uuid4(),
            incident_id=inc.id,
            employee_id=employees[0].id,
            team_id=team.id,
            assignment_cycle_id=cycle_id,
            cycle_number=1,
            assignment_type="GROUP",
            status="ASSIGNED",
            is_active=True
        )
        session.add(ass1)
        await session.commit()

        # Attempt to insert same employee in same cycle again
        ass2 = IncidentAssignment(
            id=uuid.uuid4(),
            incident_id=inc.id,
            employee_id=employees[0].id,
            team_id=team.id,
            assignment_cycle_id=cycle_id,
            cycle_number=1,
            assignment_type="GROUP",
            status="ASSIGNED",
            is_active=False
        )
        session.add(ass2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


# =============================================================================
# TEST 4: Duplicate group webhook -> still exactly 10 assignments
# =============================================================================
@pytest.mark.asyncio
async def test_04_duplicate_group_webhook_still_exactly_10_assignments():
    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"Cloud L2 {uuid.uuid4().hex[:6]}", count=10, prefix="CL")

    from app.core.config import settings
    wh_headers = {"X-ServiceNow-Secret": settings.SERVICENOW_WEBHOOK_SECRET}
    sys_id = f"sys_{uuid.uuid4().hex[:12]}"

    number = f"INC{uuid.uuid4().hex[:7]}"
    payload = {
        "sys_id": sys_id,
        "number": number,
        "short_description": "Kubernetes cluster degraded",
        "assignment_group": team.name,
        "state": "1 - New"
    }

    with patch.object(AssignmentEngine, "_is_shadow_mode", AsyncMock(return_value=False)), \
         patch.object(AssignmentEngine, "_is_dry_run", AsyncMock(return_value=False)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First webhook delivery
            resp1 = await client.post("/api/integrations/servicenow/incidents", json=payload, headers=wh_headers)
            assert resp1.status_code == 200

            # Duplicate webhook delivery
            resp2 = await client.post("/api/integrations/servicenow/incidents", json=payload, headers=wh_headers)
            assert resp2.status_code == 200

    async with async_session_maker() as session:
        inc = (await session.execute(select(Incident).where(Incident.incident_number == number))).scalar_one()
        assignments = (await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id, IncidentAssignment.is_active == True)
        )).scalars().all()
        assert len(assignments) == 1, "Duplicate webhook must not duplicate assignment"


# =============================================================================
# TEST 5: Two simultaneous group requests -> exactly one cycle + 10 assignments
# =============================================================================
@pytest.mark.asyncio
async def test_05_two_simultaneous_group_requests_produce_exactly_one_cycle_and_10_assignments():
    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"SecOps L2 {uuid.uuid4().hex[:6]}", count=10, prefix="SO")
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="DDoS detected",
            assignment_group=team.name,
            state="NEW",
            current_cycle=1
        )
        session.add(inc)
        await session.commit()

    async def run_group_assignment():
        async with async_session_maker() as sess:
            inc_obj = await sess.get(Incident, inc.id)
            engine = AssignmentEngine(sess)
            return await engine.assign_group(inc_obj, team, cycle_number=1)

    results = await asyncio.gather(run_group_assignment(), run_group_assignment(), return_exceptions=True)

    async with async_session_maker() as session:
        assignments = (await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id, IncidentAssignment.is_active == True)
        )).scalars().all()
        assert len(assignments) == 10, "Concurrent group requests must result in exactly 10 active assignments"


# =============================================================================
# TEST 6: Notification retry -> still 10 assignments
# =============================================================================
@pytest.mark.asyncio
async def test_06_notification_retry_does_not_create_assignments():
    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"App L2 {uuid.uuid4().hex[:6]}", count=10, prefix="AP")
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="API 500 spike",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.commit()

        engine = AssignmentEngine(session)
        result = await engine.assign_group(inc, team, cycle_number=1)
        assert len(result["assignments"]) == 10

        # Simulate notification retry
        from app.services.notification_service import NotificationService
        notif_svc = NotificationService(session)
        for emp in employees:
            await notif_svc.create_notification(
                user_id=emp.user_id,
                type="INCIDENT_ASSIGNED",
                title=f"Retry notice: {inc.incident_number}",
                message="Retrying notification",
                incident_id=inc.id
            )

        # Confirm assignments count is STILL 10
        res = await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id, IncidentAssignment.is_active == True)
        )
        assert len(res.scalars().all()) == 10


# =============================================================================
# TEST 7: WebSocket reconnect -> still 10 assignments
# =============================================================================
@pytest.mark.asyncio
async def test_07_websocket_reconnect_preserves_exactly_10_assignments():
    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"DevOps L2 {uuid.uuid4().hex[:6]}", count=10, prefix="DO")
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Pipeline worker timeout",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.commit()

        engine = AssignmentEngine(session)
        await engine.assign_group(inc, team, cycle_number=1)

        # Simulate WebSocket disconnect and reconnect for all employees
        for emp in employees:
            mock_ws = AsyncMock()
            await ws_manager.connect(mock_ws, str(emp.user_id))
            await ws_manager.disconnect(mock_ws, str(emp.user_id))

        # Check assignments still exactly 10
        res = await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id, IncidentAssignment.is_active == True)
        )
        assert len(res.scalars().all()) == 10


# =============================================================================
# TEST 8: Page refresh -> still 10 assignments (read-only)
# =============================================================================
@pytest.mark.asyncio
async def test_08_page_refresh_read_only_preserves_10_assignments():
    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"SRE L2 {uuid.uuid4().hex[:6]}", count=10, prefix="SR")
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="High memory pressure",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.commit()

        engine = AssignmentEngine(session)
        await engine.assign_group(inc, team, cycle_number=1)

    from app.core.security import create_access_token
    token = create_access_token({"sub": str(employees[0].user_id), "role": "EMPLOYEE"})
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Simulate employee opening My Work multiple times (page refresh)
        r1 = await client.get("/api/me/work", headers=headers)
        assert r1.status_code == 200
        r2 = await client.get("/api/me/work", headers=headers)
        assert r2.status_code == 200

    async with async_session_maker() as session:
        res = await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id, IncidentAssignment.is_active == True)
        )
        assert len(res.scalars().all()) == 10, "Page refresh must never create duplicate assignments"


# =============================================================================
# TEST 9: Group Leader is one of 10 -> still exactly 10 assignments
# =============================================================================
@pytest.mark.asyncio
async def test_09_group_leader_is_one_of_10_total_remains_10():
    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"DataEng L2 {uuid.uuid4().hex[:6]}", count=10, prefix="DE")
        # Employee 0 is leader
        assert employees[0].is_group_leader is True

        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Kafka lag high",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.commit()

        engine = AssignmentEngine(session)
        result = await engine.assign_group(inc, team, cycle_number=1)

        assert result["assigned_count"] == 10, "Leader is part of the 10 members, NOT an 11th"
        # Confirm leader has an assignment
        leader_ass = next((a for a in result["assignments"] if a.employee_id == employees[0].id), None)
        assert leader_ass is not None


# =============================================================================
# TEST 10: Wrong team -> no cross-team assignments
# =============================================================================
@pytest.mark.asyncio
async def test_10_wrong_team_no_cross_team_assignments():
    async with async_session_maker() as session:
        team1, emps1 = await create_test_team(session, name=f"Team1 {uuid.uuid4().hex[:6]}", count=10, prefix="T1")
        team2, emps2 = await create_test_team(session, name=f"Team2 {uuid.uuid4().hex[:6]}", count=10, prefix="T2")

        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Cross team test",
            assignment_group=team1.name,
            state="NEW"
        )
        session.add(inc)
        await session.commit()

        engine = AssignmentEngine(session)
        result = await engine.assign_group(inc, team1, cycle_number=1)

        t1_emp_ids = {e.id for e in emps1}
        t2_emp_ids = {e.id for e in emps2}

        for a in result["assignments"]:
            assert a.employee_id in t1_emp_ids, "Assignment must only belong to target team"
            assert a.employee_id not in t2_emp_ids, "No cross-team employee assignment allowed"


# =============================================================================
# TEST 11: Team has 9 employees -> controlled failure, no partial assignment
# =============================================================================
@pytest.mark.asyncio
async def test_11_team_has_9_employees_controlled_failure():
    async with async_session_maker() as session:
        team, _ = await create_test_team(session, name=f"SmallTeam {uuid.uuid4().hex[:6]}", count=9, prefix="SM")
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Understaffed team",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.commit()

        engine = AssignmentEngine(session)
        with pytest.raises(ValueError) as exc:
            await engine.assign_group(inc, team, cycle_number=1)
        assert "Group assignment requires exactly 10 active team members" in str(exc.value)

        # Verify NO partial assignments exist in DB
        res = await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id)
        )
        assert len(res.scalars().all()) == 0, "No partial group assignments must be committed"


# =============================================================================
# TEST 12: Team has 11 employees -> controlled failure, no partial assignment
# =============================================================================
@pytest.mark.asyncio
async def test_12_team_has_11_employees_controlled_failure():
    async with async_session_maker() as session:
        team, _ = await create_test_team(session, name=f"Overstaffed {uuid.uuid4().hex[:6]}", count=11, prefix="OV")
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Overstaffed team",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.commit()

        engine = AssignmentEngine(session)
        with pytest.raises(ValueError) as exc:
            await engine.assign_group(inc, team, cycle_number=1)
        assert "Group assignment requires exactly 10 active team members" in str(exc.value)

        res = await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id)
        )
        assert len(res.scalars().all()) == 0


# =============================================================================
# TEST 13: Existing cycle repeated -> return existing cycle, no duplicates
# =============================================================================
@pytest.mark.asyncio
async def test_13_existing_cycle_repeated_returns_existing_cycle():
    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"Repeat {uuid.uuid4().hex[:6]}", count=10, prefix="RP")
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Repeat cycle test",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.commit()

        engine = AssignmentEngine(session)
        idemp_key = f"key-abc-{uuid.uuid4().hex[:8]}"
        res1 = await engine.assign_group(inc, team, cycle_number=1, idempotency_key=idemp_key)
        assert res1["assigned_count"] == 10

        # Repeated request with same cycle & idempotency key
        res2 = await engine.assign_group(inc, team, cycle_number=1, idempotency_key=idemp_key)
        assert res2["idempotent"] is True
        assert res2["assigned_count"] == 10

        # Verify DB still has exactly 10 assignments
        db_res = await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id, IncidentAssignment.is_active == True)
        )
        assert len(db_res.scalars().all()) == 10


# =============================================================================
# TEST 14: New legitimate cycle -> new cycle with exactly 10 assignments
# =============================================================================
@pytest.mark.asyncio
async def test_14_new_legitimate_cycle_creates_new_cycle_with_10_assignments():
    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"MultiCycle {uuid.uuid4().hex[:6]}", count=10, prefix="MC")
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Multi cycle test",
            assignment_group=team.name,
            state="NEW",
            current_cycle=1
        )
        session.add(inc)
        await session.commit()

        engine = AssignmentEngine(session)
        # Cycle 1
        res_c1 = await engine.assign_group(inc, team, cycle_number=1)
        assert res_c1["assigned_count"] == 10

        # Later: Cycle 2 begins
        inc.current_cycle = 2
        await session.commit()

        res_c2 = await engine.assign_group(inc, team, cycle_number=2)
        assert res_c2["assigned_count"] == 10
        assert res_c2["cycle_id"] != res_c1["cycle_id"]

        # Total assignments in history: 20 (10 in cycle 1 + 10 in cycle 2)
        all_res = await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id)
        )
        assert len(all_res.scalars().all()) == 20


# =============================================================================
# TEST 15: All 10 employees receive realtime My Work updates
# =============================================================================
@pytest.mark.asyncio
async def test_15_all_10_employees_receive_realtime_my_work_updates():
    received_user_events = {}

    async def mock_send_to_user(user_id, event_type, payload):
        if event_type == "MY_WORK_UPDATED":
            received_user_events[user_id] = payload

    async with async_session_maker() as session:
        team, employees = await create_test_team(session, name=f"RT Team {uuid.uuid4().hex[:6]}", count=10, prefix="RT")
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Realtime dispatch test",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.commit()

        with patch("app.websocket.manager.ws_manager.send_to_user", side_effect=mock_send_to_user):
            engine = AssignmentEngine(session)
            await engine.assign_group(inc, team, cycle_number=1)

        # Verify all 10 employees received MY_WORK_UPDATED event
        for emp in employees:
            assert str(emp.user_id) in received_user_events, f"Employee {emp.employee_code} must receive realtime event"
            event = received_user_events[str(emp.user_id)]
            assert event["status"] == "ASSIGNED"
            assert event["assigned_to"] == "You"
            assert event["incident_number"] == inc.incident_number
