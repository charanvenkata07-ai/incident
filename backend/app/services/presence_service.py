from sqlalchemy.ext.asyncio import AsyncSession
from app.models.presence import PresenceRecord
from uuid import UUID
from datetime import date

class PresenceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_in(self, employee_id, shift_assignment_id) -> PresenceRecord:
        pass

    async def check_out(self, employee_id) -> PresenceRecord:
        pass

    async def set_break(self, employee_id) -> PresenceRecord:
        pass

    async def is_present(self, employee_id: UUID, check_date: date) -> bool:
        return True

    async def get_team_presence(self, team_id: UUID, check_date: date) -> list[dict]:
        return []
