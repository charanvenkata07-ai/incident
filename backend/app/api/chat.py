import os
import re
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from pydantic import BaseModel

from datetime import datetime, timezone
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, verify_token
from app.models.user import User
from app.models.team import Team
from app.models.employee import Employee
from app.models.conversation import Conversation, ConversationMember, ChatMessage, MessageReaction, ChatAttachment
from app.models.incident import Incident
from app.schemas.chat import (
    ChatMessageCreate, ChatMessageUpdate, ChatMessageResponse, ConversationResponse,
    ConversationMemberResponse, TeamMemberChatBrief, TeamChatGroupBrief,
    ChatTypingRequest, MyTeamChatResponse, AttachmentResponse, ReactionCount,
    ReplyToPreview, ReactionRequest
)
from app.services.chat_service import ChatService
from app.websocket.manager import ws_manager, CHAT_TYPING, CHAT_MESSAGE_READ

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
IMAGES_DIR = os.path.join(UPLOAD_DIR, "images")
AUDIO_DIR = os.path.join(UPLOAD_DIR, "audio")
VIDEOS_DIR = os.path.join(UPLOAD_DIR, "videos")
DOCS_DIR = os.path.join(UPLOAD_DIR, "documents")
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(DOCS_DIR, exist_ok=True)

class DirectConversationRequest(BaseModel):
    other_user_id: uuid.UUID


async def _build_message_response(db: AsyncSession, msg: ChatMessage, current_user_id: Optional[uuid.UUID] = None) -> ChatMessageResponse:
    sender = await db.get(User, msg.sender_id) if msg.sender_id else None
    inc = await db.get(Incident, msg.incident_id) if msg.incident_id else None

    reply_to_preview = None
    if msg.reply_to_message_id:
        parent = await db.get(ChatMessage, msg.reply_to_message_id)
        if parent:
            p_sender = await db.get(User, parent.sender_id) if parent.sender_id else None
            reply_to_preview = ReplyToPreview(
                id=parent.id,
                sender_id=parent.sender_id,
                sender_name=p_sender.full_name if p_sender else "System",
                content="This message was deleted" if parent.is_deleted else parent.content,
                message_type=parent.message_type,
                is_deleted=parent.is_deleted
            )

    attachment_preview = None
    if msg.attachment_id:
        att = await db.get(ChatAttachment, msg.attachment_id)
        if att:
            attachment_preview = AttachmentResponse(
                id=att.id,
                message_id=att.message_id,
                file_name=att.file_name,
                mime_type=att.mime_type,
                file_size=att.file_size,
                storage_key=att.storage_key,
                url=f"/api/chat/attachments/{att.id}/file",
                width=att.width,
                height=att.height,
                duration_seconds=att.duration_seconds,
                status=att.status,
                created_at=att.created_at
            )

    reactions_stmt = select(MessageReaction).where(MessageReaction.message_id == msg.id)
    reactions = (await db.execute(reactions_stmt)).scalars().all()
    emoji_groups: dict[str, list[str]] = {}
    user_reactions: list[str] = []
    for r in reactions:
        if r.emoji not in emoji_groups:
            emoji_groups[r.emoji] = []
        emoji_groups[r.emoji].append(str(r.user_id))
        if current_user_id and r.user_id == current_user_id:
            user_reactions.append(r.emoji)

    reaction_counts = [
        ReactionCount(emoji=emoji, count=len(uids), users=uids)
        for emoji, uids in emoji_groups.items()
    ]

    return ChatMessageResponse(
        id=msg.id,
        conversation_id=msg.conversation_id,
        sender_id=msg.sender_id,
        sender_name=sender.full_name if sender else "System",
        sender_role=sender.role if sender else "SYSTEM",
        sender_email=sender.email if sender else None,
        sender_avatar_url=sender.avatar_url if sender else None,
        content="This message was removed by a Group Leader" if (msg.is_deleted and msg.deleted_by and msg.sender_id and msg.deleted_by != msg.sender_id) else ("This message was deleted" if msg.is_deleted else msg.content),
        message_type=msg.message_type,
        incident_id=msg.incident_id,
        incident_number=inc.incident_number if inc else None,
        reply_to_message_id=msg.reply_to_message_id,
        reply_to=reply_to_preview,
        attachment_id=msg.attachment_id,
        attachment=attachment_preview,
        reactions=reaction_counts,
        user_reactions=user_reactions,
        client_message_id=msg.client_message_id,
        is_edited=msg.is_edited,
        is_deleted=msg.is_deleted,
        edited_at=msg.edited_at,
        deleted_at=msg.deleted_at,
        deleted_by=msg.deleted_by,
        delete_reason=msg.delete_reason,
        created_at=msg.created_at,
        read_by_count=0
    )



async def _build_conversation_response(db: AsyncSession, conv: Conversation, current_user_id: uuid.UUID) -> ConversationResponse:
    members_resp = []
    current_member = None
    loaded_members = conv.__dict__.get("members")
    if loaded_members:
        for m in loaded_members:
            u = m.__dict__.get("user") or (await db.get(User, m.user_id) if m.user_id else None)
            if u:
                members_resp.append(ConversationMemberResponse(
                    id=m.id,
                    user_id=u.id,
                    name=u.full_name,
                    email=u.email,
                    role=u.role,
                    avatar_url=u.avatar_url,
                    joined_at=m.joined_at,
                    last_read_at=m.last_read_at
                ))
            if m.user_id == current_user_id:
                current_member = m
    else:
        mem_stmt = select(ConversationMember).where(ConversationMember.conversation_id == conv.id)
        mems = (await db.execute(mem_stmt)).scalars().all()
        for m in mems:
            u = await db.get(User, m.user_id) if m.user_id else None
            if u:
                members_resp.append(ConversationMemberResponse(
                    id=m.id,
                    user_id=u.id,
                    name=u.full_name,
                    email=u.email,
                    role=u.role,
                    avatar_url=u.avatar_url,
                    joined_at=m.joined_at,
                    last_read_at=m.last_read_at
                ))
            if m.user_id == current_user_id:
                current_member = m

    team_obj = conv.__dict__.get("team")
    team_name = team_obj.name if team_obj else None
    if not team_name and conv.team_id:
        t = await db.get(Team, conv.team_id)
        if t:
            team_name = t.name

    inc_obj = conv.__dict__.get("incident")
    inc_number = inc_obj.incident_number if inc_obj else None
    if not inc_number and conv.incident_id:
        inc = await db.get(Incident, conv.incident_id)
        if inc:
            inc_number = inc.incident_number

    last_msg_stmt = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conv.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )
    last_msg = (await db.execute(last_msg_stmt)).scalar_one_or_none()
    last_msg_resp = await _build_message_response(db, last_msg, current_user_id) if last_msg else None

    unread_count = 0
    if current_member and current_member.last_read_at:
        unread_stmt = select(func.count(ChatMessage.id)).where(
            ChatMessage.conversation_id == conv.id,
            ChatMessage.created_at > current_member.last_read_at,
            ChatMessage.sender_id != current_user_id
        )
        unread_count = (await db.execute(unread_stmt)).scalar() or 0
    elif current_member and not current_member.last_read_at:
        unread_stmt = select(func.count(ChatMessage.id)).where(
            ChatMessage.conversation_id == conv.id,
            ChatMessage.sender_id != current_user_id
        )
        unread_count = (await db.execute(unread_stmt)).scalar() or 0

    return ConversationResponse(
        id=conv.id,
        type=conv.type,
        team_id=conv.team_id,
        team_name=team_name,
        incident_id=conv.incident_id,
        incident_number=inc_number,
        title=conv.title,
        members=members_resp,
        last_message=last_msg_resp,
        unread_count=unread_count,
        created_at=conv.created_at,
        updated_at=conv.updated_at
    )


async def _authorize_conversation_access(db: AsyncSession, conv: Conversation, current_user: User) -> None:
    """
    Validates user authorization to access conversation:
    - Admin & Supervisor can access ANY conversation.
    - Employee is authorized ONLY for their own team, incident discussions in their team,
      canonical ADMIN_TEAM (if active Group Leader), or direct chats with teammates (or Admin if Group Leader).
    """
    if current_user.role in ("ADMIN", "SUPERVISOR"):
        return

    emp_stmt = select(Employee).where(Employee.user_id == current_user.id)
    emp = (await db.execute(emp_stmt)).scalar_one_or_none()

    if conv.type == "ADMIN_TEAM":
        if not emp or not emp.is_group_leader or emp.team_id != conv.team_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "ADMIN_CHAT_LEADER_ONLY",
                    "message": "Only the active Group Leader can message Admin."
                }
            )
        mem_stmt = select(ConversationMember).where(
            ConversationMember.conversation_id == conv.id,
            ConversationMember.user_id == current_user.id
        )
        if not (await db.execute(mem_stmt)).scalar_one_or_none():
            db.add(ConversationMember(conversation_id=conv.id, user_id=current_user.id))
            await db.commit()
        return

    if conv.type == "TEAM":
        if not emp or emp.team_id != conv.team_id:
            raise HTTPException(status_code=403, detail="Forbidden: You are not authorized to access another group's chat")
        mem_stmt = select(ConversationMember).where(
            ConversationMember.conversation_id == conv.id,
            ConversationMember.user_id == current_user.id
        )
        if not (await db.execute(mem_stmt)).scalar_one_or_none():
            db.add(ConversationMember(conversation_id=conv.id, user_id=current_user.id))
            await db.commit()
        return

    if conv.type == "INCIDENT":
        if conv.incident_id and emp:
            inc = await db.get(Incident, conv.incident_id)
            if inc:
                team_id = None
                if inc.assignment_group:
                    t_res = await db.execute(select(Team.id).where(Team.name == inc.assignment_group))
                    team_id = t_res.scalar_one_or_none()
                if (team_id and team_id == emp.team_id) or inc.assigned_to in (current_user.full_name, current_user.email):
                    mem_stmt = select(ConversationMember).where(
                        ConversationMember.conversation_id == conv.id,
                        ConversationMember.user_id == current_user.id
                    )
                    if not (await db.execute(mem_stmt)).scalar_one_or_none():
                        db.add(ConversationMember(conversation_id=conv.id, user_id=current_user.id))
                        await db.commit()
                    return
        raise HTTPException(status_code=403, detail="Forbidden: You are not authorized to access this incident discussion")

    # For DIRECT conversation:
    mem_stmt = select(ConversationMember).where(
        ConversationMember.conversation_id == conv.id,
        ConversationMember.user_id == current_user.id
    )
    is_member = (await db.execute(mem_stmt)).scalar_one_or_none() is not None
    if not is_member:
        raise HTTPException(status_code=403, detail="Forbidden: You are not authorized to access this conversation")

    # Validate peer authorization in DIRECT conversation
    other_mem_stmt = select(ConversationMember).where(
        ConversationMember.conversation_id == conv.id,
        ConversationMember.user_id != current_user.id
    )
    other_mem = (await db.execute(other_mem_stmt)).scalars().first()
    if other_mem:
        other_user = await db.get(User, other_mem.user_id)
        if other_user:
            if other_user.role in ("ADMIN", "SUPERVISOR"):
                if not emp or not emp.is_group_leader:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "code": "ADMIN_CHAT_LEADER_ONLY",
                            "message": "Only the active Group Leader can message Admin."
                        }
                    )
            elif other_user.role == "EMPLOYEE":
                other_emp = (await db.execute(select(Employee).where(Employee.user_id == other_user.id))).scalar_one_or_none()
                if not emp or not other_emp or not emp.team_id or not other_emp.team_id or emp.team_id != other_emp.team_id:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "code": "CROSS_TEAM_CHAT_FORBIDDEN",
                            "message": "Cross-team direct chat is forbidden. Employees can only message teammates in the same team."
                        }
                    )
    return



@router.get("/my-team", response_model=MyTeamChatResponse)
async def get_my_team_chat(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns the canonical Team Chat for the current employee's authorized group.
    Includes:
    - Group Name (e.g. 'Database L2')
    - Canonical Conversation Details
    - Member Count
    - Present Members Count (e.g. 7 Present)
    - Active Shift Name
    - Full list of team colleagues with real presence/shift status
    """
    emp_stmt = select(Employee).where(Employee.user_id == current_user.id)
    emp = (await db.execute(emp_stmt)).scalar_one_or_none()

    if not emp or not emp.team_id:
        if current_user.role in ("ADMIN", "SUPERVISOR"):
            first_team = (await db.execute(select(Team).where(Team.is_active == True).order_by(Team.name.asc()))).scalars().first()
            if not first_team:
                raise HTTPException(status_code=404, detail="No active operational teams found")
            team_id = first_team.id
        else:
            raise HTTPException(status_code=400, detail="Employee has not been assigned to an operational team")
    else:
        team_id = emp.team_id

    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    chat_svc = ChatService(db)
    conv = await chat_svc.get_or_create_team_conversation(team_id)

    # Auto-enroll current employee as member if not already enrolled
    mem_stmt = select(ConversationMember).where(
        ConversationMember.conversation_id == conv.id,
        ConversationMember.user_id == current_user.id
    )
    if not (await db.execute(mem_stmt)).scalar_one_or_none():
        db.add(ConversationMember(conversation_id=conv.id, user_id=current_user.id))
        await db.commit()

    # Get team member stats
    members_list = await chat_svc.get_team_chat_members(current_user, team_id=team_id)
    member_count = len(members_list)
    present_count = sum(
        1 for m in members_list
        if (m.get("is_present") if isinstance(m, dict) else getattr(m, "is_present", False))
    )

    # Find active shift if any member has one
    active_shift_name = next(
        (
            (m.get("current_shift_name") if isinstance(m, dict) else getattr(m, "current_shift_name", None))
            for m in members_list
            if (m.get("current_shift_name") if isinstance(m, dict) else getattr(m, "current_shift_name", None))
        ),
        None
    )

    conv_resp = await _build_conversation_response(db, conv, current_user.id)

    return MyTeamChatResponse(
        team_id=team.id,
        team_name=team.name,
        team_description=team.description,
        conversation_id=conv.id,
        member_count=member_count,
        present_count=present_count,
        active_shift_name=active_shift_name,
        members=members_list,
        conversation=conv_resp
    )



@router.get("/conversations", response_model=list[ConversationResponse])
async def get_user_conversations(
    team_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns conversations list:
    - Admin: can view all conversations or filter by team_id
    - Employee: team chat, incident discussions, and direct messages
    """
    chat_svc = ChatService(db)
    convs = await chat_svc.get_user_conversations(current_user, team_id=team_id)
    results = []
    for c in convs:
        results.append(await _build_conversation_response(db, c, current_user.id))
    return results


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_single_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve single conversation details with authorized members."""
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await _authorize_conversation_access(db, conv, current_user)
    return await _build_conversation_response(db, conv, current_user.id)


@router.get("/groups", response_model=list[TeamChatGroupBrief])
async def get_chat_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List operational groups with their canonical team conversation ID for chatting."""
    chat_svc = ChatService(db)
    teams_stmt = select(Team).where(Team.is_active == True).order_by(Team.name.asc())
    teams = (await db.execute(teams_stmt)).scalars().all()
    results = []
    for t in teams:
        conv = await chat_svc.get_or_create_team_conversation(t.id)
        emp_count_stmt = select(func.count(Employee.id)).where(Employee.team_id == t.id)
        member_count = (await db.execute(emp_count_stmt)).scalar() or 0
        results.append(TeamChatGroupBrief(
            id=t.id,
            name=t.name,
            code=getattr(t, "code", None),
            description=t.description,
            conversation_id=conv.id,
            member_count=member_count
        ))
    return results


@router.get("/team-members", response_model=list[TeamMemberChatBrief])
async def get_team_members(
    team_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns list of team colleagues for chat with presence and shift status.
    Employees see colleagues in their team; Admins see members of specified group or all employees.
    """
    chat_svc = ChatService(db)
    return await chat_svc.get_team_chat_members(current_user, team_id=team_id)


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessageResponse])
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    limit: int = 100,
    before: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve messages for a conversation with RBAC validation."""
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await _authorize_conversation_access(db, conv, current_user)

    chat_svc = ChatService(db)
    messages = await chat_svc.get_messages(conversation_id, limit=limit, before=before)

    results = []
    for m in messages:
        results.append(await _build_message_response(db, m, current_user.id))
    return results


@router.post("/conversations/{conversation_id}/messages", response_model=ChatMessageResponse)
async def post_message_to_conversation(
    conversation_id: uuid.UUID,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Send a message to a conversation. Chat NEVER modifies incident assignments.
    Admin can send messages to ANY group without restriction.
    """
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await _authorize_conversation_access(db, conv, current_user)

    chat_svc = ChatService(db)
    msg = await chat_svc.post_message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=payload.content,
        incident_id=payload.incident_id,
        message_type=payload.message_type or "TEXT",
        reply_to_message_id=payload.reply_to_message_id,
        attachment_id=payload.attachment_id,
        client_message_id=payload.client_message_id,
        metadata_json=payload.metadata_json
    )
    return await _build_message_response(db, msg, current_user.id)


@router.post("/conversations/{conversation_id}/typing")
async def post_typing_indicator(
    conversation_id: uuid.UUID,
    payload: ChatTypingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Broadcasts realtime typing indicator to conversation peers."""
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await _authorize_conversation_access(db, conv, current_user)

    data = {
        "conversation_id": str(conversation_id),
        "user_id": str(current_user.id),
        "user_name": current_user.full_name,
        "is_typing": payload.is_typing
    }
    if conv.team_id:
        await ws_manager.broadcast_to_team(str(conv.team_id), CHAT_TYPING, data)
    else:
        members_stmt = select(ConversationMember.user_id).where(ConversationMember.conversation_id == conversation_id)
        member_ids = (await db.execute(members_stmt)).scalars().all()
        for uid in member_ids:
            if uid != current_user.id:
                await ws_manager.send_to_user(str(uid), CHAT_TYPING, data)
        await ws_manager.broadcast_to_admins(CHAT_TYPING, data)
    return {"status": "ok"}


@router.post("/direct/{target_user_id}", response_model=ConversationResponse)
async def get_or_create_direct(
    target_user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Initiate or retrieve 1-to-1 direct conversation."""
    target_user = await db.get(User, target_user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Group Leader -> Admin rule: ONLY Group Leaders can message Admin. Normal employees are denied with 403 Forbidden.
    if target_user.role in ("ADMIN", "SUPERVISOR") and current_user.role == "EMPLOYEE":
        emp_stmt = select(Employee).where(Employee.user_id == current_user.id)
        emp = (await db.execute(emp_stmt)).scalar_one_or_none()
        if not emp or not emp.is_group_leader:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "ADMIN_CHAT_LEADER_ONLY",
                    "message": "Only the active Group Leader can message Admin.",
                    "detail": "Only Group Leaders are authorized to directly message Administrators. Only the active Group Leader can message Admin."
                }
            )

    # Teammate-only direct chat rule: Employees can only direct chat with active colleagues on the same team.
    if target_user.role == "EMPLOYEE" and current_user.role == "EMPLOYEE":
        emp_curr = (await db.execute(select(Employee).where(Employee.user_id == current_user.id))).scalar_one_or_none()
        emp_target = (await db.execute(select(Employee).where(Employee.user_id == target_user.id))).scalar_one_or_none()
        if not emp_curr or not emp_target or not emp_curr.team_id or not emp_target.team_id or emp_curr.team_id != emp_target.team_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "CROSS_TEAM_CHAT_FORBIDDEN",
                    "message": "Cross-team direct chat is forbidden. Employees can only message teammates in the same team."
                }
            )

    chat_svc = ChatService(db)
    conv = await chat_svc.get_or_create_direct_conversation(current_user.id, target_user_id)
    return await _build_conversation_response(db, conv, current_user.id)


@router.post("/conversations/direct", response_model=ConversationResponse)
async def post_or_create_direct_conversation(
    payload: DirectConversationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Initiate or retrieve 1-to-1 direct conversation with another user."""
    return await get_or_create_direct(payload.other_user_id, db=db, current_user=current_user)


@router.get("/incidents/{incident_id}/conversation", response_model=ConversationResponse)
async def get_incident_conversation(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get or create incident discussion thread."""
    inc = await db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    chat_svc = ChatService(db)
    team_id = None
    if inc.assignment_group:
        t_res = await db.execute(select(Team.id).where(Team.name == inc.assignment_group))
        team_id = t_res.scalar_one_or_none()
    conv = await chat_svc.get_or_create_incident_conversation(incident_id, team_id=team_id)
    return await _build_conversation_response(db, conv, current_user.id)


@router.post("/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    chat_svc = ChatService(db)
    await chat_svc.mark_as_read(conversation_id, current_user.id)
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────
# Attachment Endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/attachments/image", response_model=AttachmentResponse)
async def upload_chat_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image type {file.content_type}. Allowed: JPEG, PNG, WEBP, GIF."
        )
    content = await file.read()
    max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image exceeds max size of {settings.MAX_IMAGE_SIZE_MB}MB"
        )

    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename or "image.png")
    att_id = uuid.uuid4()
    saved_name = f"{att_id.hex}_{clean_name}"
    save_path = os.path.join(IMAGES_DIR, saved_name)
    with open(save_path, "wb") as f:
        f.write(content)

    att = ChatAttachment(
        id=att_id,
        uploaded_by=current_user.id,
        file_name=file.filename or "image.png",
        mime_type=file.content_type,
        file_size=len(content),
        storage_key=save_path,
        status="READY",
        created_at=datetime.now(timezone.utc)
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)

    return AttachmentResponse(
        id=att.id,
        message_id=att.message_id,
        file_name=att.file_name,
        mime_type=att.mime_type,
        file_size=att.file_size,
        storage_key=att.storage_key,
        url=f"/api/chat/attachments/{att.id}/file",
        status=att.status,
        created_at=att.created_at
    )


@router.post("/attachments/audio", response_model=AttachmentResponse)
async def upload_chat_audio(
    file: UploadFile = File(...),
    duration_seconds: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    content_type = file.content_type or "audio/webm"
    if not any(t in content_type.lower() for t in ["audio", "webm", "mp4", "ogg", "wav", "m4a"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid audio format {content_type}."
        )
    content = await file.read()
    max_bytes = settings.MAX_AUDIO_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio file exceeds max size of {settings.MAX_AUDIO_SIZE_MB}MB"
        )

    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename or "voice_message.webm")
    att_id = uuid.uuid4()
    saved_name = f"{att_id.hex}_{clean_name}"
    save_path = os.path.join(AUDIO_DIR, saved_name)
    with open(save_path, "wb") as f:
        f.write(content)

    att = ChatAttachment(
        id=att_id,
        uploaded_by=current_user.id,
        file_name=file.filename or "voice_message.webm",
        mime_type=content_type,
        file_size=len(content),
        storage_key=save_path,
        duration_seconds=duration_seconds,
        status="READY",
        created_at=datetime.now(timezone.utc)
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)

    return AttachmentResponse(
        id=att.id,
        message_id=att.message_id,
        file_name=att.file_name,
        mime_type=att.mime_type,
        file_size=att.file_size,
        storage_key=att.storage_key,
        url=f"/api/chat/attachments/{att.id}/file",
        duration_seconds=att.duration_seconds,
        status=att.status,
        created_at=att.created_at
    )


@router.post("/attachments/video", response_model=AttachmentResponse)
async def upload_chat_video(
    file: UploadFile = File(...),
    duration_seconds: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    content_type = file.content_type or "video/mp4"
    allowed_types = {
        "video/mp4", "video/webm", "video/ogg", "video/quicktime",
        "video/x-matroska", "video/x-msvideo"
    }
    if not (content_type in allowed_types or content_type.startswith("video/")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid video format '{content_type}'. Allowed: MP4, WebM, OGG, QuickTime."
        )
    content = await file.read()
    max_bytes = settings.MAX_VIDEO_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video exceeds maximum allowed size of {settings.MAX_VIDEO_SIZE_MB}MB"
        )

    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename or "video.mp4")
    att_id = uuid.uuid4()
    saved_name = f"{att_id.hex}_{clean_name}"
    save_path = os.path.join(VIDEOS_DIR, saved_name)
    with open(save_path, "wb") as f:
        f.write(content)

    att = ChatAttachment(
        id=att_id,
        uploaded_by=current_user.id,
        file_name=file.filename or "video.mp4",
        mime_type=content_type,
        file_size=len(content),
        storage_key=save_path,
        duration_seconds=duration_seconds,
        status="READY",
        created_at=datetime.now(timezone.utc)
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)

    return AttachmentResponse(
        id=att.id,
        message_id=att.message_id,
        file_name=att.file_name,
        mime_type=att.mime_type,
        file_size=att.file_size,
        storage_key=att.storage_key,
        url=f"/api/chat/attachments/{att.id}/file",
        duration_seconds=att.duration_seconds,
        status=att.status,
        created_at=att.created_at
    )


@router.post("/attachments/document", response_model=AttachmentResponse)
@router.post("/attachments/file", response_model=AttachmentResponse)
async def upload_chat_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    filename = file.filename or "document"
    ext = os.path.splitext(filename)[1].lower()
    allowed_exts = set(settings.ALLOWED_DOCUMENT_EXTENSIONS)
    blocked_exts = {".exe", ".bat", ".cmd", ".sh", ".py", ".js", ".html", ".htm", ".svg", ".php", ".vbs", ".ps1"}

    if ext in blocked_exts or (allowed_exts and ext not in allowed_exts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not permitted. Allowed: {', '.join(sorted(allowed_exts))}"
        )

    content = await file.read()
    max_bytes = settings.MAX_DOCUMENT_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document exceeds maximum allowed size of {settings.MAX_DOCUMENT_SIZE_MB}MB"
        )

    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
    att_id = uuid.uuid4()
    saved_name = f"{att_id.hex}_{clean_name}"
    save_path = os.path.join(DOCS_DIR, saved_name)
    with open(save_path, "wb") as f:
        f.write(content)

    content_type = file.content_type or "application/octet-stream"
    att = ChatAttachment(
        id=att_id,
        uploaded_by=current_user.id,
        file_name=filename,
        mime_type=content_type,
        file_size=len(content),
        storage_key=save_path,
        status="READY",
        created_at=datetime.now(timezone.utc)
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)

    return AttachmentResponse(
        id=att.id,
        message_id=att.message_id,
        file_name=att.file_name,
        mime_type=att.mime_type,
        file_size=att.file_size,
        storage_key=att.storage_key,
        url=f"/api/chat/attachments/{att.id}/file",
        status=att.status,
        created_at=att.created_at
    )


async def _authenticate_media_request(request: Request, token_query: Optional[str], db: AsyncSession) -> User:
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    elif token_query:
        token = token_query.strip()

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required for chat media")

    try:
        payload = verify_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired media token")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    try:
        user_uuid = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token user ID")

    user = await db.get(User, user_uuid)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active or not found")
    return user


@router.get("/attachments/{attachment_id}/file")
async def get_attachment_file(
    attachment_id: uuid.UUID,
    request: Request,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    user = await _authenticate_media_request(request, token, db)

    att = await db.get(ChatAttachment, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Authorization verification
    is_authorized = False
    if user.role in ["ADMIN", "SUPERVISOR"] or att.uploaded_by == user.id:
        is_authorized = True
    elif att.message_id:
        msg = await db.get(ChatMessage, att.message_id)
        if msg:
            conv = await db.get(Conversation, msg.conversation_id)
            if conv:
                if conv.type == "TEAM" and conv.team_id:
                    emp = (await db.execute(
                        select(Employee).where(
                            Employee.user_id == user.id,
                            Employee.team_id == conv.team_id
                        )
                    )).scalar_one_or_none()
                    if emp:
                        is_authorized = True
                else:
                    mem = (await db.execute(
                        select(ConversationMember).where(
                            ConversationMember.conversation_id == conv.id,
                            ConversationMember.user_id == user.id
                        )
                    )).scalar_one_or_none()
                    if mem:
                        is_authorized = True
    else:
        if att.uploaded_by == user.id:
            is_authorized = True

    if not is_authorized:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to conversation media")

    if not os.path.isfile(att.storage_key):
        raise HTTPException(status_code=404, detail="File on disk not found")

    return FileResponse(
        att.storage_key,
        media_type=att.mime_type,
        filename=att.file_name,
        content_disposition_type="inline"
    )


# ─────────────────────────────────────────────────────────────
# Message Reactions Endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/messages/{message_id}/reactions")
async def add_message_reaction(
    message_id: uuid.UUID,
    payload: ReactionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    chat_svc = ChatService(db)
    try:
        return await chat_svc.add_reaction(message_id, current_user, payload.emoji)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/messages/{message_id}/reactions/{emoji}")
async def remove_message_reaction(
    message_id: uuid.UUID,
    emoji: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    chat_svc = ChatService(db)
    try:
        return await chat_svc.remove_reaction(message_id, current_user, emoji)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─────────────────────────────────────────────────────────────
# Edit & Delete Endpoints
# ─────────────────────────────────────────────────────────────

@router.patch("/messages/{message_id}", response_model=ChatMessageResponse)
async def edit_chat_message(
    message_id: uuid.UUID,
    payload: ChatMessageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    chat_svc = ChatService(db)
    try:
        msg = await chat_svc.edit_message(message_id, current_user, payload.content)
        return await _build_message_response(db, msg, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/health")
async def chat_health(db: AsyncSession = Depends(get_db)):
    """Health endpoint for chat system status."""
    db_ok = True
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "websocket": "ok"
    }


@router.get("/search")
async def search_chat_messages(
    q: Optional[str] = None,
    query: Optional[str] = None,
    sender: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    conversation_id: Optional[uuid.UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Search messages across authorized conversations by text, sender name/email, and date range.
    """
    search_term = (q or query or "").strip()
    stmt = (
        select(ChatMessage)
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .order_by(ChatMessage.created_at.desc())
    )

    # Security check: User can only search conversations they are members of (or admin)
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        mem_subq = select(ConversationMember.conversation_id).where(ConversationMember.user_id == current_user.id)
        stmt = stmt.where(ChatMessage.conversation_id.in_(mem_subq))

    if search_term:
        clean_q = f"%{search_term}%"
        stmt = stmt.where(
            or_(
                ChatMessage.content.ilike(clean_q),
                and_(
                    ChatMessage.incident_id.isnot(None),
                    ChatMessage.incident_id.in_(
                        select(Incident.id).where(Incident.incident_number.ilike(clean_q))
                    )
                )
            )
        )

    if conversation_id:
        stmt = stmt.where(ChatMessage.conversation_id == conversation_id)

    if sender:
        sender_q = f"%{sender.strip()}%"
        sender_subq = select(User.id).where(or_(User.full_name.ilike(sender_q), User.email.ilike(sender_q)))
        stmt = stmt.where(ChatMessage.sender_id.in_(sender_subq))

    if start_date:
        try:
            s_dt = datetime.fromisoformat(start_date)
            stmt = stmt.where(ChatMessage.created_at >= s_dt)
        except Exception:
            pass

    if end_date:
        try:
            e_dt = datetime.fromisoformat(end_date)
            stmt = stmt.where(ChatMessage.created_at <= e_dt)
        except Exception:
            pass

    stmt = stmt.limit(50)
    res = await db.execute(stmt)
    messages = res.scalars().all()

    items = []
    for m in messages:
        resp = await _build_message_response(db, m, current_user.id)
        items.append(resp)

    return {
        "query": search_term,
        "count": len(items),
        "results": items
    }


@router.delete("/messages/{message_id}", response_model=ChatMessageResponse)
async def delete_chat_message(
    message_id: uuid.UUID,
    payload: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Soft-deletes a message.
    - Message author can delete own message.
    - Group Leader can delete messages of teammates within their team.
    - Admin/Supervisor can delete any message.
    - Other users receive 403 Forbidden with MESSAGE_DELETE_FORBIDDEN.
    """
    chat_svc = ChatService(db)
    try:
        reason = payload.get("reason") if payload and isinstance(payload, dict) else None
        msg = await chat_svc.delete_message(message_id, current_user, reason=reason)
        return await _build_message_response(db, msg, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "MESSAGE_DELETE_FORBIDDEN", "message": "You do not have permission to delete this message."}
        )


