import pytest
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.incident import Incident
from app.models.conversation import Conversation, ConversationMember, ChatMessage
from app.models.audit import AuditLog

@pytest.mark.asyncio
async def test_group_activity_overview_and_timeline():
    """Verify GET /api/admin/teams/{id}/activity and timeline endpoint."""
    async with async_session_maker() as session:
        admin_res = await session.execute(select(User).where(User.email == "pvcharan975@gmail.com"))
        admin = admin_res.scalar_one()

        team_res = await session.execute(select(Team).where(Team.is_active == True))
        team = team_res.scalars().first()
        assert team is not None, "At least one team must exist"
        team_id = team.id

    token = create_access_token(data={"sub": str(admin.id), "role": "ADMIN"})
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get(f"/api/admin/teams/{team_id}/activity", headers=headers)
        assert res.status_code == 200, f"Error: {res.text}"
        data = res.json()
        assert "header" in data
        assert "members" in data
        assert "work_board" in data
        assert data["header"]["name"] == team.name
        assert data["header"]["health_status"] in ("HEALTHY", "DEGRADED", "ATTENTION", "CRITICAL")
        assert "unassigned" in data["work_board"]
        assert "assigned" in data["work_board"]
        assert "in_progress" in data["work_board"]

        # Test Timeline
        t_res = await ac.get(f"/api/admin/teams/{team_id}/activity/timeline", headers=headers)
        assert t_res.status_code == 200
        events = t_res.json()
        assert isinstance(events, list)

@pytest.mark.asyncio
async def test_team_chat_persistence_and_mention_resolution():
    """Verify team chat message creation, persistence, #INC resolution, and isolation."""
    async with async_session_maker() as session:
        admin_res = await session.execute(select(User).where(User.email == "pvcharan975@gmail.com"))
        admin = admin_res.scalar_one()

        team = (await session.execute(select(Team).where(Team.is_active == True))).scalars().first()
        team_id = team.id

        # Check or create an incident
        inc = (await session.execute(select(Incident))).scalars().first()
        inc_number = inc.incident_number if inc else "INC1969714"

    token = create_access_token(data={"sub": str(admin.id), "role": "ADMIN"})
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Get team conversations
        convs_res = await ac.get(f"/api/admin/teams/{team_id}/conversations", headers=headers)
        assert convs_res.status_code == 200
        convs = convs_res.json()
        assert len(convs) > 0
        team_conv = next(c for c in convs if c["type"] == "TEAM")

        # Post a message with incident reference tag
        msg_payload = {
            "content": f"Investigating issue with #{inc_number} immediately.",
            "message_type": "USER"
        }
        post_res = await ac.post(f"/api/chat/conversations/{team_conv['id']}/messages", json=msg_payload, headers=headers)
        assert post_res.status_code == 200, f"Post message failed: {post_res.text}"
        msg_data = post_res.json()
        assert msg_data["sender_role"] == "ADMIN"
        assert msg_data["sender_name"] == admin.full_name
        assert f"#{inc_number}" in msg_data["content"]
        if inc:
            assert msg_data["incident_number"] == inc_number

        # Fetch messages
        get_res = await ac.get(f"/api/chat/conversations/{team_conv['id']}/messages", headers=headers)
        assert get_res.status_code == 200
        messages = get_res.json()
        assert any(m["id"] == msg_data["id"] for m in messages)

@pytest.mark.asyncio
async def test_admin_chat_search_and_view_auditing():
    """Verify chat search and direct conversation viewing record proper audit logs."""
    async with async_session_maker() as session:
        admin = (await session.execute(select(User).where(User.email == "pvcharan975@gmail.com"))).scalar_one()
        team = (await session.execute(select(Team).where(Team.is_active == True))).scalars().first()
        team_id = team.id

    token = create_access_token(data={"sub": str(admin.id), "role": "ADMIN"})
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Chat Search
        search_res = await ac.get(f"/api/admin/teams/{team_id}/chat/search?q=Investigating", headers=headers)
        assert search_res.status_code == 200
        s_data = search_res.json()
        assert "messages" in s_data
        assert "total" in s_data

        # 2. Verify Audit log created for CHAT_SEARCHED_BY_ADMIN
        async with async_session_maker() as session:
            audit_res = await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "CHAT_SEARCHED_BY_ADMIN",
                    AuditLog.actor_id == admin.id
                ).order_by(AuditLog.created_at.desc())
            )
            audit = audit_res.scalars().first()
            assert audit is not None, "CHAT_SEARCHED_BY_ADMIN audit event must be logged"
            assert audit.new_value["query"] == "Investigating"

        # 3. Direct Conversation Audit View
        convs_res = await ac.get(f"/api/admin/teams/{team_id}/conversations", headers=headers)
        team_conv = convs_res.json()[0]
        audit_view_res = await ac.post(f"/api/admin/chat/conversations/{team_conv['id']}/audit-view", headers=headers)
        assert audit_view_res.status_code == 200

        async with async_session_maker() as session:
            v_audit = (await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "CHAT_VIEWED_BY_ADMIN",
                    AuditLog.actor_id == admin.id
                ).order_by(AuditLog.created_at.desc())
            )).scalars().first()
            assert v_audit is not None, "CHAT_VIEWED_BY_ADMIN audit event must be logged"

@pytest.mark.asyncio
async def test_group_analytics_and_employee_drawer():
    """Verify group analytics endpoint and employee details drawer."""
    async with async_session_maker() as session:
        admin = (await session.execute(select(User).where(User.email == "pvcharan975@gmail.com"))).scalar_one()
        team = (await session.execute(select(Team).where(Team.is_active == True))).scalars().first()
        emp = (await session.execute(select(Employee).where(Employee.team_id == team.id))).scalars().first()
        team_id = team.id
        emp_id = emp.id

    token = create_access_token(data={"sub": str(admin.id), "role": "ADMIN"})
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Test analytics
        analytics_res = await ac.get(f"/api/admin/teams/{team_id}/analytics?period=today", headers=headers)
        assert analytics_res.status_code == 200
        a_data = analytics_res.json()
        assert a_data["period"] == "today"
        assert "total_incidents" in a_data
        assert "auto_assignment_rate_pct" in a_data
        assert "workload_distribution" in a_data

        # Test employee drawer
        emp_res = await ac.get(f"/api/admin/employees/{emp_id}/activity", headers=headers)
        assert emp_res.status_code == 200
        emp_data = emp_res.json()
        assert emp_data["employee_id"] == str(emp_id)
        assert "active_assignments" in emp_data
        assert "today_shifts" in emp_data
        assert "recent_activity" in emp_data
