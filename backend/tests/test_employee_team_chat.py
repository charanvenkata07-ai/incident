import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.notification import Notification
from app.models.conversation import Conversation, ConversationMember, ChatMessage

@pytest.mark.asyncio
async def test_canonical_my_team_chat_endpoint():
    """Verify GET /api/chat/my-team returns canonical group chat details for employee."""
    async with async_session_maker() as session:
        # Find employee Ravi (Database L2)
        ravi_user = (await session.execute(
            select(User).where(User.email == "ravi@incidentflow.dev")
        )).scalar_one_or_none()

        assert ravi_user is not None, "Seed employee ravi@incidentflow.dev must exist"

        emp = (await session.execute(
            select(Employee).where(Employee.user_id == ravi_user.id)
        )).scalar_one_or_none()
        assert emp is not None and emp.team_id is not None

        team = await session.get(Team, emp.team_id)
        assert team is not None

    token = create_access_token(data={"sub": str(ravi_user.id), "role": ravi_user.role})
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/chat/my-team", headers=headers)
        assert res.status_code == 200, f"Failed: {res.text}"
        data = res.json()

        assert data["team_name"] == team.name
        assert data["team_id"] == str(team.id)
        assert "conversation_id" in data
        assert "member_count" in data
        assert "present_count" in data
        assert "members" in data
        assert len(data["members"]) > 0


@pytest.mark.asyncio
async def test_strict_team_chat_authorization():
    """Verify that an employee from another team cannot access or send messages to another team's chat."""
    async with async_session_maker() as session:
        ravi_user = (await session.execute(
            select(User).where(User.email == "ravi@incidentflow.dev")
        )).scalar_one()

        emp_ravi = (await session.execute(
            select(Employee).where(Employee.user_id == ravi_user.id)
        )).scalar_one()

        # Find or create a conversation for Ravi's team
        conv = (await session.execute(
            select(Conversation).where(
                Conversation.type == "TEAM",
                Conversation.team_id == emp_ravi.team_id
            )
        )).scalars().first()

        if not conv:
            conv = Conversation(
                type="TEAM",
                team_id=emp_ravi.team_id,
                title=f"{emp_ravi.team_id} Chat"
            )
            session.add(conv)
            await session.commit()
            await session.refresh(conv)

        # Find employee from a different team (e.g. ananya@incidentflow.dev or create one)
        other_user = (await session.execute(
            select(User).where(User.email == "ananya@incidentflow.dev")
        )).scalar_one_or_none()

        if not other_user:
            other_user = (await session.execute(
                select(User).join(Employee).where(Employee.team_id != emp_ravi.team_id)
            )).scalars().first()

        assert other_user is not None, "Need another user from a different team"

    # 1. Ravi can read the conversation
    ravi_token = create_access_token(data={"sub": str(ravi_user.id), "role": ravi_user.role})
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r_res = await ac.get(f"/api/chat/conversations/{conv.id}/messages", headers={"Authorization": f"Bearer {ravi_token}"})
        assert r_res.status_code == 200

        # 2. Other user tries to read Ravi's team conversation -> MUST RETURN 403
        other_token = create_access_token(data={"sub": str(other_user.id), "role": other_user.role})
        bad_res = await ac.get(f"/api/chat/conversations/{conv.id}/messages", headers={"Authorization": f"Bearer {other_token}"})
        assert bad_res.status_code == 403, f"Expected 403 Forbidden, got {bad_res.status_code}: {bad_res.text}"

        # 3. Other user tries to send a message to Ravi's team conversation -> MUST RETURN 403
        bad_send = await ac.post(
            f"/api/chat/conversations/{conv.id}/messages",
            headers={"Authorization": f"Bearer {other_token}"},
            json={"content": "Attempting unauthorized post", "message_type": "USER"}
        )
        assert bad_send.status_code == 403, f"Expected 403 Forbidden on post, got {bad_send.status_code}"


@pytest.mark.asyncio
async def test_actionable_notifications_and_mentions():
    """Verify that posting a message with @mention creates actionable notification with direct route URL."""
    async with async_session_maker() as session:
        ravi_user = (await session.execute(
            select(User).where(User.email == "ravi@incidentflow.dev")
        )).scalar_one()

        kiran_user = (await session.execute(
            select(User).where(User.email == "kiran@incidentflow.dev")
        )).scalar_one()

        emp_ravi = (await session.execute(
            select(Employee).where(Employee.user_id == ravi_user.id)
        )).scalar_one()

        conv = (await session.execute(
            select(Conversation).where(
                Conversation.type == "TEAM",
                Conversation.team_id == emp_ravi.team_id
            )
        )).scalars().first()
        assert conv is not None

    ravi_token = create_access_token(data={"sub": str(ravi_user.id), "role": ravi_user.role})
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Post a message mentioning Kiran
        msg_res = await ac.post(
            f"/api/chat/conversations/{conv.id}/messages",
            headers={"Authorization": f"Bearer {ravi_token}"},
            json={"content": f"Hey @{kiran_user.full_name}, please review the DB replica logs #INC-9999", "message_type": "USER"}
        )
        assert msg_res.status_code == 200
        msg_data = msg_res.json()
        msg_id = msg_data["id"]

    # Verify notification created for Kiran
    async with async_session_maker() as session:
        notif = (await session.execute(
            select(Notification).where(
                Notification.user_id == kiran_user.id,
                Notification.message_id == uuid.UUID(msg_id)
            ).order_by(Notification.created_at.desc())
        )).scalars().first()

        assert notif is not None, "Notification must be created for mentioned user"
        assert notif.type == "MENTION"
        assert f"/team-chat?conversation={conv.id}" in notif.action_url
        assert notif.sender_name == ravi_user.full_name
        assert notif.is_read is False

    # Mark notification as read
    kiran_token = create_access_token(data={"sub": str(kiran_user.id), "role": kiran_user.role})
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        read_res = await ac.post(
            f"/api/notifications/{notif.id}/read",
            headers={"Authorization": f"Bearer {kiran_token}"}
        )
        assert read_res.status_code == 200

    async with async_session_maker() as session:
        updated_notif = await session.get(Notification, notif.id)
        assert updated_notif.is_read is True
        assert updated_notif.read_at is not None


@pytest.mark.asyncio
async def test_observability_metrics_and_health():
    """Verify /metrics and /health endpoints meet enterprise requirements."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Prometheus Metrics
        m_res = await ac.get("/metrics")
        assert m_res.status_code == 200
        m_text = m_res.text
        assert "chat_messages" in m_text
        assert "notification_delivery" in m_text
        assert "live_pilot_assignments" in m_text

        # Health endpoint
        h_res = await ac.get("/health")
        assert h_res.status_code == 200
        h_data = h_res.json()
        assert h_data["status"].lower() in ("healthy", "degraded")
        assert "dependencies" in h_data
        assert "database" in h_data["dependencies"]
        assert "websocket" in h_data["dependencies"]
