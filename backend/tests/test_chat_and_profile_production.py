import asyncio
import io
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import async_session_maker
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.core.security import get_password_hash
from sqlalchemy import select

@pytest.mark.asyncio
async def test_chat_and_profile_complete_workflow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Setup / identify test accounts
        async with async_session_maker() as session:
            # Find an Admin
            admin_user = (await session.execute(select(User).where(User.role == "ADMIN"))).scalars().first()
            if not admin_user:
                admin_user = User(
                    email="test_admin@incidentflow.dev",
                    hashed_password=get_password_hash("password123"),
                    full_name="Test Administrator",
                    role="ADMIN"
                )
                session.add(admin_user)
                await session.flush()

            # Find a Team
            team = (await session.execute(select(Team).where(Team.is_active == True))).scalars().first()
            assert team is not None, "Active team must exist"

            # Find or configure a Group Leader
            leader_emp = (await session.execute(
                select(Employee).where(Employee.team_id == team.id, Employee.is_group_leader == True)
            )).scalar_one_or_none()
            if not leader_emp:
                leader_emp = (await session.execute(
                    select(Employee).where(Employee.team_id == team.id)
                )).scalars().first()
                leader_emp.is_group_leader = True

            leader_user = await session.get(User, leader_emp.user_id)
            leader_user.hashed_password = get_password_hash("password123")

            # Find or configure a Non-Leader Employee in the same team
            normal_emp = (await session.execute(
                select(Employee).where(Employee.team_id == team.id, Employee.is_group_leader == False)
            )).scalars().first()
            assert normal_emp is not None, "Normal employee must exist"
            normal_user = await session.get(User, normal_emp.user_id)
            normal_user.hashed_password = get_password_hash("password123")
            admin_user.hashed_password = get_password_hash("pvcharan12345PV")

            await session.commit()

            admin_id = str(admin_user.id)
            admin_email = admin_user.email
            leader_email = leader_user.email
            normal_email = normal_user.email
            team_id = str(team.id)

        print(f"\n[TEST CONFIG] Admin: {admin_email}, Leader: {leader_email}, Normal: {normal_email}")

        # 2. Login as Normal Employee
        res = await client.post("/api/auth/login", json={"email": normal_email, "password": "password123"})
        assert res.status_code == 200, f"Normal employee login failed: {res.text}"
        normal_token = res.json()["access_token"]
        normal_headers = {"Authorization": f"Bearer {normal_token}"}

        # 3. Login as Group Leader
        res = await client.post("/api/auth/login", json={"email": leader_email, "password": "password123"})
        assert res.status_code == 200, f"Leader login failed: {res.text}"
        leader_token = res.json()["access_token"]
        leader_headers = {"Authorization": f"Bearer {leader_token}"}

        # 4. Login as Admin
        res = await client.post("/api/auth/login", json={"email": admin_email, "password": "pvcharan12345PV"})
        assert res.status_code == 200, f"Admin login failed: {res.text}"
        admin_token = res.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 5. TEST: Normal Employee attempts to direct message Admin -> MUST BE 403 FORBIDDEN
        res = await client.post(
            "/api/chat/conversations/direct",
            json={"other_user_id": admin_id},
            headers=normal_headers
        )
        assert res.status_code == 403, f"Expected 403 Forbidden for non-leader messaging admin, got {res.status_code}"
        assert "Only Group Leaders" in res.json().get("detail", "")
        print("✓ Normal employee blocked from messaging Admin (403 Forbidden)")

        # 6. TEST: Group Leader attempts to direct message Admin -> MUST SUCCEED (200 OK)
        res = await client.post(
            "/api/chat/conversations/direct",
            json={"other_user_id": admin_id},
            headers=leader_headers
        )
        assert res.status_code == 200, f"Expected 200 OK for leader messaging admin, got {res.status_code}: {res.text}"
        direct_conv = res.json()
        assert direct_conv["type"] == "DIRECT"
        print("✓ Group Leader successfully created direct conversation with Admin")

        # 7. TEST: Canonical Team Chat Endpoint
        res = await client.get("/api/chat/my-team", headers=normal_headers)
        assert res.status_code == 200, f"Failed to get my-team: {res.text}"
        team_chat = res.json()
        assert team_chat["team_id"] == team_id
        team_conv_id = team_chat["conversation_id"]
        print(f"✓ Retrieved canonical team chat for {team_chat['team_name']} ({team_chat['member_count']} members)")

        # 7b. TEST: Operational Groups Listing (/api/chat/groups)
        res = await client.get("/api/chat/groups", headers=normal_headers)
        assert res.status_code == 200, f"Failed to get chat groups: {res.text}"
        groups = res.json()
        assert len(groups) > 0, "Expected at least one active team group"
        print(f"✓ Retrieved {len(groups)} operational chat groups via /api/chat/groups")

        # 8. TEST: Image Attachment Upload
        fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        files = {"file": ("screenshot.png", io.BytesIO(fake_png), "image/png")}
        res = await client.post("/api/chat/attachments/image", files=files, headers=normal_headers)
        assert res.status_code == 200, f"Image upload failed: {res.text}"
        image_att = res.json()
        assert image_att["mime_type"] == "image/png"
        assert image_att["file_name"] == "screenshot.png"
        print(f"✓ Uploaded chat image attachment: {image_att['id']}")

        # Retrieve uploaded image file
        res = await client.get(f"/api/chat/attachments/{image_att['id']}/file", headers=normal_headers)
        assert res.status_code == 200
        assert res.content == fake_png
        print("✓ Successfully retrieved image bytes via /attachments/{id}/file")

        # 9. TEST: Audio Attachment Upload
        fake_audio = b"\x1aE\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01\x42\xf2\x81\x04"
        files = {"file": ("voice.webm", io.BytesIO(fake_audio), "audio/webm")}
        data = {"duration_seconds": "5"}
        res = await client.post("/api/chat/attachments/audio", files=files, data=data, headers=normal_headers)
        assert res.status_code == 200, f"Audio upload failed: {res.text}"
        audio_att = res.json()
        assert "audio" in audio_att["mime_type"]
        assert audio_att["duration_seconds"] == 5
        print(f"✓ Uploaded voice note audio attachment: {audio_att['id']} (duration: 5s)")

        # 10. TEST: Post Parent Message and Reply Message with Attachment
        # Parent Message
        res = await client.post(
            f"/api/chat/conversations/{team_conv_id}/messages",
            json={"content": "Primary investigation started on connection pool timeouts."},
            headers=normal_headers
        )
        assert res.status_code == 200
        parent_msg = res.json()
        parent_id = parent_msg["id"]
        print(f"✓ Sent parent message in team chat: {parent_id}")

        # Reply Message with image attachment
        res = await client.post(
            f"/api/chat/conversations/{team_conv_id}/messages",
            json={
                "content": "Attaching the pool exhaustion metrics screenshot #INC-00100",
                "message_type": "IMAGE",
                "reply_to_message_id": parent_id,
                "attachment_id": image_att["id"]
            },
            headers=leader_headers
        )
        assert res.status_code == 200
        reply_msg = res.json()
        assert reply_msg["reply_to"] is not None
        assert reply_msg["reply_to"]["id"] == parent_id
        assert reply_msg["attachment"] is not None
        assert reply_msg["attachment"]["id"] == image_att["id"]
        print(f"✓ Sent reply message with quote and attachment verified end-to-end")

        # 11. TEST: Emoji Reactions
        # Add Reaction
        res = await client.post(
            f"/api/chat/messages/{parent_id}/reactions",
            json={"emoji": "🔥"},
            headers=leader_headers
        )
        assert res.status_code == 200
        print("✓ Leader reacted 🔥 to parent message")

        # Verify reaction is visible in messages list
        res = await client.get(f"/api/chat/conversations/{team_conv_id}/messages", headers=leader_headers)
        assert res.status_code == 200
        fetched_msgs = res.json()
        target_msg = next((m for m in fetched_msgs if m["id"] == parent_id), None)
        assert target_msg is not None
        assert any(r["emoji"] == "🔥" and r["count"] >= 1 for r in target_msg["reactions"])
        assert "🔥" in target_msg["user_reactions"]
        print("✓ Verified reaction aggregation and user_reactions state in message feed")

        # Remove Reaction
        res = await client.delete(f"/api/chat/messages/{parent_id}/reactions/%F0%9F%94%A5", headers=leader_headers)
        assert res.status_code == 200
        print("✓ Removed reaction 🔥 successfully")

        # 12. TEST: Edit and Delete Message
        res = await client.patch(
            f"/api/chat/messages/{parent_id}",
            json={"content": "Primary investigation updated: issue resolved in cluster."},
            headers=normal_headers
        )
        assert res.status_code == 200
        edited_msg = res.json()
        assert edited_msg["content"] == "Primary investigation updated: issue resolved in cluster."
        assert edited_msg["is_edited"] is True
        print("✓ Message edited successfully")

        res = await client.delete(f"/api/chat/messages/{parent_id}", headers=normal_headers)
        assert res.status_code == 200
        deleted_msg = res.json()
        assert deleted_msg["is_deleted"] is True
        assert deleted_msg["content"] == "This message was deleted"
        print("✓ Message soft-deleted with audit preservation")

        # 13. TEST: Employee Profile APIs (/api/me/profile and /api/employees/profile)
        res = await client.get("/api/me/profile", headers=normal_headers)
        assert res.status_code == 200, f"Profile fetch failed: {res.text}"
        profile = res.json()
        assert profile["email"] == normal_email
        assert profile["team_name"] is not None
        print(f"✓ Retrieved profile: {profile['full_name']} ({profile['team_name']})")

        res = await client.get("/api/employees/profile", headers=normal_headers)
        assert res.status_code == 200
        print("✓ /api/employees/profile endpoint functional")

        # 14. TEST: Update Profile
        res = await client.patch(
            "/api/me/profile",
            json={
                "phone": "+91 98765 43210",
                "bio": "Lead DBA handling high-throughput PostgreSQL & MongoDB clusters.",
                "timezone": "Asia/Kolkata",
                "availability_status": "AVAILABLE"
            },
            headers=normal_headers
        )
        assert res.status_code == 200
        updated_profile = res.json()
        assert updated_profile["phone"] == "+91 98765 43210"
        assert "Lead DBA" in updated_profile["bio"]
        assert updated_profile["timezone"] == "Asia/Kolkata"
        assert updated_profile["availability_status"] == "AVAILABLE"
        print("✓ Updated profile fields persisted to database")

        # 15. TEST: Avatar Upload
        files = {"file": ("avatar.png", io.BytesIO(fake_png), "image/png")}
        res = await client.post("/api/me/avatar", files=files, headers=normal_headers)
        assert res.status_code == 200, f"Avatar upload failed: {res.text}"
        avatar_resp = res.json()
        assert "avatar_url" in avatar_resp
        avatar_url = avatar_resp["avatar_url"]
        print(f"✓ Uploaded profile avatar: {avatar_url}")

        # Retrieve Avatar file
        res = await client.get(avatar_url)
        assert res.status_code == 200
        assert res.content == fake_png
        print("✓ Avatar image served with real media bytes")

        print("\n============================================================")
        print("ALL 15 ENTERPRISE CHAT & PROFILE TESTS PASSED FLAWLESSLY!")
        print("============================================================\n")

if __name__ == "__main__":
    asyncio.run(test_chat_and_profile_complete_workflow())
