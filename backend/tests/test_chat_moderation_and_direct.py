import asyncio
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import async_session_maker
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.conversation import Conversation, ChatMessage
from app.models.audit import AuditLog
from app.core.security import get_password_hash
from sqlalchemy import select

@pytest.mark.asyncio
async def test_chat_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/chat/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"
        assert data["websocket"] == "ok"


@pytest.mark.asyncio
async def test_canonical_direct_chat_pairing():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create or fetch two distinct users
        async with async_session_maker() as session:
            users = (await session.execute(select(User).where(User.role == "EMPLOYEE").limit(2))).scalars().all()
            user_a = users[0]
            user_b = users[1]

            user_a.hashed_password = get_password_hash("password123")
            user_b.hashed_password = get_password_hash("password123")
            await session.commit()

            user_a_id = str(user_a.id)
            user_b_id = str(user_b.id)
            user_a_email = user_a.email
            user_b_email = user_b.email

        # Login User A
        res_a = await client.post("/api/auth/login", json={"email": user_a_email, "password": "password123"})
        assert res_a.status_code == 200
        token_a = res_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Login User B
        res_b = await client.post("/api/auth/login", json={"email": user_b_email, "password": "password123"})
        assert res_b.status_code == 200
        token_b = res_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User A requests direct conversation with User B
        res1 = await client.post(
            "/api/chat/conversations/direct",
            json={"other_user_id": user_b_id},
            headers=headers_a
        )
        assert res1.status_code == 200
        conv_1 = res1.json()

        # User B requests direct conversation with User A
        res2 = await client.post(
            "/api/chat/conversations/direct",
            json={"other_user_id": user_a_id},
            headers=headers_b
        )
        assert res2.status_code == 200
        conv_2 = res2.json()

        # Both MUST yield the identical conversation ID
        assert conv_1["id"] == conv_2["id"], f"Expected identical direct conversation ID, got {conv_1['id']} and {conv_2['id']}"

        # Verify direct_pair_key in DB
        async with async_session_maker() as session:
            conv_db = await session.get(Conversation, uuid.UUID(conv_1["id"]))
            expected_key = f"{min(user_a_id, user_b_id)}:{max(user_a_id, user_b_id)}"
            assert conv_db.direct_pair_key == expected_key


@pytest.mark.asyncio
async def test_group_leader_moderation_and_permissions():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Setup Team, Leader, and Normal Employee
        async with async_session_maker() as session:
            team = (await session.execute(select(Team).where(Team.is_active == True))).scalars().first()
            assert team is not None

            leader_emp = (await session.execute(
                select(Employee).where(Employee.team_id == team.id, Employee.is_group_leader == True)
            )).scalar_one_or_none()
            if not leader_emp:
                leader_emp = (await session.execute(
                    select(Employee).where(Employee.team_id == team.id)
                )).scalars().first()
                leader_emp.is_group_leader = True

            normal_emp = (await session.execute(
                select(Employee).where(Employee.team_id == team.id, Employee.is_group_leader == False)
            )).scalars().first()
            assert normal_emp is not None

            leader_user = await session.get(User, leader_emp.user_id)
            normal_user = await session.get(User, normal_emp.user_id)
            leader_user.hashed_password = get_password_hash("password123")
            normal_user.hashed_password = get_password_hash("password123")
            await session.commit()

            leader_email = leader_user.email
            normal_email = normal_user.email
            team_id = str(team.id)

        # Login Leader
        res_l = await client.post("/api/auth/login", json={"email": leader_email, "password": "password123"})
        assert res_l.status_code == 200
        token_l = res_l.json()["access_token"]
        headers_l = {"Authorization": f"Bearer {token_l}"}

        # Login Normal Employee
        res_n = await client.post("/api/auth/login", json={"email": normal_email, "password": "password123"})
        assert res_n.status_code == 200
        token_n = res_n.json()["access_token"]
        headers_n = {"Authorization": f"Bearer {token_n}"}

        # Get Team Conversation
        res_conv = await client.get("/api/chat/my-team", headers=headers_n)
        assert res_conv.status_code == 200
        conv_id = res_conv.json()["conversation_id"]

        # 2. Normal employee posts a message
        res_msg1 = await client.post(
            f"/api/chat/conversations/{conv_id}/messages",
            json={"content": "Normal employee testing message moderation", "message_type": "TEXT"},
            headers=headers_n
        )
        assert res_msg1.status_code == 200
        msg1_id = res_msg1.json()["id"]

        # 3. Leader deletes the normal employee's message (Group Leader Moderation)
        del_res = await client.delete(f"/api/chat/messages/{msg1_id}", headers=headers_l)
        assert del_res.status_code == 200, f"Leader should be allowed to moderate teammate message: {del_res.text}"
        assert del_res.json()["is_deleted"] is True

        # Check conversation messages to verify moderated text
        list_res = await client.get(f"/api/chat/conversations/{conv_id}/messages", headers=headers_n)
        assert list_res.status_code == 200
        messages = list_res.json()
        deleted_m1 = next((m for m in messages if m["id"] == msg1_id), None)
        assert deleted_m1 is not None
        assert deleted_m1["is_deleted"] == True
        assert deleted_m1["content"] == "This message was removed by a Group Leader"
        assert deleted_m1["deleted_by"] is not None

        # Verify MESSAGE_MODERATED audit log was written
        async with async_session_maker() as session:
            audit_entry = (await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "MESSAGE_MODERATED",
                    AuditLog.entity_id == uuid.UUID(msg1_id)
                )
            )).scalar_one_or_none()
            assert audit_entry is not None
            assert "Group Leader" in audit_entry.reason

        # 4. Leader posts a message
        res_msg2 = await client.post(
            f"/api/chat/conversations/{conv_id}/messages",
            json={"content": "Important leader message", "message_type": "TEXT"},
            headers=headers_l
        )
        assert res_msg2.status_code == 200
        msg2_id = res_msg2.json()["id"]

        # 5. Normal employee attempts to delete the leader's message -> Must get 403 Forbidden MESSAGE_DELETE_FORBIDDEN
        forbidden_del = await client.delete(f"/api/chat/messages/{msg2_id}", headers=headers_n)
        assert forbidden_del.status_code == 403
        assert "MESSAGE_DELETE_FORBIDDEN" in forbidden_del.text

        # 6. Normal employee posts another message and deletes their own message -> Allowed
        res_msg3 = await client.post(
            f"/api/chat/conversations/{conv_id}/messages",
            json={"content": "Self message to delete", "message_type": "TEXT"},
            headers=headers_n
        )
        assert res_msg3.status_code == 200
        msg3_id = res_msg3.json()["id"]

        del_own = await client.delete(f"/api/chat/messages/{msg3_id}", headers=headers_n)
        assert del_own.status_code == 200
        assert del_own.json()["is_deleted"] is True


@pytest.mark.asyncio
async def test_chat_search_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Setup user and team
        async with async_session_maker() as session:
            team = (await session.execute(select(Team).where(Team.is_active == True))).scalars().first()
            emp = (await session.execute(select(Employee).where(Employee.team_id == team.id))).scalars().first()
            user = await session.get(User, emp.user_id)
            user.hashed_password = get_password_hash("password123")
            await session.commit()
            email = user.email
            team_id = str(team.id)

        # Login
        res_login = await client.post("/api/auth/login", json={"email": email, "password": "password123"})
        assert res_login.status_code == 200
        token = res_login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Get Team Conversation
        res_conv = await client.get("/api/chat/my-team", headers=headers)
        assert res_conv.status_code == 200
        conv_id = res_conv.json()["conversation_id"]

        # Post unique message
        unique_term = f"DIAGNOSTIC_QUERY_{uuid.uuid4().hex[:8]}"
        msg_res = await client.post(
            f"/api/chat/conversations/{conv_id}/messages",
            json={"content": f"Critical diagnostic output: {unique_term} confirmed", "message_type": "TEXT"},
            headers=headers
        )
        assert msg_res.status_code == 200

        # Search for unique message
        search_res = await client.get(f"/api/chat/search?q={unique_term}", headers=headers)
        assert search_res.status_code == 200
        results = search_res.json()["results"]
        assert len(results) >= 1
        assert any(unique_term in r["content"] for r in results)
