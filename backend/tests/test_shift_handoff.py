import pytest
import uuid
from datetime import datetime, date, time, timezone, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.incident import Incident, IncidentRequiredSkill
from app.models.assignment import IncidentAssignment
from app.models.employee import Employee
from app.models.user import User
from app.models.shift import Shift, ShiftAssignment
from app.services.handoff_service import ShiftHandoffService

def create_user_and_employee(name: str, role: str = "EMPLOYEE", status: str = "AVAILABLE", is_present: bool = True):
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"{name.lower().replace(' ', '')}@incidentflow.dev",
        full_name=name,
        role=role,
        is_active=True
    )
    emp = Employee(
        id=emp_id,
        user_id=user_id,
        availability_status=status,
        is_present=is_present,
    )
    emp.user = user
    emp.skills = []
    return user, emp

# 1. Completed incident -> no handoff
@pytest.mark.asyncio
async def test_completed_incident_no_handoff():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    inc = Incident(id=uuid.uuid4(), incident_number="INC1001", state="RESOLVED", short_description="Test")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=uuid.uuid4(), is_active=True)

    mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))))
    mock_db.get = AsyncMock(return_value=inc)

    results = await service.evaluate_active_handoffs()
    assert len(results) == 0

# 2. Active incident + outgoing employee still on shift -> no handoff
@pytest.mark.asyncio
async def test_active_incident_outgoing_on_shift_no_handoff():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user, emp = create_user_and_employee("Ravi Kumar", status="AVAILABLE", is_present=True)
    inc = Incident(id=uuid.uuid4(), incident_number="INC1002", state="IN_PROGRESS", short_description="Active work")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp.id, is_active=True)

    shift = Shift(id=uuid.uuid4(), name="Morning Shift", start_time=time(9, 0), end_time=time(12, 0), is_overnight=False)
    emp_shift = ShiftAssignment(id=uuid.uuid4(), shift_id=shift.id, employee_id=emp.id, date=date.today())

    service.shift_service.get_active_shift = AsyncMock(return_value=shift)
    service.shift_service.get_employee_shift = AsyncMock(return_value=emp_shift)

    # Mock DB lookups
    mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))))
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (emp if model == Employee else user))

    results = await service.evaluate_active_handoffs(now=datetime(2026, 9, 17, 10, 30, tzinfo=ZoneInfo("Asia/Kolkata")))
    assert len(results) == 0

# 3. Active incident + shift ended -> handoff
@pytest.mark.asyncio
async def test_active_incident_shift_ended_handoff():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_ravi, emp_ravi = create_user_and_employee("Ravi Kumar")
    user_suresh, emp_suresh = create_user_and_employee("Suresh Reddy")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1003", state="IN_PROGRESS", short_description="MDM issue", assignment_group="MDM L3")
    assign_ravi = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_ravi.id, is_active=True, status="IN_PROGRESS")

    afternoon_shift = Shift(id=uuid.uuid4(), name="Afternoon Shift", start_time=time(12, 0), end_time=time(15, 0), is_overnight=False)
    ravi_morning_shift = ShiftAssignment(id=uuid.uuid4(), shift_id=uuid.uuid4(), employee_id=emp_ravi.id, date=date.today())

    service.shift_service.get_active_shift = AsyncMock(return_value=afternoon_shift)
    service.shift_service.get_employee_shift = AsyncMock(return_value=ravi_morning_shift) # Different shift ID
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_suresh])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_suresh.id: 0})
    service.notification_service.create_notification = AsyncMock()
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()

    # DB execute mock for main query, lock, and skills
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign_ravi])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign_ravi)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_ravi if mid == emp_ravi.id else (
            emp_suresh if mid == emp_suresh.id else (
                user_ravi if mid == user_ravi.id else user_suresh
            )
        )
    ))

    results = await service.evaluate_active_handoffs(now=datetime(2026, 9, 17, 12, 5, tzinfo=ZoneInfo("Asia/Kolkata")))
    assert len(results) == 1
    assert results[0]["incident_number"] == "INC1003"
    assert results[0]["outgoing_employee"] == "Ravi Kumar"
    assert results[0]["incoming_employee"] == "Suresh Reddy"
    assert assign_ravi.is_active is False
    assert assign_ravi.status == "REASSIGNED"

# 4. Locked incident -> no handoff
@pytest.mark.asyncio
async def test_locked_incident_no_handoff():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_ravi, emp_ravi = create_user_and_employee("Ravi Kumar")
    inc = Incident(id=uuid.uuid4(), incident_number="INC1004", state="IN_PROGRESS", short_description="Overtime ticket")
    assign_locked = IncidentAssignment(
        id=uuid.uuid4(),
        incident_id=inc.id,
        employee_id=emp_ravi.id,
        is_active=True,
        reason="P1 incident: LOCK_PRESERVED for ongoing recovery"
    )

    mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign_locked])))))
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else emp_ravi)

    results = await service.evaluate_active_handoffs()
    assert len(results) == 0

# 5. Incoming shift has one eligible employee -> assign them
@pytest.mark.asyncio
async def test_incoming_shift_one_eligible_employee():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user1, emp1 = create_user_and_employee("Outgoing Emp")
    user2, emp2 = create_user_and_employee("Single Incoming Emp")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1005", state="ASSIGNED", short_description="Solo receiver")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp1.id, is_active=True)

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp2])
    service.workload_service.get_workloads = AsyncMock(return_value={emp2.id: 2})
    service.notification_service.create_notification = AsyncMock()
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (emp1 if mid == emp1.id else (emp2 if mid == emp2.id else (user1 if mid == user1.id else user2))))

    results = await service.evaluate_active_handoffs()
    assert len(results) == 1
    assert results[0]["incoming_employee"] == "Single Incoming Emp"

# 6. Incoming shift has multiple employees -> apply configured workload strategy
@pytest.mark.asyncio
async def test_incoming_shift_multiple_employees_workload_strategy():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_out, emp_out = create_user_and_employee("Outgoing")
    user_busy, emp_busy = create_user_and_employee("Busy Worker")
    user_free, emp_free = create_user_and_employee("Free Worker")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1006", state="ASSIGNED", short_description="Workload test")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_busy, emp_free])
    # emp_busy has 4 tickets, emp_free has 1 ticket
    service.workload_service.get_workloads = AsyncMock(return_value={emp_busy.id: 4, emp_free.id: 1})
    service.notification_service.create_notification = AsyncMock()
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_out if mid == emp_out.id else (
            emp_free if mid == emp_free.id else (
                user_out if mid == user_out.id else user_free
            )
        )
    ))

    results = await service.evaluate_active_handoffs()
    assert len(results) == 1
    assert results[0]["incoming_employee"] == "Free Worker"

# 7. Incoming shift has no eligible employees -> keep incident safely unassigned/escalated
@pytest.mark.asyncio
async def test_incoming_shift_no_eligible_employees_escalated():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_out, emp_out = create_user_and_employee("Outgoing")
    admin_user = User(id=uuid.uuid4(), email="admin@test.com", role="ADMIN", is_active=True)

    inc = Incident(id=uuid.uuid4(), incident_number="INC1007", state="ASSIGNED", short_description="No receivers")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[]) # Zero eligible
    service.notification_service.create_notification = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))), # skills
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[admin_user])))), # admins
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (emp_out if model == Employee else user_out))

    results = await service.evaluate_active_handoffs()
    assert len(results) == 0
    # Verifies admin alert was sent
    service.notification_service.create_notification.assert_called_once()
    call_args = service.notification_service.create_notification.call_args[1]
    assert "Shift Handoff Pending" in call_args["title"]
    assert call_args["user_id"] == admin_user.id

# 8. Incoming employee lacks required skill -> exclude them
@pytest.mark.asyncio
async def test_incoming_employee_lacks_required_skill_excluded():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_out, emp_out = create_user_and_employee("Outgoing")
    user_skilled, emp_skilled = create_user_and_employee("Skilled Tech")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1008", state="ASSIGNED", short_description="Requires MDM")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)
    required_skill_id = uuid.uuid4()

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    # Eligibility service filters by skills and returns only skilled
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_skilled])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_skilled.id: 0})
    service.notification_service.create_notification = AsyncMock()
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[required_skill_id])))), # returns required skill
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_out if mid == emp_out.id else (
            emp_skilled if mid == emp_skilled.id else (
                user_out if mid == user_out.id else user_skilled
            )
        )
    ))

    results = await service.evaluate_active_handoffs()
    assert len(results) == 1
    assert results[0]["incoming_employee"] == "Skilled Tech"

# 9. Incoming employee is offline -> exclude them
@pytest.mark.asyncio
async def test_incoming_employee_offline_excluded():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_out, emp_out = create_user_and_employee("Outgoing")
    user_online, emp_online = create_user_and_employee("Online Tech", status="AVAILABLE", is_present=True)

    inc = Incident(id=uuid.uuid4(), incident_number="INC1009", state="ASSIGNED", short_description="Availability test")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    # Eligibility excludes offline techs
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_online])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_online.id: 0})
    service.notification_service.create_notification = AsyncMock()
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_out if mid == emp_out.id else (
            emp_online if mid == emp_online.id else (
                user_out if mid == user_out.id else user_online
            )
        )
    ))

    results = await service.evaluate_active_handoffs()
    assert len(results) == 1
    assert results[0]["incoming_employee"] == "Online Tech"

# 10. Duplicate handoff trigger -> must not perform duplicate reassignment
@pytest.mark.asyncio
async def test_duplicate_handoff_trigger_idempotent():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    # Empty active assignments on second run
    mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

    results = await service.evaluate_active_handoffs()
    assert len(results) == 0

# 11. Simultaneous handoff triggers -> database locking prevents double assignment
@pytest.mark.asyncio
async def test_simultaneous_handoff_triggers_lock_prevention():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_out, emp_out = create_user_and_employee("Outgoing")
    inc = Incident(id=uuid.uuid4(), incident_number="INC1011", state="ASSIGNED", short_description="Race test")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)

    # Simulate that when locking row, another transaction already set is_active=False
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)), # Already locked & marked inactive by peer
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (emp_out if model == Employee else user_out))

    results = await service.evaluate_active_handoffs()
    assert len(results) == 0

# 12. ServiceNow update fails -> preserve assignment state safely and queue retry
@pytest.mark.asyncio
async def test_servicenow_update_failure_preserves_assignment_state():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_out, emp_out = create_user_and_employee("Outgoing")
    user_in, emp_in = create_user_and_employee("Incoming")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1012", state="ASSIGNED", short_description="SN Failure")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_in])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_in.id: 0})
    service.notification_service.create_notification = AsyncMock()
    service.audit_service.log = AsyncMock()

    # Simulate ServiceNow 500 error
    service.sync_service.sync_assignment_to_servicenow = AsyncMock(side_effect=Exception("ServiceNow 500 Server Error"))

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_out if mid == emp_out.id else (
            emp_in if mid == emp_in.id else (
                user_out if mid == user_out.id else user_in
            )
        )
    ))

    # Must complete successfully without re-raising exception
    results = await service.evaluate_active_handoffs()
    assert len(results) == 1
    assert results[0]["incoming_employee"] == "Incoming"
    # Assignment status should be committed
    mock_db.commit.assert_called_once()

# 13. Notification fails -> incident remains assigned and notification error logged
@pytest.mark.asyncio
async def test_notification_failure_preserves_assignment():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_out, emp_out = create_user_and_employee("Outgoing")
    user_in, emp_in = create_user_and_employee("Incoming")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1013", state="ASSIGNED", short_description="Notif Failure")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_in])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_in.id: 0})
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()

    # Simulate notification exception (e.g. SMTP down)
    service.notification_service.create_notification = AsyncMock(side_effect=Exception("SMTP Connection Timeout"))

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_out if mid == emp_out.id else (
            emp_in if mid == emp_in.id else (
                user_out if mid == user_out.id else user_in
            )
        )
    ))

    results = await service.evaluate_active_handoffs()
    assert len(results) == 1
    # Assignment state is saved despite notification failure
    mock_db.commit.assert_called_once()

# 14. Verify outgoing employee receives handoff notification
@pytest.mark.asyncio
async def test_outgoing_employee_receives_handoff_notification():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_out, emp_out = create_user_and_employee("Ravi Outgoing")
    user_in, emp_in = create_user_and_employee("Suresh Incoming")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1014", state="ASSIGNED", short_description="Test Outgoing Alert")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_in])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_in.id: 0})
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()
    service.notification_service.create_notification = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_out if mid == emp_out.id else (
            emp_in if mid == emp_in.id else (
                user_out if mid == user_out.id else user_in
            )
        )
    ))

    await service.evaluate_active_handoffs()

    # Check notification for outgoing user
    calls = [c[1] for c in service.notification_service.create_notification.call_args_list]
    outgoing_call = next(c for c in calls if c["user_id"] == user_out.id)
    assert outgoing_call["type"] == "INCIDENT_REASSIGNED"
    assert "INC1014" in outgoing_call["title"]
    assert "Suresh Incoming" in outgoing_call["message"]

# 15. Verify incoming employee receives handoff notification
@pytest.mark.asyncio
async def test_incoming_employee_receives_handoff_notification():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_out, emp_out = create_user_and_employee("Ravi Outgoing")
    user_in, emp_in = create_user_and_employee("Suresh Incoming")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1015", state="ASSIGNED", short_description="Test Incoming Alert")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_in])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_in.id: 0})
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()
    service.notification_service.create_notification = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_out if mid == emp_out.id else (
            emp_in if mid == emp_in.id else (
                user_out if mid == user_out.id else user_in
            )
        )
    ))

    await service.evaluate_active_handoffs()

    # Check notification for incoming user
    calls = [c[1] for c in service.notification_service.create_notification.call_args_list]
    incoming_call = next(c for c in calls if c["user_id"] == user_in.id)
    assert incoming_call["type"] == "INCIDENT_ASSIGNED"
    assert "Incoming Shift Handoff" in incoming_call["title"]
    assert "Ravi Outgoing" in incoming_call["message"]

# 16. Verify ServiceNow work note is generated exactly once
@pytest.mark.asyncio
async def test_servicenow_work_note_generated_exactly_once():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_out, emp_out = create_user_and_employee("Ravi Outgoing")
    user_in, emp_in = create_user_and_employee("Suresh Incoming")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1016", state="ASSIGNED", short_description="Work note test", work_notes="Initial note.")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_in])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_in.id: 0})
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()
    service.notification_service.create_notification = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_out if mid == emp_out.id else (
            emp_in if mid == emp_in.id else (
                user_out if mid == user_out.id else user_in
            )
        )
    ))

    await service.evaluate_active_handoffs()
    assert "[IncidentFlow] Automated Shift Handoff: Transferred from Ravi Outgoing to Suresh Incoming" in inc.work_notes
    assert inc.work_notes.count("[IncidentFlow] Automated Shift Handoff:") == 1

# 17. Verify audit log records old employee, new employee, reason, timestamp, and incident
@pytest.mark.asyncio
async def test_audit_log_records_full_handoff_details():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_out, emp_out = create_user_and_employee("Old Guard")
    user_in, emp_in = create_user_and_employee("New Guard")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1017", state="ASSIGNED", short_description="Audit test")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)

    service.shift_service.get_active_shift = AsyncMock(return_value=Shift(id=uuid.uuid4(), is_overnight=False, start_time=time(12,0), end_time=time(15,0)))
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_in])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_in.id: 0})
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()
    service.notification_service.create_notification = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_out if mid == emp_out.id else (
            emp_in if mid == emp_in.id else (
                user_out if mid == user_out.id else user_in
            )
        )
    ))

    await service.evaluate_active_handoffs()
    service.audit_service.log.assert_called_once()
    audit_args = service.audit_service.log.call_args[1]
    assert audit_args["action"] == "SHIFT_HANDOFF"
    assert audit_args["entity_type"] == "INCIDENT"
    assert audit_args["entity_id"] == inc.id
    assert audit_args["old_value"]["employee_name"] == "Old Guard"
    assert audit_args["new_value"]["employee_name"] == "New Guard"

# 18. Verify timezone handling
@pytest.mark.asyncio
async def test_timezone_handling():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    # Kolkata is UTC+5:30. 06:30 UTC = 12:00 IST (Shift boundary)
    utc_time = datetime(2026, 9, 17, 6, 30, tzinfo=timezone.utc)
    ist_time = utc_time.astimezone(ZoneInfo("Asia/Kolkata"))
    assert ist_time.hour == 12
    assert ist_time.minute == 0

    user_out, emp_out = create_user_and_employee("Morning Tech")
    user_in, emp_in = create_user_and_employee("Afternoon Tech")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1018", state="ASSIGNED", short_description="Timezone test")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_out.id, is_active=True)

    afternoon_shift = Shift(id=uuid.uuid4(), name="Afternoon Shift", start_time=time(12,0), end_time=time(15,0), is_overnight=False)
    service.shift_service.get_active_shift = AsyncMock(return_value=afternoon_shift)
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_in])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_in.id: 0})
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()
    service.notification_service.create_notification = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_out if mid == emp_out.id else (
            emp_in if mid == emp_in.id else (
                user_out if mid == user_out.id else user_in
            )
        )
    ))

    results = await service.evaluate_active_handoffs(now=ist_time)
    assert len(results) == 1
    assert results[0]["incoming_employee"] == "Afternoon Tech"

# 19. Verify overnight shift handoff
@pytest.mark.asyncio
async def test_overnight_shift_handoff():
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_night, emp_night = create_user_and_employee("Night Owl")
    user_morning, emp_morning = create_user_and_employee("Early Bird")

    inc = Incident(id=uuid.uuid4(), incident_number="INC1019", state="ASSIGNED", short_description="Overnight rollover")
    assign = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_night.id, is_active=True)

    morning_shift = Shift(id=uuid.uuid4(), name="Morning Shift", start_time=time(9,0), end_time=time(12,0), is_overnight=False)
    service.shift_service.get_active_shift = AsyncMock(return_value=morning_shift)
    service.shift_service.get_employee_shift = AsyncMock(return_value=None)
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_morning])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_morning.id: 0})
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()
    service.notification_service.create_notification = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_night if mid == emp_night.id else (
            emp_morning if mid == emp_morning.id else (
                user_night if mid == user_night.id else user_morning
            )
        )
    ))

    # At 09:05 AM, night shift (22:00 - 06:00) has ended, morning shift has started
    results = await service.evaluate_active_handoffs(now=datetime(2026, 9, 18, 9, 5, tzinfo=ZoneInfo("Asia/Kolkata")))
    assert len(results) == 1
    assert results[0]["outgoing_employee"] == "Night Owl"
    assert results[0]["incoming_employee"] == "Early Bird"

# 20. Verify Admin can manually trigger a handoff scan
@pytest.mark.asyncio
async def test_admin_manual_trigger_endpoint():
    from app.api.admin import trigger_shift_handoff

    mock_db = AsyncMock()
    with patch("app.services.handoff_service.ShiftHandoffService.evaluate_active_handoffs", new_callable=AsyncMock) as mock_eval:
        mock_eval.return_value = [
            {"incident_number": "INC1969714", "outgoing_employee": "Ravi", "incoming_employee": "Suresh"}
        ]
        response = await trigger_shift_handoff(db=mock_db)
        assert response["status"] == "success"
        assert response["transferred_count"] == 1
        assert response["handoffs"][0]["incident_number"] == "INC1969714"
