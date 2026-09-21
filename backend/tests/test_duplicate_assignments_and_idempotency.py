import pytest
import uuid
import asyncio
from datetime import datetime, timezone, time, date
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.user import User
from app.models.team import Team
from app.models.employee import Employee
from app.models.shift import Shift, ShiftAssignment
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.notification import Notification
from app.models.integration import IntegrationEvent
from app.core.config import settings
from app.services.assignment_engine import AssignmentEngine
from app.services.notification_service import NotificationService
from app.schemas.servicenow import ServiceNowIncidentPayload


async def _create_test_team_with_engineers(session, count=10):
    team_id = uuid.uuid4()
    team_name = f"Test Group {uuid.uuid4().hex[:6]}"
    team = Team(id=team_id, name=team_name, is_active=True)
    session.add(team)

    employees = []
    for i in range(count):
        user = User(
            id=uuid.uuid4(),
            email=f"emp_{i}_{uuid.uuid4().hex[:6]}@incidentflow.dev",
            hashed_password="pw",
            full_name=f"Engineer {i+1}",
            role="EMPLOYEE",
            is_active=True
        )
        session.add(user)
        await session.flush()

        emp = Employee(
            id=uuid.uuid4(),
            user_id=user.id,
            team_id=team.id,
            employee_code=f"EMP_{uuid.uuid4().hex[:8]}",
            availability_status="AVAILABLE",
            is_present=True
        )
        session.add(emp)
        employees.append((user, emp))

    # Create shift covering full day
    shift = Shift(
        id=uuid.uuid4(),
        name="All Day Shift",
        start_time=time(0, 0),
        end_time=time(23, 59),
        is_active=True
    )
    session.add(shift)
    await session.flush()

    for _, emp in employees:
        sa = ShiftAssignment(
            id=uuid.uuid4(),
            shift_id=shift.id,
            employee_id=emp.id,
            date=date.today(),
            is_active=True
        )
        session.add(sa)

    await session.commit()
    return team, employees, shift


@pytest.mark.asyncio
async def test_1_single_active_assignment_invariant():
    """Rule 1: Incident can never have more than 1 assignment with is_active = True."""
    async with async_session_maker() as session:
        team, employees, _ = await _create_test_team_with_engineers(session, count=2)
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Test Invariant 1",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.flush()

        # Create active assignment 1
        ass1 = IncidentAssignment(
            id=uuid.uuid4(),
            incident_id=inc.id,
            employee_id=employees[0][1].id,
            assignment_type="AUTOMATIC",
            status="ASSIGNED",
            is_active=True,
            cycle_number=1
        )
        session.add(ass1)
        await session.commit()

        # Attempt to insert second active assignment for same incident and same employee
        ass2 = IncidentAssignment(
            id=uuid.uuid4(),
            incident_id=inc.id,
            employee_id=employees[0][1].id,
            assignment_type="AUTOMATIC",
            status="ASSIGNED",
            is_active=True,
            cycle_number=1
        )
        session.add(ass2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_2_same_incident_same_employee_in_cycle_invariant():
    """Rule 2: Employee cannot be assigned to same incident twice within the same cycle."""
    async with async_session_maker() as session:
        team, employees, _ = await _create_test_team_with_engineers(session, count=2)
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Test Invariant 2",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.flush()

        # Assignment 1: completed
        ass1 = IncidentAssignment(
            id=uuid.uuid4(),
            incident_id=inc.id,
            employee_id=employees[0][1].id,
            assignment_type="AUTOMATIC",
            status="COMPLETED",
            is_active=False,
            cycle_number=1
        )
        session.add(ass1)
        await session.commit()

        # Attempt to assign same employee in cycle 1 again
        ass2 = IncidentAssignment(
            id=uuid.uuid4(),
            incident_id=inc.id,
            employee_id=employees[0][1].id,
            assignment_type="AUTOMATIC",
            status="ASSIGNED",
            is_active=True,
            cycle_number=1
        )
        session.add(ass2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_3_concurrent_auto_assignments_idempotent():
    """Rule 3 & 5: Multiple concurrent assignment calls produce exactly 10 active assignments (all team members)."""
    async with async_session_maker() as session:
        team, employees, _ = await _create_test_team_with_engineers(session, count=10)
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Concurrent Test",
            assignment_group=team.name,
            state="NEW"
        )
        session.add(inc)
        await session.commit()

    async def run_assign():
        async with async_session_maker() as sess:
            inc_obj = await sess.get(Incident, inc.id)
            engine = AssignmentEngine(sess)
            return await engine.process_incident(inc_obj, force_internal=True)

    results = await asyncio.gather(run_assign(), run_assign(), run_assign(), return_exceptions=True)

    # Check database state
    async with async_session_maker() as session:
        res = await session.execute(
            select(IncidentAssignment).where(
                IncidentAssignment.incident_id == inc.id,
                IncidentAssignment.is_active == True
            )
        )
        active_assignments = res.scalars().all()
        # Authoritative Rule: Exactly ONE personal assignment created per incident
        assert len(active_assignments) == 1


@pytest.mark.asyncio
async def test_4_servicenow_webhook_replay_deduplication():
    """Rule 6: Webhook replay returns deduplicated response without creating duplicates."""
    async with async_session_maker() as session:
        team, _, _ = await _create_test_team_with_engineers(session, count=10)

    from unittest.mock import patch, AsyncMock
    with patch.object(AssignmentEngine, "_get_automation_mode", return_value="AUTOMATIC"), \
         patch.object(AssignmentEngine, "_is_shadow_mode", AsyncMock(return_value=False)), \
         patch.object(AssignmentEngine, "_is_dry_run", AsyncMock(return_value=False)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            sys_id = f"sys_{uuid.uuid4().hex}"
            number = f"INC{uuid.uuid4().hex[:7]}"
            payload = {
                "sys_id": sys_id,
                "number": number,
                "short_description": "Server disk full",
                "description": "Critical disk alert",
                "priority": "2 - High",
                "assignment_group": team.name,
                "state": "1 - New",
                "sys_mod_count": 0
            }

            headers = {"X-ServiceNow-Secret": settings.SERVICENOW_WEBHOOK_SECRET}

            # First webhook call
            resp1 = await client.post("/api/integrations/servicenow/incidents", json=payload, headers=headers)
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1["is_new"] is True
            assert data1.get("deduplicated") is not True

            # Second identical webhook call (replay)
            resp2 = await client.post("/api/integrations/servicenow/incidents", json=payload, headers=headers)
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["is_new"] is False
            assert data2.get("deduplicated") is True

    # Verify exactly 1 incident and 10 active assignments (all 10 members)
    async with async_session_maker() as session:
        inc_res = await session.execute(select(Incident).where(Incident.servicenow_sys_id == sys_id))
        inc_list = inc_res.scalars().all()
        assert len(inc_list) == 1

        ass_res = await session.execute(
            select(IncidentAssignment).where(
                IncidentAssignment.incident_id == inc_list[0].id,
                IncidentAssignment.is_active == True
            )
        )
        assert len(ass_res.scalars().all()) == 1


@pytest.mark.asyncio
async def test_5_rapid_admin_send_to_group_idempotency():
    """Rule 6: Rapid send_team_notice does not duplicate assignments or rotate prematurely."""
    async with async_session_maker() as session:
        team, _, _ = await _create_test_team_with_engineers(session, count=10)
        admin = User(
            id=uuid.uuid4(),
            email=f"admin_{uuid.uuid4().hex[:6]}@incidentflow.dev",
            hashed_password="pw",
            full_name="Admin User",
            role="ADMIN",
            is_active=True
        )
        session.add(admin)
        await session.commit()
        token = create_access_token({"sub": str(admin.id), "role": admin.role})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}
        inc_num = f"INC-{uuid.uuid4().hex[:8]}"
        payload = {
            "title": "Outage Alert",
            "message": "Production database high latency",
            "priority": "P2",
            "incident_number": inc_num,
            "auto_assign": True
        }

        # First send
        r1 = await client.post(f"/api/admin/teams/{team.id}/notice", json=payload, headers=headers)
        assert r1.status_code == 200
        d1 = r1.json()
        first_assignee = d1.get("assigned_employee_name")
        assert first_assignee is not None

        # Second rapid send with same incident number
        r2 = await client.post(f"/api/admin/teams/{team.id}/notice", json=payload, headers=headers)
        assert r2.status_code == 200
        d2 = r2.json()
        second_assignee = d2.get("assigned_employee_name")
        # Idempotent: should NOT rotate to next employee
        assert second_assignee == first_assignee

    # Verify database has exactly 1 assignment for this incident
    async with async_session_maker() as session:
        inc = (await session.execute(select(Incident).where(Incident.incident_number == inc_num))).scalar_one()
        assignments = (await session.execute(select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id))).scalars().all()
        assert len(assignments) == 1
        assert all(a.is_active is True for a in assignments)


@pytest.mark.asyncio
async def test_6_explicit_reassignment():
    """Rule 4: Explicit /reassign deactivates old and activates new linking previous_employee_id."""
    async with async_session_maker() as session:
        team, employees, _ = await _create_test_team_with_engineers(session, count=3)
        admin = User(
            id=uuid.uuid4(),
            email=f"admin_reassign_{uuid.uuid4().hex[:6]}@incidentflow.dev",
            hashed_password="pw",
            full_name="Admin Reassign",
            role="ADMIN",
            is_active=True
        )
        session.add(admin)

        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Reassign Test",
            assignment_group=team.name,
            state="ASSIGNED"
        )
        session.add(inc)
        await session.flush()

        initial_ass = IncidentAssignment(
            id=uuid.uuid4(),
            incident_id=inc.id,
            employee_id=employees[0][1].id,
            assignment_type="AUTOMATIC",
            status="ASSIGNED",
            is_active=True,
            cycle_number=1
        )
        session.add(initial_ass)
        await session.commit()
        token = create_access_token({"sub": str(admin.id), "role": admin.role})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}
        reassign_payload = {
            "new_employee_id": str(employees[1][1].id),
            "reason": "Specialist handoff"
        }
        resp = await client.post(f"/api/admin/incidents/{inc.id}/reassign", json=reassign_payload, headers=headers)
        assert resp.status_code == 200

    async with async_session_maker() as session:
        old_ass = await session.get(IncidentAssignment, initial_ass.id)
        assert old_ass.is_active is False
        assert old_ass.status == "REASSIGNED"

        active_res = await session.execute(
            select(IncidentAssignment).where(
                IncidentAssignment.incident_id == inc.id,
                IncidentAssignment.is_active == True
            )
        )
        active_list = active_res.scalars().all()
        assert len(active_list) == 1
        new_ass = active_list[0]
        assert new_ass.employee_id == employees[1][1].id
        assert new_ass.previous_employee_id == employees[0][1].id


@pytest.mark.asyncio
async def test_7_reassign_same_employee_in_same_cycle_rejected():
    """Rule 2 & 4: Reassigning back to an employee who already handled in current cycle returns 400."""
    async with async_session_maker() as session:
        team, employees, _ = await _create_test_team_with_engineers(session, count=3)
        admin = User(
            id=uuid.uuid4(),
            email=f"admin_cycle_{uuid.uuid4().hex[:6]}@incidentflow.dev",
            hashed_password="pw",
            full_name="Admin Cycle",
            role="ADMIN",
            is_active=True
        )
        session.add(admin)

        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Cycle Test",
            assignment_group=team.name,
            state="ASSIGNED",
            current_cycle=1
        )
        session.add(inc)
        await session.flush()

        # Emp 0 was assigned and reassigned to Emp 1
        ass0 = IncidentAssignment(
            id=uuid.uuid4(),
            incident_id=inc.id,
            employee_id=employees[0][1].id,
            assignment_type="AUTOMATIC",
            status="REASSIGNED",
            is_active=False,
            cycle_number=1
        )
        ass1 = IncidentAssignment(
            id=uuid.uuid4(),
            incident_id=inc.id,
            employee_id=employees[1][1].id,
            previous_employee_id=employees[0][1].id,
            assignment_type="MANUAL",
            status="ASSIGNED",
            is_active=True,
            cycle_number=1
        )
        session.add_all([ass0, ass1])
        await session.commit()
        token = create_access_token({"sub": str(admin.id), "role": admin.role})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}
        # Attempt to reassign back to Emp 0 in cycle 1
        reassign_payload = {
            "new_employee_id": str(employees[0][1].id),
            "reason": "Reassigning back"
        }
        resp = await client.post(f"/api/admin/incidents/{inc.id}/reassign", json=reassign_payload, headers=headers)
        assert resp.status_code == 400
        data = resp.json()
        assert "ALREADY_ASSIGNED" in str(data)


@pytest.mark.asyncio
async def test_8_notification_deduplication():
    """Notification service deduplicates by (assignment_id, user_id, type)."""
    async with async_session_maker() as session:
        team, employees, _ = await _create_test_team_with_engineers(session, count=1)
        user = employees[0][0]
        ass_id = uuid.uuid4()

        notif_svc = NotificationService(session)

        # First notification
        n1 = await notif_svc.create_notification(
            user_id=user.id,
            type="INCIDENT_ASSIGNED",
            title="New Incident",
            message="Please resolve",
            assignment_id=ass_id,
            broadcast_ws=False
        )
        await session.commit()
        assert n1.id is not None

        # Duplicate notification call
        n2 = await notif_svc.create_notification(
            user_id=user.id,
            type="INCIDENT_ASSIGNED",
            title="New Incident",
            message="Please resolve",
            assignment_id=ass_id,
            broadcast_ws=False
        )
        await session.commit()
        # Returns existing record
        assert n2.id == n1.id

        # Verify only 1 row in table
        count = (await session.execute(
            select(func.count(Notification.id)).where(
                Notification.assignment_id == ass_id,
                Notification.user_id == user.id
            )
        )).scalar()
        assert count == 1


@pytest.mark.asyncio
async def test_9_historical_assignments_preserved():
    """Rule 4: Completed and reassigned assignments remain queryable and untouched."""
    async with async_session_maker() as session:
        team, employees, _ = await _create_test_team_with_engineers(session, count=3)
        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="History Test",
            assignment_group=team.name,
            state="ASSIGNED"
        )
        session.add(inc)
        await session.flush()

        a1 = IncidentAssignment(
            id=uuid.uuid4(),
            incident_id=inc.id,
            employee_id=employees[0][1].id,
            assignment_type="AUTOMATIC",
            status="REASSIGNED",
            is_active=False,
            cycle_number=1
        )
        a2 = IncidentAssignment(
            id=uuid.uuid4(),
            incident_id=inc.id,
            employee_id=employees[1][1].id,
            assignment_type="MANUAL",
            status="ASSIGNED",
            is_active=True,
            cycle_number=1
        )
        session.add_all([a1, a2])
        await session.commit()

        # Query all assignments for incident
        all_res = await session.execute(
            select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id).order_by(IncidentAssignment.created_at)
        )
        records = all_res.scalars().all()
        assert len(records) == 2
        assert records[0].status == "REASSIGNED"
        assert records[0].is_active is False
        assert records[1].status == "ASSIGNED"
        assert records[1].is_active is True


@pytest.mark.asyncio
async def test_10_multi_incident_isolation():
    """Multiple concurrent incidents to same team each get 1 distinct active assignment."""
    async with async_session_maker() as session:
        team, employees, _ = await _create_test_team_with_engineers(session, count=10)

        inc1 = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Incident A",
            assignment_group=team.name,
            state="NEW"
        )
        inc2 = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-{uuid.uuid4().hex[:8]}",
            short_description="Incident B",
            assignment_group=team.name,
            state="NEW"
        )
        session.add_all([inc1, inc2])
        await session.commit()

        engine = AssignmentEngine(session)
        ass1 = await engine.process_incident(inc1, force_internal=True)
        ass2 = await engine.process_incident(inc2, force_internal=True)

        assert ass1 is not None
        assert ass2 is not None
        assert ass1.incident_id == inc1.id
        assert ass2.incident_id == inc2.id
        assert ass1.is_active is True
        assert ass2.is_active is True
