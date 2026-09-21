import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation, ConversationMember, ChatMessage, MessageRead, MessageReaction, ChatAttachment
from app.models.user import User
from app.models.team import Team
from app.models.employee import Employee
from app.models.incident import Incident
from app.websocket.manager import (
    ws_manager,
    CHAT_MESSAGE_CREATED,
    CHAT_MESSAGE_UPDATED,
    CHAT_MESSAGE_DELETED,
    CHAT_MESSAGE_REACTION_ADDED,
    CHAT_MESSAGE_REACTION_REMOVED
)

INCIDENT_TAG_REGEX = re.compile(r'#(INC\d+)', re.IGNORECASE)

class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_team_conversation(self, team_id: uuid.UUID) -> Conversation:
        """Find or create the canonical TEAM conversation for a group."""
        stmt = (
            select(Conversation)
            .where(Conversation.type == "TEAM", Conversation.team_id == team_id)
            .order_by(Conversation.created_at.asc())
            .options(selectinload(Conversation.members).selectinload(ConversationMember.user))
        )
        res = await self.db.execute(stmt)
        conv = res.scalars().first()
        if not conv:
            team = await self.db.get(Team, team_id)
            team_name = team.name if team else "Team"
            conv = Conversation(
                type="TEAM",
                team_id=team_id,
                title=f"{team_name} Team Chat"
            )
            self.db.add(conv)
            await self.db.flush()

            # Add all current active employees in the team as members
            emp_stmt = select(Employee).where(Employee.team_id == team_id)
            emp_res = await self.db.execute(emp_stmt)
            for emp in emp_res.scalars().all():
                if emp.user_id:
                    self.db.add(ConversationMember(conversation_id=conv.id, user_id=emp.user_id))
            await self.db.commit()

            # Re-fetch with relationships
            res = await self.db.execute(stmt)
            conv = res.scalars().first()

        return conv

    async def get_or_create_admin_team_conversation(self, team_id: uuid.UUID, leader_user_id: Optional[uuid.UUID] = None) -> Conversation:
        """Find or create the canonical ADMIN_TEAM leadership conversation for a group."""
        stmt = (
            select(Conversation)
            .where(Conversation.type == "ADMIN_TEAM", Conversation.team_id == team_id)
            .order_by(Conversation.created_at.asc())
            .options(selectinload(Conversation.members).selectinload(ConversationMember.user))
        )
        res = await self.db.execute(stmt)
        conv = res.scalars().first()

        # If leader_user_id not provided, find the active group leader of this team
        target_leader_uid = leader_user_id
        if not target_leader_uid:
            leader_emp = (await self.db.execute(
                select(Employee).where(
                    Employee.team_id == team_id,
                    Employee.is_group_leader == True
                )
            )).scalar_one_or_none()
            if leader_emp:
                target_leader_uid = leader_emp.user_id

        if not conv:
            team = await self.db.get(Team, team_id)
            team_name = team.name if team else "Team"
            conv = Conversation(
                type="ADMIN_TEAM",
                team_id=team_id,
                title=f"{team_name} - Admin Leadership Chat"
            )
            self.db.add(conv)
            await self.db.flush()

            # Add all active admins as members
            admins = (await self.db.execute(
                select(User).where(User.role.in_(["ADMIN", "SUPERVISOR"]), User.is_active == True)
            )).scalars().all()
            for adm in admins:
                self.db.add(ConversationMember(conversation_id=conv.id, user_id=adm.id))

            # Add leader if found
            if target_leader_uid:
                self.db.add(ConversationMember(conversation_id=conv.id, user_id=target_leader_uid))

            await self.db.commit()

            res = await self.db.execute(stmt)
            conv = res.scalars().first()
        else:
            # If conversation already exists and leader_user_id is provided, ensure membership
            if target_leader_uid:
                mem_stmt = select(ConversationMember).where(
                    ConversationMember.conversation_id == conv.id,
                    ConversationMember.user_id == target_leader_uid
                )
                if not (await self.db.execute(mem_stmt)).scalar_one_or_none():
                    self.db.add(ConversationMember(conversation_id=conv.id, user_id=target_leader_uid))
                    await self.db.commit()
                    res = await self.db.execute(stmt)
                    conv = res.scalars().first()

        return conv

    async def get_or_create_direct_conversation(self, user_1_id: uuid.UUID, user_2_id: uuid.UUID) -> Conversation:
        """Find or create a 1-to-1 direct conversation between two users with canonical direct_pair_key."""
        pair_key = f"{min(str(user_1_id), str(user_2_id))}:{max(str(user_1_id), str(user_2_id))}"

        # 1. First attempt to lookup by canonical direct_pair_key
        stmt = (
            select(Conversation)
            .where(Conversation.type == "DIRECT", Conversation.direct_pair_key == pair_key)
            .options(selectinload(Conversation.members).selectinload(ConversationMember.user))
            .execution_options(populate_existing=True)
        )
        res = await self.db.execute(stmt)
        conv = res.scalars().first()

        # 2. Fallback check for any legacy direct conversation without direct_pair_key
        if not conv:
            stmt_legacy = (
                select(Conversation)
                .join(ConversationMember, Conversation.id == ConversationMember.conversation_id)
                .where(
                    Conversation.type == "DIRECT",
                    ConversationMember.user_id.in_([user_1_id, user_2_id])
                )
                .group_by(Conversation.id)
                .having(func.count(ConversationMember.id) == 2)
                .order_by(Conversation.created_at.asc())
            )
            res_legacy = await self.db.execute(stmt_legacy)
            conv_legacy = res_legacy.scalars().first()
            if conv_legacy:
                conv_legacy.direct_pair_key = pair_key
                await self.db.flush()
                res = await self.db.execute(stmt)
                conv = res.scalars().first()

        # 3. If neither exists, create canonical direct conversation
        if not conv:
            u1 = await self.db.get(User, user_1_id)
            u2 = await self.db.get(User, user_2_id)
            u1_name = u1.full_name if u1 else "User 1"
            u2_name = u2.full_name if u2 else "User 2"
            
            # Find common team if any
            team_id = None
            emp1 = (await self.db.execute(select(Employee).where(Employee.user_id == user_1_id))).scalar_one_or_none()
            emp2 = (await self.db.execute(select(Employee).where(Employee.user_id == user_2_id))).scalar_one_or_none()
            if emp1 and emp2 and emp1.team_id == emp2.team_id:
                team_id = emp1.team_id

            conv = Conversation(
                type="DIRECT",
                direct_pair_key=pair_key,
                team_id=team_id,
                title=f"{u1_name} & {u2_name}"
            )
            self.db.add(conv)
            await self.db.flush()

            self.db.add(ConversationMember(conversation_id=conv.id, user_id=user_1_id))
            self.db.add(ConversationMember(conversation_id=conv.id, user_id=user_2_id))
            await self.db.flush()

        await self.db.commit()
        res = await self.db.execute(stmt)
        return res.scalars().first()

    async def get_or_create_incident_conversation(self, incident_id: uuid.UUID, team_id: Optional[uuid.UUID] = None) -> Conversation:
        """Find or create an INCIDENT discussion thread."""
        stmt = (
            select(Conversation)
            .where(Conversation.type == "INCIDENT", Conversation.incident_id == incident_id)
            .order_by(Conversation.created_at.asc())
            .options(selectinload(Conversation.members).selectinload(ConversationMember.user))
        )
        res = await self.db.execute(stmt)
        conv = res.scalars().first()
        if not conv:
            inc = await self.db.get(Incident, incident_id)
            inc_number = inc.incident_number if inc else "Incident"
            conv = Conversation(
                type="INCIDENT",
                incident_id=incident_id,
                team_id=team_id,
                title=f"Discussion: #{inc_number}"
            )
            self.db.add(conv)
            await self.db.flush()
            await self.db.commit()

            res = await self.db.execute(stmt)
            conv = res.scalars().first()

        return conv

    async def post_message(
        self,
        conversation_id: uuid.UUID,
        sender_id: Optional[uuid.UUID],
        content: str,
        incident_id: Optional[uuid.UUID] = None,
        message_type: str = "TEXT",
        reply_to_message_id: Optional[uuid.UUID] = None,
        attachment_id: Optional[uuid.UUID] = None,
        client_message_id: Optional[str] = None,
        metadata_json: Optional[str] = None
    ) -> ChatMessage:
        """
        Creates and stores a chat message, auto-resolving #INC incident mentions,
        and broadcasting via WebSockets. Chat NEVER modifies incident assignments.
        """
        # Parse incident mention if not explicitly supplied
        resolved_incident_id = incident_id
        if not resolved_incident_id:
            match = INCIDENT_TAG_REGEX.search(content)
            if match:
                inc_num = match.group(1).upper()
                inc_res = await self.db.execute(select(Incident).where(Incident.incident_number == inc_num))
                inc = inc_res.scalar_one_or_none()
                if inc:
                    resolved_incident_id = inc.id

        # Ensure conversation exists
        conv = await self.db.get(Conversation, conversation_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Idempotency: if client_message_id provided, return existing message without duplicate insert
        if client_message_id:
            existing_stmt = select(ChatMessage).where(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.client_message_id == client_message_id
            )
            existing_res = await self.db.execute(existing_stmt)
            existing_msg = existing_res.scalar_one_or_none()
            if existing_msg:
                return existing_msg

        msg = ChatMessage(
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=content.strip(),
            message_type=message_type,
            incident_id=resolved_incident_id,
            reply_to_message_id=reply_to_message_id,
            attachment_id=attachment_id,
            client_message_id=client_message_id,
            metadata_json=metadata_json,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(msg)
        await self.db.flush()

        if attachment_id:
            att = await self.db.get(ChatAttachment, attachment_id)
            if att:
                att.message_id = msg.id

        # Update member last_read for sender
        if sender_id:
            mem_stmt = select(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id == sender_id
            )
            mem_res = await self.db.execute(mem_stmt)
            member = mem_res.scalar_one_or_none()
            if member:
                member.last_read_at = msg.created_at
            else:
                # Add sender to conversation if missing
                self.db.add(ConversationMember(
                    conversation_id=conversation_id,
                    user_id=sender_id,
                    last_read_at=msg.created_at
                ))
            
            # Record read
            self.db.add(MessageRead(message_id=msg.id, user_id=sender_id, read_at=msg.created_at))

        conv.updated_at = msg.created_at
        await self.db.commit()

        # Build payload for WebSocket broadcast
        sender = await self.db.get(User, sender_id) if sender_id else None
        inc = await self.db.get(Incident, resolved_incident_id) if resolved_incident_id else None

        reply_to_data = None
        if reply_to_message_id:
            p_msg = await self.db.get(ChatMessage, reply_to_message_id)
            if p_msg:
                p_sender = await self.db.get(User, p_msg.sender_id) if p_msg.sender_id else None
                reply_to_data = {
                    "id": str(p_msg.id),
                    "sender_id": str(p_msg.sender_id) if p_msg.sender_id else None,
                    "sender_name": p_sender.full_name if p_sender else "System",
                    "content": "This message was deleted" if p_msg.is_deleted else p_msg.content,
                    "message_type": p_msg.message_type,
                    "is_deleted": p_msg.is_deleted
                }

        attachment_data = None
        if attachment_id:
            att = await self.db.get(ChatAttachment, attachment_id)
            if att:
                attachment_data = {
                    "id": str(att.id),
                    "file_name": att.file_name,
                    "mime_type": att.mime_type,
                    "file_size": att.file_size,
                    "url": f"/api/chat/attachments/{att.id}/file",
                    "width": att.width,
                    "height": att.height,
                    "duration_seconds": att.duration_seconds,
                    "status": att.status
                }

        broadcast_data = {
            "id": str(msg.id),
            "conversation_id": str(conv.id),
            "conversation_type": conv.type,
            "team_id": str(conv.team_id) if conv.team_id else None,
            "sender_id": str(sender.id) if sender else None,
            "sender_name": sender.full_name if sender else "System",
            "sender_role": sender.role if sender else "SYSTEM",
            "sender_email": sender.email if sender else None,
            "sender_avatar_url": sender.avatar_url if sender else None,
            "content": msg.content,
            "message_type": msg.message_type,
            "incident_id": str(inc.id) if inc else None,
            "incident_number": inc.incident_number if inc else None,
            "reply_to_message_id": str(reply_to_message_id) if reply_to_message_id else None,
            "reply_to": reply_to_data,
            "attachment_id": str(attachment_id) if attachment_id else None,
            "attachment": attachment_data,
            "reactions": [],
            "user_reactions": [],
            "client_message_id": client_message_id,
            "event_id": str(uuid.uuid4()),
            "notification_eligible_roles": ["EMPLOYEE"],
            "created_at": msg.created_at.isoformat(),
        }

        # Query all member user IDs
        members_stmt = select(ConversationMember.user_id).where(ConversationMember.conversation_id == conversation_id)
        member_uids = set((await self.db.execute(members_stmt)).scalars().all())

        # If team conversation (type TEAM), include all active team employees
        team_uids = set()
        if conv.team_id and conv.type == "TEAM":
            team_emp_stmt = select(Employee.user_id).where(Employee.team_id == conv.team_id)
            team_uids = set((await self.db.execute(team_emp_stmt)).scalars().all())
            member_uids.update(team_uids)

        member_ids = [str(uid) for uid in member_uids if uid]

        if conv.team_id and conv.type == "TEAM":
            await ws_manager.broadcast_to_team(str(conv.team_id), CHAT_MESSAGE_CREATED, broadcast_data, member_ids)
        else:
            for uid in member_ids:
                await ws_manager.send_to_user(uid, CHAT_MESSAGE_CREATED, broadcast_data)
            await ws_manager.broadcast_to_admins(CHAT_MESSAGE_CREATED, broadcast_data)

        # Detect @mentions across all active users
        mentioned_uids = set()
        if "@" in msg.content:
            active_users_stmt = select(User).where(User.is_active == True)
            all_users = (await self.db.execute(active_users_stmt)).scalars().all()
            content_lower = msg.content.lower()
            for u in all_users:
                if sender_id and u.id == sender_id:
                    continue
                first_name = u.full_name.split()[0].lower() if u.full_name else ""
                full_lower = u.full_name.lower() if u.full_name else ""
                email_prefix = u.email.split("@")[0].lower() if u.email else ""
                if (first_name and f"@{first_name}" in content_lower) or \
                   (full_lower and f"@{full_lower}" in content_lower) or \
                   (email_prefix and f"@{email_prefix}" in content_lower):
                    mentioned_uids.add(u.id)

        all_target_uids = (member_uids | mentioned_uids)
        if sender_id:
            all_target_uids.discard(sender_id)

        # Create actionable in-app notifications for conversation members & mentioned users
        try:
            from app.services.notification_service import NotificationService
            notif_svc = NotificationService(self.db)
            sender_full_name = sender.full_name if sender else "Colleague"
            team_obj = await self.db.get(Team, conv.team_id) if conv.team_id else None
            team_name = team_obj.name if team_obj else (conv.title or "Team")

            for recip_uid in all_target_uids:
                if not recip_uid:
                    continue
                user_recip = await self.db.get(User, recip_uid)
                if not user_recip:
                    continue

                is_mentioned = recip_uid in mentioned_uids

                if is_mentioned:
                    notif_type = "MENTION"
                    notif_title = f"💬 {sender_full_name} mentioned you"
                    notif_message = msg.content
                elif conv.type == "DIRECT":
                    notif_type = "DIRECT_MESSAGE"
                    notif_title = f"💬 {sender_full_name}"
                    notif_message = msg.content
                elif conv.type == "TEAM":
                    notif_type = "TEAM_CHAT_MESSAGE"
                    notif_title = f"💬 {team_name} Chat"
                    notif_message = f"{sender_full_name}: {msg.content}"
                elif conv.type == "INCIDENT":
                    inc_label = inc.incident_number if inc else "Incident"
                    notif_type = "INCIDENT_CHAT_MESSAGE"
                    notif_title = f"💬 Incident Discussion — {inc_label}"
                    notif_message = f"{sender_full_name}: {msg.content}"
                else:
                    notif_type = "CHAT_MESSAGE"
                    notif_title = f"💬 Message from {sender_full_name}"
                    notif_message = msg.content

                await notif_svc.create_notification(
                    user_id=recip_uid,
                    type=notif_type,
                    title=notif_title,
                    message=notif_message,
                    incident_id=resolved_incident_id,
                    incident=inc,
                    conversation_id=conversation_id,
                    message_id=msg.id,
                    team_id=conv.team_id,
                    sender_id=sender_id,
                    sender_name=sender_full_name,
                    broadcast_ws=True
                )
            await self.db.commit()
        except Exception as ex:
            import structlog
            structlog.get_logger().error("Failed to dispatch chat notifications", error=str(ex), exc_info=True)

        return msg


    async def get_messages(self, conversation_id: uuid.UUID, limit: int = 50, before: Optional[datetime] = None) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
        )
        if before:
            stmt = stmt.where(ChatMessage.created_at < before)
        stmt = stmt.order_by(ChatMessage.created_at.desc()).limit(limit)
        res = await self.db.execute(stmt)
        msgs = list(res.scalars().all())
        msgs.reverse()
        return msgs

    async def search_messages(self, query: str, team_id: Optional[uuid.UUID] = None) -> list[ChatMessage]:
        clean_q = f"%{query.strip()}%"
        stmt = (
            select(ChatMessage)
            .join(Conversation, ChatMessage.conversation_id == Conversation.id)
            .where(
                or_(
                    ChatMessage.content.ilike(clean_q),
                    and_(
                        ChatMessage.incident_id != None,
                        ChatMessage.incident_id.in_(
                            select(Incident.id).where(Incident.incident_number.ilike(clean_q))
                        )
                    )
                )
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(50)
        )
        if team_id:
            stmt = stmt.where(Conversation.team_id == team_id)

        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def mark_as_read(self, conversation_id: uuid.UUID, user_id: uuid.UUID):
        now = datetime.now(timezone.utc)
        mem_stmt = select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id
        )
        mem = (await self.db.execute(mem_stmt)).scalar_one_or_none()
        if mem:
            mem.last_read_at = now
    async def add_reaction(self, message_id: uuid.UUID, user: User, emoji: str) -> dict:
        msg = await self.db.get(ChatMessage, message_id)
        if not msg:
            raise ValueError("Message not found")
        
        stmt = select(MessageReaction).where(
            MessageReaction.message_id == message_id,
            MessageReaction.user_id == user.id,
            MessageReaction.emoji == emoji
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if not existing:
            reaction = MessageReaction(
                message_id=message_id,
                user_id=user.id,
                emoji=emoji,
                created_at=datetime.now(timezone.utc)
            )
            self.db.add(reaction)
            await self.db.commit()

        conv = await self.db.get(Conversation, msg.conversation_id)
        event_payload = {
            "message_id": str(message_id),
            "conversation_id": str(msg.conversation_id),
            "user_id": str(user.id),
            "user_name": user.full_name,
            "emoji": emoji,
            "action": "ADD"
        }
        if conv and conv.team_id:
            await ws_manager.broadcast_to_team(str(conv.team_id), CHAT_MESSAGE_REACTION_ADDED, event_payload)
        else:
            await ws_manager.broadcast_to_admins(CHAT_MESSAGE_REACTION_ADDED, event_payload)
        return {"status": "success", "emoji": emoji, "action": "ADD"}

    async def remove_reaction(self, message_id: uuid.UUID, user: User, emoji: str) -> dict:
        msg = await self.db.get(ChatMessage, message_id)
        if not msg:
            raise ValueError("Message not found")
        
        stmt = select(MessageReaction).where(
            MessageReaction.message_id == message_id,
            MessageReaction.user_id == user.id,
            MessageReaction.emoji == emoji
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            await self.db.delete(existing)
            await self.db.commit()

        conv = await self.db.get(Conversation, msg.conversation_id)
        event_payload = {
            "message_id": str(message_id),
            "conversation_id": str(msg.conversation_id),
            "user_id": str(user.id),
            "user_name": user.full_name,
            "emoji": emoji,
            "action": "REMOVE"
        }
        if conv and conv.team_id:
            await ws_manager.broadcast_to_team(str(conv.team_id), CHAT_MESSAGE_REACTION_REMOVED, event_payload)
        else:
            await ws_manager.broadcast_to_admins(CHAT_MESSAGE_REACTION_REMOVED, event_payload)
        return {"status": "success", "emoji": emoji, "action": "REMOVE"}

    async def edit_message(self, message_id: uuid.UUID, user: User, new_content: str) -> ChatMessage:
        msg = await self.db.get(ChatMessage, message_id)
        if not msg:
            raise ValueError("Message not found")
        if user.role not in ("ADMIN", "SUPERVISOR") and msg.sender_id != user.id:
            raise PermissionError("Not authorized to edit this message")
        
        msg.content = new_content.strip()
        msg.is_edited = True
        msg.edited_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(msg)

        conv = await self.db.get(Conversation, msg.conversation_id)
        payload = {
            "id": str(msg.id),
            "conversation_id": str(msg.conversation_id),
            "content": msg.content,
            "is_edited": True,
            "edited_at": msg.edited_at.isoformat()
        }
        if conv and conv.team_id:
            await ws_manager.broadcast_to_team(str(conv.team_id), CHAT_MESSAGE_UPDATED, payload)
        else:
            await ws_manager.broadcast_to_admins(CHAT_MESSAGE_UPDATED, payload)
        return msg

    async def delete_message(self, message_id: uuid.UUID, user: User, reason: Optional[str] = None) -> ChatMessage:
        msg = await self.db.get(ChatMessage, message_id)
        if not msg:
            raise ValueError("Message not found")

        conv = await self.db.get(Conversation, msg.conversation_id)

        # Check permissions:
        # 1. Author can delete own message
        # 2. Admin / Supervisor can delete any message
        # 3. Group Leader of the conversation's team can delete peer messages
        is_author = (msg.sender_id == user.id)
        is_admin = (user.role in ("ADMIN", "SUPERVISOR"))
        is_group_leader = False

        if not (is_author or is_admin) and conv and conv.team_id:
            emp_stmt = select(Employee).where(
                Employee.user_id == user.id,
                Employee.team_id == conv.team_id
            )
            emp = (await self.db.execute(emp_stmt)).scalar_one_or_none()
            if emp and emp.is_group_leader:
                is_group_leader = True

        if not (is_author or is_admin or is_group_leader):
            raise PermissionError("MESSAGE_DELETE_FORBIDDEN")

        is_moderation = not is_author
        msg.is_deleted = True
        msg.deleted_at = datetime.now(timezone.utc)
        msg.deleted_by = user.id
        msg.delete_reason = reason or ("Removed by Group Leader" if is_group_leader else ("Removed by Admin" if is_admin else "Deleted by user"))
        
        if is_moderation:
            msg.content = "This message was removed by a Group Leader"
            # Audit log MESSAGE_MODERATED
            try:
                from app.services.audit_service import AuditService
                audit_svc = AuditService(self.db)
                await audit_svc.log(
                    action="MESSAGE_MODERATED",
                    entity_type="CHAT_MESSAGE",
                    entity_id=msg.id,
                    actor_id=user.id,
                    new_value={
                        "conversation_id": str(msg.conversation_id),
                        "original_sender_id": str(msg.sender_id) if msg.sender_id else None,
                        "moderator_id": str(user.id),
                        "moderator_name": user.full_name,
                        "reason": msg.delete_reason
                    },
                    reason=msg.delete_reason
                )
            except Exception as ex:
                import structlog
                structlog.get_logger().error("message_moderated_audit_failed", error=str(ex))
        else:
            msg.content = "This message was deleted"

        await self.db.commit()
        await self.db.refresh(msg)

        payload = {
            "id": str(msg.id),
            "conversation_id": str(msg.conversation_id),
            "content": msg.content,
            "is_deleted": True,
            "deleted_at": msg.deleted_at.isoformat(),
            "deleted_by": str(user.id),
            "delete_reason": msg.delete_reason,
            "is_moderated": is_moderation
        }
        if conv and conv.team_id:
            await ws_manager.broadcast_to_team(str(conv.team_id), CHAT_MESSAGE_DELETED, payload)
        else:
            await ws_manager.broadcast_to_admins(CHAT_MESSAGE_DELETED, payload)
        return msg

    async def create_group_conversation(self, title: str, creator_id: uuid.UUID, member_ids: list[uuid.UUID]) -> Conversation:
        conv = Conversation(
            type="GROUP",
            title=title,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(conv)
        await self.db.flush()

        all_members = set(member_ids) | {creator_id}
        for uid in all_members:
            self.db.add(ConversationMember(
                conversation_id=conv.id,
                user_id=uid,
                joined_at=datetime.now(timezone.utc)
            ))
        await self.db.commit()
        await self.db.refresh(conv)
        return conv

    async def get_user_conversations(
        self,
        user: User,
        team_id: Optional[uuid.UUID] = None
    ) -> list[Conversation]:
        """
        Retrieves all conversations accessible to the user:
        - ADMIN: can view and read ANY conversation across all groups, incident threads, and direct chats.
        - EMPLOYEE: can view their team conversation, relevant incident threads, teammate direct chats,
          and (if Group Leader) the canonical ADMIN_TEAM leadership conversation and Admin direct chats.
        """
        if user.role in ("ADMIN", "SUPERVISOR"):
            if team_id:
                await self.get_or_create_team_conversation(team_id)
                await self.get_or_create_admin_team_conversation(team_id)
            else:
                teams = (await self.db.execute(select(Team).where(Team.is_active == True))).scalars().all()
                for t in teams:
                    await self.get_or_create_team_conversation(t.id)
                    await self.get_or_create_admin_team_conversation(t.id)

            stmt = (
                select(Conversation)
                .options(
                    selectinload(Conversation.members).selectinload(ConversationMember.user),
                    selectinload(Conversation.team),
                    selectinload(Conversation.incident)
                )
                .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
            )
            if team_id:
                stmt = stmt.where(Conversation.team_id == team_id)
            res = await self.db.execute(stmt)
            return list(res.scalars().all())

        # For EMPLOYEE:
        emp = (await self.db.execute(select(Employee).where(Employee.user_id == user.id))).scalar_one_or_none()
        if not emp or not emp.team_id:
            return []

        # Auto-enroll in team conversation
        team_conv = await self.get_or_create_team_conversation(emp.team_id)
        mem_stmt = select(ConversationMember).where(
            ConversationMember.conversation_id == team_conv.id,
            ConversationMember.user_id == user.id
        )
        if not (await self.db.execute(mem_stmt)).scalar_one_or_none():
            self.db.add(ConversationMember(conversation_id=team_conv.id, user_id=user.id))
            await self.db.commit()

        # If group leader, ensure enrolled in canonical ADMIN_TEAM conversation
        if emp.is_group_leader:
            await self.get_or_create_admin_team_conversation(emp.team_id, leader_user_id=user.id)

        conds = [
            Conversation.id.in_(
                select(ConversationMember.conversation_id).where(ConversationMember.user_id == user.id)
            ),
            and_(Conversation.type == "TEAM", Conversation.team_id == emp.team_id)
        ]

        stmt = (
            select(Conversation)
            .where(or_(*conds))
            .options(
                selectinload(Conversation.members).selectinload(ConversationMember.user),
                selectinload(Conversation.team),
                selectinload(Conversation.incident)
            )
            .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
        )
        if team_id:
            stmt = stmt.where(Conversation.team_id == team_id)

        all_convs = (await self.db.execute(stmt)).scalars().all()

        # Filter out unauthorized conversations:
        # - ADMIN_TEAM: only for active group leaders of that team
        # - DIRECT: other user must be in same team, or if other user is admin, current user must be active group leader
        filtered_convs = []
        for c in all_convs:
            if c.type == "ADMIN_TEAM":
                if emp.is_group_leader and c.team_id == emp.team_id:
                    filtered_convs.append(c)
                continue

            if c.type == "DIRECT":
                # Find other member
                other_mem = next((m for m in c.members if m.user_id != user.id), None)
                if not other_mem:
                    om_res = await self.db.execute(select(ConversationMember).where(
                        ConversationMember.conversation_id == c.id,
                        ConversationMember.user_id != user.id
                    ))
                    other_mem = om_res.scalars().first()

                if other_mem:
                    other_u = await self.db.get(User, other_mem.user_id)
                    if other_u:
                        if other_u.role in ("ADMIN", "SUPERVISOR"):
                            # Only active group leaders can have direct chat with Admin
                            if emp.is_group_leader:
                                filtered_convs.append(c)
                            continue
                        elif other_u.role == "EMPLOYEE":
                            # Teammates must be in the same team
                            other_emp = (await self.db.execute(select(Employee).where(Employee.user_id == other_u.id))).scalar_one_or_none()
                            if other_emp and other_emp.team_id == emp.team_id:
                                filtered_convs.append(c)
                            continue
                continue

            if c.type == "TEAM":
                if c.team_id == emp.team_id:
                    filtered_convs.append(c)
                continue

            if c.type == "INCIDENT":
                filtered_convs.append(c)
                continue

            filtered_convs.append(c)

        return filtered_convs

    async def get_team_chat_members(
        self,
        user: User,
        team_id: Optional[uuid.UUID] = None
    ) -> list[dict]:
        """
        Returns list of team colleagues for chatting and presence display.
        For EMPLOYEE: returns members in employee's team (and Administrators if Group Leader).
        For ADMIN: returns members in specified team or all active employees.
        """
        target_team_id = team_id
        if user.role not in ("ADMIN", "SUPERVISOR") or not target_team_id:
            if user.role not in ("ADMIN", "SUPERVISOR"):
                emp = (await self.db.execute(select(Employee).where(Employee.user_id == user.id))).scalar_one_or_none()
                target_team_id = emp.team_id if emp else None

        stmt = (
            select(Employee)
            .join(User, Employee.user_id == User.id)
            .where(User.is_active == True, User.role == "EMPLOYEE")
        )
        if target_team_id:
            stmt = stmt.where(Employee.team_id == target_team_id)

        emp_list = (await self.db.execute(stmt)).scalars().all()

        from zoneinfo import ZoneInfo
        from app.core.config import settings
        from app.services.shift_service import ShiftService
        from app.models.shift import ShiftAssignment
        now = datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE))
        shift_svc = ShiftService(self.db)
        active_shift = await shift_svc.get_active_shift(now)
        active_shift_name = active_shift.name if active_shift else None
        active_shift_id = active_shift.id if active_shift else None

        assigned_emp_ids = set()
        if active_shift_id:
            sa_res = await self.db.execute(
                select(ShiftAssignment.employee_id).where(
                    ShiftAssignment.shift_id == active_shift_id,
                    ShiftAssignment.date == now.date(),
                    ShiftAssignment.is_active == True
                )
            )
            assigned_emp_ids = set(sa_res.scalars().all())

        results = []

        # If user is a Group Leader or Admin, include Administrators so Group Leader can DM them directly
        is_gl = False
        if user.role == "EMPLOYEE":
            curr_emp = (await self.db.execute(select(Employee).where(Employee.user_id == user.id))).scalar_one_or_none()
            is_gl = bool(curr_emp and curr_emp.is_group_leader)

        if user.role in ("ADMIN", "SUPERVISOR") or is_gl:
            admin_users = (await self.db.execute(
                select(User).where(User.role.in_(["ADMIN", "SUPERVISOR"]), User.is_active == True)
            )).scalars().all()
            for adm in admin_users:
                if adm.id != user.id:
                    results.append({
                        "user_id": adm.id,
                        "employee_id": adm.id,
                        "full_name": adm.full_name,
                        "email": adm.email,
                        "employee_code": "ADMIN",
                        "role": adm.role,
                        "is_group_leader": False,
                        "avatar_url": adm.avatar_url,
                        "is_present": True,
                        "availability_status": "AVAILABLE",
                        "on_shift": True,
                        "current_shift_name": "Management",
                    })

        for emp in emp_list:
            u = await self.db.get(User, emp.user_id) if emp.user_id else None
            if not u:
                continue
            on_shift = emp.id in assigned_emp_ids
            results.append({
                "user_id": u.id,
                "employee_id": emp.id,
                "full_name": u.full_name,
                "email": u.email,
                "employee_code": getattr(emp, "employee_code", None),
                "role": u.role,
                "is_group_leader": getattr(emp, "is_group_leader", False),
                "avatar_url": getattr(u, "avatar_url", None),
                "is_present": emp.is_present,
                "availability_status": emp.availability_status,
                "on_shift": on_shift,
                "current_shift_name": active_shift_name if on_shift else None,
            })
        return results


