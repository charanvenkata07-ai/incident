import pytest
import uuid
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone

from app.main import app
from app.core.database import async_session_maker
from app.models.team import Team
from app.models.employee import Employee
from app.models.user import User
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.notification import Notification
from app.models.audit import AuditLog
from app.services.group_notice_service import GroupNoticeService
from sqlalchemy import select, func


@pytest.mark.asyncio
async def test_group_crud_and_members_api():
    """Test group creation, listing, updating, and member listing via Admin API."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login as Admin
        login_res = await client.post("/api/auth/login", json={"email": "admin@incidentflow.dev", "password": "pvcharan12345PV"})
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create a new group
        unique_group_name = f"Network L2 - {uuid.uuid4().hex[:6]}"
        create_res = await client.post(
            "/api/admin/teams",
            json={
                "name": unique_group_name,
                "description": "Network operations and tier 2 triage",
                "servicenow_group_id": "sn_network_l2"
            },
            headers=headers
        )
        assert create_res.status_code == 200
        group_id = create_res.json()["id"]

        # 2. List groups and verify newly created group is present
        list_res = await client.get("/api/admin/teams", headers=headers)
        assert list_res.status_code == 200
        teams = list_res.json()["teams"]
        found = next((t for t in teams if t["id"] == group_id), None)
        assert found is not None
        assert found["name"] == unique_group_name
        assert found["servicenow_group_id"] == "sn_network_l2"

        # 3. Update group
        patch_res = await client.patch(
            f"/api/admin/teams/{group_id}",
            json={"description": "Updated network tier 2 team", "is_active": True},
            headers=headers
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["message"] == "Updated"

        # 4. View group members
        members_res = await client.get(f"/api/admin/teams/{group_id}/members", headers=headers)
        assert members_res.status_code == 200
        members_data = members_res.json()
        assert "members" in members_data
        assert "summary" in members_data


@pytest.mark.asyncio
async def test_send_notice_to_group_does_not_assign_incident():
    """
    CRITICAL SAFETY REQUIREMENT:
    SEND NOTICE != ASSIGN INCIDENT
    Admin sends a notice to group members.
    Verify:
    1. Notification records are created for all group members with type="GROUP_NOTICE"
    2. WebSocket event GROUP_NOTICE_CREATED is dispatched
    3. Audit log is recorded
    4. Incident state and assigned_to remain 100% UNCHANGED
    5. Zero IncidentAssignment records created
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login as Admin
        login_res = await client.post("/api/auth/login", json={"email": "admin@incidentflow.dev", "password": "pvcharan12345PV"})
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        async with async_session_maker() as session:
            # Pick the seeded MDM L3 team
            team_res = await session.execute(select(Team).where(Team.name == "MDM L3"))
            team = team_res.scalar_one_or_none()
            if not team:
                # Fallback to any active team
                team_res = await session.execute(select(Team).limit(1))
                team = team_res.scalar_one()

            # Create an unassigned incident
            inc_number = f"INC_TEST_{uuid.uuid4().hex[:6].upper()}"
            test_inc = Incident(
                incident_number=inc_number,
                short_description="Critical DB latency warning",
                assignment_group=team.name,
                state="NEW",
                priority="P2",
                assigned_to=None
            )
            session.add(test_inc)
            await session.commit()
            await session.refresh(test_inc)
            inc_id = test_inc.id

            # Count initial assignments
            count_res = await session.execute(
                select(func.count(IncidentAssignment.id)).where(IncidentAssignment.incident_id == inc_id)
            )
            initial_assignments_count = count_res.scalar() or 0

        # Mock WebSocket manager to verify broadcast
        with patch("app.services.group_notice_service.ws_manager.send_to_user", new_callable=AsyncMock) as mock_ws_send:
            notice_payload = {
                "title": "Scheduled Maintenance Window",
                "message": "Routine database maintenance will occur at 23:00 IST. Please monitor pipelines.",
                "priority": "MEDIUM",
                "incident_number": inc_number
            }

            resp = await client.post(
                f"/api/admin/teams/{team.id}/notice",
                json=notice_payload,
                headers=headers
            )
            assert resp.status_code == 200
            data = resp.json()

            # Verify response explicitly denotes NO assignment occurred
            assert data["assignment_triggered"] is False
            assert "No incident was assigned" in data["policy"]
            assert data["success"] > 0

            # Verify WebSocket was called for each recipient
            assert mock_ws_send.call_count == data["success"]
            for call in mock_ws_send.call_args_list:
                args, kwargs = call
                assert args[1] == "GROUP_NOTICE_CREATED"
                payload = args[2]
                assert payload["type"] == "GROUP_NOTICE"
                assert payload["title"] == notice_payload["title"]
                assert payload["incident_number"] == inc_number

        # Check DB state after notice
        async with async_session_maker() as session:
            # 1. Incident is STILL state="NEW", assigned_to=None
            inc_check = await session.get(Incident, inc_id)
            assert inc_check.state == "NEW", "Incident state must NEVER change from SEND NOTICE"
            assert inc_check.assigned_to is None, "assigned_to must NEVER change from SEND NOTICE"

            # 2. Assignment count is STILL unchanged
            count_res_after = await session.execute(
                select(func.count(IncidentAssignment.id)).where(IncidentAssignment.incident_id == inc_id)
            )
            assert count_res_after.scalar() == initial_assignments_count, "Zero assignments may be created"

            # 3. Notification records exist with type="GROUP_NOTICE"
            notifs = (await session.execute(
                select(Notification).where(
                    Notification.incident_id == inc_id,
                    Notification.type == "GROUP_NOTICE"
                )
            )).scalars().all()
            assert len(notifs) == data["success"]
            for n in notifs:
                assert n.title == notice_payload["title"]
                assert n.is_read is False

            # 4. AuditLog recorded SEND_GROUP_NOTICE with is_assignment=False
            audit = (await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "SEND_GROUP_NOTICE",
                    AuditLog.entity_id == team.id
                ).order_by(AuditLog.created_at.desc())
            )).scalars().first()
            assert audit is not None
            assert audit.new_value["is_assignment"] is False
            assert audit.new_value["title"] == notice_payload["title"]
