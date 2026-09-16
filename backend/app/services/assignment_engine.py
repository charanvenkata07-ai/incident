from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.employee import Employee
from app.models.user import User
from app.services.eligibility import EligibilityService
from app.services.shift_service import ShiftService
from app.services.workload_service import WorkloadService
from app.services.notification_service import NotificationService
from app.services.audit_service import AuditService
from app.core.config import settings
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import structlog

logger = structlog.get_logger()

class AssignmentEngine:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.eligibility = EligibilityService(db)
        self.shift_service = ShiftService(db)
        self.workload_service = WorkloadService(db)
        self.notification_service = NotificationService(db)
        self.audit_service = AuditService(db)

    async def process_incident(self, incident: Incident) -> IncidentAssignment | None:
        if not await self._is_auto_assignment_enabled():
            await self.audit_service.log('AUTO_ASSIGN_SKIPPED', 'INCIDENT', incident.id, reason='Auto assignment disabled')
            return None
        
        eligible = await self.eligibility.find_eligible_employees(
            assignment_group=incident.assignment_group,
            required_skills=await self._get_required_skills(incident),
            now=datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE))
        )
        
        if not eligible:
            await self._handle_no_eligible(incident)
            return None
        
        strategy = await self._get_strategy(incident)
        selected = await self._apply_strategy(strategy, eligible, incident)
        
        if settings.DRY_RUN_MODE or await self._is_dry_run():
            await self.audit_service.log('DRY_RUN', 'INCIDENT', incident.id, new_value={'recommended': str(selected.id), 'strategy': strategy})
            return None
        
        if settings.SHADOW_MODE or await self._is_shadow_mode():
            await self.audit_service.log('SHADOW_ASSIGN', 'INCIDENT', incident.id, new_value={'recommended': str(selected.id), 'strategy': strategy})
            return None
        
        assignment = await self._create_assignment(incident, selected, strategy)
        return assignment

    async def _apply_strategy(self, strategy: str, eligible: list[Employee], incident: Incident) -> Employee:
        if strategy == 'ROUND_ROBIN':
            return await self._round_robin(eligible)
        elif strategy == 'LEAST_WORKLOAD':
            return await self._least_workload(eligible)
        elif strategy == 'SKILL_BASED':
            return await self._skill_based(eligible, incident)
        else:
            return await self._skill_plus_workload(eligible, incident)

    async def _least_workload(self, eligible: list[Employee]) -> Employee:
        workloads = await self.workload_service.get_workloads([e.id for e in eligible])
        return min(eligible, key=lambda e: workloads.get(e.id, 0))

    async def _round_robin(self, eligible: list[Employee]) -> Employee:
        last = await self._get_last_assigned_employee()
        sorted_employees = sorted(eligible, key=lambda e: str(e.id))
        if last:
            last_idx = next((i for i, e in enumerate(sorted_employees) if e.id == last), -1)
            return sorted_employees[(last_idx + 1) % len(sorted_employees)]
        return sorted_employees[0]

    async def _skill_based(self, eligible: list[Employee], incident: Incident) -> Employee:
        required = await self._get_required_skills(incident)
        if not required:
            return eligible[0]
        scores = []
        for emp in eligible:
            emp_skills = {es.skill_id for es in emp.skills}
            match_count = len(required & emp_skills)
            scores.append((emp, match_count))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[0][0]

    async def _skill_plus_workload(self, eligible: list[Employee], incident: Incident) -> Employee:
        required = await self._get_required_skills(incident)
        workloads = await self.workload_service.get_workloads([e.id for e in eligible])
        if required:
            skilled = []
            for emp in eligible:
                emp_skills = {es.skill_id for es in emp.skills}
                if required.issubset(emp_skills):
                    skilled.append(emp)
            if skilled:
                eligible = skilled
        return min(eligible, key=lambda e: workloads.get(e.id, 0))

    async def _create_assignment(self, incident, employee, strategy) -> IncidentAssignment:
        stmt = select(Employee).where(Employee.id == employee.id).with_for_update()
        result = await self.db.execute(stmt)
        locked_employee = result.scalar_one()
        
        reason = f"Selected by {strategy} strategy. Employee is on active shift, present, and available."
        
        assignment = IncidentAssignment(
            incident_id=incident.id,
            employee_id=locked_employee.id,
            assignment_type='AUTOMATIC',
            status='ASSIGNED',
            reason=reason,
            assigned_at=datetime.now(timezone.utc),
            is_active=True
        )
        self.db.add(assignment)
        
        incident.state = 'ASSIGNED'
        incident.assigned_to = locked_employee.user.full_name
        
        await self.db.flush()
        
        await self.audit_service.log(
            action='AUTO_ASSIGN',
            entity_type='INCIDENT',
            entity_id=incident.id,
            new_value={'employee_id': str(locked_employee.id), 'employee_name': locked_employee.user.full_name, 'strategy': strategy, 'reason': reason}
        )
        
        await self.notification_service.create_notification(
            user_id=locked_employee.user_id,
            type='INCIDENT_ASSIGNED',
            title=f'New incident assigned: {incident.incident_number}',
            message=f'{incident.short_description}',
            incident_id=incident.id
        )
        
        await self.db.commit()
        return assignment

    async def _handle_no_eligible(self, incident):
        incident.state = 'NEW'
        await self.audit_service.log(
            action='AUTO_ASSIGN_FAILED',
            entity_type='INCIDENT', 
            entity_id=incident.id,
            reason='No eligible employees currently available'
        )
        admins = await self.db.execute(select(User).where(User.role == 'ADMIN', User.is_active == True))
        for admin in admins.scalars().all():
            await self.notification_service.create_notification(
                user_id=admin.id,
                type='SYSTEM',
                title=f'Unassigned incident: {incident.incident_number}',
                message=f'No eligible employee found. {incident.short_description}',
                incident_id=incident.id
            )
        await self.db.commit()

    async def _is_auto_assignment_enabled(self) -> bool:
        from app.models.settings import SystemSetting
        result = await self.db.execute(
            select(SystemSetting).where(SystemSetting.key == 'auto_assignment_enabled')
        )
        setting = result.scalar_one_or_none()
        if setting and setting.value is not None:
            return bool(setting.value.get('enabled', True))
        return settings.AUTO_ASSIGNMENT_ENABLED

    async def _get_required_skills(self, incident: Incident) -> set:
        from app.models.incident import IncidentRequiredSkill
        result = await self.db.execute(
            select(IncidentRequiredSkill.skill_id).where(
                IncidentRequiredSkill.incident_id == incident.id
            )
        )
        return set(result.scalars().all())

    async def _get_strategy(self, incident: Incident) -> str:
        from app.models.settings import AssignmentRule
        # Check for team-specific rule first
        if incident.assignment_group:
            from app.models.team import Team
            team_result = await self.db.execute(
                select(Team.id).where(
                    (Team.name == incident.assignment_group) |
                    (Team.servicenow_group_id == incident.assignment_group)
                )
            )
            team_id = team_result.scalar_one_or_none()
            if team_id:
                rule_result = await self.db.execute(
                    select(AssignmentRule).where(
                        AssignmentRule.team_id == team_id,
                        AssignmentRule.is_active == True,
                    )
                )
                rule = rule_result.scalar_one_or_none()
                if rule:
                    return rule.strategy

        # Check for global rule
        result = await self.db.execute(
            select(AssignmentRule).where(
                AssignmentRule.team_id.is_(None),
                AssignmentRule.is_active == True,
            )
        )
        global_rule = result.scalar_one_or_none()
        if global_rule:
            return global_rule.strategy

        # Fall back to system setting
        from app.models.settings import SystemSetting
        setting_result = await self.db.execute(
            select(SystemSetting).where(SystemSetting.key == 'assignment_strategy')
        )
        setting = setting_result.scalar_one_or_none()
        if setting and setting.value:
            return setting.value.get('strategy', settings.ASSIGNMENT_STRATEGY)
        return settings.ASSIGNMENT_STRATEGY

    async def _is_dry_run(self) -> bool:
        if settings.AUTOMATION_MODE.upper() == "DRY_RUN":
            return True
        from app.models.settings import SystemSetting
        result = await self.db.execute(
            select(SystemSetting).where(SystemSetting.key == 'dry_run_mode')
        )
        setting = result.scalar_one_or_none()
        if setting and setting.value is not None:
            return bool(setting.value.get('enabled', False))
        return False

    async def _is_shadow_mode(self) -> bool:
        if settings.AUTOMATION_MODE.upper() == "SHADOW":
            return True
        from app.models.settings import SystemSetting
        result = await self.db.execute(
            select(SystemSetting).where(SystemSetting.key == 'shadow_mode')
        )
        setting = result.scalar_one_or_none()
        if setting and setting.value is not None:
            return bool(setting.value.get('enabled', False))
        return False

    async def _get_last_assigned_employee(self):
        result = await self.db.execute(
            select(IncidentAssignment.employee_id)
            .where(IncidentAssignment.assignment_type == 'AUTOMATIC', IncidentAssignment.is_active == True)
            .order_by(IncidentAssignment.assigned_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
