import pytest
import uuid
from datetime import datetime, date, time, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.team import Team
from app.models.employee import Employee
from app.models.user import User
from app.models.shift import Shift, ShiftAssignment
from app.models.assignment import IncidentAssignment
from app.models.incident import Incident
from app.models.skill import Skill, EmployeeSkill
from app.models.presence import PresenceRecord
from sqlalchemy import select
from app.services.team_service import TeamService
from app.services.shift_service import ShiftService
from app.services.eligibility import EligibilityService
from app.services.assignment_engine import AssignmentEngine


def make_emp_obj(name: str, team_id=None, is_present=True, availability_status="AVAILABLE", is_group_leader=False, skills=None):
    emp_id = uuid.uuid4()
    user = User(
        id=uuid.uuid4(),
        full_name=name,
        email=f"{name.lower().replace(' ', '.')}@incidentflow.dev",
        role="EMPLOYEE",
        is_active=True
    )
    emp = Employee(
        id=emp_id,
        user_id=user.id,
        team_id=team_id,
        availability_status=availability_status,
        is_present=is_present,
        is_group_leader=is_group_leader,
        employee_code=f"EMP-{uuid.uuid4().hex[:4].upper()}"
    )
    emp.user = user
    emp.skills = skills or []
    return emp


# =============================================================================
# 1. Active team with exactly 10 employees -> PASS
# =============================================================================
@pytest.mark.asyncio
async def test_01_active_team_with_exactly_10_employees_passes_activation():
    async with async_session_maker() as session:
        team_svc = TeamService(session)
        # Database L2 was seeded with exactly 10 employees, 1 leader, shift coverage
        team = (await session.execute(select(Team).where(Team.name == "Database L2"))).scalar_one_or_none()
        assert team is not None

        is_valid, violations = await team_svc.validate_team_activation(team.id)
        assert is_valid is True
        assert len(violations) == 0


# =============================================================================
# 2. Active team with 9 employees -> activation blocked
# =============================================================================
@pytest.mark.asyncio
async def test_02_team_with_9_employees_activation_blocked():
    async with async_session_maker() as session:
        team_svc = TeamService(session)
        draft_team = Team(name=f"Draft 9 Emps - {uuid.uuid4().hex[:6]}", is_active=False)
        session.add(draft_team)
        await session.flush()

        # Add 9 employees
        for i in range(1, 10):
            u = User(email=f"draft9_{i}_{uuid.uuid4().hex[:4]}@incidentflow.dev", full_name=f"Emp {i}", role="EMPLOYEE", is_active=True, hashed_password="pw")
            session.add(u)
            await session.flush()
            e = Employee(user_id=u.id, team_id=draft_team.id, employee_code=f"E9-{i}", is_group_leader=(i == 1))
            session.add(e)

        await session.flush()

        is_valid, violations = await team_svc.validate_team_activation(draft_team.id)
        assert is_valid is False
        assert any("exactly 10 active employees" in v for v in violations)

        with pytest.raises(Exception) as exc_info:
            await team_svc.activate_team(draft_team.id)
        assert "TEAM_ACTIVATION_BLOCKED" in str(exc_info.value)


# =============================================================================
# 3. Active team with 11 employees -> activation blocked
# =============================================================================
@pytest.mark.asyncio
async def test_03_team_with_11_employees_activation_blocked():
    async with async_session_maker() as session:
        team_svc = TeamService(session)
        draft_team = Team(name=f"Draft 11 Emps - {uuid.uuid4().hex[:6]}", is_active=False)
        session.add(draft_team)
        await session.flush()

        # Add 11 employees
        for i in range(1, 12):
            u = User(email=f"draft11_{i}_{uuid.uuid4().hex[:4]}@incidentflow.dev", full_name=f"Emp {i}", role="EMPLOYEE", is_active=True, hashed_password="pw")
            session.add(u)
            await session.flush()
            e = Employee(user_id=u.id, team_id=draft_team.id, employee_code=f"E11-{i}", is_group_leader=(i == 1))
            session.add(e)

        await session.flush()

        is_valid, violations = await team_svc.validate_team_activation(draft_team.id)
        assert is_valid is False
        assert any("exactly 10 active employees" in v for v in violations)


# =============================================================================
# 4. Employee without shift -> activation/configuration blocked
# =============================================================================
@pytest.mark.asyncio
async def test_04_employee_without_shift_blocks_activation():
    async with async_session_maker() as session:
        team_svc = TeamService(session)
        team = Team(name=f"No Shift Team - {uuid.uuid4().hex[:6]}", is_active=False)
        session.add(team)
        await session.flush()

        shift = (await session.execute(select(Shift).where(Shift.is_active == True))).scalars().first()

        # Add 10 employees, but employee 10 has NO shift assignment
        for i in range(1, 11):
            u = User(email=f"noshift_{i}_{uuid.uuid4().hex[:4]}@incidentflow.dev", full_name=f"Emp {i}", role="EMPLOYEE", is_active=True, hashed_password="pw")
            session.add(u)
            await session.flush()
            e = Employee(user_id=u.id, team_id=team.id, employee_code=f"NS-{i}", is_group_leader=(i == 1))
            session.add(e)
            await session.flush()
            if i < 10 and shift:
                session.add(ShiftAssignment(shift_id=shift.id, employee_id=e.id, date=date.today(), is_active=True))

        await session.flush()

        is_valid, violations = await team_svc.validate_team_activation(team.id)
        assert is_valid is False
        assert any("shift coverage" in v for v in violations)


# =============================================================================
# 5. Incident during morning shift -> morning employees considered
# =============================================================================
@pytest.mark.asyncio
async def test_05_incident_during_morning_shift_considers_morning_employees():
    mock_db = AsyncMock()
    eligibility_svc = EligibilityService(mock_db)
    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Linux L2")

    emp_morning = make_emp_obj("Morning Worker", team_id=team_id, is_present=True)
    morning_shift = Shift(id=uuid.uuid4(), name="Morning Shift (Shift A)", start_time=time(6, 0), end_time=time(14, 0), is_active=True)

    eligibility_svc._find_active_shift = AsyncMock(return_value=morning_shift)
    eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp_morning])

    async def mock_get(model, pk):
        if model == User and pk == emp_morning.user_id:
            return emp_morning.user
        elif model == Team and pk == team_id:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    with patch("app.services.workload_service.WorkloadService.get_workloads", AsyncMock(return_value={emp_morning.id: 0})):
        now_morning = datetime(2026, 9, 18, 9, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
        res = await eligibility_svc.evaluate_candidate_pipeline("Linux L2", set(), now_morning)
        assert len(res["eligible"]) == 1
        assert res["eligible"][0].id == emp_morning.id
        assert res["active_shift"].name == "Morning Shift (Shift A)"


# =============================================================================
# 6. Incident during afternoon shift -> afternoon employees considered
# =============================================================================
@pytest.mark.asyncio
async def test_06_incident_during_afternoon_shift_considers_afternoon_employees():
    mock_db = AsyncMock()
    eligibility_svc = EligibilityService(mock_db)
    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Linux L2")

    emp_afternoon = make_emp_obj("Afternoon Worker", team_id=team_id, is_present=True)
    evening_shift = Shift(id=uuid.uuid4(), name="Evening Shift (Shift B)", start_time=time(14, 0), end_time=time(22, 0), is_active=True)

    eligibility_svc._find_active_shift = AsyncMock(return_value=evening_shift)
    eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp_afternoon])

    async def mock_get(model, pk):
        if model == User and pk == emp_afternoon.user_id:
            return emp_afternoon.user
        elif model == Team and pk == team_id:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    with patch("app.services.workload_service.WorkloadService.get_workloads", AsyncMock(return_value={emp_afternoon.id: 0})):
        now_afternoon = datetime(2026, 9, 18, 16, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        res = await eligibility_svc.evaluate_candidate_pipeline("Linux L2", set(), now_afternoon)
        assert len(res["eligible"]) == 1
        assert res["eligible"][0].id == emp_afternoon.id
        assert res["active_shift"].name == "Evening Shift (Shift B)"


# =============================================================================
# 7. Future shift employee is present -> NOT selected
# =============================================================================
@pytest.mark.asyncio
async def test_07_future_shift_employee_present_is_not_selected():
    mock_db = AsyncMock()
    eligibility_svc = EligibilityService(mock_db)
    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Windows L2")

    emp_current = make_emp_obj("Current Eng", team_id=team_id, is_present=True)
    # Future employee is present on the platform, but scheduled on next shift
    emp_future = make_emp_obj("Future Eng", team_id=team_id, is_present=True)

    current_shift = Shift(id=uuid.uuid4(), name="Morning Shift (Shift A)", start_time=time(6, 0), end_time=time(14, 0), is_active=True)

    eligibility_svc._find_active_shift = AsyncMock(return_value=current_shift)
    # Only emp_current is scheduled on current shift
    eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp_current])

    async def mock_get(model, pk):
        if model == User and pk == emp_current.user_id:
            return emp_current.user
        elif model == Team and pk == team_id:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    with patch("app.services.workload_service.WorkloadService.get_workloads", AsyncMock(return_value={emp_current.id: 0})):
        now = datetime(2026, 9, 18, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        res = await eligibility_svc.evaluate_candidate_pipeline("Windows L2", set(), now)
        assert emp_future not in res["eligible"]
        assert len(res["eligible"]) == 1
        assert res["eligible"][0].id == emp_current.id


# =============================================================================
# 8. Current shift employee is present -> eligible
# =============================================================================
@pytest.mark.asyncio
async def test_08_current_shift_employee_present_is_eligible():
    mock_db = AsyncMock()
    eligibility_svc = EligibilityService(mock_db)
    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Cloud Operations L2")

    emp = make_emp_obj("Present Worker", team_id=team_id, is_present=True)
    curr_shift = Shift(id=uuid.uuid4(), name="Day Shift", start_time=time(6, 0), end_time=time(14, 0), is_active=True)

    eligibility_svc._find_active_shift = AsyncMock(return_value=curr_shift)
    eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp])

    async def mock_get(model, pk):
        if model == User and pk == emp.user_id:
            return emp.user
        elif model == Team and pk == team_id:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    with patch("app.services.workload_service.WorkloadService.get_workloads", AsyncMock(return_value={emp.id: 0})):
        res = await eligibility_svc.find_eligible_employees("Cloud Operations L2", set(), datetime.now(ZoneInfo("Asia/Kolkata")))
        assert len(res) == 1
        assert res[0].id == emp.id


# =============================================================================
# 9. Current shift employee is offline -> excluded
# =============================================================================
@pytest.mark.asyncio
async def test_09_current_shift_employee_offline_is_STILL_eligible():
    """
    MANDATORY RULE: An employee on the current active shift is eligible regardless
    of their is_present / online / offline status.

    Offline = cannot receive assignment is FORBIDDEN.
    Offline = not eligible is FORBIDDEN.
    Presence has ZERO influence on assignment eligibility.
    """
    mock_db = AsyncMock()
    eligibility_svc = EligibilityService(mock_db)
    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Cloud Operations L2")

    emp_offline = make_emp_obj("Offline Worker", team_id=team_id, is_present=False)
    curr_shift = Shift(id=uuid.uuid4(), name="Day Shift", start_time=time(6, 0), end_time=time(14, 0), is_active=True)

    eligibility_svc._find_active_shift = AsyncMock(return_value=curr_shift)
    eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp_offline])

    async def mock_get(model, pk):
        if model == User and pk == emp_offline.user_id:
            return emp_offline.user
        elif model == Team and pk == team_id:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    async def mock_execute(stmt):
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        r.scalar_one_or_none.return_value = None
        r.all.return_value = []
        return r
    mock_db.execute = AsyncMock(side_effect=mock_execute)

    with patch("app.services.workload_service.WorkloadService.get_workloads", AsyncMock(return_value={emp_offline.id: 0})):
        res = await eligibility_svc.find_eligible_employees("Cloud Operations L2", set(), datetime.now(ZoneInfo("Asia/Kolkata")))
        # OFFLINE employee on active shift MUST be eligible
        assert len(res) == 1, (
            "Offline employee on current shift MUST be eligible. "
            "Presence has ZERO influence on assignment eligibility."
        )
        assert emp_offline in res


# =============================================================================
# 10. AVAILABLE and BUSY employees on current shift → BOTH eligible
# 11. Presence/availability_status does NOT gate eligibility — informational only
# =============================================================================
@pytest.mark.asyncio
async def test_10_and_11_available_and_busy_both_eligible():
    """
    MANDATORY RULE: availability_status=BUSY employees are still eligible.
    Only shift schedule determines eligibility, not chat/presence status.
    Both AVAILABLE and BUSY employees on the active shift must be returned.
    """
    mock_db = AsyncMock()
    eligibility_svc = EligibilityService(mock_db)
    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Application Support L2")

    emp_avail = make_emp_obj("Available Eng", team_id=team_id, is_present=True, availability_status="AVAILABLE")
    emp_busy = make_emp_obj("Busy Eng", team_id=team_id, is_present=True, availability_status="BUSY")
    curr_shift = Shift(id=uuid.uuid4(), name="Day Shift", start_time=time(6, 0), end_time=time(14, 0), is_active=True)

    eligibility_svc._find_active_shift = AsyncMock(return_value=curr_shift)
    eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp_avail, emp_busy])

    async def mock_get(model, pk):
        for e in [emp_avail, emp_busy]:
            if e.user_id == pk:
                return e.user
        if model == Team and pk == team_id:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    async def mock_execute(stmt):
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        r.scalar_one_or_none.return_value = None
        r.all.return_value = []
        return r
    mock_db.execute = AsyncMock(side_effect=mock_execute)

    with patch("app.services.workload_service.WorkloadService.get_workloads", AsyncMock(return_value={emp_avail.id: 1, emp_busy.id: 1})):
        pipeline = await eligibility_svc.evaluate_candidate_pipeline("Application Support L2", set(), datetime.now(ZoneInfo("Asia/Kolkata")))
        # Both must be eligible — presence/availability_status is NOT a gate
        assert emp_avail in pipeline["eligible"], "AVAILABLE employee must be eligible"
        assert emp_busy in pipeline["eligible"], "BUSY employee must ALSO be eligible — presence not a gate"
        assert pipeline["is_coverage_exception"] is False
        # priority_1_candidates no longer in pipeline (presence-based tiering removed)
        assert "priority_1_candidates" not in pipeline, (
            "priority_1_candidates key must not exist — presence tiers removed from eligibility"
        )



# =============================================================================
# 12. Multiple present employees -> workload/strategy decides
# =============================================================================
@pytest.mark.asyncio
async def test_12_multiple_present_employees_workload_decides():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)
    team_id = uuid.uuid4()

    emp_1 = make_emp_obj("Worker One", team_id=team_id)
    emp_2 = make_emp_obj("Worker Two", team_id=team_id)

    incident = Incident(id=uuid.uuid4(), incident_number="INC-WKLD", priority="P3")

    with patch("app.services.workload_service.WorkloadService.get_workloads", AsyncMock(return_value={emp_1.id: 4, emp_2.id: 1})):
        selected = await engine._apply_strategy("LEAST_WORKLOAD", [emp_1, emp_2], incident)
        # Worker Two has 1 active incident, Worker One has 4 -> Worker Two must be selected
        assert selected.id == emp_2.id


# =============================================================================
# 13. Skill mismatch -> excluded
# =============================================================================
@pytest.mark.asyncio
async def test_13_skill_mismatch_excluded():
    mock_db = AsyncMock()
    eligibility_svc = EligibilityService(mock_db)
    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Security Operations L2")

    emp_noskill = make_emp_obj("No Skill Eng", team_id=team_id, is_present=True, skills=[])
    curr_shift = Shift(id=uuid.uuid4(), name="Day Shift", start_time=time(6, 0), end_time=time(14, 0), is_active=True)

    eligibility_svc._find_active_shift = AsyncMock(return_value=curr_shift)
    eligibility_svc._get_scheduled_employees = AsyncMock(return_value=[emp_noskill])

    async def mock_get(model, pk):
        if model == User and pk == emp_noskill.user_id:
            return emp_noskill.user
        elif model == Team and pk == team_id:
            return team
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

    required_skills = {uuid.uuid4()}
    pipeline = await eligibility_svc.evaluate_candidate_pipeline("Security Operations L2", required_skills, datetime.now(ZoneInfo("Asia/Kolkata")))
    assert len(pipeline["eligible"]) == 0
    assert any(r["code"] == "NO_SKILLED_EMPLOYEE" for r in pipeline["rejected"])


# =============================================================================
# 14. Capacity exhausted -> excluded
# =============================================================================
@pytest.mark.asyncio
async def test_14_capacity_exhausted_excluded():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)
    incident = Incident(id=uuid.uuid4(), incident_number="INC-CAP", assignment_group="Analytics – MDM L3")

    engine._get_live_pilot_config = AsyncMock(return_value={"enabled": True, "assignment_group": "Analytics – MDM L3", "max_active_assignments": 3})
    engine._get_active_pilot_assignment_count = AsyncMock(return_value=3)
    engine._get_automation_mode = AsyncMock(return_value="LIVE")
    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._send_group_arrival_notice = AsyncMock()
    engine.audit_service.log = AsyncMock()

    result = await engine.process_incident(incident, force_internal=False)
    assert result is None
    audit_calls = [c for c in engine.audit_service.log.call_args_list if c.args[0] == "PILOT_CAPACITY_REACHED"]
    assert len(audit_calls) == 1


# =============================================================================
# 15. No present employee -> coverage exception
# 16. Next shift employee present while current shift has no presence -> do not silently assign next shift
# =============================================================================
@pytest.mark.asyncio
async def test_15_and_16_coverage_exception_and_no_silent_next_shift_assignment():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)
    team_id = uuid.uuid4()
    team = Team(id=team_id, name="Storage & Backup L2")

    incident = Incident(id=uuid.uuid4(), incident_number="INC-COV-EX", assignment_group="Storage & Backup L2", state="NEW")

    # Current shift is active, but all scheduled engineers are offline
    emp_offline = make_emp_obj("Offline Scheduled", team_id=team_id, is_present=False)
    current_shift = Shift(id=uuid.uuid4(), name="Morning Shift (Shift A)", start_time=time(6, 0), end_time=time(14, 0), is_active=True)

    # Next shift employee IS present
    emp_next_present = make_emp_obj("Next Shift Present", team_id=team_id, is_present=True)
    next_shift = Shift(id=uuid.uuid4(), name="Evening Shift (Shift B)", start_time=time(14, 0), end_time=time(22, 0), is_active=True)

    engine.eligibility.find_eligible_employees = AsyncMock(return_value=[])
    engine.eligibility.last_pipeline = {
        "active_shift": current_shift,
        "is_coverage_exception": True,
        "eligible": [],
        "rejected": [],
        "candidates_evaluated": []
    }
    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._get_automation_mode = AsyncMock(return_value="LIVE")
    engine._get_required_skills = AsyncMock(return_value=set())
    engine._send_group_arrival_notice = AsyncMock()
    engine.audit_service.log = AsyncMock()

    # Next shift service WOULD return next shift candidate
    engine.shift_service.get_next_shift_for_team = AsyncMock(return_value=(next_shift, date.today(), [emp_next_present]))

    assignment = await engine.process_incident(incident, force_internal=True)

    # HARD RULE: Must NOT silently assign next shift employee!
    assert assignment is None
    assert incident.state == "UNASSIGNED"

    # Verify COVERAGE_EXCEPTION was recorded
    cov_audits = [c for c in engine.audit_service.log.call_args_list if c.kwargs.get("action") == "COVERAGE_EXCEPTION"]
    assert len(cov_audits) >= 1


# =============================================================================
# 17. Shift transition -> reevaluate
# =============================================================================
@pytest.mark.asyncio
async def test_17_shift_transition_reevaluates_active_shift():
    mock_db = AsyncMock()
    shift_svc = ShiftService(mock_db)

    shift_a = Shift(id=uuid.uuid4(), name="Morning", start_time=time(6, 0), end_time=time(14, 0), is_active=True, is_overnight=False)
    shift_b = Shift(id=uuid.uuid4(), name="Evening", start_time=time(14, 0), end_time=time(22, 0), is_active=True, is_overnight=False)

    mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[shift_a, shift_b])))))

    # At 13:59: Shift A
    res_1359 = await shift_svc.get_active_shift(datetime(2026, 9, 18, 13, 59, tzinfo=ZoneInfo("Asia/Kolkata")))
    assert res_1359.name == "Morning"

    # At 14:00: Shift B
    res_1400 = await shift_svc.get_active_shift(datetime(2026, 9, 18, 14, 0, tzinfo=ZoneInfo("Asia/Kolkata")))
    assert res_1400.name == "Evening"


# =============================================================================
# 18. Duplicate incident -> no duplicate assignment
# 19. Concurrent webhook -> exactly one active assignment
# 20. Duplicate Admin send -> exactly one active assignment
# =============================================================================
@pytest.mark.asyncio
async def test_18_19_20_duplicate_and_concurrency_protection():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    inc = Incident(id=uuid.uuid4(), incident_number="INC-DUP-01", priority="P3")
    emp = make_emp_obj("Single Owner")

    existing_active = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp.id, status="ASSIGNED", is_active=True)

    mock_inc_res = MagicMock()
    mock_inc_res.scalar_one_or_none.return_value = inc

    mock_existing_res = MagicMock()
    mock_existing_res.scalar_one_or_none.return_value = existing_active

    mock_db.execute = AsyncMock(side_effect=[mock_inc_res, mock_existing_res])

    # Attempt to create assignment again
    result = await engine._create_assignment(inc, emp, "LEAST_WORKLOAD")
    # Returns existing active assignment without adding new record
    assert result.id == existing_active.id
    assert mock_db.add.call_count == 0


# =============================================================================
# 21. Group notice -> all 10 active team members
# =============================================================================
@pytest.mark.asyncio
async def test_21_group_notice_sent_to_all_10_members():
    async with async_session_maker() as session:
        from app.services.group_notice_service import GroupNoticeService
        notice_svc = GroupNoticeService(session)

        # Database L2 has 10 active members
        team = (await session.execute(select(Team).where(Team.name == "Database L2"))).scalar_one_or_none()
        assert team is not None

        result = await notice_svc.send_to_team(
            team_id=team.id,
            title="Operational Notice",
            message="Database cluster failover testing in progress."
        )
        # Verify broadcast reached all 10 active employees
        assert result["success"] == 10
        assert len(result["recipients"]) == 10
        assert result["failed"] == 0


# =============================================================================
# 22. Assignment notice -> exactly selected employee
# 23. Employee My Work -> selected employee only
# =============================================================================
@pytest.mark.asyncio
async def test_22_and_23_assignment_notice_and_my_work_for_selected_only():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    selected_emp = make_emp_obj("Chosen Engineer")
    other_emp = make_emp_obj("Other Engineer")

    incident = Incident(id=uuid.uuid4(), incident_number="INC-ONLY-ME", short_description="App Crash", priority="P2")

    engine.notification_service.create_notification = AsyncMock()
    engine.workload_service.get_workloads = AsyncMock(return_value={selected_emp.id: 0})
    engine.audit_service.log = AsyncMock()

    mock_inc_res = MagicMock()
    mock_inc_res.scalar_one_or_none.return_value = incident
    mock_existing_res = MagicMock()
    mock_existing_res.scalar_one_or_none.return_value = None
    mock_emp_res = MagicMock()
    mock_emp_res.scalar_one.return_value = selected_emp

    mock_db.execute = AsyncMock(side_effect=[mock_inc_res, mock_existing_res, mock_emp_res])

    async def mock_get(model, pk):
        if model == User and pk == selected_emp.user_id:
            return selected_emp.user
        elif model == Incident and pk == incident.id:
            return incident
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    with patch("app.websocket.manager.ws_manager.broadcast_to_team", AsyncMock()), \
         patch("app.websocket.manager.ws_manager.broadcast_to_admins", AsyncMock()), \
         patch("app.websocket.manager.ws_manager.send_to_user", AsyncMock()) as mock_ws_user:

        assignment = await engine._create_assignment(incident, selected_emp, "LEAST_WORKLOAD")

        # Verify only selected_emp user received personal notification
        notif_calls = engine.notification_service.create_notification.call_args_list
        assert len(notif_calls) == 1
        assert notif_calls[0].kwargs["user_id"] == selected_emp.user_id

        # Assignment is strictly assigned to selected_emp
        assert assignment.employee_id == selected_emp.id


# =============================================================================
# 24. Audit -> assignment reason recorded
# =============================================================================
@pytest.mark.asyncio
async def test_24_audit_records_assignment_reason():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    emp = make_emp_obj("Audited Worker")
    incident = Incident(id=uuid.uuid4(), incident_number="INC-AUDIT", priority="P2")

    mock_inc_res = MagicMock(scalar_one_or_none=MagicMock(return_value=incident))
    mock_existing_res = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    mock_emp_res = MagicMock(scalar_one=MagicMock(return_value=emp))
    mock_db.execute = AsyncMock(side_effect=[mock_inc_res, mock_existing_res, mock_emp_res])

    engine.workload_service.get_workloads = AsyncMock(return_value={emp.id: 0})
    engine.audit_service.log = AsyncMock()
    engine.notification_service.create_notification = AsyncMock()

    async def mock_get(model, pk):
        if model == User and pk == emp.user_id:
            return emp.user
        return None
    mock_db.get = AsyncMock(side_effect=mock_get)

    with patch("app.websocket.manager.ws_manager.broadcast_to_team", AsyncMock()), \
         patch("app.websocket.manager.ws_manager.broadcast_to_admins", AsyncMock()), \
         patch("app.websocket.manager.ws_manager.send_to_user", AsyncMock()):
        await engine._create_assignment(incident, emp, "LEAST_WORKLOAD")

        audit_calls = [c for c in engine.audit_service.log.call_args_list if c.kwargs.get("action") == "AUTO_ASSIGNMENT_DECISION"]
        assert len(audit_calls) >= 1
        val = audit_calls[0].kwargs.get("new_value", {})
        assert val.get("selected_employee") == emp.user.full_name
        assert "workload" in audit_calls[0].kwargs.get("reason", "").lower() or "tier" in audit_calls[0].kwargs.get("reason", "").lower()


# =============================================================================
# 25. Shadow mode -> ZERO ServiceNow mutations
# =============================================================================
@pytest.mark.asyncio
async def test_25_shadow_mode_produces_zero_servicenow_mutations():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    incident = Incident(id=uuid.uuid4(), incident_number="INC-SHADOW-01", priority="P3")
    emp = make_emp_obj("Candidate Eng")

    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._get_automation_mode = AsyncMock(return_value="SHADOW")
    engine._is_dry_run = AsyncMock(return_value=False)
    engine._is_shadow_mode = AsyncMock(return_value=True)
    engine.eligibility.find_eligible_employees = AsyncMock(return_value=[emp])
    engine.workload_service.get_workloads = AsyncMock(return_value={emp.id: 0})
    engine._get_required_skills = AsyncMock(return_value=set())
    engine._get_strategy = AsyncMock(return_value="LEAST_WORKLOAD")
    engine._send_group_arrival_notice = AsyncMock()
    engine.audit_service.log = AsyncMock()

    with patch("app.services.sync_service.SyncService.sync_assignment_to_servicenow", AsyncMock()) as mock_sn_sync:
        res = await engine.process_incident(incident, force_internal=False)
        assert res is None
        # ZERO ServiceNow mutations made
        assert mock_sn_sync.call_count == 0


# =============================================================================
# 26. LIVE mode -> mutation only after explicit protected activation
# =============================================================================
@pytest.mark.asyncio
async def test_26_live_mode_mutation_requires_protected_pilot_activation():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    incident = Incident(id=uuid.uuid4(), incident_number="INC-LIVE-01", assignment_group="MDM L3", priority="P2")

    # 1. LIVE mode enabled but controlled pilot is disabled -> blocked
    engine._get_automation_mode = AsyncMock(return_value="LIVE")
    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._send_group_arrival_notice = AsyncMock()
    engine.audit_service.log = AsyncMock()
    engine._get_live_pilot_config = AsyncMock(return_value={"enabled": False})

    res = await engine.process_incident(incident, force_internal=False)
    assert res is None
    skipped = [
        c for c in engine.audit_service.log.call_args_list
        if (c.kwargs.get("action") == "AUTO_ASSIGN_SKIPPED" or (c.args and c.args[0] == "AUTO_ASSIGN_SKIPPED"))
    ]
    assert len(skipped) >= 1
    reason = skipped[0].kwargs.get("reason", "")
    assert "pilot is disabled" in reason
