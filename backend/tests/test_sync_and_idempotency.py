import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.incident import Incident
from app.services.sync_service import SyncService
from app.services.incident_service import IncidentService
from app.schemas.servicenow import ServiceNowIncidentPayload

@pytest.mark.asyncio
async def test_duplicate_servicenow_events():
    mock_db = AsyncMock()
    incident_service = IncidentService(mock_db)
    
    payload = ServiceNowIncidentPayload(
        sys_id="sys_12345",
        number="INC1969714",
        short_description="MDM sync failure"
    )
    
    # Simulate existing incident found
    existing_incident = Incident(
        id=uuid.uuid4(),
        servicenow_sys_id="sys_12345",
        incident_number="INC1969714",
        short_description="MDM sync failure"
    )
    
    incident_service._find_existing = AsyncMock(return_value=existing_incident)
    incident_service._update_incident = AsyncMock(return_value=existing_incident)
    
    incident, is_new = await incident_service.create_or_update_from_servicenow(payload)
    assert is_new is False
    assert incident.incident_number == "INC1969714"
    incident_service._update_incident.assert_called_once_with(existing_incident, payload)

@pytest.mark.asyncio
async def test_servicenow_sync_failure_handling():
    mock_db = AsyncMock()
    sync_service = SyncService(mock_db)
    
    incident = Incident(
        id=uuid.uuid4(),
        servicenow_sys_id="sys_fail_1",
        incident_number="INC1969714",
        sync_status="PENDING"
    )
    
    emp = MagicMock()
    emp.user.full_name = "Ravi Kumar"
    
    # Mock client failure
    mock_client = AsyncMock()
    mock_client.update_assignment = AsyncMock(side_effect=Exception("ServiceNow API 503 Service Unavailable"))
    sync_service._get_client = MagicMock(return_value=mock_client)
    sync_service._create_sync_failure = AsyncMock()
    
    await sync_service.sync_assignment_to_servicenow(incident, emp)
    
    assert incident.sync_status == "SYNC_FAILED"
    sync_service._create_sync_failure.assert_called_once()
