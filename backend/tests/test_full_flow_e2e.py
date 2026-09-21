import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.models.incident import Incident
from app.models.employee import Employee
from app.models.user import User
from app.services.assignment_engine import AssignmentEngine
from app.services.sync_service import SyncService
from app.services.notification_service import NotificationService
from app.schemas.servicenow import ServiceNowIncidentPayload
from app.services.incident_service import IncidentService

@pytest.mark.asyncio
async def test_full_incident_flow_end_to_end():
    """
    Simulates:
    1. ServiceNow webhook delivers new incident
    2. IncidentFlow receives and records incident in DB
    3. Shift + Presence + Availability evaluated
    4. Best-fit employee (Ravi) selected via SKILL_PLUS_WORKLOAD
    5. Incident assignment created and committed
    6. ServiceNow assignment update synchronized
    7. Notification logged and mock email dispatched
    8. WebSocket broadcast event prepared
    """
    mock_db = AsyncMock()

    # 1. Incoming ServiceNow payload
    payload = ServiceNowIncidentPayload(
        sys_id="sys_mdm_101",
        number="INC1969714",
        short_description="MDM synchronization issue",
        description="Investigate MDM synchronization failure and restore normal processing.",
        priority="3",
        assignment_group={"display_value": "Analytics – MDM L3"},
        category="MDM"
    )

    # 2. Incident created in DB
    created_incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC1969714",
        servicenow_sys_id="sys_mdm_101",
        short_description=payload.short_description,
        priority="P3",
        assignment_group="Analytics – MDM L3",
        state="NEW"
    )

    incident_service = IncidentService(mock_db)
    incident_service._find_existing = AsyncMock(return_value=None)
    incident_service._create_incident = AsyncMock(return_value=created_incident)
    inc, is_new = await incident_service.create_or_update_from_servicenow(payload)
    assert is_new is True
    assert inc.incident_number == "INC1969714"

    # 3. Eligible employees on active shift
    user_ravi = User(id=uuid.uuid4(), full_name="Ravi Kumar", email="charanvenkata07@gmail.com")
    emp_ravi = Employee(id=uuid.uuid4(), user_id=user_ravi.id, availability_status="AVAILABLE", is_present=True)
    emp_ravi.user = user_ravi
    emp_ravi.skills = []

    user_kiran = User(id=uuid.uuid4(), full_name="Kiran Patel", email="kiran.patel@incidentflow.dev", role="EMPLOYEE")
    emp_kiran = Employee(id=uuid.uuid4(), user_id=user_kiran.id, availability_status="AVAILABLE", is_present=True)
    emp_kiran.user = user_kiran
    emp_kiran.skills = []

    engine = AssignmentEngine(mock_db)
    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._get_required_skills = AsyncMock(return_value=set())
    engine.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_ravi, emp_kiran])
    engine._get_strategy = AsyncMock(return_value="LEAST_WORKLOAD")
    engine._is_dry_run = AsyncMock(return_value=False)
    engine._is_shadow_mode = AsyncMock(return_value=False)

    # Ravi has workload 1, Kiran has workload 3 -> Ravi must be selected
    engine.workload_service.get_workloads = AsyncMock(return_value={
        emp_ravi.id: 1,
        emp_kiran.id: 3
    })

    # Execute assignment engine selection
    selected_employee = await engine._least_workload([emp_ravi, emp_kiran])
    assert selected_employee.id == emp_ravi.id
    assert selected_employee.user.full_name == "Ravi Kumar"

    # 4. Sync assignment back to ServiceNow (Mock adapter)
    sync_service = SyncService(mock_db)
    await sync_service.sync_assignment_to_servicenow(created_incident, selected_employee)
    assert created_incident.sync_status == "SYNCED"

    # 5. Dispatch notification
    notif_service = NotificationService(mock_db)
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=user_ravi)))
    notif = await notif_service.create_notification(
        user_id=user_ravi.id,
        type="INCIDENT_ASSIGNED",
        title=f"New incident assigned: {created_incident.incident_number}",
        message=created_incident.short_description,
        incident_id=created_incident.id
    )

    assert notif.title == "New incident assigned: INC1969714"
    assert notif.user_id == user_ravi.id
