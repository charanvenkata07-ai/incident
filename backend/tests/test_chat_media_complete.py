"""
Automated test suite for IncidentFlow Realtime Chat Complete Media Sharing:
- Image, Video, Audio, Document, and File uploads
- Security: Token authentication via Bearer header and query param ?token=
- Range requests (HTTP 206 Partial Content) for video/audio seeking
- Forbidden extensions blocking (.exe, .sh, .py, .html)
- Message creation with attachments, replies, and reactions
"""
import io
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import async_session_maker
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.conversation import Conversation, ConversationMember, ChatMessage, ChatAttachment
from app.core.security import get_password_hash, create_access_token
from sqlalchemy import select

@pytest.mark.asyncio
async def test_chat_complete_media_sharing():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Fetch users and create tokens directly
        async with async_session_maker() as session:
            team = (await session.execute(select(Team).where(Team.is_active == True))).scalars().first()
            assert team is not None, "Active team required"

            emp1 = (await session.execute(
                select(Employee).where(Employee.team_id == team.id)
            )).scalars().first()
            assert emp1 is not None, "Employee 1 required"

            user1 = await session.get(User, emp1.user_id)
            admin_user = (await session.execute(select(User).where(User.role == "ADMIN"))).scalars().first()
            assert admin_user is not None, "Admin required"

            token1 = create_access_token({"sub": str(user1.id), "email": user1.email, "role": user1.role})
            token_admin = create_access_token({"sub": str(admin_user.id), "email": admin_user.email, "role": admin_user.role})

        headers1 = {"Authorization": f"Bearer {token1}"}
        headers_admin = {"Authorization": f"Bearer {token_admin}"}

        # 3. Get team conversation
        r_myteam = await client.get("/api/chat/my-team", headers=headers1)
        assert r_myteam.status_code == 200
        conv_id = r_myteam.json()["conversation_id"]

        # 4. Test Image Upload
        tiny_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        files_img = {"file": ("screenshot.png", io.BytesIO(tiny_png), "image/png")}
        r_img = await client.post("/api/chat/attachments/image", headers=headers1, files=files_img)
        assert r_img.status_code in (200, 201), f"Image upload failed: {r_img.text}"
        img_data = r_img.json()
        assert img_data["mime_type"] == "image/png"
        img_id = img_data["id"]

        # 5. Test Video Upload
        mock_mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42\x00\x00\x00\x08free\x00\x00\x00\x08mdat"
        files_vid = {"file": ("demo_recording.mp4", io.BytesIO(mock_mp4), "video/mp4")}
        r_vid = await client.post("/api/chat/attachments/video", headers=headers1, files=files_vid)
        assert r_vid.status_code in (200, 201), f"Video upload failed: {r_vid.text}"
        vid_data = r_vid.json()
        assert vid_data["mime_type"] == "video/mp4"
        vid_id = vid_data["id"]

        # 6. Test Document / File Upload
        mock_pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\nxref\n0 1\n0000000000 65535 f\ntrailer<</Size 1/Root 1 0 R>>\nstartxref\n50\n%%EOF"
        files_doc = {"file": ("runbook_incident.pdf", io.BytesIO(mock_pdf), "application/pdf")}
        r_doc = await client.post("/api/chat/attachments/document", headers=headers1, files=files_doc)
        assert r_doc.status_code in (200, 201), f"Doc upload failed: {r_doc.text}"
        doc_data = r_doc.json()
        assert "pdf" in doc_data["file_name"].lower()
        doc_id = doc_data["id"]

        # 7. Test Forbidden File Upload (.exe / .sh blocked)
        bad_file = {"file": ("exploit.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")}
        r_bad = await client.post("/api/chat/attachments/document", headers=headers1, files=bad_file)
        assert r_bad.status_code == 400
        assert "not permitted" in r_bad.json()["detail"].lower() or "not allowed" in r_bad.json()["detail"].lower()

        # 8. Test Media File Serving & Authorization
        # A) Unauthorized access (no token) -> 401
        r_no_auth = await client.get(f"/api/chat/attachments/{vid_id}/file")
        assert r_no_auth.status_code == 401

        # B) Authorized via Bearer header -> 200
        r_auth_bearer = await client.get(f"/api/chat/attachments/{vid_id}/file", headers=headers1)
        assert r_auth_bearer.status_code == 200
        assert r_auth_bearer.headers["content-type"] == "video/mp4"
        assert r_auth_bearer.content == mock_mp4

        # C) Authorized via ?token= query parameter -> 200 (for <img>, <video>, <audio>, <a> tags)
        r_auth_param = await client.get(f"/api/chat/attachments/{vid_id}/file?token={token1}")
        assert r_auth_param.status_code == 200
        assert r_auth_param.content == mock_mp4

        # D) Video Range Request (HTTP 206 Partial Content) for seekable playback
        range_headers = {"Authorization": f"Bearer {token1}", "Range": "bytes=0-10"}
        r_range = await client.get(f"/api/chat/attachments/{vid_id}/file", headers=range_headers)
        assert r_range.status_code == 206
        assert "content-range" in r_range.headers or "Content-Range" in r_range.headers
        assert len(r_range.content) == 11

        # 9. Send Messages with Attachments
        # Send Video Message
        r_msg_vid = await client.post(
            f"/api/chat/conversations/{conv_id}/messages",
            headers=headers1,
            json={
                "content": "Check this video issue",
                "message_type": "VIDEO",
                "attachment_id": vid_id,
            },
        )
        assert r_msg_vid.status_code in (200, 201)
        msg_vid = r_msg_vid.json()
        assert msg_vid["attachment_id"] == vid_id
        assert msg_vid["attachment"]["mime_type"] == "video/mp4"

        # Send Document Message
        r_msg_doc = await client.post(
            f"/api/chat/conversations/{conv_id}/messages",
            headers=headers1,
            json={
                "content": "Latest runbook attached",
                "message_type": "DOCUMENT",
                "attachment_id": doc_id,
            },
        )
        assert r_msg_doc.status_code in (200, 201)
        msg_doc = r_msg_doc.json()
        assert msg_doc["attachment_id"] == doc_id

        # 10. Reply and Reaction to Media Message
        # Reply to video message
        r_reply = await client.post(
            f"/api/chat/conversations/{conv_id}/messages",
            headers=headers1,
            json={
                "content": "Received the video, investigating now.",
                "message_type": "USER",
                "reply_to_message_id": msg_vid["id"],
            },
        )
        assert r_reply.status_code in (200, 201)
        reply_data = r_reply.json()
        assert reply_data["reply_to"]["id"] == msg_vid["id"]

        # Add Reaction 👍
        r_react = await client.post(
            f"/api/chat/messages/{msg_vid['id']}/reactions",
            headers=headers1,
            json={"emoji": "👍"},
        )
        assert r_react.status_code == 200
        react_data = r_react.json()
        assert react_data["status"] == "success"
        assert react_data["emoji"] == "👍"

        # Toggle reaction off
        r_unreact = await client.delete(
            f"/api/chat/messages/{msg_vid['id']}/reactions/%F0%9F%91%8D",
            headers=headers1,
        )
        assert r_unreact.status_code == 200


@pytest.mark.asyncio
async def test_chat_media_authorization_and_limits():
    """Verify security isolation: cross-team users are rejected with 403 when accessing private attachments."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with async_session_maker() as session:
            teams = (await session.execute(select(Team).where(Team.is_active == True).limit(2))).scalars().all()
            assert len(teams) >= 2, "At least 2 teams required"
            team_a, team_b = teams[0], teams[1]

            emp_a = (await session.execute(select(Employee).where(Employee.team_id == team_a.id))).scalars().first()
            emp_b = (await session.execute(select(Employee).where(Employee.team_id == team_b.id))).scalars().first()
            assert emp_a and emp_b, "Employees from both teams required"

            user_a = await session.get(User, emp_a.user_id)
            user_b = await session.get(User, emp_b.user_id)

            token_a = create_access_token({"sub": str(user_a.id), "email": user_a.email, "role": user_a.role})
            token_b = create_access_token({"sub": str(user_b.id), "email": user_b.email, "role": user_b.role})

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 1. User A gets Team A conversation and posts an attachment
        r_team_a = await client.get("/api/chat/my-team", headers=headers_a)
        conv_a_id = r_team_a.json()["conversation_id"]

        tiny_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        files_img = {"file": ("team_secret.png", io.BytesIO(tiny_png), "image/png")}
        r_att = await client.post("/api/chat/attachments/image", headers=headers_a, files=files_img)
        assert r_att.status_code in (200, 201)
        att_id = r_att.json()["id"]

        # Link attachment to Team A conversation message
        r_post = await client.post(
            f"/api/chat/conversations/{conv_a_id}/messages",
            headers=headers_a,
            json={"content": "Confidential internal doc", "message_type": "IMAGE", "attachment_id": att_id}
        )
        assert r_post.status_code in (200, 201)

        # 2. User B (from different team) tries to access Team A's media file -> 403 Forbidden!
        r_unauth = await client.get(f"/api/chat/attachments/{att_id}/file", headers=headers_b)
        assert r_unauth.status_code == 403

        # Also via ?token= query param with User B's token -> 403 Forbidden!
        r_unauth_param = await client.get(f"/api/chat/attachments/{att_id}/file?token={token_b}")
        assert r_unauth_param.status_code == 403

        # 3. Audio upload with duration
        mock_audio = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00"
        files_audio = {"file": ("voice_memo.webm", io.BytesIO(mock_audio), "audio/webm")}
        r_audio = await client.post(
            "/api/chat/attachments/audio",
            headers=headers_a,
            files=files_audio,
            data={"duration_seconds": "15"}
        )
        assert r_audio.status_code in (200, 201)
        audio_data = r_audio.json()
        assert audio_data["mime_type"] == "audio/webm"
        assert audio_data["duration_seconds"] == 15
