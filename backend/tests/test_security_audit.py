import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.core.config import settings
from app.models.user import User
from app.models.employee import Employee
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.notification import Notification
from app.integrations.servicenow.client import ServiceNowClient
from app.api.incidents import get_incident, acknowledge_incident
from app.api.notifications import read_notification
from app.api.auth import register
from app.schemas.auth import RegisterRequest
from app.schemas.servicenow import ServiceNowIncidentPayload
from app.integrations.servicenow.webhook import receive_incident

@pytest.mark.asyncio
async def test_idor_employee_cannot_view_unassigned_incident():
    """IDOR: An employee cannot access details or timeline of an incident assigned to someone else."""
    mock_db = AsyncMock()
    
    current_user = User(id=uuid.uuid4(), email="emp1@test.com", full_name="User One", role="EMPLOYEE")
    emp1 = Employee(id=uuid.uuid4(), user_id=current_user.id)
    
    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC88888",
        short_description="Confidential ticket",
        assigned_to="User Two"
    )
    
    # DB mock: Incident exists, employee exists, but has no assignment for this incident
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=incident)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=emp1)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
    ])
    
    with pytest.raises(HTTPException) as exc_info:
        await get_incident(incident_number="INC88888", current_user=current_user, db=mock_db)
    
    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.detail

@pytest.mark.asyncio
async def test_idor_employee_cannot_modify_unassigned_incident_assignment():
    """IDOR: An employee cannot acknowledge, start, or complete another employee's active assignment."""
    mock_db = AsyncMock()
    
    attacker_user = User(id=uuid.uuid4(), email="attacker@test.com", full_name="Attacker", role="EMPLOYEE")
    attacker_emp = Employee(id=uuid.uuid4(), user_id=attacker_user.id)
    victim_emp_id = uuid.uuid4()
    
    target_incident_id = str(uuid.uuid4())
    assignment = IncidentAssignment(
        id=uuid.uuid4(),
        incident_id=uuid.UUID(target_incident_id),
        employee_id=victim_emp_id,
        is_active=True,
        status="ASSIGNED"
    )
    
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=assignment)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=attacker_emp))
    ])
    
    with pytest.raises(HTTPException) as exc_info:
        await acknowledge_incident(incident_id=target_incident_id, current_user=attacker_user, db=mock_db)
    
    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.detail

@pytest.mark.asyncio
async def test_idor_employee_cannot_mark_other_user_notification_as_read():
    """IDOR: User cannot mark another user's notifications as read."""
    mock_db = AsyncMock()
    
    current_user = User(id=uuid.uuid4(), email="user1@test.com", full_name="User 1", role="EMPLOYEE")
    other_user_id = uuid.uuid4()
    
    notif = Notification(
        id=uuid.uuid4(),
        user_id=other_user_id,
        type="INCIDENT_ASSIGNED",
        title="Notice",
        message="Text",
        is_read=False
    )
    
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=notif)))
    
    with pytest.raises(HTTPException) as exc_info:
        await read_notification(id=str(notif.id), current_user=current_user, db=mock_db)
    
    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.detail

def test_ssrf_servicenow_client_blocks_aws_metadata_and_internal_ips():
    """SSRF: ServiceNowClient must block requests targeting cloud metadata and private network ranges."""
    with pytest.raises(ValueError) as exc1:
        ServiceNowClient.validate_target_url("http://169.254.169.254/latest/meta-data", environment="STAGING")
    assert "SSRF Protection" in str(exc1.value)
    
    with pytest.raises(ValueError) as exc2:
        ServiceNowClient.validate_target_url("https://10.0.0.1/api/now/table/incident", environment="PRODUCTION")
    assert "SSRF Protection" in str(exc2.value)

    with pytest.raises(ValueError) as exc3:
        ServiceNowClient.validate_target_url("http://dev12345.service-now.com", environment="PRODUCTION")
    assert "Insecure scheme" in str(exc3.value)

    # Valid HTTPS ServiceNow staging URL must be allowed
    try:
        ServiceNowClient.validate_target_url("https://dev12345.service-now.com", environment="PRODUCTION")
    except ValueError:
        pytest.fail("Valid HTTPS ServiceNow staging URL should not raise ValueError")

@pytest.mark.asyncio
async def test_privilege_escalation_in_registration_blocked():
    """Privilege escalation: Unauthenticated registration cannot claim ADMIN role in staging/production."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    
    req = RegisterRequest(
        email="attacker@test.com",
        password="ValidPassword123!",
        full_name="Attacker",
        role="ADMIN"
    )
    
    with patch.object(settings, "ENVIRONMENT", "PRODUCTION"):
        with pytest.raises(HTTPException) as exc_info:
            await register(req=req, db=mock_db)
        assert exc_info.value.status_code == 403
        assert "Privilege escalation prohibited" in exc_info.value.detail

@pytest.mark.asyncio
async def test_registration_short_password_rejected():
    """Password Policy: Short passwords under 8 characters must be rejected."""
    mock_db = AsyncMock()
    req = RegisterRequest(
        email="short@test.com",
        password="123",
        full_name="User",
        role="EMPLOYEE"
    )
    with pytest.raises(HTTPException) as exc_info:
        await register(req=req, db=mock_db)
    assert exc_info.value.status_code == 400
    assert "Password must be at least 8 characters long" in exc_info.value.detail

@pytest.mark.asyncio
async def test_webhook_oversized_payload_rejected():
    """Webhook: Payloads exceeding 1MB must be rejected with HTTP 413."""
    mock_request = MagicMock()
    mock_request.headers = {"content-length": "2000000"}
    
    payload = ServiceNowIncidentPayload(sys_id="sys_huge", number="INC99999")
    mock_db = AsyncMock()
    
    with pytest.raises(HTTPException) as exc_info:
        await receive_incident(
            payload=payload,
            request=mock_request,
            db=mock_db,
            x_servicenow_secret="token",
            authorization=None
        )
    assert exc_info.value.status_code == 413
    assert "Payload exceeds maximum limit" in exc_info.value.detail

@pytest.mark.asyncio
async def test_security_headers_present():
    """Security Headers: Middleware must attach enterprise defense headers."""
    from app.core.middleware import SecurityHeadersMiddleware
    
    app_mock = MagicMock()
    middleware = SecurityHeadersMiddleware(app_mock)
    
    mock_request = MagicMock()
    mock_request.url.scheme = "https"
    
    async def call_next(req):
        from starlette.responses import Response
        return Response(content="ok", media_type="text/plain")
        
    response = await middleware.dispatch(mock_request, call_next)
    
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" in response.headers
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
