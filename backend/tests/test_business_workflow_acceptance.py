import pytest
import uuid
import json
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.core.database import async_session_maker
from app.models.incident import Incident
from app.models.employee import Employee
from app.models.user import User
from app.models.audit import AuditLog
from app.models.team import Team
from app.models.shift import Shift, ShiftAssignment
from app.services.shift_service import ShiftService
from sqlalchemy import select
from zoneinfo import ZoneInfo
from app.integrations.servicenow.client import ServiceNowClient

@pytest.mark.asyncio
async def test_end_to_end_business_workflow_acceptance():
    """
    PHASE 11: Real Business Workflow Acceptance Test
    """
    # Ensure MDM L3 has an active scheduled & present employee on the current shift
    async with async_session_maker() as setup_session:
        team_res = await setup_session.execute(
            select(Team).where((Team.name == "MDM L3") | (Team.name == "Analytics – MDM L3"))
        )
        mdm_team = team_res.scalar_one_or_none()
        if mdm_team:
            emp_res = await setup_session.execute(
                select(Employee).where(Employee.team_id == mdm_team.id)
            )
            emp = emp_res.scalars().first()
            if emp:
                shift_svc = ShiftService(setup_session)
                now_local = datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE))
                active_shift = await shift_svc.get_active_shift(now_local)
                if active_shift:
                    sa_res = await setup_session.execute(
                        select(ShiftAssignment).where(
                            ShiftAssignment.shift_id == active_shift.id,
                            ShiftAssignment.employee_id == emp.id,
                            ShiftAssignment.date == now_local.date()
                        )
                    )
                    if not sa_res.scalar_one_or_none():
                        setup_session.add(ShiftAssignment(
                            shift_id=active_shift.id,
                            employee_id=emp.id,
                            date=now_local.date(),
                            is_active=True
                        ))
                    emp.is_present = True
                    emp.availability_status = "AVAILABLE"
                    await setup_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Prepare synthetic staging incident payload
        synth_sys_id = f"sys_accept_{uuid.uuid4().hex[:8]}"
        synth_number = f"INC_ACCEPT_{uuid.uuid4().hex[:6].upper()}"

        synthetic_payload = {
            "sys_id": synth_sys_id,
            "number": synth_number,
            "short_description": "TEST - IncidentFlow Synthetic Staging Verification",
            "description": "Production database connection pool exhaustion alert on primary replica.",
            "priority": "3 - Moderate",
            "impact": "2 - Medium",
            "urgency": "2 - Medium",
            "category": "Database",
            "subcategory": "ConnectionPool",
            "assignment_group": {"display_value": "Analytics – MDM L3"},
            "assigned_to": {"display_value": ""},
            "caller_id": {"display_value": "Automated Synthetics Engine"},
            "cmdb_ci": {"display_value": "db-staging-replica"},
            "state": "1 - New",
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "work_notes": "Diagnostic alert auto-generated for acceptance verification.",
            "comments": "Acceptance test probe.",
            "u_work_instructions": "Check pg_stat_activity, terminate idle connections exceeding 600s, restart pgpool if necessary."
        }

        # Step 2: Webhook Ingress & Idempotency
        # First delivery
        wh_headers = {"X-ServiceNow-Secret": settings.SERVICENOW_WEBHOOK_SECRET}
        resp1 = await client.post(
            "/api/integrations/servicenow/incidents",
            json=synthetic_payload,
            headers=wh_headers
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["status"] == "processed"
        assert data1["is_new"] is True
        assert data1["incident_number"] == synth_number

        # Duplicate delivery (same event delivered twice)
        resp2 = await client.post(
            "/api/integrations/servicenow/incidents",
            json=synthetic_payload,
            headers=wh_headers
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["status"] == "processed"
        assert data2["is_new"] is False  # Idempotent deduplication

        # Step 3: Verify Single Incident Record & Zero ServiceNow Mutation
        async with async_session_maker() as session:
            inc_res = await session.execute(select(Incident).where(Incident.incident_number == synth_number))
            incidents = inc_res.scalars().all()
            assert len(incidents) == 1, "Exactly one incident record must exist (no duplicates)"
            stored_inc = incidents[0]
            assert stored_inc.short_description == "TEST - IncidentFlow Synthetic Staging Verification"
            assert stored_inc.priority == "P3"
            assert stored_inc.work_instructions == synthetic_payload["u_work_instructions"]

            # Step 4: Verify Shadow Audit Dossier
            audit_res = await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "SHADOW_ASSIGN",
                    AuditLog.entity_id == stored_inc.id
                )
            )
            shadow_log = audit_res.scalar_one_or_none()
            assert shadow_log is not None, "Shadow assignment decision dossier must be logged"
            dossier = shadow_log.new_value
            assert dossier["incident_number"] == synth_number
            assert "recommended" in dossier
            selected_emp_id = dossier["recommended"]
            assert dossier["strategy"] in ("SKILL_PLUS_WORKLOAD", "LEAST_WORKLOAD", "ROUND_ROBIN")

            # Resolve selected candidate user
            selected_emp = await session.get(Employee, uuid.UUID(selected_emp_id))
            selected_user = await session.get(User, selected_emp.user_id)
            candidate_email = selected_user.email
            candidate_name = selected_user.full_name
            from app.core.security import get_password_hash
            selected_user.hashed_password = get_password_hash("pvcharan12345")
            await session.commit()

        # Step 5: Verify Outbound ServiceNow Mutation Guard (Zero Mutations)
        sn_client = ServiceNowClient(base_url="https://dev-staging.service-now.com")
        mut_res = await sn_client.update_incident(synth_sys_id, {"assigned_to": candidate_name})
        assert mut_res["status"] == "skipped"
        assert "SHADOW" in mut_res["reason"]

        # Step 6: Employee Experience (Zero Manual Copy/Paste/Self-Assign)
        # Login as the selected candidate engineer
        login_res = await client.post(
            "/api/auth/login",
            json={"email": candidate_email, "password": "pvcharan12345"}
        )
        assert login_res.status_code == 200
        emp_token = login_res.json()["access_token"]
        emp_headers = {"Authorization": f"Bearer {emp_token}"}

        # 6a. Employee Dashboard / My Work
        work_res = await client.get("/api/me/work", headers=emp_headers)
        assert work_res.status_code == 200
        work_list = work_res.json()
        matching_work = next((w for w in work_list if w["incident_number"] == synth_number), None)
        assert matching_work is not None, "Employee must automatically see the incident on their dashboard without copying or manual assignment"

        # 6b. Incident Detail & YOUR TASK
        detail_res = await client.get(f"/api/incidents/{synth_number}", headers=emp_headers)
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        inc_data = detail_data["incident"]
        assert inc_data["incident_number"] == synth_number
        assert inc_data["work_instructions"] == synthetic_payload["u_work_instructions"]
        # Verify YOUR TASK section contains actual ServiceNow-backed work instructions
        assert "Check pg_stat_activity" in inc_data["work_instructions"]

        # 6c. Acknowledge -> Start Work -> Complete Workflow
        inc_id = str(stored_inc.id)
        ack_res = await client.post(f"/api/incidents/{inc_id}/acknowledge", headers=emp_headers)
        assert ack_res.status_code == 200

        start_res = await client.post(f"/api/incidents/{inc_id}/start", headers=emp_headers)
        assert start_res.status_code == 200

        complete_res = await client.post(f"/api/incidents/{inc_id}/complete", headers=emp_headers)
        assert complete_res.status_code == 200

        # Step 7: Incident Lifecycle Stages Endpoint
        # Admin checks lifecycle
        admin_login = await client.post("/api/auth/login", json={"email": "admin@incidentflow.dev", "password": "pvcharan12345PV"})
        admin_token = admin_login.json()["access_token"]
        life_res = await client.get(f"/api/incidents/{synth_number}/lifecycle", headers={"Authorization": f"Bearer {admin_token}"})
        assert life_res.status_code == 200
        life_data = life_res.json()
        assert life_data["servicenow_assigned"] is False  # Mutation skipped in SHADOW mode
        stage_names = [s["stage"] for s in life_data["lifecycle"] if s.get("completed")]
        assert "RECEIVED" in stage_names
        assert "VALIDATED" in stage_names
        assert "PERSISTED" in stage_names
        assert "ELIGIBILITY_EVALUATED" in stage_names
