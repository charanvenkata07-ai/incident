import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.conversation import Conversation, ConversationMember, ChatMessage
from app.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_leader_only_admin_chat_and_transfer_lifecycle():
    """
    Verify:
    1. Normal employee messaging Admin is denied with HTTP 403 and exact JSON:
       {"code": "ADMIN_CHAT_LEADER_ONLY", "message": "Only the active Group Leader can message Admin."}
    2. Group Leader messaging Admin succeeds with HTTP 200.
    3. Canonical ADMIN_TEAM conversation created and accessible to Leader.
    4. Group Leader changed from A to B:
       - Former leader A is immediately denied (HTTP 403 ADMIN_CHAT_LEADER_ONLY) on database check
       - New leader B gains access (HTTP 200)
       - Historical messages in ADMIN_TEAM conversation are preserved
    """
    async with async_session_maker() as session:
        admin_user = (await session.execute(select(User).where(User.role == "ADMIN"))).scalars().first()
        assert admin_user is not None

        # Pick a team with at least 2 active employees
        teams = (await session.execute(select(Team).where(Team.is_active == True))).scalars().all()
        target_team = None
        team_members = []
        for t in teams:
            m_res = await session.execute(
                select(Employee, User).join(User, Employee.user_id == User.id).where(
                    Employee.team_id == t.id,
                    User.is_active == True,
                    User.role == "EMPLOYEE"
                )
            )
            members = m_res.all()
            if len(members) >= 2:
                target_team = t
                team_members = members
                break

        assert target_team is not None, "Need a team with >= 2 active employees"

        emp_a, user_a = team_members[0]
        emp_b, user_b = team_members[1]

        # Designate emp_a as group leader initially, emp_b as non-leader
        emp_a.is_group_leader = True
        emp_b.is_group_leader = False
        await session.commit()

        team_id = target_team.id
        user_a_id = user_a.id
        user_b_id = user_b.id
        admin_id = admin_user.id

    transport = ASGITransport(app=app)
    token_a = create_access_token(data={"sub": str(user_a_id), "role": "EMPLOYEE"})
    token_b = create_access_token(data={"sub": str(user_b_id), "role": "EMPLOYEE"})
    token_admin = create_access_token(data={"sub": str(admin_id), "role": "ADMIN"})

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Non-leader emp_b attempts to DM Admin -> MUST BE 403 FORBIDDEN with exact body
        res_b_to_admin = await ac.post(
            "/api/chat/conversations/direct",
            headers=headers_b,
            json={"other_user_id": str(admin_id)}
        )
        assert res_b_to_admin.status_code == 403, f"Expected 403, got {res_b_to_admin.status_code}"
        b_body = res_b_to_admin.json()
        assert b_body["code"] == "ADMIN_CHAT_LEADER_ONLY"
        assert "Only the active Group Leader can message Admin." in b_body["message"]

        # 2. Group leader emp_a attempts to DM Admin -> MUST SUCCEED (200 OK)
        res_a_to_admin = await ac.post(
            "/api/chat/conversations/direct",
            headers=headers_a,
            json={"other_user_id": str(admin_id)}
        )
        assert res_a_to_admin.status_code == 200
        conv_direct = res_a_to_admin.json()
        assert conv_direct["type"] == "DIRECT"

        # 3. Create/access canonical ADMIN_TEAM leadership conversation
        async with async_session_maker() as session:
            chat_svc = ChatService(session)
            admin_team_conv = await chat_svc.get_or_create_admin_team_conversation(team_id, leader_user_id=user_a_id)
            admin_team_conv_id = admin_team_conv.id

        # Post a message in the canonical ADMIN_TEAM conversation by Leader A
        res_post_a = await ac.post(
            f"/api/chat/conversations/{admin_team_conv_id}/messages",
            headers=headers_a,
            json={"content": "Initial leadership update from Leader A"}
        )
        assert res_post_a.status_code == 200
        msg_a_id = res_post_a.json()["id"]

        # Non-leader emp_b cannot access ADMIN_TEAM conversation -> 403
        res_get_b = await ac.get(f"/api/chat/conversations/{admin_team_conv_id}/messages", headers=headers_b)
        assert res_get_b.status_code == 403
        assert res_get_b.json()["code"] == "ADMIN_CHAT_LEADER_ONLY"

        # 4. Admin changes Group Leader from emp_a to emp_b
        res_switch = await ac.post(
            f"/api/admin/teams/{team_id}/group-leader",
            headers=headers_admin,
            json={"employee_id": str(emp_b.id), "reason": "Leadership rotation"}
        )
        assert res_switch.status_code == 200
        assert res_switch.json()["status"] == "success"

        # 5. IMMEDIATELY verify former leader A is denied (Database check)
        res_post_a_denied = await ac.post(
            f"/api/chat/conversations/{admin_team_conv_id}/messages",
            headers=headers_a,
            json={"content": "Attempted message from former leader A"}
        )
        assert res_post_a_denied.status_code == 403
        assert res_post_a_denied.json()["code"] == "ADMIN_CHAT_LEADER_ONLY"

        # Former leader A denied on direct message to Admin as well
        res_a_dm_denied = await ac.post(
            "/api/chat/conversations/direct",
            headers=headers_a,
            json={"other_user_id": str(admin_id)}
        )
        assert res_a_dm_denied.status_code == 403
        assert res_a_dm_denied.json()["code"] == "ADMIN_CHAT_LEADER_ONLY"

        # 6. New leader B NOW HAS FULL ACCESS to the canonical ADMIN_TEAM conversation
        res_get_b_allowed = await ac.get(f"/api/chat/conversations/{admin_team_conv_id}/messages", headers=headers_b)
        assert res_get_b_allowed.status_code == 200
        history = res_get_b_allowed.json()

        # Historical messages preserved
        assert any(m["id"] == msg_a_id for m in history)

        # New leader B can post to ADMIN_TEAM conversation
        res_post_b = await ac.post(
            f"/api/chat/conversations/{admin_team_conv_id}/messages",
            headers=headers_b,
            json={"content": "Leader B has taken over leadership."}
        )
        assert res_post_b.status_code == 200


@pytest.mark.asyncio
async def test_teammate_only_direct_chat_and_cross_team_restriction():
    """
    Verify:
    1. Employees in the SAME team can direct chat (HTTP 200).
    2. Employees in DIFFERENT teams CANNOT direct chat (HTTP 403 Forbidden with CROSS_TEAM_CHAT_FORBIDDEN).
    """
    async with async_session_maker() as session:
        # Find 2 distinct active teams
        teams = (await session.execute(select(Team).where(Team.is_active == True))).scalars().all()
        assert len(teams) >= 2, "Need at least 2 active teams"
        team_1 = teams[0]
        team_2 = teams[1]

        # Find 2 members of team 1
        t1_members = (await session.execute(
            select(Employee, User).join(User, Employee.user_id == User.id).where(
                Employee.team_id == team_1.id,
                User.is_active == True,
                User.role == "EMPLOYEE"
            )
        )).all()
        assert len(t1_members) >= 2
        emp_1a, user_1a = t1_members[0]
        emp_1b, user_1b = t1_members[1]

        # Find 1 member of team 2
        t2_members = (await session.execute(
            select(Employee, User).join(User, Employee.user_id == User.id).where(
                Employee.team_id == team_2.id,
                User.is_active == True,
                User.role == "EMPLOYEE"
            )
        )).all()
        assert len(t2_members) >= 1
        emp_2a, user_2a = t2_members[0]

        # Ensure non-leaders
        emp_1a.is_group_leader = False
        emp_1b.is_group_leader = False
        emp_2a.is_group_leader = False
        await session.commit()

        user_1a_id = user_1a.id
        user_1b_id = user_1b.id
        user_2a_id = user_2a.id

    transport = ASGITransport(app=app)
    token_1a = create_access_token(data={"sub": str(user_1a_id), "role": "EMPLOYEE"})
    headers_1a = {"Authorization": f"Bearer {token_1a}"}

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Teammate chat (1a -> 1b, same team) -> MUST SUCCEED (200 OK)
        res_same_team = await ac.post(
            "/api/chat/conversations/direct",
            headers=headers_1a,
            json={"other_user_id": str(user_1b_id)}
        )
        assert res_same_team.status_code == 200, f"Same-team chat failed: {res_same_team.text}"
        conv_data = res_same_team.json()
        assert conv_data["type"] == "DIRECT"

        # 2. Cross-team chat (1a -> 2a, different teams) -> MUST BE 403 FORBIDDEN
        res_cross_team = await ac.post(
            "/api/chat/conversations/direct",
            headers=headers_1a,
            json={"other_user_id": str(user_2a_id)}
        )
        assert res_cross_team.status_code == 403, f"Expected 403 Forbidden for cross-team chat, got {res_cross_team.status_code}"
        err_body = res_cross_team.json()
        assert err_body["code"] == "CROSS_TEAM_CHAT_FORBIDDEN"
        assert "Cross-team direct chat is forbidden" in err_body["message"]
