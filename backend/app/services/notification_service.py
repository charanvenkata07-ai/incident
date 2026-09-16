from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notification import Notification

class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(self, user_id, type, title, message, incident_id=None) -> Notification:
        notif = Notification(user_id=user_id, type=type, title=title, message=message, incident_id=incident_id)
        self.db.add(notif)
        await self.db.flush()
        return notif

    async def get_user_notifications(self, user_id, limit=50) -> tuple[list[Notification], int]:
        return [], 0

    async def mark_read(self, notification_id, user_id):
        pass

    async def mark_all_read(self, user_id):
        pass
