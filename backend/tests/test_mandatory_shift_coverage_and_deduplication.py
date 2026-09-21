import uuid
import pytest
from datetime import datetime, time, date, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

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
from app.services.eligibility import EligibilityService
from app.services.assignment_engine import AssignmentEngine
from app.services.shift_service import ShiftService


def make_emp(name, team_id=None, is_present=True, status="AVAILABLE", is_leader=False):
    emp_id = uuid.uuid4()
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"{name.lower().replace(' ', '_')}@incidentflow.dev",
        full_name=name,
        role="EMPLOYEE",
        is_active=True
    )
    emp = Employee(
        id=emp_id,
        user_id=user_id,
        team_id=team_id or uuid.uuid4(),
        employee_code=f"EMP-{str(emp_id)[:4]}",
        is_present=is_present,
        availability_status=status,
        is_group_leader=is_leader
    )
    emp.user = user
    return emp


@pytest.mark.asyncio
async def test_mandatory_shift_coverage_all_scheduled_employees_eligible():
    """
    MANDATORY RULE: All employees scheduled on the active shift are eligible.
    Presence/availability_status is informational ONLY — never gates eligible[].

    New rule replaces the old 4-tier presence-based filter:
    - Tier 1 (Available + 0 workload) exclusively selected → PROHIBITED
    - Offline employees returned as COVERAGE_EXCEPTION → PROHIBITED
    - is_coverage_exception = True → PROHIBITED

    All 4 employees (online, busy, offline) must be in eligible[].
    decision_priority = SCHEDULED_SHIFT_CANDIDATES_FOUND for all.
    is_coverage_exception = False always.
    """
    mock_db = AsyncMock()
    eligibility_svc = EligibilityService(mock_db)
    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Database L2")

    emp_t1 = make_emp("Alice T1", team_id=team_id, is_present=True, status="AVAILABLE")
    emp_t2 = make_emp("Bob T2", team_id=team_id, is_present=True, status="AVAILABLE")
    emp_t3 = make_emp("Charlie T3", team_id=team_id, is_present=True, status="BUSY")
    emp_t4 = make_emp("David T4", team_id=team_id, is_present=False, status="OFFLINE")

    mock_shift = Shift(
        id=uuid.uuid4(),
        name="Morning Shift (09:00 - 17:00)",
        start_time=time(9, 0),
        end_time=time(17, 0),
        is_active=True
    )

    eligibility_svc._find_active_shift = AsyncMock(return_value=mock_shift)
    eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp_t1, emp_t2, emp_t3, emp_t4])

    async def mock_get(model, pk):
        if model == User:
            for e in [emp_t1, emp_t2, emp_t3, emp_t4]:
                if e.user_id == pk:
                    return e.user
        elif model == Team and pk == team_id:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    async def mock_execute(stmt):
        r = AsyncMock()
        r.scalars.return_value.all.return_value = []
        r.scalar_one_or_none.return_value = None
        r.all.return_value = []
        return r
    mock_db.execute = AsyncMock(side_effect=mock_execute)

    with pytest.MonkeyPatch.context() as mp:
        from app.services.workload_service import WorkloadService
        mp.setattr(WorkloadService, "get_workloads", AsyncMock(return_value={
            emp_t1.id: 0,
            emp_t2.id: 2,
            emp_t3.id: 1,
            emp_t4.id: 0
        }))

        now = datetime(2026, 9, 18, 11, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

        # Case 1: All 4 scheduled — ALL must be eligible regardless of presence
        res = await eligibility_svc.evaluate_candidate_pipeline("Database L2", set(), now)
        assert len(res["eligible"]) == 4, (
            "All 4 scheduled employees must be eligible. "
            "Presence has ZERO influence on assignment eligibility."
        )
        assert emp_t4 in res["eligible"], "Offline employee (emp_t4) must be eligible"
        assert emp_t3 in res["eligible"], "Busy employee (emp_t3) must be eligible"
        assert res["decision_priority"] == "SCHEDULED_SHIFT_CANDIDATES_FOUND"
        assert res["is_coverage_exception"] is False, "is_coverage_exception must always be False"
        # Presence info is in candidates_evaluated for audit only
        assert all(c["eligible"] is True for c in res["candidates_evaluated"])
        assert all(c["eligibility_basis"] == "ACTIVE_EMPLOYEE_ON_SCHEDULED_SHIFT" for c in res["candidates_evaluated"])

        # Case 2: Only offline employee scheduled — still eligible
        eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp_t4])
        res4 = await eligibility_svc.evaluate_candidate_pipeline("Database L2", set(), now)
        assert len(res4["eligible"]) == 1, "Offline employee alone on shift must still be eligible"
        assert res4["eligible"][0].id == emp_t4.id
        assert res4["decision_priority"] == "SCHEDULED_SHIFT_CANDIDATES_FOUND"
        assert res4["is_coverage_exception"] is False, "COVERAGE_EXCEPTION must never be True"

        # Case 3: Only busy employee scheduled — still eligible
        eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp_t3])
        res3 = await eligibility_svc.evaluate_candidate_pipeline("Database L2", set(), now)
        assert len(res3["eligible"]) == 1, "Busy employee on shift must be eligible"
        assert res3["eligible"][0].id == emp_t3.id
        assert res3["is_coverage_exception"] is False




@pytest.mark.asyncio
async def test_assignment_deduplication_candidate_already_assigned():
    """
    Verify candidate deduplication:
    An employee holding active assignment for INC-001 CANNOT receive INC-001 again,
    but REMAINS ELIGIBLE for subsequent incidents INC-002, etc.
    """
    async with async_session_maker() as session:
        admin_user = (await session.execute(select(User).where(User.role == "ADMIN"))).scalars().first()
        team = (await session.execute(select(Team).where(Team.is_active == True))).scalars().first()

        # Find 2 active employees in team
        emp_rows = (await session.execute(
            select(Employee).where(Employee.team_id == team.id)
        )).scalars().all()
        assert len(emp_rows) >= 2
        emp_a = emp_rows[0]
        emp_b = emp_rows[1]

        # Create Incident 1
        inc1 = Incident(
            incident_number=f"INC-DEDUP1-{uuid.uuid4().hex[:6].upper()}",
            short_description="Deduplication Verification Test 1",
            state="NEW",
            priority="2 - High",
            assignment_group=team.name
        )
        session.add(inc1)
        await session.flush()

        # Assign Incident 1 to Employee A
        assign1 = IncidentAssignment(
            incident_id=inc1.id,
            employee_id=emp_a.id,
            assignment_type="MANUAL",
            status="ASSIGNED",
            assigned_at=datetime.now(timezone.utc),
            is_active=True
        )
        session.add(assign1)
        await session.commit()
        inc1_id = inc1.id
        inc1_num = inc1.incident_number

    transport = ASGITransport(app=app)
    admin_token = create_access_token(data={"sub": str(admin_user.id), "role": admin_user.role})
    headers = {"Authorization": f"Bearer {admin_token}"}

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Attempt manual assign Incident 1 to Employee A AGAIN -> MUST BE REJECTED
        res_reassign_same = await ac.post(
            f"/api/admin/incidents/{inc1_id}/assign",
            headers=headers,
            json={"employee_id": str(emp_a.id), "reason": "Attempting duplicate assignment"}
        )
        assert res_reassign_same.status_code == 400
        assert res_reassign_same.json().get("code") == "ALREADY_ASSIGNED_THIS_INCIDENT"

        # 2. Reassign endpoint also rejects reassigning to the SAME active employee
        res_reassign_ep = await ac.post(
            f"/api/admin/incidents/{inc1_id}/reassign",
            headers=headers,
            json={"new_employee_id": str(emp_a.id), "reason": "Attempting duplicate reassign"}
        )
        assert res_reassign_ep.status_code == 400
        assert res_reassign_ep.json().get("code") == "ALREADY_ASSIGNED_THIS_INCIDENT"

        # 3. Idempotent group send: sending Incident 1 to the group again returns ALREADY_ASSIGNED
        res_group_send = await ac.post(
            f"/api/admin/incidents/{inc1_id}/send-to-group",
            headers=headers,
            json={"team_id": str(team.id), "message": "Resending incident"}
        )
        assert res_group_send.status_code == 200
        send_data = res_group_send.json()
        assert send_data.get("status") in ("already_assigned", "already_processed", "success") or send_data.get("decision_code") == "ALREADY_ASSIGNED_THIS_INCIDENT"

        # 4. Employee A is NOT permanently excluded: create Incident 2 and assign to Employee A -> SUCCESS
        async with async_session_maker() as session:
            inc2 = Incident(
                incident_number=f"INC-DEDUP2-{uuid.uuid4().hex[:6].upper()}",
                short_description="Deduplication Verification Test 2",
                state="NEW",
                priority="2 - High",
                assignment_group=team.name
            )
            session.add(inc2)
            await session.commit()
            inc2_id = inc2.id

        res_inc2 = await ac.post(
            f"/api/admin/incidents/{inc2_id}/assign",
            headers=headers,
            json={"employee_id": str(emp_a.id), "reason": "Assigning new incident"}
        )
        assert res_inc2.status_code == 200


@pytest.mark.asyncio
async def test_reassignment_lifecycle_and_lineage():
    """
    Verify POST /api/admin/incidents/{incident_id}/reassign:
    - Closes previous assignment (is_active=False, status='REASSIGNED')
    - Links previous_employee_id in new assignment
    - Logs REASSIGN in AuditLog with previous and new employee info
    """
    async with async_session_maker() as session:
        admin_user = (await session.execute(select(User).where(User.role == "ADMIN"))).scalars().first()
        team = (await session.execute(select(Team).where(Team.is_active == True))).scalars().first()

        emps = (await session.execute(
            select(Employee).where(Employee.team_id == team.id)
        )).scalars().all()
        assert len(emps) >= 2
        emp_orig = emps[0]
        emp_new = emps[1]

        inc = Incident(
            incident_number=f"INC-REASSIGN-{uuid.uuid4().hex[:6].upper()}",
            short_description="Reassignment Lineage Test",
            state="ASSIGNED",
            priority="1 - Critical",
            assignment_group=team.name
        )
        session.add(inc)
        await session.flush()

        orig_assign = IncidentAssignment(
            incident_id=inc.id,
            employee_id=emp_orig.id,
            assignment_type="MANUAL",
            status="ASSIGNED",
            assigned_at=datetime.now(timezone.utc),
            is_active=True
        )
        session.add(orig_assign)
        await session.commit()
        inc_id = inc.id

    transport = ASGITransport(app=app)
    admin_token = create_access_token(data={"sub": str(admin_user.id), "role": admin_user.role})
    headers = {"Authorization": f"Bearer {admin_token}"}

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        reassign_res = await ac.post(
            f"/api/admin/incidents/{inc_id}/reassign",
            headers=headers,
            json={
                "new_employee_id": str(emp_new.id),
                "reason": "Engineer on shift handoff"
            }
        )
        assert reassign_res.status_code == 200
        data = reassign_res.json()
        assert data["status"] == "success"
        assert data["previous_employee_id"] == str(emp_orig.id)
        assert data["new_employee_id"] == str(emp_new.id)

    # Verify Database state
    async with async_session_maker() as session:
        # Check old assignment is deactivated
        old_a = (await session.execute(
            select(IncidentAssignment).where(
                IncidentAssignment.incident_id == inc_id,
                IncidentAssignment.employee_id == emp_orig.id
            )
        )).scalar_one()
        assert old_a.is_active is False
        assert old_a.status == "REASSIGNED"

        # Check new assignment is active and links previous_employee_id
        new_a = (await session.execute(
            select(IncidentAssignment).where(
                IncidentAssignment.incident_id == inc_id,
                IncidentAssignment.employee_id == emp_new.id
            )
        )).scalar_one()
        assert new_a.is_active is True
        assert new_a.previous_employee_id == emp_orig.id

        # Verify exactly ONE active assignment exists for this incident (Database Invariant)
        active_assignments = (await session.execute(
            select(IncidentAssignment).where(
                IncidentAssignment.incident_id == inc_id,
                IncidentAssignment.is_active == True
            )
        )).scalars().all()
        assert len(active_assignments) == 1

        # Check audit log
        audit = (await session.execute(
            select(AuditLog).where(
                AuditLog.action == "REASSIGN",
                AuditLog.entity_id == inc_id
            ).order_by(AuditLog.created_at.desc())
        )).scalars().first()
        assert audit is not None
        assert audit.new_value["employee_id"] == str(emp_new.id)
        assert audit.old_value["employee_id"] == str(emp_orig.id)
