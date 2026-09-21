"""
Comprehensive End-to-End Operational Workflow Verification:
Group: Database L2 (10 members)
Current Shift: 2 employees (1 Available, 1 Busy)
Incident: INC-REAL-E2E-001
Flow:
1. Incident arrives via ServiceNow Webhook
2. Group Notice sent to ALL 10 Database L2 members (informational only)
3. 2 current-shift employees evaluated (busy employee excluded)
4. Exactly 1 available employee assigned
5. Random task from Database L2 Task Catalog attached to incident and notification
6. Employee acknowledges, starts work, and completes work
7. Local completion recorded with completed_at timestamp
8. Duplicate completion rejected
9. Audit log verified
10. In SHADOW mode: ZERO ServiceNow mutations
"""
import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, func

from app.main import app
from app.core.config import settings
from app.core.database import async_session_maker
from app.models.team import Team
from app.models.employee import Employee
from app.models.user import User
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.notification import Notification
from app.models.audit import AuditLog
from app.models.task_template import TaskTemplate
from app.models.shift import Shift, ShiftAssignment
from app.services.shift_service import ShiftService
from app.integrations.servicenow.client import ServiceNowClient


@pytest.mark.asyncio
async def test_real_operations_e2e_scenario():
    tz = ZoneInfo("Asia/Kolkata")
    now_local = datetime.now(tz)
    today = now_local.date()

    async with async_session_maker() as session:
        # 1. Resolve Database L2
        team_res = await session.execute(select(Team).where(Team.name == "Database L2"))
        team = team_res.scalar_one_or_none()
        assert team is not None, "Database L2 team must exist"
        assert team.work_domain == "Database Operations & Support"

        # Verify 10 members exist
        members_res = await session.execute(
            select(Employee).join(User, Employee.user_id == User.id).where(
                Employee.team_id == team.id,
                User.is_active == True
            )
        )
        members = members_res.scalars().all()
        assert len(members) == 10, f"Database L2 must have 10 members, found {len(members)}"

        # Verify task catalog contains 4 tasks
        tasks_res = await session.execute(
            select(TaskTemplate).where(TaskTemplate.team_id == team.id, TaskTemplate.is_active == True)
        )
        task_templates = tasks_res.scalars().all()
        assert len(task_templates) >= 4, "Database L2 must have at least 4 task templates"
        task_titles = {t.title for t in task_templates}

        # 2. Identify active shift and ensure exactly 2 employees are scheduled on it:
        # 1 AVAILABLE, 1 BUSY, remaining 8 off-shift
        shift_svc = ShiftService(session)
        active_shift = await shift_svc.get_active_shift(now_local)
        assert active_shift is not None, "There must be an active shift right now"

        # Designate candidate employees and ensure they are assigned to active_shift today
        emp_available = members[0]
        emp_busy = members[1]

        for cand in [emp_available, emp_busy]:
            sa_res = await session.execute(
                select(ShiftAssignment).where(
                    ShiftAssignment.shift_id == active_shift.id,
                    ShiftAssignment.employee_id == cand.id,
                    ShiftAssignment.date == today
                )
            )
            if not sa_res.scalar_one_or_none():
                session.add(ShiftAssignment(
                    shift_id=active_shift.id,
                    employee_id=cand.id,
                    date=today,
                    is_active=True
                ))

        emp_available.is_present = True
        emp_available.availability_status = "AVAILABLE"

        emp_busy.is_present = True
        emp_busy.availability_status = "BUSY"

        for m in members[2:]:
            m.is_present = False
            m.availability_status = "OFFLINE"

        await session.commit()

    # 3. Simulate Incident Arrival via Webhook
    synth_sys_id = f"sys_real_e2e_{uuid.uuid4().hex[:8]}"
    synth_number = f"INC-REAL-E2E-{uuid.uuid4().hex[:6].upper()}"

    webhook_payload = {
        "sys_id": synth_sys_id,
        "number": synth_number,
        "short_description": "Production PostgreSQL connection pool saturated on primary shard",
        "description": "Connection pool reached 98% threshold. Active query latency spiking.",
        "priority": "2 - High",
        "impact": "2 - Medium",
        "urgency": "2 - Medium",
        "category": "Database",
        "subcategory": "ConnectionPool",
        "assignment_group": {"display_value": "Database L2"},
        "assigned_to": {"display_value": ""},
        "state": "1 - New",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        # Intentionally no u_work_instructions: triggers random selection from Task Catalog
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingress
        wh_headers = {"X-ServiceNow-Secret": settings.SERVICENOW_WEBHOOK_SECRET}
        resp = await client.post(
            "/api/integrations/servicenow/incidents",
            json=webhook_payload,
            headers=wh_headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "processed"

        # 4. Verify DB state after ingestion
        async with async_session_maker() as session:
            inc_res = await session.execute(select(Incident).where(Incident.incident_number == synth_number))
            inc = inc_res.scalar_one_or_none()
            assert inc is not None, "Incident must be persisted"

            # 5. Verify Random Task attached from Task Catalog
            assert inc.work_instructions is not None, "Task must be selected from Task Catalog"
            matched_title = any(t in inc.work_instructions for t in task_titles)
            assert matched_title, f"Task '{inc.work_instructions}' must originate from Database L2 Task Catalog"

            # 6. Verify Group Notice sent to ALL 10 Database L2 members
            notifs = (await session.execute(
                select(Notification).where(
                    Notification.incident_id == inc.id,
                    Notification.type == "GROUP_NOTICE"
                )
            )).scalars().all()
            assert len(notifs) == 10, f"Group notice must be sent to all 10 members, got {len(notifs)}"

            # 7. Verify Candidate Selection in SHADOW mode (dossier created)
            shadow_audit = (await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "SHADOW_ASSIGN",
                    AuditLog.entity_id == inc.id
                )
            )).scalar_one_or_none()
            assert shadow_audit is not None, "Shadow assignment decision dossier must be logged"

            # Recommended candidate must be the AVAILABLE employee (emp_available), NOT the BUSY employee
            dossier = shadow_audit.new_value
            assert dossier["recommended"] == str(emp_available.id), (
                f"Candidate must be the AVAILABLE employee ({emp_available.id}), not the BUSY employee ({emp_busy.id})"
            )

        # 8. Outbound Mutation Guard: verify ZERO ServiceNow mutations in SHADOW mode
        sn_client = ServiceNowClient(base_url="https://dev-staging.service-now.com")
        mut_res = await sn_client.update_incident(synth_sys_id, {"assigned_to": "Database Specialist"})
        assert mut_res["status"] == "skipped"
        assert "SHADOW" in mut_res["reason"]

        # 9. Employee Workflow Execution (Acknowledge -> Start -> Complete)
        # Login as the selected engineer
        async with async_session_maker() as session:
            user = await session.get(User, emp_available.user_id)
            user_email = user.email

        login_res = await client.post(
            "/api/auth/login",
            json={"email": user_email, "password": "pvcharan12345", "team_id": str(team.id)}
        )
        assert login_res.status_code == 200
        emp_token = login_res.json()["access_token"]
        emp_headers = {"Authorization": f"Bearer {emp_token}"}

        # Step 9a: Check My Work
        work_res = await client.get("/api/me/work", headers=emp_headers)
        assert work_res.status_code == 200
        my_incidents = work_res.json()
        target_work = next((w for w in my_incidents if w["incident_number"] == synth_number), None)
        assert target_work is not None, "Incident must appear in My Work"
        assert target_work["work_instructions"] is not None
        assert target_work["assignment_group"] == "Database L2"

        # Step 9b: Acknowledge Work
        ack_res = await client.post(f"/api/incidents/{synth_number}/acknowledge", headers=emp_headers)
        assert ack_res.status_code == 200

        # Step 9c: Start Work
        start_res = await client.post(f"/api/incidents/{synth_number}/start", headers=emp_headers)
        assert start_res.status_code == 200

        # Step 9d: Complete Work
        complete_res = await client.post(f"/api/incidents/{synth_number}/complete", headers=emp_headers)
        assert complete_res.status_code == 200
        assert complete_res.json()["status"] == "success"

        # Step 9e: Duplicate completion must be prevented
        dup_complete = await client.post(f"/api/incidents/{synth_number}/complete", headers=emp_headers)
        assert dup_complete.status_code == 400
        assert "already completed" in dup_complete.json()["detail"]

        # 10. Verify DB records completion
        async with async_session_maker() as session:
            inc_final = (await session.execute(
                select(Incident).where(Incident.incident_number == synth_number)
            )).scalar_one()
            assert inc_final.state == "RESOLVED"
            assert inc_final.resolved_at is not None

            assignment_final = (await session.execute(
                select(IncidentAssignment).where(
                    IncidentAssignment.incident_id == inc_final.id,
                    IncidentAssignment.employee_id == emp_available.id
                )
            )).scalar_one()
            assert assignment_final.status == "COMPLETED"
            assert assignment_final.completed_at is not None

            # Verify audit log contains INCIDENT_COMPLETED
            comp_audit = (await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "INCIDENT_COMPLETED",
                    AuditLog.entity_id == inc_final.id
                )
            )).scalar_one_or_none()
            assert comp_audit is not None
            assert comp_audit.actor_id == user.id
