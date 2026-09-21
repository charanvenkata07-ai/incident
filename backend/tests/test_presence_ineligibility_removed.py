"""
test_presence_ineligibility_removed.py
=======================================
Tests proving that presence / availability_status / online / offline / busy
state has ZERO influence on assignment eligibility.

MANDATORY RULES tested:
  - Employee offline in chat          → still eligible
  - Employee WebSocket disconnected   → still eligible
  - Employee browser closed           → still eligible
  - Employee marked busy              → still eligible
  - Employee availability = BUSY      → still eligible
  - Employee availability = OFFLINE   → still eligible
  - Employee is_present = False       → still eligible
  - Employee not currently logged in  → still eligible
  - Employee inside scheduled shift   → eligible
  - Employee outside scheduled shift  → NOT eligible (shift-based, not presence-based)
  - Employee already handled same incident in current cycle → skip by HISTORY, not availability
"""

import pytest
import uuid
from datetime import datetime, timezone, time, date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.eligibility import EligibilityService
from app.services.assignment_engine import AssignmentEngine
from app.models.employee import Employee
from app.models.user import User
from app.models.assignment import IncidentAssignment
from app.models.incident import Incident
from app.models.shift import Shift


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(full_name="Test Employee", is_active=True, role="EMPLOYEE"):
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.full_name = full_name
    u.is_active = is_active
    u.role = role
    return u


def _make_employee(
    user_id=None,
    team_id=None,
    availability_status="AVAILABLE",
    is_present=True,
    employee_code=None
):
    emp = MagicMock(spec=Employee)
    emp.id = uuid.uuid4()
    emp.user_id = user_id or uuid.uuid4()
    emp.team_id = team_id or uuid.uuid4()
    emp.availability_status = availability_status
    emp.is_present = is_present
    emp.employee_code = employee_code or f"EMP_{uuid.uuid4().hex[:6]}"
    emp.skills = []
    emp.team = None
    return emp


def _make_shift(name="Day Shift", start_h=0, end_h=23):
    s = MagicMock(spec=Shift)
    s.id = uuid.uuid4()
    s.name = name
    s.start_time = time(start_h, 0)
    s.end_time = time(end_h, 59)
    return s


def _make_incident(assignment_group="Test Group"):
    inc = MagicMock(spec=Incident)
    inc.id = uuid.uuid4()
    inc.incident_number = f"INC{uuid.uuid4().hex[:7].upper()}"
    inc.assignment_group = assignment_group
    inc.current_cycle = 1
    return inc


# ---------------------------------------------------------------------------
# Fixture: build EligibilityService with mocked db
# ---------------------------------------------------------------------------

def _build_eligibility_service_for_employees(
    employees: list,
    users: dict,
    already_assigned_ids: set = None,
    workloads: dict = None
):
    """
    Returns an EligibilityService wired with mocked db that returns the given
    employees as scheduled for the active shift.
    """
    team_id = employees[0].team_id if employees else uuid.uuid4()

    from app.models.team import Team
    team = MagicMock(spec=Team)
    team.id = team_id
    team.name = "Test Group"
    team.servicenow_group_id = None
    for emp in employees:
        emp.team = team
        emp.team_id = team_id

    shift = _make_shift()

    db = AsyncMock()

    # db.get returns user objects keyed by user_id
    async def mock_get(model, pk):
        if model == User:
            return users.get(pk)
        if model == Team:
            return team
        return None

    db.get = mock_get

    # Track execute calls to correctly route different queries
    _call_tracker = {"incident_assignment_calls": 0}

    async def mock_execute(stmt):
        stmt_str = str(stmt).lower()

        # Already assigned employee_id check:
        # select incident_assignments.employee_id where incident_id = ? and is_active = true
        if (
            "incident_assignments" in stmt_str
            and "employee_id" in stmt_str
            and "incident_id" in stmt_str
            and "is_active" in stmt_str
        ):
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = list(already_assigned_ids or set())
            return mock_result

        # WorkloadService query: select employee_id, count(...) from incident_assignments
        if "incident_assignments" in stmt_str and "count" in stmt_str:
            rows = [(eid, wl) for eid, wl in (workloads or {}).items()]
            mock_result = MagicMock()
            mock_result.all.return_value = rows
            return mock_result

        # EmployeeSkill
        if "employeeskill" in stmt_str or "employee_skill" in stmt_str:
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            return mock_result

        # Any other incident_assignments query
        if "incident_assignments" in stmt_str:
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        return mock_result

    db.execute = mock_execute



    svc = EligibilityService(db)

    # Mock shift_service
    svc.shift_service = MagicMock()
    svc.shift_service.get_active_shift = AsyncMock(return_value=shift)
    svc.shift_service.get_shift_employees = AsyncMock(return_value=employees)

    return svc


# ===========================================================================
# TEST GROUP 1: Presence flags never block eligibility
# ===========================================================================

class TestPresenceNeverBlocksEligibility:

    @pytest.mark.asyncio
    async def test_offline_employee_is_eligible(self):
        """Employee with is_present=False and availability_status='OFFLINE' must still be eligible."""
        user = _make_user("DB001 Offline")
        emp = _make_employee(user_id=user.id, is_present=False, availability_status="OFFLINE")
        svc = _build_eligibility_service_for_employees([emp], {user.id: user})

        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc))
        assert len(result) == 1, "Offline employee must be eligible"
        assert result[0].id == emp.id

    @pytest.mark.asyncio
    async def test_busy_employee_is_eligible(self):
        """Employee with availability_status='BUSY' must be eligible."""
        user = _make_user("DB002 Busy")
        emp = _make_employee(user_id=user.id, is_present=True, availability_status="BUSY")
        svc = _build_eligibility_service_for_employees([emp], {user.id: user})

        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc))
        assert len(result) == 1, "Busy employee must be eligible"

    @pytest.mark.asyncio
    async def test_unavailable_employee_is_eligible(self):
        """Employee with availability_status='UNAVAILABLE' must be eligible."""
        user = _make_user("DB003 Unavailable")
        emp = _make_employee(user_id=user.id, is_present=False, availability_status="UNAVAILABLE")
        svc = _build_eligibility_service_for_employees([emp], {user.id: user})

        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc))
        assert len(result) == 1, "Unavailable employee must be eligible"

    @pytest.mark.asyncio
    async def test_not_present_employee_is_eligible(self):
        """Employee with is_present=False (browser closed / WS disconnected) must be eligible."""
        user = _make_user("DB004 Not Present")
        emp = _make_employee(user_id=user.id, is_present=False, availability_status="AVAILABLE")
        svc = _build_eligibility_service_for_employees([emp], {user.id: user})

        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc))
        assert len(result) == 1, "Employee with is_present=False must be eligible"

    @pytest.mark.asyncio
    async def test_all_offline_employees_are_all_eligible(self):
        """10 employees all offline → all 10 must be returned as eligible."""
        employees = []
        users = {}
        for i in range(10):
            u = _make_user(f"DB{i+1:03d} Offline")
            e = _make_employee(user_id=u.id, is_present=False, availability_status="OFFLINE")
            employees.append(e)
            users[u.id] = u

        svc = _build_eligibility_service_for_employees(employees, users)
        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc))
        assert len(result) == 10, "All 10 offline employees must be eligible"

    @pytest.mark.asyncio
    async def test_mixed_presence_all_eligible(self):
        """Mix of online/offline/busy employees → all must be eligible."""
        statuses = [
            ("ONLINE", True),
            ("OFFLINE", False),
            ("BUSY", True),
            ("UNAVAILABLE", False),
            ("AVAILABLE", True),
            ("OFFLINE", False),
            ("BUSY", False),
            ("AVAILABLE", False),
            ("OFFLINE", True),
            ("BUSY", True),
        ]
        employees = []
        users = {}
        for i, (status, is_pres) in enumerate(statuses):
            u = _make_user(f"DB{i+1:03d}")
            e = _make_employee(user_id=u.id, is_present=is_pres, availability_status=status)
            employees.append(e)
            users[u.id] = u

        svc = _build_eligibility_service_for_employees(employees, users)
        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc))
        assert len(result) == 10, "All 10 employees regardless of presence must be eligible"

    @pytest.mark.asyncio
    async def test_is_coverage_exception_always_false(self):
        """is_coverage_exception must always be False — presence doesn't gate assignment."""
        user = _make_user("DB001 Offline")
        emp = _make_employee(user_id=user.id, is_present=False, availability_status="OFFLINE")
        svc = _build_eligibility_service_for_employees([emp], {user.id: user})

        pipeline = await svc.evaluate_candidate_pipeline("Test Group", set(), datetime.now(timezone.utc))
        assert pipeline["is_coverage_exception"] is False, (
            "is_coverage_exception must always be False — presence never gates assignment"
        )


# ===========================================================================
# TEST GROUP 2: Shift-based eligibility (not presence-based)
# ===========================================================================

class TestShiftBasedEligibility:

    @pytest.mark.asyncio
    async def test_no_active_shift_returns_empty(self):
        """When no shift is active, eligible must be empty (shift-based, not presence-based)."""
        user = _make_user("DB001")
        emp = _make_employee(user_id=user.id, is_present=True, availability_status="AVAILABLE")
        svc = _build_eligibility_service_for_employees([emp], {user.id: user})

        # Override: no active shift
        svc.shift_service.get_active_shift = AsyncMock(return_value=None)

        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc))
        assert len(result) == 0, "No active shift → no eligible employees (shift gate, not presence gate)"

    @pytest.mark.asyncio
    async def test_employee_on_active_shift_is_eligible_even_if_offline(self):
        """Employee on the current shift is eligible regardless of is_present=False."""
        user = _make_user("DB001 On Shift But Offline")
        # Offline but on active shift
        emp = _make_employee(user_id=user.id, is_present=False, availability_status="OFFLINE")
        svc = _build_eligibility_service_for_employees([emp], {user.id: user})

        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc))
        assert emp in result, (
            "Employee on active shift must be eligible regardless of is_present=False"
        )


# ===========================================================================
# TEST GROUP 3: Cycle/history-based deduplication (not presence-based)
# ===========================================================================

class TestCycleHistoryDeduplication:

    @pytest.mark.asyncio
    async def test_already_assigned_employee_skipped_by_history_not_presence(self):
        """Employee already in the current cycle is skipped due to assignment history, not presence."""
        users = {}
        employees = []
        for i in range(3):
            u = _make_user(f"DB{i+1:03d}")
            # All online
            e = _make_employee(user_id=u.id, is_present=True, availability_status="AVAILABLE")
            employees.append(e)
            users[u.id] = u

        incident_id = uuid.uuid4()
        # DB001 already assigned this incident
        already_assigned = {employees[0].id}

        svc = _build_eligibility_service_for_employees(
            employees, users, already_assigned_ids=already_assigned
        )

        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc), incident_id=incident_id)
        assert len(result) == 2, "Only unassigned employees in current cycle should be returned"
        assert employees[0] not in result, "DB001 already in cycle — must be excluded by HISTORY, not presence"
        assert employees[1] in result
        assert employees[2] in result

    @pytest.mark.asyncio
    async def test_already_assigned_offline_is_skipped_by_history(self):
        """Already-assigned offline employee skipped by history. Non-assigned offline employee is still eligible."""
        users = {}
        employees = []
        for i in range(2):
            u = _make_user(f"DB{i+1:03d} Offline")
            # All offline
            e = _make_employee(user_id=u.id, is_present=False, availability_status="OFFLINE")
            employees.append(e)
            users[u.id] = u

        incident_id = uuid.uuid4()
        already_assigned = {employees[0].id}

        svc = _build_eligibility_service_for_employees(
            employees, users, already_assigned_ids=already_assigned
        )
        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc), incident_id=incident_id)

        assert employees[0] not in result, "DB001 excluded — already in cycle (history)"
        assert employees[1] in result, "DB002 still eligible even though offline"

    @pytest.mark.asyncio
    async def test_rotation_skips_already_assigned_respects_history_not_presence(self):
        """
        Rotation with 5 employees: DB001–DB003 already assigned (all offline).
        DB004–DB005 not yet assigned (also offline).
        Result must include DB004 and DB005 — excluded by HISTORY only.
        """
        users = {}
        employees = []
        for i in range(5):
            u = _make_user(f"DB{i+1:03d}")
            e = _make_employee(user_id=u.id, is_present=False, availability_status="OFFLINE")
            employees.append(e)
            users[u.id] = u

        incident_id = uuid.uuid4()
        # DB001, DB002, DB003 already in cycle
        already_assigned = {employees[0].id, employees[1].id, employees[2].id}

        svc = _build_eligibility_service_for_employees(
            employees, users, already_assigned_ids=already_assigned
        )
        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc), incident_id=incident_id)

        assert len(result) == 2
        assert employees[3] in result, "DB004 not yet in cycle → eligible"
        assert employees[4] in result, "DB005 not yet in cycle → eligible"
        for emp in employees[:3]:
            assert emp not in result, f"{emp.employee_code} already in cycle → excluded by history"


# ===========================================================================
# TEST GROUP 4: Audit data reflects presence but doesn't gate
# ===========================================================================

class TestAuditDataIntegrity:

    @pytest.mark.asyncio
    async def test_candidates_evaluated_has_communication_status_informational(self):
        """
        candidates_evaluated must include communication_status for audit.
        It must NOT affect the eligible list.
        """
        user = _make_user("DB001 Offline")
        emp = _make_employee(user_id=user.id, is_present=False, availability_status="OFFLINE")
        svc = _build_eligibility_service_for_employees([emp], {user.id: user})

        pipeline = await svc.evaluate_candidate_pipeline("Test Group", set(), datetime.now(timezone.utc))

        assert len(pipeline["eligible"]) == 1, "Eligible must have 1 even though offline"
        evaluated = pipeline["candidates_evaluated"]
        assert len(evaluated) == 1
        assert evaluated[0]["eligible"] is True
        assert "communication_status" in evaluated[0], "presence info must be in audit data"
        assert evaluated[0]["eligibility_basis"] == "ACTIVE_EMPLOYEE_ON_SCHEDULED_SHIFT"
        assert "OFFLINE" in evaluated[0]["communication_status"] or evaluated[0]["is_present_informational"] is False

    @pytest.mark.asyncio
    async def test_presence_note_in_details(self):
        """Pipeline details must contain presence_note explaining presence is informational."""
        user = _make_user("DB001")
        emp = _make_employee(user_id=user.id)
        svc = _build_eligibility_service_for_employees([emp], {user.id: user})

        pipeline = await svc.evaluate_candidate_pipeline("Test Group", set(), datetime.now(timezone.utc))
        assert "presence_note" in pipeline["details"]
        assert "ZERO" in pipeline["details"]["presence_note"] or "informational" in pipeline["details"]["presence_note"]


# ===========================================================================
# TEST GROUP 5: find_eligible_employees returns all (no presence filter)
# ===========================================================================

class TestFindEligibleNoPresenceFilter:

    @pytest.mark.asyncio
    async def test_find_eligible_returns_all_regardless_of_presence(self):
        """find_eligible_employees must return ALL scheduled employees regardless of any presence field."""
        users = {}
        employees = []
        presence_combos = [
            (True, "AVAILABLE"),
            (False, "OFFLINE"),
            (True, "BUSY"),
            (False, "BUSY"),
            (False, "UNAVAILABLE"),
        ]
        for i, (is_pres, status) in enumerate(presence_combos):
            u = _make_user(f"DB{i+1:03d}")
            e = _make_employee(user_id=u.id, is_present=is_pres, availability_status=status)
            employees.append(e)
            users[u.id] = u

        svc = _build_eligibility_service_for_employees(employees, users)
        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc))

        assert len(result) == 5, (
            f"Expected 5 eligible employees, got {len(result)}. "
            "Presence must NEVER filter out scheduled employees."
        )

    @pytest.mark.asyncio
    async def test_coverage_exception_never_returned_in_pipeline(self):
        """is_coverage_exception in pipeline must always be False."""
        users = {}
        employees = []
        for i in range(3):
            u = _make_user(f"DB{i+1:03d}")
            # Deliberately all offline
            e = _make_employee(user_id=u.id, is_present=False, availability_status="OFFLINE")
            employees.append(e)
            users[u.id] = u

        svc = _build_eligibility_service_for_employees(employees, users)
        pipeline = await svc.evaluate_candidate_pipeline("Test Group", set(), datetime.now(timezone.utc))

        assert pipeline.get("is_coverage_exception") is False, (
            "is_coverage_exception must be False — all scheduled employees are eligible"
        )

    @pytest.mark.asyncio
    async def test_empty_eligible_only_when_no_scheduled_employees(self):
        """Eligible is empty ONLY when no employees are scheduled on the shift — not because they're offline."""
        svc = EligibilityService(AsyncMock())
        svc.shift_service = MagicMock()
        shift = _make_shift()
        svc.shift_service.get_active_shift = AsyncMock(return_value=shift)
        # No employees scheduled
        svc.shift_service.get_shift_employees = AsyncMock(return_value=[])

        result = await svc.find_eligible_employees("Test Group", set(), datetime.now(timezone.utc))
        assert result == [], "Empty only when no scheduled employees, not because of presence"
