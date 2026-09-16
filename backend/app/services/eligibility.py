from sqlalchemy.ext.asyncio import AsyncSession
from app.models.employee import Employee
from app.services.shift_service import ShiftService

class EligibilityService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.shift_service = ShiftService(db)

    async def find_eligible_employees(self, assignment_group, required_skills, now) -> list[Employee]:
        active_shift = await self._find_active_shift(now)
        if not active_shift:
            return []
        
        scheduled = await self._get_scheduled_employees(active_shift, now.date())
        
        if assignment_group:
            scheduled = [e for e in scheduled if e.team and (e.team.name == assignment_group or e.team.servicenow_group_id == assignment_group)]
        
        present = [e for e in scheduled if e.is_present]
        available = [e for e in present if e.availability_status == 'AVAILABLE']
        
        if required_skills:
            skilled = []
            for emp in available:
                emp_skill_ids = {es.skill_id for es in emp.skills}
                if required_skills.issubset(emp_skill_ids):
                    skilled.append(emp)
            return skilled
        
        return available

    async def _find_active_shift(self, now):
        return await self.shift_service.get_active_shift(now)
        
    async def _get_scheduled_employees(self, active_shift, date):
        return await self.shift_service.get_shift_employees(active_shift.id, date)
