import uuid
from typing import Optional, List, Dict, Any
import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc, func
from app.models.notification import Notification
from app.models.user import User
from app.models.incident import Incident
from app.core.config import settings
from app.websocket.manager import ws_manager, NOTIFICATION_CREATED, NOTIFICATION_READ
from app.core.metrics import metrics

logger = structlog.get_logger()


def build_notification_actions(notif: Notification, incident_number: Optional[str] = None) -> List[Dict[str, str]]:
    """Builds deterministic, actionable button targets based on notification type and context."""
    actions = []
    ntype = notif.type.upper() if notif.type else ""

    if ntype in ("CHAT_MESSAGE", "DIRECT_MESSAGE"):
        conv_q = f"conversation={notif.conversation_id}" if notif.conversation_id else ""
        msg_q = f"&message={notif.message_id}" if notif.message_id else ""
        reply_url = f"/team-chat?{conv_q}{msg_q}" if conv_q else "/team-chat"
        actions.append({"label": "Reply", "action": "REPLY", "url": reply_url, "variant": "default"})
        actions.append({"label": "View Chat", "action": "VIEW", "url": reply_url, "variant": "outline"})

    elif ntype == "TEAM_CHAT_MESSAGE":
        conv_q = f"conversation={notif.conversation_id}" if notif.conversation_id else ""
        msg_q = f"&message={notif.message_id}" if notif.message_id else ""
        reply_url = f"/team-chat?{conv_q}{msg_q}" if conv_q else "/team-chat"
        view_url = f"/team-chat?{conv_q}" if conv_q else "/team-chat"
        actions.append({"label": "Reply", "action": "REPLY", "url": reply_url, "variant": "default"})
        actions.append({"label": "View Team Chat", "action": "VIEW", "url": view_url, "variant": "outline"})

    elif ntype in ("GROUP_CHAT_MESSAGE", "INCIDENT_CHAT_MESSAGE"):
        inc_url = f"/incidents/{notif.incident_id}" if notif.incident_id else "/my-work"
        chat_url = f"/incidents/{notif.incident_id}?tab=chat" if notif.incident_id else f"/team-chat?conversation={notif.conversation_id}"
        actions.append({"label": "Reply", "action": "REPLY", "url": chat_url, "variant": "default"})
        actions.append({"label": "View Incident Chat", "action": "VIEW", "url": chat_url, "variant": "outline"})
        if notif.incident_id:
            actions.append({"label": "Open Incident", "action": "OPEN_INCIDENT", "url": inc_url, "variant": "secondary"})

    elif ntype in ("INCIDENT_ASSIGNED", "TASK_ASSIGNED", "INCIDENT_REASSIGNED"):
        work_url = f"/my-work" + (f"?incident={incident_number}" if incident_number else "")
        inc_url = f"/incidents/{notif.incident_id}" if notif.incident_id else "/my-work"
        actions.append({"label": "View Work", "action": "VIEW_WORK", "url": work_url, "variant": "default"})
        if notif.incident_id:
            actions.append({"label": "Open Incident", "action": "OPEN_INCIDENT", "url": inc_url, "variant": "outline"})

    elif ntype in ("GROUP_NOTICE", "NEW_INCIDENT"):
        inc_url = f"/incidents/{notif.incident_id}" if notif.incident_id else "/my-work"
        team_url = f"/admin/groups/{notif.team_id}/activity" if notif.team_id else "/my-shift"
        actions.append({"label": "View Incident", "action": "OPEN_INCIDENT", "url": inc_url, "variant": "default"})
        actions.append({"label": "View Group", "action": "VIEW_GROUP", "url": team_url, "variant": "outline"})

    elif ntype == "MENTION":
        conv_q = f"conversation={notif.conversation_id}" if notif.conversation_id else ""
        msg_q = f"&message={notif.message_id}" if notif.message_id else ""
        url = f"/team-chat?{conv_q}{msg_q}" if conv_q else "/team-chat"
        actions.append({"label": "Reply", "action": "REPLY", "url": url, "variant": "default"})
        actions.append({"label": "View Message", "action": "VIEW", "url": url, "variant": "outline"})

    elif notif.action_url:
        actions.append({"label": notif.action_type or "View", "action": notif.action_type or "VIEW", "url": notif.action_url, "variant": "default"})

    return actions


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(
        self,
        user_id: uuid.UUID,
        type: str,
        title: str,
        message: str,
        incident_id: Optional[uuid.UUID] = None,
        # Optional rich incident data for email body
        incident=None,
        assigned_to_name: Optional[str] = None,
        assigned_at: Optional[datetime] = None,
        # Actionable metadata
        conversation_id: Optional[uuid.UUID] = None,
        message_id: Optional[uuid.UUID] = None,
        assignment_id: Optional[uuid.UUID] = None,
        team_id: Optional[uuid.UUID] = None,
        sender_id: Optional[uuid.UUID] = None,
        sender_name: Optional[str] = None,
        action_url: Optional[str] = None,
        action_type: Optional[str] = None,
        extra_data: Optional[dict] = None,
        broadcast_ws: bool = True,
    ) -> Notification:
        """
        Create an in-app actionable notification (always) and send email (if configured).
        Broadcasts realtime event to recipient user immediately.
        """
        resolved_inc_id = incident_id or (getattr(incident, "id", None) if incident else None)
        resolved_inc_num = getattr(incident, "incident_number", None) if incident else None

        # Determine default action URL if not provided
        computed_action_url = action_url
        if not computed_action_url:
            if conversation_id:
                computed_action_url = f"/team-chat?conversation={conversation_id}" + (f"&message={message_id}" if message_id else "")
            elif resolved_inc_id:
                if type in ("INCIDENT_ASSIGNED", "TASK_ASSIGNED"):
                    computed_action_url = "/my-work"
                else:
                    computed_action_url = f"/incidents/{resolved_inc_id}"

        # Deduplication check for assignment-linked notifications
        if assignment_id:
            dup_stmt = select(Notification).where(
                Notification.assignment_id == assignment_id,
                Notification.user_id == user_id,
                Notification.type == type
            )
            dup_res = await self.db.execute(dup_stmt)
            existing_notif = dup_res.scalar_one_or_none()
            if existing_notif:
                logger.info("notification_deduplicated", assignment_id=str(assignment_id), user_id=str(user_id), type=type)
                return existing_notif

        notif = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            incident_id=resolved_inc_id,
            conversation_id=conversation_id,
            message_id=message_id,
            assignment_id=assignment_id,
            team_id=team_id,
            sender_id=sender_id,
            sender_name=sender_name,
            action_url=computed_action_url,
            action_type=action_type or ("REPLY" if conversation_id else "VIEW"),
            extra_data=extra_data,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(notif)
        try:
            await self.db.flush()
        except Exception:
            # If concurrent insert triggered unique constraint, return existing
            if assignment_id:
                dup_stmt = select(Notification).where(
                    Notification.assignment_id == assignment_id,
                    Notification.user_id == user_id,
                    Notification.type == type
                )
                dup_res = await self.db.execute(dup_stmt)
                existing_notif = dup_res.scalar_one_or_none()
                if existing_notif:
                    return existing_notif
            raise

        metrics.inc("notification_delivery")

        # Broadcast realtime notification event to user
        if broadcast_ws:
            actions_list = build_notification_actions(notif, resolved_inc_num)
            ws_packet = {
                "id": str(notif.id),
                "notification_id": str(notif.id),
                "type": notif.type,
                "title": notif.title,
                "message": notif.message,
                "incident_id": str(notif.incident_id) if notif.incident_id else None,
                "incident_number": resolved_inc_num,
                "conversation_id": str(notif.conversation_id) if notif.conversation_id else None,
                "message_id": str(notif.message_id) if notif.message_id else None,
                "assignment_id": str(notif.assignment_id) if notif.assignment_id else None,
                "team_id": str(notif.team_id) if notif.team_id else None,
                "sender_id": str(notif.sender_id) if notif.sender_id else None,
                "sender_name": notif.sender_name,
                "action_url": notif.action_url,
                "action_type": notif.action_type,
                "actions": actions_list,
                "extra_data": notif.extra_data,
                "is_read": False,
                "created_at": notif.created_at.isoformat(),
                "timestamp": notif.created_at.isoformat(),
            }
            await ws_manager.send_to_user(str(user_id), NOTIFICATION_CREATED, ws_packet)

        # Email delivery — never raises
        await self._send_email_notification(
            user_id=user_id,
            title=title,
            message=message,
            incident=incident,
            incident_id=resolved_inc_id,
            assigned_to_name=assigned_to_name,
            assigned_at=assigned_at,
        )
        return notif

    async def _send_email_notification(
        self,
        user_id: uuid.UUID,
        title: str,
        message: str,
        incident=None,
        incident_id: uuid.UUID = None,
        assigned_to_name: str = None,
        assigned_at: datetime = None,
    ):
        """Resolve recipient and delegate to EmailService. Never raises."""
        try:
            result = await self.db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user or not user.email:
                logger.warning("email_skipped_no_user", user_id=str(user_id))
                return

            recipient_email = user.email
            recipient_name = user.full_name or recipient_email

            from app.services.email_service import EmailService
            email_svc = EmailService(self.db)

            if incident is not None:
                # Rich incident-aware email
                await email_svc.send_assignment_email(
                    recipient_email=recipient_email,
                    recipient_name=recipient_name,
                    incident_number=getattr(incident, "incident_number", "UNKNOWN"),
                    short_description=getattr(incident, "short_description", message),
                    priority=getattr(incident, "priority", "P4"),
                    assignment_group=getattr(incident, "assignment_group", "—"),
                    assigned_to=assigned_to_name or getattr(incident, "assigned_to", recipient_name),
                    work_instructions=getattr(incident, "work_instructions", None),
                    assigned_at=assigned_at or datetime.now(timezone.utc),
                    incident_id=incident_id,
                )
            else:
                # Fallback: plain notification email
                await email_svc.send_assignment_email(
                    recipient_email=recipient_email,
                    recipient_name=recipient_name,
                    incident_number="—",
                    short_description=message,
                    priority="—",
                    assignment_group="—",
                    assigned_to=recipient_name,
                    work_instructions=None,
                    assigned_at=assigned_at or datetime.now(timezone.utc),
                    incident_id=incident_id,
                )
        except Exception as exc:
            metrics.inc("notification_failures")
            logger.error(
                "email_notification_dispatch_error",
                user_id=str(user_id),
                error=str(exc),
            )

    async def get_user_notifications(self, user_id: uuid.UUID, limit: int = 50) -> tuple[list[dict], int]:
        """Returns actionable notifications for user with incident details and actions."""
        stmt = (
            select(Notification, Incident)
            .outerjoin(Incident, Notification.incident_id == Incident.id)
            .where(Notification.user_id == user_id)
            .order_by(desc(Notification.created_at))
            .limit(limit)
        )
        res = await self.db.execute(stmt)

        results = []
        for notif, inc in res.all():
            inc_num = inc.incident_number if inc else None
            prio = inc.priority if inc else None
            actions = build_notification_actions(notif, inc_num)

            notif_dict = {
                "id": notif.id,
                "type": notif.type,
                "title": notif.title,
                "message": notif.message,
                "incident_id": notif.incident_id,
                "incident_number": inc_num,
                "conversation_id": notif.conversation_id,
                "message_id": notif.message_id,
                "assignment_id": notif.assignment_id,
                "team_id": notif.team_id,
                "sender_id": notif.sender_id,
                "sender_name": notif.sender_name,
                "action_url": notif.action_url,
                "action_type": notif.action_type,
                "actions": actions,
                "extra_data": notif.extra_data,
                "is_read": notif.is_read,
                "read_at": notif.read_at,
                "created_at": notif.created_at,
                "priority": prio,
            }
            results.append(notif_dict)

        unread_count_res = await self.db.execute(
            select(func.count(Notification.id))
            .where(Notification.user_id == user_id, Notification.is_read == False)
        )
        unread_count = unread_count_res.scalar() or 0
        return results, unread_count

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID):
        now = datetime.now(timezone.utc)
        await self.db.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(is_read=True, read_at=now)
        )
        await self.db.flush()

        await ws_manager.send_to_user(str(user_id), NOTIFICATION_READ, {
            "notification_id": str(notification_id),
            "user_id": str(user_id),
            "read_at": now.isoformat(),
            "timestamp": now.isoformat()
        })

    async def mark_all_read(self, user_id: uuid.UUID):
        now = datetime.now(timezone.utc)
        await self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id)
            .values(is_read=True, read_at=now)
        )
        await self.db.flush()

        await ws_manager.send_to_user(str(user_id), NOTIFICATION_READ, {
            "all": True,
            "user_id": str(user_id),
            "read_at": now.isoformat(),
            "timestamp": now.isoformat()
        })

