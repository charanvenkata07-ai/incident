from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLog

class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(self, action, entity_type, entity_id=None, old_value=None, new_value=None, reason=None, actor_id=None):
        audit = AuditLog(
            action=action, entity_type=entity_type, entity_id=entity_id, 
            old_value=old_value, new_value=new_value, reason=reason, actor_id=actor_id
        )
        self.db.add(audit)
        await self.db.flush()

    async def get_logs(self, filters, page, per_page) -> tuple[list[AuditLog], int]:
        return [], 0

    async def get_entity_timeline(self, entity_type, entity_id) -> list[AuditLog]:
        return []
