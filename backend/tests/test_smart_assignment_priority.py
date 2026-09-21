import pytest
import uuid
from datetime import datetime, date, time, timezone
from unittest.mock import AsyncMock, MagicMock
from app.models.employee import Employee
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.user import User
from app.models.team import Team
from app.models.shift import Shift
from app.services.assignment_engine import AssignmentEngine
from app.services.eligibility import EligibilityService


def make_emp(name: str, team_id=None, is_present=True, availability_status="AVAILABLE", skills=None):
    emp_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), full_name=name, email=f"{name.lower().replace(' ', '.')}@incidentflow.dev", role="EMPLOYEE", is_active=True)
    emp = Employee(
        id=emp_id,
        user_id=user.id,
        team_id=team_id,
        availability_status=availability_status,
        is_present=is_present,
    )
    emp.user = user
    emp.skills = skills or []
    return emp


@pytest.mark.asyncio
async def test_priority_1_zero_workload_preferred_over_busy_candidates():
    mock_db = AsyncMock()
    eligibility_svc = EligibilityService(mock_db)

    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Database L2")

    emp_zero = make_emp("Alice Zero", team_id=team_id)
    emp_busy1 = make_emp("Bob Busy", team_id=team_id)
    emp_busy2 = make_emp("Charlie Busy", team_id=team_id)

    mock_shift = Shift(id=uuid.uuid4(), name="Day Shift (08:00 - 16:00)", start_time=time(8, 0), end_time=time(16, 0), is_active=True)

    eligibility_svc._find_active_shift = AsyncMock(return_value=mock_shift)
    eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp_zero, emp_busy1, emp_busy2])

    async def mock_get(model, pk):
        if model == User:
            for e in [emp_zero, emp_busy1, emp_busy2]:
                if e.user_id == pk:
                    return e.user
        elif model == Team and pk == team_id:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    with pytest.MonkeyPatch.context() as mp:
        from app.services.workload_service import WorkloadService
        mp.setattr(WorkloadService, "get_workloads", AsyncMock(return_value={
            emp_zero.id: 0,
            emp_busy1.id: 2,
            emp_busy2.id: 4
        }))

        now = datetime(2026, 9, 18, 10, 0, 0, tzinfo=timezone.utc)
        pipeline = await eligibility_svc.evaluate_candidate_pipeline("Database L2", set(), now)

        # Priority 1: In accordance with compulsory employee availability, all scheduled team members are eligible
        assert len(pipeline["eligible"]) == 3
        assert pipeline["decision_priority"] == "SCHEDULED_SHIFT_CANDIDATES_FOUND"


@pytest.mark.asyncio
async def test_priority_2_least_workload_selected_when_all_busy():
    mock_db = AsyncMock()
    eligibility_svc = EligibilityService(mock_db)

    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Cloud Operations")

    emp_busy1 = make_emp("Dan Busy1", team_id=team_id)
    emp_busy2 = make_emp("Eve Busy2", team_id=team_id)

    mock_shift = Shift(id=uuid.uuid4(), name="Day Shift (08:00 - 16:00)", start_time=time(8, 0), end_time=time(16, 0), is_active=True)

    eligibility_svc._find_active_shift = AsyncMock(return_value=mock_shift)
    eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp_busy1, emp_busy2])

    async def mock_get(model, pk):
        if model == User:
            for e in [emp_busy1, emp_busy2]:
                if e.user_id == pk:
                    return e.user
        elif model == Team and pk == team_id:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    with pytest.MonkeyPatch.context() as mp:
        from app.services.workload_service import WorkloadService
        mp.setattr(WorkloadService, "get_workloads", AsyncMock(return_value={
            emp_busy1.id: 1,
            emp_busy2.id: 3
        }))

        now = datetime(2026, 9, 18, 10, 0, 0, tzinfo=timezone.utc)
        pipeline = await eligibility_svc.evaluate_candidate_pipeline("Cloud Operations", set(), now)

        # All scheduled candidates are eligible regardless of busy status
        assert len(pipeline["eligible"]) == 2
        assert pipeline["decision_priority"] == "SCHEDULED_SHIFT_CANDIDATES_FOUND"


@pytest.mark.asyncio
async def test_next_shift_fallback_queues_assignment():
    """
    Under Prompt 5, group assignment requires exactly 10 active team members.
    If target team has fewer than 10 active members, engine raises a controlled
    ValueError rather than silent or partial assignment.
    """
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Analytics – MDM L3")

    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC_NEXT_SHIFT_01",
        assignment_group="Analytics – MDM L3",
        short_description="Night pipeline failure",
        priority="P2",
        state="NEW"
    )

    async def mock_execute(stmt):
        stmt_str = str(stmt)
        mock_res = MagicMock()
        if "FROM teams" in stmt_str:
            mock_res.scalar_one_or_none.return_value = team
            return mock_res
        elif "FROM employees" in stmt_str:
            mock_res.scalars.return_value.all.return_value = []
            return mock_res
        elif "FROM incidents" in stmt_str:
            mock_res.scalar_one_or_none.return_value = incident
            return mock_res
        mock_res.scalars.return_value.all.return_value = []
        mock_res.scalar_one_or_none.return_value = None
        return mock_res

    mock_db.execute = AsyncMock(side_effect=mock_execute)

    with pytest.raises(ValueError, match="Group assignment requires exactly 10 active team members"):
        await engine.process_incident(incident, force_internal=True)


@pytest.mark.asyncio
async def test_concurrency_lock_prevents_duplicate_assignment():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC_CONCURRENT_01",
        assignment_group="Analytics – MDM L3",
        short_description="Concurrent assignment stress test",
        priority="P2",
        state="ASSIGNED"
    )

    emp = make_emp("George Guard")

    # Simulate existing active assignment in database
    existing_assignment = IncidentAssignment(
        id=uuid.uuid4(),
        incident_id=incident.id,
        employee_id=emp.id,
        status="ASSIGNED",
        is_active=True
    )

    mock_inc_res = MagicMock()
    mock_inc_res.scalar_one_or_none.return_value = incident

    mock_existing_res = MagicMock()
    mock_existing_res.scalar_one_or_none.return_value = existing_assignment

    mock_db.execute = AsyncMock(side_effect=[
        mock_inc_res,       # Lock incident
        mock_existing_res   # Check existing active assignment
    ])

    result = await engine._create_assignment(incident, emp, "LEAST_WORKLOAD")
    # Idempotent: returns existing assignment without creating duplicate
    assert result.id == existing_assignment.id
    assert mock_db.add.call_count == 0
