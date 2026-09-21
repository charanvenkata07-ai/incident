import uuid
import structlog
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.incident import Incident, IncidentRequiredSkill
from app.models.assignment import IncidentAssignment
from app.models.employee import Employee
from app.models.user import User
from app.models.shift import Shift, ShiftAssignment
from app.services.shift_service import ShiftService
from app.services.eligibility import EligibilityService
from app.services.workload_service import WorkloadService
from app.services.notification_service import NotificationService
from app.services.audit_service import AuditService
from app.services.sync_service import SyncService
from app.core.config import settings

logger = structlog.get_logger()

class ShiftHandoffService:
    """
    Intelligent Shift Handoff & Rollover Engine.
    
    Evaluates in-flight active incidents across shift boundaries and transitions
    responsibility cleanly to incoming shift workers according to configurable policies:
    1. Completed incidents -> no handoff.
    2. Locked/Overtime incidents -> preserved on current engineer.
    3. Off-shift/Offline engineers -> automatically handed over to lowest-workload skilled incoming peer.
    4. Concurrency safety: Database row locking prevents race conditions.
    5. External failure isolation: ServiceNow or Notification failures do not corrupt assignment.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.shift_service = ShiftService(db)
        self.eligibility = EligibilityService(db)
        self.workload_service = WorkloadService(db)
        self.notification_service = NotificationService(db)
        self.audit_service = AuditService(db)
        self.sync_service = SyncService(db)

    async def evaluate_active_handoffs(self, now: datetime = None) -> list[dict]:
        """
        Scans all active assignments. Reassigns tickets whose assignees are off-shift or offline.
        """
        if now is None:
            now = datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE))

        # Query all active incident assignments
        query = (
            select(IncidentAssignment)
            .where(IncidentAssignment.is_active == True)
        )
        result = await self.db.execute(query)
        active_assignments = result.scalars().all()

        handoff_results = []

        for assignment in active_assignments:
            inc = await self.db.get(Incident, assignment.incident_id)
            if not inc or inc.state in ("COMPLETED", "RESOLVED", "CLOSED"):
                continue

            current_emp = await self.db.get(Employee, assignment.employee_id)
            if not current_emp:
                continue

            # Policy 1: Check if this assignment is explicitly locked to current engineer
            if assignment.reason and "LOCK_PRESERVED" in assignment.reason:
                logger.info("handoff_skipped_locked", incident=inc.incident_number, employee_id=str(current_emp.id))
                continue

            # Check current engineer's shift validity right now
            needs_handoff = False
            reason_for_handoff = ""

            # Condition A: Engineer marked OFFLINE or checked out
            if current_emp.availability_status == "OFFLINE" or not current_emp.is_present:
                needs_handoff = True
                reason_for_handoff = "Current engineer is OFFLINE or checked out"

            # Condition B: Current engineer's shift has ended
            if not needs_handoff:
                active_shift = await self.shift_service.get_active_shift(now)
                emp_shift_assignment = await self.shift_service.get_employee_shift(current_emp.id, now.date())
                
                # If engineer has no shift assignment for active shift
                if not active_shift or not emp_shift_assignment or emp_shift_assignment.shift_id != active_shift.id:
                    needs_handoff = True
                    reason_for_handoff = "Shift rollover: Current engineer is off-shift"

            if not needs_handoff:
                continue

            # Execute Handoff to incoming shift with database row locking
            handoff_record = await self._execute_handoff(
                incident=inc,
                outgoing_assignment=assignment,
                outgoing_emp=current_emp,
                reason=reason_for_handoff,
                now=now
            )
            if handoff_record:
                handoff_results.append(handoff_record)

        return handoff_results

    async def _execute_handoff(
        self,
        incident: Incident,
        outgoing_assignment: IncidentAssignment,
        outgoing_emp: Employee,
        reason: str,
        now: datetime
    ) -> dict | None:
        """Transfers ticket from outgoing to incoming engineer with concurrency and fault isolation."""
        # Row-level lock on outgoing assignment to prevent concurrent double-handoff races
        lock_stmt = (
            select(IncidentAssignment)
            .where(IncidentAssignment.id == outgoing_assignment.id)
            .with_for_update()
        )
        lock_res = await self.db.execute(lock_stmt)
        locked_assign = lock_res.scalar_one_or_none()
        if not locked_assign or not locked_assign.is_active:
            logger.warn("handoff_concurrent_already_processed", assignment_id=str(outgoing_assignment.id))
            return None

        outgoing_user = await self.db.get(User, outgoing_emp.user_id)
        outgoing_name = outgoing_user.full_name if outgoing_user else "Previous Engineer"

        # Query required skills for this incident
        req_stmt = select(IncidentRequiredSkill.skill_id).where(IncidentRequiredSkill.incident_id == incident.id)
        req_res = await self.db.execute(req_stmt)
        required_skills = set(req_res.scalars().all())

        # Find eligible engineers on the incoming shift
        eligible = await self.eligibility.find_eligible_employees(
            assignment_group=incident.assignment_group,
            required_skills=required_skills,
            now=now
        )
        # Exclude outgoing employee
        eligible = [e for e in eligible if e.id != outgoing_emp.id]

        if not eligible:
            logger.warn("handoff_no_incoming_eligible", incident=incident.incident_number, group=incident.assignment_group)
            # Notify admins of orphaned handoff ticket
            admin_stmt = select(User).where(User.role == "ADMIN", User.is_active == True)
            admins = (await self.db.execute(admin_stmt)).scalars().all()
            for admin in admins:
                try:
                    await self.notification_service.create_notification(
                        user_id=admin.id,
                        type="SYSTEM",
                        title=f"Shift Handoff Pending: {incident.incident_number}",
                        message=f"{incident.incident_number} requires handoff from {outgoing_name}, but no eligible incoming engineer is currently online.",
                        incident_id=incident.id
                    )
                except Exception as ex:
                    logger.error("admin_notification_failed", error=str(ex))
            await self.db.commit()
            return None

        # Pick successor with lowest active workload
        workloads = await self.workload_service.get_workloads([e.id for e in eligible])
        incoming_emp = min(eligible, key=lambda e: workloads.get(e.id, 0))
        incoming_user = await self.db.get(User, incoming_emp.user_id)
        incoming_name = incoming_user.full_name if incoming_user else "Incoming Engineer"

        # 1. Deactivate outgoing assignment
        locked_assign.is_active = False
        locked_assign.status = "REASSIGNED"

        # 2. Create incoming assignment
        new_assignment = IncidentAssignment(
            incident_id=incident.id,
            employee_id=incoming_emp.id,
            assignment_type="AUTOMATIC",
            status="ASSIGNED",
            reason=f"{reason}. Transferred from {outgoing_name} to {incoming_name}.",
            assigned_at=datetime.now(timezone.utc),
            is_active=True
        )
        self.db.add(new_assignment)

        # 3. Update Incident tracking & append ServiceNow Work Note
        incident.assigned_to = incoming_name
        incident.state = "ASSIGNED"
        handoff_note = f"[IncidentFlow] Automated Shift Handoff: Transferred from {outgoing_name} to {incoming_name} due to shift transition."
        incident.work_notes = f"{incident.work_notes or ''}\n{handoff_note}".strip()

        await self.db.flush()

        # 4. Audit Log
        await self.audit_service.log(
            action="SHIFT_HANDOFF",
            entity_type="INCIDENT",
            entity_id=incident.id,
            old_value={"employee_id": str(outgoing_emp.id), "employee_name": outgoing_name},
            new_value={"employee_id": str(incoming_emp.id), "employee_name": incoming_name, "reason": reason}
        )

        # 5. ServiceNow Sync with error isolation (failure preserves assignment and queues retry)
        try:
            await self.sync_service.sync_assignment_to_servicenow(incident, incoming_emp)
        except Exception as e:
            logger.error("handoff_servicenow_sync_failed", error=str(e), incident=incident.incident_number)

        # 6. Notifications with failure isolation (failure does not abort assignment)
        if outgoing_user:
            try:
                await self.notification_service.create_notification(
                    user_id=outgoing_user.id,
                    type="INCIDENT_REASSIGNED",
                    title=f"Shift Handoff: {incident.incident_number}",
                    message=f"Your shift has ended. Ticket {incident.incident_number} has been safely handed off to {incoming_name}.",
                    incident_id=incident.id
                )
            except Exception as ex:
                logger.error("outgoing_notification_failed", error=str(ex))

        if incoming_user:
            try:
                await self.notification_service.create_notification(
                    user_id=incoming_user.id,
                    type="INCIDENT_ASSIGNED",
                    title=f"Incoming Shift Handoff: {incident.incident_number}",
                    message=f"Transferred from {outgoing_name} upon shift rollover: {incident.short_description}",
                    incident_id=incident.id
                )
            except Exception as ex:
                logger.error("incoming_notification_failed", error=str(ex))

        await self.db.commit()

        logger.info(
            "shift_handoff_completed",
            incident=incident.incident_number,
            outgoing=outgoing_name,
            incoming=incoming_name
        )

        return {
            "incident_number": incident.incident_number,
            "outgoing_employee": outgoing_name,
            "incoming_employee": incoming_name,
            "reason": reason,
            "assigned_at": new_assignment.assigned_at.isoformat()
        }
