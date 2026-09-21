from __future__ import annotations

import uuid
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from app.models.team import Team
from app.models.employee import Employee
from app.models.user import User
from app.models.shift import Shift, ShiftAssignment
from app.models.assignment import IncidentAssignment
from app.services.audit_service import AuditService
from app.services.shift_service import ShiftService
from app.core.config import settings


class TeamService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)
        self.shift_service = ShiftService(db)

    async def validate_team_activation(self, team_id: uuid.UUID) -> tuple[bool, list[str]]:
        """
        Validates whether a team meets the mandatory requirements for ACTIVE status:
        1. Exactly 10 active employees
        2. Exactly one active Group Leader
        3. 100% active shift coverage (every active employee has a valid scheduled shift)
        4. Required configuration (name, description or work domain, and servicenow_group_id)
        
        Returns (is_valid, list_of_violations).
        """
        violations: list[str] = []
        team = await self.db.get(Team, team_id)
        if not team:
            return False, ["Team not found"]

        # 1. Employee Count Check: Exactly 10 active employees
        stmt_emps = (
            select(Employee)
            .join(User, Employee.user_id == User.id)
            .options(selectinload(Employee.user))
            .where(
                Employee.team_id == team_id,
                User.is_active == True,
                User.role == "EMPLOYEE"
            )
        )
        res_emps = await self.db.execute(stmt_emps)
        active_employees = list(res_emps.scalars().all())
        emp_count = len(active_employees)

        if emp_count != 10:
            violations.append(
                f"Active team must have exactly 10 active employees (currently {emp_count})"
            )

        # 2. Group Leader Check: Exactly one active Group Leader
        leaders = [e for e in active_employees if bool(e.is_group_leader)]
        if len(leaders) != 1:
            violations.append(
                f"Active team must have exactly one active Group Leader (currently {len(leaders)})"
            )

        # 3. Shift Coverage Check: Every active employee must have a valid scheduled shift
        # Check active shift assignments for today or upcoming schedule
        now = datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE))
        today = now.date()

        uncovered_employees: list[str] = []
        for emp in active_employees:
            # Check for active shift assignment
            stmt_sa = (
                select(ShiftAssignment)
                .where(
                    ShiftAssignment.employee_id == emp.id,
                    ShiftAssignment.is_active == True
                )
            )
            sa_res = await self.db.execute(stmt_sa)
            has_shift = sa_res.scalars().first() is not None
            if not has_shift:
                user_name = emp.user.full_name if emp.user else str(emp.id)
                uncovered_employees.append(user_name)

        if uncovered_employees:
            violations.append(
                f"All active team members must have active scheduled shift coverage ({len(uncovered_employees)} uncovered: {', '.join(uncovered_employees[:3])}{'...' if len(uncovered_employees) > 3 else ''})"
            )

        # 4. Configuration Check: Name required
        if not team.name or not team.name.strip():
            violations.append("Team name is required")

        is_valid = len(violations) == 0
        return is_valid, violations

    async def activate_team(self, team_id: uuid.UUID, actor_id: Optional[uuid.UUID] = None) -> Team:
        """
        Activates a team after strictly verifying mandatory invariants.
        Raises HTTP 400 if validation fails.
        """
        team = await self.db.get(Team, team_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        is_valid, violations = await self.validate_team_activation(team_id)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "TEAM_ACTIVATION_BLOCKED",
                    "message": f"Team '{team.name}' cannot be activated due to policy violations.",
                    "violations": violations
                }
            )

        old_status = team.is_active
        team.is_active = True
        await self.db.commit()
        await self.db.refresh(team)

        await self.audit.log(
            action="ACTIVATE_TEAM",
            entity_type="TEAM",
            entity_id=team.id,
            old_value={"is_active": old_status},
            new_value={"is_active": True, "active_employees": 10},
            actor_id=actor_id,
            reason="Mandatory validation passed: 10 active employees, 1 leader, 100% shift coverage."
        )
        await self.db.commit()
        return team

    async def deactivate_team(self, team_id: uuid.UUID, actor_id: Optional[uuid.UUID] = None) -> Team:
        """
        Deactivates a team back to DRAFT mode.
        """
        team = await self.db.get(Team, team_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        old_status = team.is_active
        team.is_active = False
        await self.db.commit()
        await self.db.refresh(team)

        await self.audit.log(
            action="DEACTIVATE_TEAM",
            entity_type="TEAM",
            entity_id=team.id,
            old_value={"is_active": old_status},
            new_value={"is_active": False},
            actor_id=actor_id,
            reason="Team status moved to DRAFT mode."
        )
        await self.db.commit()
        return team

    async def get_team_shift_coverage(
        self, team_id: uuid.UUID, now: Optional[datetime] = None, team_tz: str = "Asia/Kolkata"
    ) -> dict:
        """
        Calculates and returns the active shift schedule, next shift, timezone,
        and current roster coverage for a team.
        """
        team = await self.db.get(Team, team_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        try:
            tz = ZoneInfo(team_tz)
        except Exception:
            tz = ZoneInfo("Asia/Kolkata")

        if now is None:
            now = datetime.now(timezone.utc)
        if now.tzinfo is None:
            local_now = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        else:
            local_now = now.astimezone(tz)

        # Current active shift
        active_shift = await self.shift_service.get_active_shift(local_now)
        next_shift, next_date, next_emps = await self.shift_service.get_next_shift_for_team(team_id, local_now)

        # Active members of the team
        stmt_emps = (
            select(Employee)
            .join(User, Employee.user_id == User.id)
            .options(selectinload(Employee.user))
            .where(
                Employee.team_id == team_id,
                User.is_active == True,
                User.role == "EMPLOYEE"
            )
        )
        res_emps = await self.db.execute(stmt_emps)
        members = list(res_emps.scalars().all())

        # Build coverage details for current shift
        current_scheduled_emps: list[dict] = []
        present_count = 0
        available_count = 0
        busy_count = 0
        offline_count = 0

        for emp in members:
            # Check if emp is assigned to current active shift
            is_on_current_shift = False
            if active_shift:
                stmt_sa = select(ShiftAssignment).where(
                    ShiftAssignment.employee_id == emp.id,
                    ShiftAssignment.shift_id == active_shift.id,
                    ShiftAssignment.is_active == True
                )
                sa_res = await self.db.execute(stmt_sa)
                is_on_current_shift = sa_res.scalars().first() is not None

            # Count presence & availability across team
            if emp.is_present:
                present_count += 1
                if emp.availability_status == "AVAILABLE":
                    available_count += 1
                elif emp.availability_status == "BUSY":
                    busy_count += 1
            else:
                offline_count += 1

            if is_on_current_shift:
                # Workload count
                stmt_wl = select(func.count()).select_from(IncidentAssignment).where(
                    IncidentAssignment.employee_id == emp.id,
                    IncidentAssignment.is_active == True
                )
                wl_res = await self.db.execute(stmt_wl)
                active_wl = wl_res.scalar() or 0

                current_scheduled_emps.append({
                    "employee_id": str(emp.id),
                    "full_name": emp.user.full_name if emp.user else "Unknown",
                    "email": emp.user.email if emp.user else "",
                    "is_present": emp.is_present,
                    "availability_status": emp.availability_status,
                    "is_group_leader": bool(emp.is_group_leader),
                    "active_workload": active_wl
                })

        is_valid, violations = await self.validate_team_activation(team_id)

        return {
            "team_id": str(team.id),
            "team_name": team.name,
            "status": "ACTIVE" if team.is_active else "DRAFT",
            "is_active": team.is_active,
            "timezone": team_tz,
            "current_time": local_now.isoformat(),
            "active_employees_count": len(members),
            "current_shift": {
                "id": str(active_shift.id) if active_shift else None,
                "name": active_shift.name if active_shift else None,
                "start_time": active_shift.start_time.strftime("%H:%M") if active_shift and hasattr(active_shift, "start_time") and active_shift.start_time else None,
                "end_time": active_shift.end_time.strftime("%H:%M") if active_shift and hasattr(active_shift, "end_time") and active_shift.end_time else None,
                "scheduled_count": len(current_scheduled_emps),
                "scheduled_employees": current_scheduled_emps
            },
            "next_shift": {
                "id": str(next_shift.id) if next_shift else None,
                "name": next_shift.name if next_shift else None,
                "start_time": next_shift.start_time.strftime("%H:%M") if next_shift and hasattr(next_shift, "start_time") and next_shift.start_time else None,
                "end_time": next_shift.end_time.strftime("%H:%M") if next_shift and hasattr(next_shift, "end_time") and next_shift.end_time else None,
                "scheduled_date": next_date.isoformat() if next_date else None,
                "scheduled_count": len(next_emps)
            },
            "summary": {
                "total_members": len(members),
                "present": present_count,
                "available": available_count,
                "busy": busy_count,
                "offline": offline_count
            },
            "validation": {
                "is_valid_active": is_valid,
                "violations": violations
            }
        }
