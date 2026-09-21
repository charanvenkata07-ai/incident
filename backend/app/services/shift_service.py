from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, date, time
from uuid import UUID
from app.models.shift import Shift, ShiftAssignment
from app.models.employee import Employee

from sqlalchemy.orm import selectinload

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
            select(Employee)
            .options(
                selectinload(Employee.user),
                selectinload(Employee.team),
                selectinload(Employee.skills)
            )
            .join(ShiftAssignment, ShiftAssignment.employee_id == Employee.id)
            .where(
                ShiftAssignment.shift_id == shift_id,
                ShiftAssignment.date == date,
                ShiftAssignment.is_active == True
            )
        )
        emps = list(result.scalars().all())
        if not emps:
            # Fallback to standing active assignments for this shift if date-specific records are absent
            fallback_res = await self.db.execute(
                select(Employee)
                .options(
                    selectinload(Employee.user),
                    selectinload(Employee.team),
                    selectinload(Employee.skills)
                )
                .join(ShiftAssignment, ShiftAssignment.employee_id == Employee.id)
                .where(
                    ShiftAssignment.shift_id == shift_id,
                    ShiftAssignment.is_active == True
                )
            )
            emps = list(fallback_res.scalars().all())
        return emps

    async def is_within_shift(self, shift: Shift, current_time: time) -> bool:
        if shift.is_overnight:
            return current_time >= shift.start_time or current_time < shift.end_time
        return shift.start_time <= current_time < shift.end_time

    async def get_current_scheduled_employees_for_team(
        self, team_id: UUID, now: datetime, team_tz: str = "Asia/Kolkata"
    ) -> tuple[Shift | None, list[Employee]]:
        """
        Resolves the active shift for the team's timezone and returns (active_shift, scheduled_employees).
        Guarantees timezone-aware datetime handling using ZoneInfo.
        """
        from zoneinfo import ZoneInfo
        try:
            tz = ZoneInfo(team_tz)
        except Exception:
            tz = ZoneInfo("Asia/Kolkata")

        if now.tzinfo is None:
            local_now = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        else:
            local_now = now.astimezone(tz)

        shifts_res = await self.db.execute(select(Shift).where(Shift.is_active == True))
        all_shifts = shifts_res.scalars().all()
        current_time = local_now.time()
        matching_shifts = [s for s in all_shifts if await self.is_within_shift(s, current_time)]

        if not matching_shifts:
            return None, []

        # Find which matching shift has scheduled employees for this team on local_now.date()
        for sh in matching_shifts:
            stmt = (
                select(Employee)
                .options(
                    selectinload(Employee.user),
                    selectinload(Employee.team),
                    selectinload(Employee.skills)
                )
                .join(ShiftAssignment, ShiftAssignment.employee_id == Employee.id)
                .where(
                    ShiftAssignment.shift_id == sh.id,
                    ShiftAssignment.date == local_now.date(),
                    ShiftAssignment.is_active == True,
                    Employee.team_id == team_id
                )
            )
            res = await self.db.execute(stmt)
            emps = list(res.scalars().all())
            if emps:
                return sh, emps

        # Fallback: check standing active shift assignments for this team on matching shifts
        for sh in matching_shifts:
            stmt = (
                select(Employee)
                .options(
                    selectinload(Employee.user),
                    selectinload(Employee.team),
                    selectinload(Employee.skills)
                )
                .join(ShiftAssignment, ShiftAssignment.employee_id == Employee.id)
                .where(
                    ShiftAssignment.shift_id == sh.id,
                    ShiftAssignment.is_active == True,
                    Employee.team_id == team_id
                )
            )
            res = await self.db.execute(stmt)
            emps = list(res.scalars().all())
            if emps:
                return sh, emps

        return matching_shifts[0], []

    async def get_next_shift_for_team(self, team_id: UUID, now: datetime) -> tuple[Shift | None, date | None, list[Employee]]:
        """
        Finds the chronologically next scheduled shift for members of a specific team.
        Checks scheduled shift assignments for today and upcoming days.
        Returns (next_shift, scheduled_date, scheduled_employees).
        """
        from datetime import timedelta
        shifts_res = await self.db.execute(select(Shift).where(Shift.is_active == True).order_by(Shift.start_time.asc()))
        all_shifts = [s for s in shifts_res.scalars().all() if hasattr(s, "start_time") and s.start_time is not None]
        if not all_shifts:
            return None, None, []

        current_date = now.date()
        current_time = now.time()

        check_days = [current_date, current_date + timedelta(days=1), current_date + timedelta(days=2)]

        for chk_date in check_days:
            for sh in all_shifts:
                if chk_date == current_date and sh.start_time <= current_time and not sh.is_overnight:
                    continue

                stmt = (
                    select(Employee)
                    .options(
                        selectinload(Employee.user),
                        selectinload(Employee.team),
                        selectinload(Employee.skills)
                    )
                    .join(ShiftAssignment, ShiftAssignment.employee_id == Employee.id)
                    .where(
                        ShiftAssignment.shift_id == sh.id,
                        ShiftAssignment.date == chk_date,
                        ShiftAssignment.is_active == True,
                        Employee.team_id == team_id
                    )
                )
                emps = list((await self.db.execute(stmt)).scalars().all())
                if emps:
                    return sh, chk_date, emps

        # Fallback: check any active shift assignment for members of this team
        for sh in all_shifts:
            stmt = (
                select(Employee)
                .options(
                    selectinload(Employee.user),
                    selectinload(Employee.team),
                    selectinload(Employee.skills)
                )
                .join(ShiftAssignment, ShiftAssignment.employee_id == Employee.id)
                .where(
                    ShiftAssignment.shift_id == sh.id,
                    ShiftAssignment.is_active == True,
                    Employee.team_id == team_id
                )
            )
            emps = list((await self.db.execute(stmt)).scalars().all())
            if emps:
                return sh, current_date, emps

        return None, None, []
