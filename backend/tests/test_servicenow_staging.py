import pytest
import uuid
import httpx
from datetime import datetime, time, date, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.integrations.servicenow.client import ServiceNowClient
from app.integrations.servicenow.mapper import ServiceNowMapper
from app.models.incident import Incident, IncidentRequiredSkill
from app.models.assignment import IncidentAssignment
from app.models.employee import Employee
from app.models.user import User
from app.models.team import Team
from app.models.shift import Shift, ShiftAssignment
from app.models.integration import IntegrationEvent, SyncFailure
from app.models.audit import AuditLog
from app.schemas.servicenow import ServiceNowIncidentPayload
from app.services.incident_service import IncidentService
from app.services.assignment_engine import AssignmentEngine
from app.services.eligibility import EligibilityService
from app.services.sync_service import SyncService
from app.services.handoff_service import ShiftHandoffService

# ==============================================================================
# 1. SERVICENOW CLIENT & SAFETY GUARD TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_servicenow_client_test_connection_success():
    client = ServiceNowClient(
        base_url="https://dev-staging.service-now.com",
        username="incidentflow_svc",
        password="test_password"
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": [{"sys_id": "abc123"}]}

    with patch.object(client, "_execute_with_retry", new=AsyncMock(return_value=mock_resp)):
        res = await client.test_connection()
        assert res["status"] == "connected"
        assert res["status_code"] == 200
        assert res["records_found"] == 1

@pytest.mark.asyncio
async def test_servicenow_client_test_connection_auth_failed():
    client = ServiceNowClient(
        base_url="https://dev-staging.service-now.com",
        username="bad_user",
        password="bad_password"
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "User Not Authenticated"

    with patch.object(client, "_execute_with_retry", new=AsyncMock(return_value=mock_resp)):
        res = await client.test_connection()
        assert res["status"] == "auth_failed"
        assert res["status_code"] == 401

@pytest.mark.asyncio
async def test_servicenow_client_mutation_prohibited_in_shadow_mode():
    """Verify ServiceNow staging ticket is NEVER mutated when AUTOMATION_MODE=SHADOW."""
    client = ServiceNowClient(base_url="https://dev-staging.service-now.com")
    
    with patch.object(settings, "AUTOMATION_MODE", "SHADOW"), \
         patch.object(settings, "SHADOW_MODE", True):
        
        # update_incident
        res_inc = await client.update_incident("sys_999", {"assigned_to": "Ravi Kumar"})
        assert res_inc["status"] == "skipped"
        assert "SHADOW" in res_inc["reason"]

        # update_assignment
        res_assign = await client.update_assignment("sys_999", "Ravi Kumar")
        assert res_assign["status"] == "skipped"

        # add_work_note
        res_note = await client.add_work_note("sys_999", "Testing note")
        assert res_note["status"] == "skipped"

# ==============================================================================
# 2. FIELD MAPPING & INGESTION TESTS
# ==============================================================================

def test_servicenow_mapper_defensive_field_extraction():
    mapper = ServiceNowMapper()
    raw_payload = {
        "number": "INC1969714",
        "sys_id": "sys_mdm_999",
        "short_description": "MDM synchronization issue",
        "description": "Kafka consumer group lagged by 50,000 events",
        "priority": "1 - Critical",
        "impact": "1",
        "urgency": "1",
        "assignment_group": {"display_value": "Analytics – MDM L3"},
        "assigned_to": {"display_value": ""},
        "caller_id": {"display_value": "Monitoring System"},
        "cmdb_ci": {"display_value": "kafka-prod-cluster-01"},
        "state": "1 - New",
        "u_work_instructions": "Check lag on partition 4, restart worker pod if stuck.",
        "work_notes": "Alert triggered at 11:55 AM",
        "opened_at": "2026-09-17T11:55:00Z"
    }

    incident_dict = mapper.to_incident(raw_payload)
    assert incident_dict["incident_number"] == "INC1969714"
    assert incident_dict["servicenow_sys_id"] == "sys_mdm_999"
    assert incident_dict["priority"] == "P1"
    assert incident_dict["assignment_group"] == "Analytics – MDM L3"
    assert incident_dict["configuration_item"] == "kafka-prod-cluster-01"
    assert incident_dict["state"] == "NEW"
    assert incident_dict["work_instructions"] == "Check lag on partition 4, restart worker pod if stuck."

@pytest.mark.asyncio
async def test_incident_service_idempotent_ingest():
    mock_db = AsyncMock()
    service = IncidentService(mock_db)

    payload = ServiceNowIncidentPayload(
        sys_id="sys_111",
        number="INC1969714",
        short_description="MDM Sync lag",
        priority="2",
        u_work_instructions="Restart pod"
    )

    # First ingest: new ticket
    service._find_existing = AsyncMock(return_value=None)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    inc, is_new = await service.create_or_update_from_servicenow(payload)
    assert is_new is True
    assert inc.incident_number == "INC1969714"

    # Second ingest: duplicate/update
    service._find_existing = AsyncMock(return_value=inc)
    updated_inc, is_new_dup = await service.create_or_update_from_servicenow(payload)
    assert is_new_dup is False
    assert updated_inc.incident_number == "INC1969714"

# ==============================================================================
# 3. WEBHOOK SECURITY & AUTHENTICATION TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_webhook_unauthorized_when_secret_mismatch():
    from app.integrations.servicenow.webhook import receive_incident
    from fastapi import HTTPException

    mock_db = AsyncMock()
    payload = ServiceNowIncidentPayload(sys_id="sys_sec_1", number="INC9901")

    with patch.object(settings, "SERVICENOW_WEBHOOK_SECRET", "super_secret_token_123"):
        # Without secret header
        with pytest.raises(HTTPException) as exc:
            await receive_incident(payload=payload, db=mock_db, x_servicenow_secret=None, authorization=None)
        assert exc.value.status_code == 401

        # With wrong secret
        with pytest.raises(HTTPException) as exc:
            await receive_incident(payload=payload, db=mock_db, x_servicenow_secret="wrong_secret", authorization=None)
        assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_webhook_authorized_and_records_integration_event():
    from app.integrations.servicenow.webhook import receive_incident

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    payload = ServiceNowIncidentPayload(
        sys_id="sys_sec_2",
        number="INC9902",
        short_description="Staging test webhook"
    )

    with patch.object(settings, "SERVICENOW_WEBHOOK_SECRET", "super_secret_token_123"), \
         patch("app.integrations.servicenow.webhook.IncidentService.create_or_update_from_servicenow",
               new=AsyncMock(return_value=(Incident(id=uuid.uuid4(), incident_number="INC9902", servicenow_sys_id="sys_sec_2"), True))), \
         patch("app.integrations.servicenow.webhook.AssignmentEngine.process_incident", new=AsyncMock()):

        res = await receive_incident(
            payload=payload,
            db=mock_db,
            x_servicenow_secret="super_secret_token_123",
            authorization=None
        )
        assert res["status"] == "processed"
        assert res["incident_number"] == "INC9902"
        assert res["sys_id"] == "sys_sec_2"
        assert mock_db.commit.called

# ==============================================================================
# 4. SHADOW MODE CANDIDATE AUDITING & MULTI-SHIFT WORKFLOW (10 EMPLOYEES)
# ==============================================================================

@pytest.mark.asyncio
async def test_shadow_mode_candidate_pipeline_and_dossier():
    """
    Test real staging scenario:
    10 employees across shifts.
    Shift 1 (09:00 - 12:00): Ravi (workload 2), Kiran (workload 5).
    Shift 2 (12:00 - 15:00): Suresh, Arun.
    Incident arrives for 'Analytics – MDM L3'.
    IncidentFlow identifies Ravi as lowest-workload eligible engineer,
    records candidate dossier with explicit rejection reasons,
    and preserves ServiceNow without mutation.
    """
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    # Shift 1 active
    shift1 = Shift(id=uuid.uuid4(), name="Morning Shift", start_time=time(9, 0), end_time=time(12, 0))
    team_mdm = Team(id=uuid.uuid4(), name="Analytics – MDM L3", servicenow_group_id="analytics_mdm_l3")

    # Shift 1 engineers
    user_ravi = User(id=uuid.uuid4(), full_name="Ravi Kumar", email="ravi@incidentflow.dev")
    emp_ravi = Employee(id=uuid.uuid4(), user_id=user_ravi.id, availability_status="AVAILABLE", is_present=True, team=team_mdm)
    emp_ravi.user = user_ravi

    user_kiran = User(id=uuid.uuid4(), full_name="Kiran Patel", email="kiran@incidentflow.dev")
    emp_kiran = Employee(id=uuid.uuid4(), user_id=user_kiran.id, availability_status="AVAILABLE", is_present=True, team=team_mdm)
    emp_kiran.user = user_kiran

    # Simulated candidate dossier
    eligible_summary = [
        {"employee_id": str(emp_ravi.id), "employee_name": "Ravi Kumar", "active_workload": 2},
        {"employee_id": str(emp_kiran.id), "employee_name": "Kiran Patel", "active_workload": 5}
    ]
    rejected_summary = [
        {"employee_id": "emp_suresh", "employee_name": "Suresh Reddy", "reason": "OFF_SHIFT (Shift 2: 12:00 - 15:00)"},
        {"employee_id": "emp_arun", "employee_name": "Arun Verma", "reason": "MISSING_SKILL: MDM"},
        {"employee_id": "emp_deepa", "employee_name": "Deepa Shah", "reason": "Availability status is BUSY"}
    ]

    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC1969714",
        servicenow_sys_id="sys_mdm_1969714",
        short_description="MDM synchronization issue",
        assignment_group="Analytics – MDM L3",
        priority="P3"
    )

    engine.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_ravi, emp_kiran])
    engine.eligibility.last_pipeline = {
        "active_shift": shift1,
        "eligible": [emp_ravi, emp_kiran],
        "rejected": rejected_summary,
        "details": {"shift_name": "Morning Shift (09:00 - 12:00)"}
    }
    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._get_required_skills = AsyncMock(return_value=set())
    engine._get_strategy = AsyncMock(return_value="SKILL_PLUS_WORKLOAD")
    engine.workload_service.get_workloads = AsyncMock(return_value={emp_ravi.id: 2, emp_kiran.id: 5})
    engine._is_dry_run = AsyncMock(return_value=False)
    engine._is_shadow_mode = AsyncMock(return_value=True) # SHADOW active
    engine.audit_service.log = AsyncMock()

    result = await engine.process_incident(incident)

    # 1. Zero destructive assignment in SHADOW mode
    assert result is None

    # 2. Audit log must record SHADOW_ASSIGN with candidate dossier
    engine.audit_service.log.assert_called_once()
    args, kwargs = engine.audit_service.log.call_args
    assert args[0] == "SHADOW_ASSIGN"
    assert args[1] == "INCIDENT"
    assert args[2] == incident.id

    dossier = kwargs["new_value"]
    assert dossier["selected_employee"]["name"] == "Ravi Kumar"
    assert len(dossier["eligible_candidates"]) == 2
    assert len(dossier["rejected_candidates"]) == 3
    assert dossier["strategy"] == "SKILL_PLUS_WORKLOAD"
    assert "Shadow Mode" in kwargs["reason"]

# ==============================================================================
# 5. SHIFT HANDOFF IN SHADOW MODE
# ==============================================================================

@pytest.mark.asyncio
async def test_shift_handoff_evaluates_correct_incoming_peer():
    """Shift 1 (09:00-12:00) ends -> ticket evaluated for Shift 2 incoming peer."""
    mock_db = AsyncMock()
    service = ShiftHandoffService(mock_db)

    user_ravi = User(id=uuid.uuid4(), full_name="Ravi Kumar")
    emp_ravi = Employee(id=uuid.uuid4(), user_id=user_ravi.id, availability_status="AVAILABLE", is_present=True)

    user_c = User(id=uuid.uuid4(), full_name="Employee C")
    emp_c = Employee(id=uuid.uuid4(), user_id=user_c.id, availability_status="AVAILABLE", is_present=True)

    inc = Incident(id=uuid.uuid4(), incident_number="INC1969714", state="IN_PROGRESS", assignment_group="Analytics – MDM L3")
    assign_ravi = IncidentAssignment(id=uuid.uuid4(), incident_id=inc.id, employee_id=emp_ravi.id, is_active=True, status="IN_PROGRESS")

    afternoon_shift = Shift(id=uuid.uuid4(), name="Shift 2 (12:00-15:00)", start_time=time(12, 0), end_time=time(15, 0))
    ravi_morning = ShiftAssignment(id=uuid.uuid4(), shift_id=uuid.uuid4(), employee_id=emp_ravi.id, date=date.today())

    service.shift_service.get_active_shift = AsyncMock(return_value=afternoon_shift)
    service.shift_service.get_employee_shift = AsyncMock(return_value=ravi_morning) # Shift expired
    service.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_c])
    service.workload_service.get_workloads = AsyncMock(return_value={emp_c.id: 0})
    service.notification_service.create_notification = AsyncMock()
    service.audit_service.log = AsyncMock()
    service.sync_service.sync_assignment_to_servicenow = AsyncMock()

    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[assign_ravi])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=assign_ravi)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ])
    mock_db.get = AsyncMock(side_effect=lambda model, mid: inc if model == Incident else (
        emp_ravi if mid == emp_ravi.id else (
            emp_c if mid == emp_c.id else (
                user_ravi if mid == user_ravi.id else user_c
            )
        )
    ))

    # Evaluate at 12:01 (Shift 2)
    results = await service.evaluate_active_handoffs(now=datetime(2026, 9, 17, 12, 1, tzinfo=ZoneInfo("Asia/Kolkata")))
    assert len(results) == 1
    assert results[0]["outgoing_employee"] == "Ravi Kumar"
    assert results[0]["incoming_employee"] == "Employee C"

# ==============================================================================
# 6. FAILURE RECOVERY & DLQ SYSTEM
# ==============================================================================

@pytest.mark.asyncio
async def test_dlq_sync_failure_retry_and_dead_letter():
    mock_db = AsyncMock()
    sync_service = SyncService(mock_db)

    fail1 = SyncFailure(
        id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        operation="UPDATE_ASSIGNMENT",
        retry_count=0,
        max_retries=3,
        status="PENDING",
        payload={"assigned_to": "Ravi Kumar"}
    )
    fail_exhausted = SyncFailure(
        id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        operation="UPDATE_STATUS",
        retry_count=3,
        max_retries=3,
        status="PENDING",
        payload={"state": "IN_PROGRESS"}
    )

    mock_db.execute = AsyncMock(return_value=MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[fail1, fail_exhausted])))
    ))
    mock_db.get = AsyncMock(return_value=Incident(id=uuid.uuid4(), incident_number="INC8801", servicenow_sys_id="sys_8801"))
    mock_db.commit = AsyncMock()

    # Mock client update_assignment to succeed
    sync_service.client.update_assignment = AsyncMock(return_value={"status": "skipped"})

    stats = await sync_service.retry_failed_syncs()
    assert stats["processed"] == 2
    assert stats["recovered"] == 1
    assert stats["dead_lettered"] == 1
    assert fail1.status == "RESOLVED"
    assert fail_exhausted.status == "DEAD_LETTER"

# ==============================================================================
# 7. EMAIL FORMATTING TEST
# ==============================================================================

@pytest.mark.asyncio
async def test_email_payload_formatting():
    """Verify test-email endpoint returns safe result structure."""
    from app.api.admin import test_email_dispatch

    mock_db = AsyncMock()
    # User lookup returns None (recipient not a DB user — OK)
    scalar_mock = MagicMock()
    scalar_mock.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=scalar_mock)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    payload = {
        "recipient": "ravi@incidentflow.dev",
        "incident_number": "INC1969714",
        "short_description": "MDM synchronization issue",
        "priority": "P3"
    }
    result = await test_email_dispatch(payload, db=mock_db)

    # Basic structure checks
    assert "probe" in result
    assert "send" in result
    assert result["environment"] in ("STAGING", "DEVELOPMENT", "PRODUCTION")
    # Password must never appear in result
    assert settings.SMTP_PASSWORD not in str(result) if settings.SMTP_PASSWORD else True
    # send result has provider field
    assert "provider" in result["send"]

# ==============================================================================
# 8. SEND INCIDENT NOTIFICATION FEATURE TESTS (SEND != ASSIGN)
# ==============================================================================

@pytest.mark.asyncio
async def test_send_incident_preview_and_dispatch():
    from app.api.admin import preview_send_incident, send_incident_notification
    from fastapi import HTTPException

    mock_db = AsyncMock()
    inc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    emp_id = uuid.uuid4()

    test_user = User(id=user_id, full_name="Ravi Kumar", email="ravi@incidentflow.dev")
    test_emp = Employee(id=emp_id, user_id=user_id, availability_status="AVAILABLE", is_present=True)
    test_inc = Incident(
        id=inc_id,
        incident_number="INC1969714",
        short_description="MDM Sync degradation",
        priority="P2",
        assigned_to="Original Assignee",
        state="NEW"
    )

    mock_db.get = AsyncMock(side_effect=lambda model, mid: (
        test_inc if model == Incident and mid == inc_id else (
            test_emp if model == Employee and mid == emp_id else (
                test_user if model == User and mid == user_id else None
            )
        )
    ))
    mock_db.commit = AsyncMock()

    # 1. Preview
    preview_res = await preview_send_incident(
        incident_id=inc_id,
        payload={"employee_ids": [str(emp_id)], "message": "Investigate immediately"},
        db=mock_db
    )
    assert preview_res["recipient_count"] == 1
    assert preview_res["recipients"][0]["email"] == "ravi@incidentflow.dev"
    assert "Investigate immediately" in preview_res["body_preview"]
    assert "Incident assigned_to remains untouched" in preview_res["policy_note"]

    # 2. Dispatch without confirmation must fail
    with pytest.raises(HTTPException) as exc:
        await send_incident_notification(
            incident_id=inc_id,
            payload={"employee_ids": [str(emp_id)], "confirmed": False},
            db=mock_db
        )
    assert exc.value.status_code == 400

    # 3. Confirmed Dispatch
    with patch("app.api.admin.NotificationService.create_notification", new=AsyncMock()), \
         patch("app.api.admin.AuditService.log", new=AsyncMock()) as mock_audit:
        
        send_res = await send_incident_notification(
            incident_id=inc_id,
            payload={"employee_ids": [str(emp_id)], "confirmed": True},
            db=mock_db
        )
        assert send_res["status"] == "sent"
        assert send_res["dispatched_count"] == 1
        assert send_res["servicenow_modified"] is False
        assert send_res["assigned_to_modified"] is False
        
        # Verify SEND does not ASSIGN
        assert test_inc.assigned_to == "Original Assignee"
        assert test_inc.state == "NEW"
        
        # Verify Audit Log
        mock_audit.assert_called_once()
        args, kwargs = mock_audit.call_args
        assert kwargs["action"] == "SEND_INCIDENT_NOTIFICATION"

# ==============================================================================
# 9. INTEGRATION CONTROL CENTER & DIAGNOSTICS TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_integration_status_configured_vs_unverified():
    from app.api.admin import servicenow_integration_status

    mock_db = AsyncMock()
    mock_audit_res = MagicMock()
    mock_audit_res.scalar_one_or_none.return_value = None  # Never verified via real call

    mock_db.execute = AsyncMock(return_value=mock_audit_res)

    # With placeholder credentials in env
    status = await servicenow_integration_status(db=mock_db)
    assert "connection_status" in status
    assert "config_checklist" in status
    assert status["config_checklist"]["readonly_connection"]["verified"] is False

@pytest.mark.asyncio
async def test_integration_events_listing_and_secret_redaction():
    from app.api.admin import list_integration_events

    mock_db = AsyncMock()
    ev_id = uuid.uuid4()
    test_event = IntegrationEvent(
        id=ev_id,
        event_type="INCIDENT_INGEST",
        source="SERVICENOW",
        payload={
            "sys_id": "sys_987",
            "number": "INC2000001",
            "short_description": "Production alert",
            "password": "super_secret_password",
            "webhook_secret": "raw_secret_xyz"
        },
        incident_number="INC2000001",
        status="PROCESSED"
    )

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [test_event]
    mock_db.execute = AsyncMock(return_value=mock_res)

    events = await list_integration_events(limit=10, status_filter=None, db=mock_db)
    assert len(events) == 1
    sanitized = events[0]["payload_sanitized"]
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["webhook_secret"] == "[REDACTED]"
    assert sanitized["short_description"] == "Production alert"

@pytest.mark.asyncio
async def test_set_automation_mode_live_requires_typed_confirmation():
    from app.api.admin import set_automation_mode
    from fastapi import HTTPException

    mock_db = AsyncMock()

    # 1. LIVE without confirmed flag
    with pytest.raises(HTTPException) as exc1:
        await set_automation_mode({"mode": "LIVE", "confirmed": False}, db=mock_db)
    assert exc1.value.status_code == 400

    # 2. LIVE with confirmed: True but wrong phrase
    with pytest.raises(HTTPException) as exc2:
        await set_automation_mode({
            "mode": "LIVE",
            "confirmed": True,
            "confirmation_phrase": "YES LIVE"
        }, db=mock_db)
    assert exc2.value.status_code == 400
    assert "ENABLE LIVE ASSIGNMENT" in exc2.value.detail

    # 3. LIVE with exact phrase succeeds
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    with patch("app.api.admin.AuditService.log", new=AsyncMock()):
        res = await set_automation_mode({
            "mode": "LIVE",
            "confirmed": True,
            "confirmation_phrase": "ENABLE LIVE ASSIGNMENT"
        }, db=mock_db)
        assert res["mode"] == "LIVE"

@pytest.mark.asyncio
async def test_servicenow_diagnostics_when_unconfigured():
    from app.api.admin import servicenow_diagnostics

    mock_db = AsyncMock()
    diag = await servicenow_diagnostics(db=mock_db)
    assert diag["incident_table_read"] == "FAIL"
    assert diag["overall_status"] == "BLOCKED"

