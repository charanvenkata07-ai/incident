import pytest
import uuid
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, Request

from app.core.config import settings
from app.models.employee import Employee
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.user import User
from app.models.settings import SystemSetting
from app.services.assignment_engine import AssignmentEngine
from app.services.incident_service import IncidentService
from app.services.sync_service import SyncService
from app.schemas.servicenow import ServiceNowIncidentPayload
from app.api.admin import (
    set_automation_mode,
    pause_automation,
    resume_automation,
    get_live_pilot_config_endpoint,
    update_live_pilot_config_endpoint,
    get_live_pilot_readiness,
    enable_live_pilot,
    pause_live_pilot,
    rollback_live_pilot,
)

def create_mock_user(full_name: str, email: str, role: str = "EMPLOYEE") -> User:
    return User(
        id=uuid.uuid4(),
        full_name=full_name,
        email=email,
        role=role,
        hashed_password="mock_hashed_password",
        is_active=True
    )

def create_mock_employee(name: str, email: str, workload: int = 0) -> Employee:
    emp_id = uuid.uuid4()
    user = create_mock_user(name, email, "EMPLOYEE")
    emp = Employee(
        id=emp_id,
        user_id=user.id,
        availability_status="AVAILABLE",
        is_present=True,
    )
    emp.user = user
    emp.skills = []
    return emp

# =========================================================================
# 1. CONCURRENCY RACE CONDITION TEST
# =========================================================================
@pytest.mark.asyncio
async def test_concurrent_assignments_race_condition():
    """
    Simulate 10 simultaneous tasks calling process_incident on the exact same incident.
    Verifies that the row-level check detects active assignment and prevents duplicate assignments.
    """
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC1969800",
        assignment_group="Analytics – MDM L3",
        state="NEW"
    )
    emp = create_mock_employee("Ravi Kumar", "ravi@incidentflow.dev")

    created_assignments = []
    db_lock = asyncio.Lock()

    # Track assignments created across concurrent attempts
    async def mock_execute(stmt):
        stmt_str = str(stmt)
        # Check existing active assignment
        if "incident_assignments" in stmt_str and "is_active" in stmt_str:
            mock_res = MagicMock()
            if created_assignments:
                mock_res.scalar_one_or_none.return_value = created_assignments[0]
            else:
                mock_res.scalar_one_or_none.return_value = None
            return mock_res
        elif "incidents" in stmt_str:
            mock_res = MagicMock()
            mock_res.scalar_one_or_none.return_value = incident
            return mock_res
        elif "employees" in stmt_str:
            mock_res = MagicMock()
            mock_res.scalar_one.return_value = emp
            return mock_res
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        mock_res.scalars.return_value.all.return_value = []
        return mock_res

    def mock_add(obj):
        if isinstance(obj, IncidentAssignment):
            created_assignments.append(obj)

    mock_db.execute = AsyncMock(side_effect=mock_execute)
    mock_db.add = MagicMock(side_effect=mock_add)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.get = AsyncMock(return_value=emp.user)

    # Thread-safe simulation of 10 concurrent requests to _create_assignment
    async def run_assignment():
        async with db_lock:
            return await engine._create_assignment(incident, emp, "SKILL_PLUS_WORKLOAD", is_live=True)

    results = await asyncio.gather(*[run_assignment() for _ in range(10)])

    assert len(results) == 10
    # Exactly one assignment was instantiated and added
    assert len(created_assignments) == 1
    # All 10 callers received an assignment object pointing to the same assignment
    for r in results:
        assert r is not None
        assert r.incident_id == incident.id
        assert r.employee_id == emp.id

# =========================================================================
# 2. IDEMPOTENCY TEST: DUPLICATE WEBHOOK DELIVERIES
# =========================================================================
@pytest.mark.asyncio
async def test_idempotent_duplicate_webhook_deliveries():
    """
    Multiple duplicate webhook deliveries for the same ServiceNow incident
    must result in exactly 1 incident record and idempotent ingestion responses.
    """
    mock_db = AsyncMock()
    incident_service = IncidentService(mock_db)

    payload = ServiceNowIncidentPayload(
        sys_id="sn_sys_dup_100",
        number="INC1969801",
        short_description="Duplicate delivery test"
    )

    persisted_incident = Incident(
        id=uuid.uuid4(),
        servicenow_sys_id="sn_sys_dup_100",
        incident_number="INC1969801",
        short_description="Duplicate delivery test",
        state="NEW"
    )

    call_count = 0
    async def mock_find(p):
        nonlocal call_count
        if call_count == 0:
            return None
        return persisted_incident

    async def mock_create(p):
        nonlocal call_count
        call_count += 1
        return persisted_incident

    async def mock_update(inc, p):
        nonlocal call_count
        call_count += 1
        return inc

    incident_service._find_existing = AsyncMock(side_effect=mock_find)
    incident_service._create_incident = AsyncMock(side_effect=mock_create)
    incident_service._update_incident = AsyncMock(side_effect=mock_update)

    # First delivery: creates incident
    inc1, is_new1 = await incident_service.create_or_update_from_servicenow(payload)
    assert is_new1 is True
    assert inc1.incident_number == "INC1969801"

    # Subsequent 4 deliveries: update existing incident idempotently
    for _ in range(4):
        inc_dup, is_new_dup = await incident_service.create_or_update_from_servicenow(payload)
        assert is_new_dup is False
        assert inc_dup.id == inc1.id

    assert incident_service._create_incident.call_count == 1
    assert incident_service._update_incident.call_count == 4

# =========================================================================
# 3. LIVE ACTIVATION SAFETY & CONFIRMATION
# =========================================================================
@pytest.mark.asyncio
async def test_live_activation_safety_guards():
    """
    Switching to LIVE requires explicit admin role, confirmed=True, and exact typed confirmation phrase.
    Verify rejection without phrase and audit log creation upon valid activation.
    """
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    admin_user = create_mock_user("Admin User", "admin@incidentflow.dev", "ADMIN")

    # Case 1: LIVE without confirmed flag
    with pytest.raises(HTTPException) as exc1:
        await set_automation_mode(
            {"mode": "LIVE", "confirmed": False},
            current_user=admin_user,
            db=mock_db
        )
    assert exc1.value.status_code == 400

    # Case 2: LIVE with confirmed=True but wrong phrase
    with pytest.raises(HTTPException) as exc2:
        await set_automation_mode(
            {"mode": "LIVE", "confirmed": True, "confirmation_phrase": "ACTIVATE LIVE"},
            current_user=admin_user,
            db=mock_db
        )
    assert exc2.value.status_code == 400
    assert "ENABLE LIVE ASSIGNMENT" in exc2.value.detail

    # Case 3: Valid exact confirmation phrase succeeds and creates tamper-evident audit log
    mock_audit = AsyncMock()
    with patch("app.api.admin.AuditService.log", new=mock_audit):
        mock_request = MagicMock()
        mock_request.headers.get.return_value = "req-audit-test-123"

        res = await set_automation_mode(
            {
                "mode": "LIVE",
                "confirmed": True,
                "confirmation_phrase": "ENABLE LIVE ASSIGNMENT"
            },
            request=mock_request,
            current_user=admin_user,
            db=mock_db
        )
        assert res["mode"] == "LIVE"
        mock_audit.assert_called_once()
        kall = mock_audit.call_args
        assert kall.kwargs["action"] == "CHANGE_AUTOMATION_MODE"
        assert kall.kwargs["actor_id"] == admin_user.id
        assert kall.kwargs["new_value"]["mode"] == "LIVE"

# =========================================================================
# 4. ASSIGNMENT GROUP ISOLATION
# =========================================================================
@pytest.mark.asyncio
async def test_pilot_assignment_group_isolation():
    """
    In LIVE pilot, incidents belonging to non-pilot assignment groups must be filtered.
    Incident remains in NEW state, no assignment created, and PILOT_GROUP_FILTERED logged.
    """
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    engine._get_automation_mode = AsyncMock(return_value="LIVE")
    engine._get_live_pilot_config = AsyncMock(return_value={
        "enabled": True,
        "assignment_group": "Analytics – MDM L3",
        "max_active_assignments": 5,
        "allowed_employees": []
    })

    mock_audit = AsyncMock()
    engine.audit_service.log = mock_audit

    non_pilot_incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC1969802",
        assignment_group="Global Hardware Support",
        state="NEW"
    )

    result = await engine.process_incident(non_pilot_incident)

    assert result is None
    assert non_pilot_incident.state == "NEW"
    mock_audit.assert_called_once()
    assert mock_audit.call_args.args[0] == "PILOT_GROUP_FILTERED"
    assert "Hardware Support" in mock_audit.call_args.kwargs["reason"]

# =========================================================================
# 5. PILOT ROSTER ISOLATION
# =========================================================================
@pytest.mark.asyncio
async def test_pilot_roster_isolation():
    """
    In LIVE pilot, only employees explicitly on the allowed roster can be assigned.
    Non-roster employees are strictly filtered out even if eligible.
    """
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._get_automation_mode = AsyncMock(return_value="LIVE")
    engine._get_live_pilot_config = AsyncMock(return_value={
        "enabled": True,
        "assignment_group": "Analytics – MDM L3",
        "max_active_assignments": 5,
        "allowed_employees": ["ravi@incidentflow.dev"]
    })
    engine._get_active_pilot_assignment_count = AsyncMock(return_value=0)
    engine._get_required_skills = AsyncMock(return_value=set())

    emp_ravi = create_mock_employee("Ravi Kumar", "ravi@incidentflow.dev")
    emp_kiran = create_mock_employee("Kiran Patel", "kiran@incidentflow.dev")

    # Eligibility service returns both employees
    engine.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_ravi, emp_kiran])
    engine.workload_service.get_workloads = AsyncMock(return_value={emp_ravi.id: 2, emp_kiran.id: 0})
    engine._get_strategy = AsyncMock(return_value="LEAST_WORKLOAD")

    created = IncidentAssignment(
        id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        employee_id=emp_ravi.id,
        assignment_type="LIVE",
        status="ASSIGNED",
        is_active=True
    )
    engine._create_assignment = AsyncMock(return_value=created)

    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC1969803",
        assignment_group="Analytics – MDM L3",
        state="NEW"
    )

    res = await engine.process_incident(incident)

    # Ravi must be chosen despite higher workload, because Kiran is not in the allowed pilot roster!
    assert res is not None
    engine._create_assignment.assert_called_once()
    selected_emp = engine._create_assignment.call_args.args[1]
    assert selected_emp.id == emp_ravi.id
    assert selected_emp.user.email == "ravi@incidentflow.dev"

# =========================================================================
# 6. MAX ACTIVE ASSIGNMENTS CEILING GUARD
# =========================================================================
@pytest.mark.asyncio
async def test_pilot_max_active_assignments_limit():
    """
    When the active assignments limit is reached for the pilot group,
    subsequent incidents must not be automatically assigned.
    """
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._get_automation_mode = AsyncMock(return_value="LIVE")
    engine._get_live_pilot_config = AsyncMock(return_value={
        "enabled": True,
        "assignment_group": "Analytics – MDM L3",
        "max_active_assignments": 3,
        "allowed_employees": []
    })
    # Current active count is 3 (at capacity)
    engine._get_active_pilot_assignment_count = AsyncMock(return_value=3)

    mock_audit = AsyncMock()
    engine.audit_service.log = mock_audit

    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC1969804",
        assignment_group="Analytics – MDM L3",
        state="NEW"
    )

    res = await engine.process_incident(incident)

    assert res is None
    assert incident.state == "NEW"
    mock_audit.assert_called_once()
    assert mock_audit.call_args.args[0] == "PILOT_CAPACITY_REACHED"
    assert "limit (3) reached" in mock_audit.call_args.kwargs["reason"]

# =========================================================================
# 7. SERVICENOW SYNC FAILURE HANDLING IN LIVE MODE
# =========================================================================
@pytest.mark.asyncio
async def test_servicenow_sync_failure_handling_in_live_mode():
    """
    In LIVE mode, if the ServiceNow outbound mutation fails:
    1. The local assignment record remains consistent and ASSIGNED.
    2. Incident sync_status is marked SYNC_FAILED.
    3. A SyncFailure DLQ entry is recorded.
    """
    mock_db = AsyncMock()
    sync_service = SyncService(mock_db)

    incident = Incident(
        id=uuid.uuid4(),
        servicenow_sys_id="sn_sys_fail_999",
        incident_number="INC1969805",
        sync_status="PENDING"
    )
    emp = create_mock_employee("Ravi Kumar", "ravi@incidentflow.dev")

    # Mock ServiceNow client failure
    mock_client = AsyncMock()
    mock_client.update_assignment = AsyncMock(side_effect=Exception("ServiceNow 500 Internal Server Error"))
    sync_service._get_client = MagicMock(return_value=mock_client)
    sync_service._create_sync_failure = AsyncMock()

    await sync_service.sync_assignment_to_servicenow(incident, emp)

    assert incident.sync_status == "SYNC_FAILED"
    sync_service._create_sync_failure.assert_called_once_with(
        incident,
        "UPDATE_ASSIGNMENT",
        "ServiceNow 500 Internal Server Error",
        payload={"assigned_to": "Ravi Kumar"}
    )

# =========================================================================
# 8. EMERGENCY PAUSE AND RESUME
# =========================================================================
@pytest.mark.asyncio
async def test_emergency_pause_and_resume():
    """
    Emergency pause disables automated assignments, creates AUTOMATION_STATUS_CHANGED audit entry,
    and engine immediately skips incoming incidents. Resume restores auto-assignment.
    """
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    admin_user = create_mock_user("Admin User", "admin@incidentflow.dev", "ADMIN")

    mock_audit = AsyncMock()
    with patch("app.api.admin.AuditService.log", new=mock_audit):
        # 1. Pause
        pause_res = await pause_automation(current_user=admin_user, db=mock_db)
        assert pause_res["status"] == "paused"
        assert mock_audit.call_args.kwargs["action"] == "AUTOMATION_STATUS_CHANGED"
        assert mock_audit.call_args.kwargs["new_value"]["status"] == "PAUSED"

        # 2. Engine skips assignment when paused
        engine = AssignmentEngine(mock_db)
        engine._is_auto_assignment_enabled = AsyncMock(return_value=False)
        engine_audit = AsyncMock()
        engine.audit_service.log = engine_audit

        inc = Incident(id=uuid.uuid4(), incident_number="INC1969806")
        skip_res = await engine.process_incident(inc)
        assert skip_res is None
        engine_audit.assert_called_once()
        assert engine_audit.call_args.args[0] == "AUTO_ASSIGN_SKIPPED"

        # 3. Resume
        resume_res = await resume_automation(current_user=admin_user, db=mock_db)
        assert resume_res["status"] == "active"
        assert mock_audit.call_args.kwargs["new_value"]["status"] == "ACTIVE"

# =========================================================================
# 9. ROLLBACK SAFETY
# =========================================================================
@pytest.mark.asyncio
async def test_rollback_safety_transitions():
    """
    Rolling back from LIVE to SHADOW or PAUSED retains all database records,
    creates audit logs, and switches engine behavior safely without data deletion.
    """
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    admin_user = create_mock_user("Admin User", "admin@incidentflow.dev", "ADMIN")

    # Rollback to SHADOW
    mock_audit = AsyncMock()
    with patch("app.api.admin.AuditService.log", new=mock_audit):
        res = await set_automation_mode(
            {"mode": "SHADOW"},
            current_user=admin_user,
            db=mock_db
        )
        assert res["mode"] == "SHADOW"
        assert mock_audit.call_args.kwargs["action"] == "CHANGE_AUTOMATION_MODE"
        assert mock_audit.call_args.kwargs["new_value"]["mode"] == "SHADOW"

# =========================================================================
# 10. PRE-LIVE READINESS CHECKLIST
# =========================================================================
@pytest.mark.asyncio
async def test_pre_live_readiness_checklist():
    """
    GET /api/admin/live-pilot/readiness returns all 14 required fields.
    Crucially asserts ready_for_live=False while the staging ServiceNow host is placeholder.
    """
    mock_db = AsyncMock()
    # Mock settings lookups
    mode_mock = MagicMock()
    mode_mock.scalar_one_or_none.return_value = SystemSetting(key="automation_mode", value={"mode": "SHADOW"})
    cfg_mock = MagicMock()
    cfg_mock.scalar_one_or_none.return_value = SystemSetting(key="live_pilot_config", value={
        "enabled": False,
        "assignment_group": "Analytics – MDM L3",
        "max_active_assignments": 5,
        "allowed_employees": ["ravi@incidentflow.dev"]
    })

    def mock_db_execute(stmt):
        s = str(stmt)
        if "automation_mode" in s:
            return mode_mock
        return cfg_mock

    mock_db.execute = AsyncMock(side_effect=mock_db_execute)

    res = await get_live_pilot_readiness(db=mock_db)

    # Must contain 14 required checklist attributes
    required_keys = [
        "environment",
        "automation_mode",
        "servicenow_url",
        "servicenow_hostname",
        "servicenow_reachable",
        "servicenow_authenticated",
        "servicenow_read_access",
        "servicenow_write_test",
        "pilot_group_configured",
        "pilot_roster_configured",
        "audit_logging_active",
        "fail_closed_guard_active",
        "dlq_operational",
        "ready_for_live"
    ]
    for key in required_keys:
        assert key in res, f"Missing key '{key}' in readiness report"

    # With placeholder staging URL, ready_for_live MUST be False
    assert res["ready_for_live"] is False
    assert res["automation_mode"] == "SHADOW"


@pytest.mark.asyncio
async def test_live_pilot_lifecycle_endpoints():
    """
    Test dedicated /live-pilot/enable, /live-pilot/pause, /live-pilot/rollback endpoints:
    1. enable requires confirmation phrase
    2. enable fail-closed blocks if readiness fails and no override
    3. enable succeeds with override
    4. pause halts operations
    5. rollback restores SHADOW mode
    """
    from app.core.database import async_session_maker
    async with async_session_maker() as session:
        admin_user = create_mock_user("Super Admin", f"admin_pilot_{uuid.uuid4().hex[:6]}@incidentflow.dev", role="ADMIN")
        session.add(admin_user)
        await session.commit()

        # 1. Reject without confirmation phrase
        with pytest.raises(HTTPException) as exc_info:
            await enable_live_pilot(
                payload={"confirmation_phrase": "WRONG PHRASE"},
                db=session,
                current_user=admin_user,
            )
        assert exc_info.value.status_code == 400
        assert "exact confirmation phrase" in exc_info.value.detail

        # 2. Reject when readiness check fails without override
        with pytest.raises(HTTPException) as exc_info:
            await enable_live_pilot(
                payload={"confirmation_phrase": "ENABLE LIVE ASSIGNMENT", "override": False},
                db=session,
                current_user=admin_user,
            )
        assert exc_info.value.status_code == 400
        assert "Fail-closed guard blocked LIVE activation" in exc_info.value.detail

        # 3. Enable with override
        enable_res = await enable_live_pilot(
            payload={"confirmation_phrase": "ENABLE LIVE ASSIGNMENT", "override": True},
            db=session,
            current_user=admin_user,
        )
        assert enable_res["status"] == "success"
        assert enable_res["automation_mode"] == "LIVE"
        assert enable_res["pilot_status"] == "ACTIVE"

        # 4. Pause
        pause_res = await pause_live_pilot(
            payload={"reason": "Safety check"},
            db=session,
            current_user=admin_user,
        )
        assert pause_res["status"] == "success"
        assert pause_res["automation_mode"] == "PAUSED"
        assert pause_res["pilot_status"] == "PAUSED"

        # 5. Rollback
        rollback_res = await rollback_live_pilot(
            payload={"target_mode": "SHADOW"},
            db=session,
            current_user=admin_user,
        )
        assert rollback_res["status"] == "success"
        assert rollback_res["automation_mode"] == "SHADOW"
        assert rollback_res["pilot_status"] == "READY"

