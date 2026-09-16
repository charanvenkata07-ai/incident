from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, date, time
from uuid import UUID
from app.models.shift import Shift, ShiftAssignment
from app.models.employee import Employee

class ShiftService:
    def __init__(self, db: AsyncSession):
        self.db = db
        
    async def get_active_shift(self, now: datetime) -> Shift | None:
        result = await self.db.execute(select(Shift).where(Shift.is_active == True))
        shifts = result.scalars().all()
        current_time = now.time()
        for shift in shifts:
            if await self.is_within_shift(shift, current_time):
                return shift
        return None

    async def get_employee_shift(self, employee_id: UUID, date: date) -> ShiftAssignment | None:
        result = await self.db.execute(
            select(ShiftAssignment).where(
                ShiftAssignment.employee_id == employee_id,
                ShiftAssignment.date == date,
                ShiftAssignment.is_active == True
            )
        )
        return result.scalar_one_or_none()

    async def get_shift_employees(self, shift_id: UUID, date: date) -> list[Employee]:
        result = await self.db.execute(
            select(Employee).join(ShiftAssignment).where(
                ShiftAssignment.shift_id == shift_id,
                ShiftAssignment.date == date,
                ShiftAssignment.is_active == True
            )
        )
        return list(result.scalars().all())

    async def is_within_shift(self, shift: Shift, current_time: time) -> bool:
        if shift.is_overnight:
            return current_time >= shift.start_time or current_time < shift.end_time
        return shift.start_time <= current_time < shift.end_time
