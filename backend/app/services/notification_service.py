import uuid
import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc, func
from app.models.notification import Notification
from app.models.user import User
from app.core.config import settings

logger = structlog.get_logger()

class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(self, user_id: uuid.UUID, type: str, title: str, message: str, incident_id: uuid.UUID = None) -> Notification:
        notif = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            incident_id=incident_id
        )
        self.db.add(notif)
        await self.db.flush()

        # Send email via configured provider
        await self._send_email_notification(user_id, title, message)
        return notif

    async def _send_email_notification(self, user_id: uuid.UUID, title: str, message: str):
        # Lookup recipient user email
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.email:
            logger.warn("email_skipped_no_user", user_id=str(user_id))
            return

        recipient_email = user.email

        if settings.EMAIL_PROVIDER == "MOCK":
            logger.info(
                "mock_email_dispatched",
                recipient=recipient_email,
                subject=title,
                body=message[:100]
            )
            return

        if settings.EMAIL_PROVIDER == "SMTP" and settings.SMTP_USER and settings.SMTP_PASSWORD:
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart

                msg = MIMEMultipart()
                msg["From"] = settings.SMTP_FROM
                msg["To"] = recipient_email
                msg["Subject"] = f"[IncidentFlow] {title}"
                msg.attach(MIMEText(message, "plain"))

                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                    if settings.SMTP_TLS:
                        server.starttls()
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.send_message(msg)
                logger.info("smtp_email_sent_successfully", recipient=recipient_email)
            except Exception as e:
                logger.error("smtp_email_delivery_failed", recipient=recipient_email, error=str(e))

    async def get_user_notifications(self, user_id: uuid.UUID, limit: int = 50) -> tuple[list[Notification], int]:
        result = await self.db.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(desc(Notification.created_at))
            .limit(limit)
        )
        notifs = list(result.scalars().all())

        unread_count_res = await self.db.execute(
            select(func.count(Notification.id))
            .where(Notification.user_id == user_id, Notification.is_read == False)
        )
        unread_count = unread_count_res.scalar() or 0
        return notifs, unread_count

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID):
        await self.db.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(is_read=True)
        )
        await self.db.flush()

    async def mark_all_read(self, user_id: uuid.UUID):
        await self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id)
            .values(is_read=True)
        )
        await self.db.flush()
