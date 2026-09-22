import pytest
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.team import Team
from app.models.employee import Employee
from app.models.user import User
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.audit import AuditLog


@pytest.mark.asyncio
async def test_employee_task_acknowledgement_sync():
    """
    Verify complete task acknowledgement flow:
    1. Assigned employee acknowledges task.
    2. DB records Incident.state == 'ACKNOWLEDGED' and IncidentAssignment.status == 'ACKNOWLEDGED'.
    3. Employee's My Work (/api/me/work) returns state == 'ACKNOWLEDGED' and assignment_status == 'ACKNOWLEDGED'.
    4. Admin live assignments (/api/admin/assignments/live) returns status == 'ACKNOWLEDGED'.
    5. Duplicate acknowledge is idempotent (returns 200 without duplicate audit logs).
    6. Non-assigned employee attempting to acknowledge is rejected with 403 Forbidden.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Resolve an employee and a second employee for authorization testing
        async with async_session_maker() as session:
            team_res = await session.execute(select(Team).limit(1))
            team = team_res.scalar_one()

            emp_res = await session.execute(
                select(Employee, User).join(User, Employee.user_id == User.id).where(
                    Employee.team_id == team.id,
                    User.is_active == True
                ).limit(2)
            )
            emps = emp_res.all()
            assert len(emps) >= 2, "At least 2 active employees needed for test"
            emp1, user1 = emps[0]
            emp2, user2 = emps[1]

            admin_res = await session.execute(select(User).where(User.role == "ADMIN", User.is_active == True).limit(1))
            admin_user = admin_res.scalar_one()

            # Create a dedicated test incident
            inc_number = f"INC-TEST-ACK-{uuid.uuid4().hex[:6].upper()}"
            incident = Incident(
                id=uuid.uuid4(),
                incident_number=inc_number,
                short_description="Task Acknowledgement Realtime Sync Verification",
                priority="P2",
                state="ASSIGNED",
                assignment_group=team.name,
                assigned_to=user1.full_name,
                work_instructions="Verify that acknowledgement syncs both Employee UI and Admin",
                created_at=datetime.now(timezone.utc),
            )
            session.add(incident)
            await session.flush()

            # Create assignment to emp1
            assignment = IncidentAssignment(
                id=uuid.uuid4(),
                incident_id=incident.id,
                employee_id=emp1.id,
                assignment_type="AUTOMATIC",
                status="ASSIGNED",
                reason="Primary test assignment",
                assigned_at=datetime.now(timezone.utc),
                is_active=True
            )
            session.add(assignment)
            await session.commit()
            inc_id_str = str(incident.id)

        # 2. Authorize via direct JWT tokens
        token1 = create_access_token(data={"sub": str(user1.id), "role": user1.role})
        emp1_headers = {"Authorization": f"Bearer {token1}"}

        token2 = create_access_token(data={"sub": str(user2.id), "role": user2.role})
        emp2_headers = {"Authorization": f"Bearer {token2}"}

        admin_token = create_access_token(data={"sub": str(admin_user.id), "role": admin_user.role})
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 3. Verify initial state in My Work before acknowledgement
        before_work = await client.get("/api/me/work", headers=emp1_headers)
        assert before_work.status_code == 200
        item_before = next((i for i in before_work.json() if i["incident_number"] == inc_number), None)
        assert item_before is not None
        assert item_before["state"] == "ASSIGNED"
        assert item_before["assignment_status"] == "ASSIGNED"

        # 4. Authorization check: Employee 2 (unassigned) attempts to acknowledge
        forbidden_ack = await client.post(f"/api/incidents/{inc_id_str}/acknowledge", headers=emp2_headers)
        assert forbidden_ack.status_code in (403, 404), "Unassigned employee must be forbidden from acknowledging"

        # 5. Employee 1 acknowledges the incident
        ack_res = await client.post(f"/api/incidents/{inc_id_str}/acknowledge", headers=emp1_headers)
        assert ack_res.status_code == 200
        ack_data = ack_res.json()
        assert ack_data["status"] == "success"
        assert ack_data["state"] == "ACKNOWLEDGED"
        assert ack_data["assignment_status"] == "ACKNOWLEDGED"

        # 6. Verify Database updated: BOTH Incident.state and IncidentAssignment.status are 'ACKNOWLEDGED'
        async with async_session_maker() as session:
            db_inc = await session.get(Incident, uuid.UUID(inc_id_str))
            assert db_inc.state == "ACKNOWLEDGED", "Incident.state must be ACKNOWLEDGED in database"

            db_asgn_res = await session.execute(
                select(IncidentAssignment).where(IncidentAssignment.incident_id == db_inc.id, IncidentAssignment.is_active == True)
            )
            db_asgn = db_asgn_res.scalar_one()
            assert db_asgn.status == "ACKNOWLEDGED", "IncidentAssignment.status must be ACKNOWLEDGED in database"
            assert db_asgn.acknowledged_at is not None

        # 7. Verify Employee My Work API immediately returns updated state
        after_work = await client.get("/api/me/work", headers=emp1_headers)
        assert after_work.status_code == 200
        item_after = next((i for i in after_work.json() if i["incident_number"] == inc_number), None)
        assert item_after is not None
        assert item_after["state"] == "ACKNOWLEDGED", "Employee My Work must return state == ACKNOWLEDGED"
        assert item_after["assignment_status"] == "ACKNOWLEDGED", "Employee My Work must return assignment_status == ACKNOWLEDGED"
        assert item_after["assigned_at"] is not None

        # 8. Verify Admin Live Assignments reflects ACKNOWLEDGED
        admin_live = await client.get("/api/admin/assignments/live", headers=admin_headers)
        assert admin_live.status_code == 200
        admin_items = admin_live.json()
        matching_admin = next((a for a in admin_items if a["incident_number"] == inc_number), None)
        assert matching_admin is not None
        assert matching_admin["status"] == "ACKNOWLEDGED", "Admin live assignments must show ACKNOWLEDGED"

        # 9. Verify Duplicate Acknowledgement is Idempotent
        async with async_session_maker() as session:
            audits_before = (await session.execute(
                select(AuditLog).where(AuditLog.action == "INCIDENT_ACKNOWLEDGED", AuditLog.entity_id == uuid.UUID(inc_id_str))
            )).scalars().all()
            count_before = len(audits_before)

        dup_ack = await client.post(f"/api/incidents/{inc_id_str}/acknowledge", headers=emp1_headers)
        assert dup_ack.status_code == 200
        dup_data = dup_ack.json()
        assert dup_data["status"] == "success"
        assert dup_data["state"] == "ACKNOWLEDGED"

        async with async_session_maker() as session:
            audits_after = (await session.execute(
                select(AuditLog).where(AuditLog.action == "INCIDENT_ACKNOWLEDGED", AuditLog.entity_id == uuid.UUID(inc_id_str))
            )).scalars().all()
            assert len(audits_after) == count_before, "Duplicate acknowledge must not create redundant audit logs"
