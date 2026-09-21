from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
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

    async def get_logs(self, action: str | None = None, entity_type: str | None = None, page: int = 1, per_page: int = 50) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog)
        count_stmt = select(func.count(AuditLog.id))
        if action:
            stmt = stmt.where(AuditLog.action == action)
            count_stmt = count_stmt.where(AuditLog.action == action)
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
            count_stmt = count_stmt.where(AuditLog.entity_type == entity_type)
            
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar() or 0
        
        stmt = stmt.order_by(desc(AuditLog.created_at)).offset((page - 1) * per_page).limit(per_page)
        res = await self.db.execute(stmt)
        return list(res.scalars().all()), total

    async def get_entity_timeline(self, entity_type: str, entity_id) -> list[AuditLog]:
        stmt = select(AuditLog).where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id).order_by(AuditLog.created_at.asc())
        res = await self.db.execute(stmt)
        return list(res.scalars().all())
