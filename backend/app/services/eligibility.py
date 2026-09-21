from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.employee import Employee
from app.models.user import User
from app.models.assignment import IncidentAssignment
from app.services.shift_service import ShiftService
import structlog

logger = structlog.get_logger()

class EligibilityService:
    """
    Determines which employees are eligible to receive an assignment for a given incident.

    MANDATORY RULE — PRESENCE HAS ZERO INFLUENCE ON ASSIGNMENT ELIGIBILITY:
    =========================================================================
    An active employee is ALWAYS eligible if:
      1. They belong to the correct team (assignment group match)
      2. They have a currently active scheduled shift
      3. They have not already handled this specific incident in the current cycle
      4. They have the required skills (if incident specifies any)

    Presence, online status, offline status, busy status, chat status, WebSocket
    connection state, browser open/closed — NONE of these affect eligibility.

    The presence/availability_status field is recorded in candidates_evaluated[]
    ONLY for informational audit/reporting purposes. It is NEVER used as a gate.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.shift_service = ShiftService(db)
        self.last_pipeline: dict = {}

    async def find_eligible_employees(
        self,
        assignment_group: str,
        required_skills: set,
        now,
        incident_id: Optional[UUID] = None
    ) -> list[Employee]:
        """
        Returns all employees eligible for assignment.

        Eligibility criteria (presence-free):
          - Active employee with active user account (role=EMPLOYEE)
          - Belongs to the correct team (assignment_group match)
          - Has a currently active scheduled shift
          - Has required skills (if specified)
          - Has NOT already handled this incident in the current cycle

        Presence / online / offline / busy / available status: NOT USED.
        """
        pipeline = await self.evaluate_candidate_pipeline(
            assignment_group, required_skills, now, incident_id=incident_id
        )
        self.last_pipeline = pipeline
        # Return all eligible candidates — NO presence filter
        return pipeline.get("eligible", [])

    async def evaluate_candidate_pipeline(
        self,
        assignment_group: str,
        required_skills: set,
        now,
        incident_id: Optional[UUID] = None
    ) -> dict:
        """
        Evaluates candidate eligibility through the authoritative gates:

        Gate 1: Active scheduled shift exists for the current time window.
        Gate 2: Employee belongs to the correct team (assignment group match).
        Gate 3: Employee has not already been assigned this incident in the current cycle.
        Gate 4: Employee has the required skills (if incident specifies any).

        Presence, availability_status, online/offline, busy, chat state:
        recorded in candidates_evaluated[] for AUDIT ONLY — NEVER used as a gate.
        """
        active_shift = await self._find_active_shift(now)
        if not active_shift:
            logger.info(
                "eligibility_no_active_shift",
                assignment_group=assignment_group,
                now=str(now)
            )
            result: dict = {
                "active_shift": None,
                "eligible": [],
                "candidates_evaluated": [],
                "workloads": {},
                "decision_priority": "NO_CURRENT_SCHEDULED_COVERAGE",
                "is_coverage_exception": False,
                "rejected": [],
                "details": {
                    "shift_found": False,
                    "reason": "No active shift covering current timestamp",
                    "code": "NO_CURRENT_SCHEDULED_COVERAGE"
                }
            }
            self.last_pipeline = result
            return result

        # All employees scheduled on the active shift today
        scheduled = await self._get_scheduled_employees(active_shift, now.date())

        # Employees already actively assigned to this incident (cycle deduplication by HISTORY, not presence)
        already_assigned_emp_ids: set = set()
        if incident_id:
            try:
                stmt_assigned = select(IncidentAssignment.employee_id).where(
                    IncidentAssignment.incident_id == incident_id,
                    IncidentAssignment.is_active == True
                )
                res_assigned = await self.db.execute(stmt_assigned)
                already_assigned_emp_ids = set(res_assigned.scalars().all())
            except Exception:
                already_assigned_emp_ids = set()

        passing_candidates: list[Employee] = []
        rejected: list[dict] = []

        for emp in scheduled:
            user = await self.db.get(User, emp.user_id) if emp.user_id else None

            # Must be an active employee user
            if not user or not user.is_active or user.role != "EMPLOYEE":
                continue
            emp_name = user.full_name

            # Gate 1: Assignment Group / Team Match
            team = None
            try:
                team = emp.team
            except Exception:
                pass
            if team is None and emp.team_id:
                try:
                    from app.models.team import Team
                    team = await self.db.get(Team, emp.team_id)
                except Exception:
                    pass

            if assignment_group:
                ag_clean = assignment_group.strip().lower()
                tm_clean = (team.name or "").strip().lower() if team else ""
                sn_clean = (team.servicenow_group_id or "").strip().lower() if team else ""

                group_matched = team and (
                    tm_clean == ag_clean or
                    sn_clean == ag_clean or
                    tm_clean in ag_clean or
                    ag_clean in tm_clean
                )
                if not group_matched:
                    rejected.append({
                        "employee_id": str(emp.id),
                        "employee_name": emp_name,
                        "code": "TEAM_MISMATCH",
                        "reason": f"Team mismatch (Team: {team.name if team else 'None'} vs group: {assignment_group})"
                    })
                    continue

            # Gate 2: Incident cycle deduplication (assignment HISTORY, NOT presence)
            if emp.id in already_assigned_emp_ids:
                rejected.append({
                    "employee_id": str(emp.id),
                    "employee_name": emp_name,
                    "code": "ALREADY_ASSIGNED_THIS_INCIDENT",
                    "reason": "Candidate already holds an active assignment for this incident in the current cycle"
                })
                continue

            # Gate 3: Skill Matching (only if incident requires specific skills)
            if required_skills:
                emp_skill_ids: set = set()
                try:
                    if emp.skills:
                        emp_skill_ids = {es.skill_id for es in emp.skills}
                except Exception:
                    pass
                if not emp_skill_ids:
                    try:
                        from app.models.skill import EmployeeSkill
                        sk_res = await self.db.execute(
                            select(EmployeeSkill.skill_id).where(EmployeeSkill.employee_id == emp.id)
                        )
                        emp_skill_ids = set(sk_res.scalars().all())
                    except Exception:
                        pass

                if not required_skills.issubset(emp_skill_ids):
                    missing = required_skills - emp_skill_ids
                    rejected.append({
                        "employee_id": str(emp.id),
                        "employee_name": emp_name,
                        "code": "NO_SKILLED_EMPLOYEE",
                        "reason": f"Missing required skills (count missing: {len(missing)})"
                    })
                    continue

            # Passed all authoritative gates — eligible regardless of any presence state
            passing_candidates.append(emp)

        # -----------------------------------------------------------------------
        # Workload calculation — used by LEAST_WORKLOAD and SKILL_PLUS_WORKLOAD
        # strategies for deterministic selection among eligible candidates.
        # -----------------------------------------------------------------------
        from app.services.workload_service import WorkloadService
        workload_svc = WorkloadService(self.db)
        passing_ids = [e.id for e in passing_candidates]
        workloads = await workload_svc.get_workloads(passing_ids) if passing_ids else {}

        # -----------------------------------------------------------------------
        # Audit / reporting: record communication presence per candidate.
        # INFORMATIONAL ONLY — does NOT affect which employees are returned.
        # -----------------------------------------------------------------------
        candidates_evaluated: list[dict] = []
        for emp in passing_candidates:
            user = await self.db.get(User, emp.user_id) if emp.user_id else None
            emp_name = user.full_name if user else "Employee"
            wl = workloads.get(emp.id, 0)
            presence_status = getattr(emp, "availability_status", "UNKNOWN") or "UNKNOWN"
            is_pres = bool(getattr(emp, "is_present", False))
            candidates_evaluated.append({
                "employee_id": str(emp.id),
                "employee_name": emp_name,
                "active_workload": wl,
                # Informational only — never used for eligibility gating
                "communication_status": presence_status,
                "is_present_informational": is_pres,
                "eligible": True,
                "eligibility_basis": "ACTIVE_EMPLOYEE_ON_SCHEDULED_SHIFT"
            })

        # All passing candidates are eligible — sorted by workload for deterministic order
        eligible = sorted(passing_candidates, key=lambda e: (workloads.get(e.id, 0), str(e.id)))
        decision_priority = (
            "SCHEDULED_SHIFT_CANDIDATES_FOUND" if eligible else "NO_ELIGIBLE_SCHEDULED_EMPLOYEE"
        )

        logger.info(
            "eligibility_pipeline_complete",
            assignment_group=assignment_group,
            scheduled_count=len(scheduled),
            passing_count=len(passing_candidates),
            eligible_count=len(eligible),
            rejected_count=len(rejected),
            decision=decision_priority
        )

        result = {
            "active_shift": active_shift,
            "eligible": eligible,
            # is_coverage_exception is always False — presence never gates assignment
            "is_coverage_exception": False,
            "candidates_evaluated": candidates_evaluated,
            "workloads": workloads,
            "decision_priority": decision_priority,
            "rejected": rejected,
            "details": {
                "shift_id": str(active_shift.id),
                "shift_name": active_shift.name,
                "scheduled_count": len(scheduled),
                "passing_count": len(passing_candidates),
                "eligible_count": len(eligible),
                "rejected_count": len(rejected),
                "is_coverage_exception": False,
                "decision_priority": decision_priority,
                "presence_note": (
                    "Presence/online/offline/busy status has ZERO influence on assignment eligibility. "
                    "communication_status in candidates_evaluated is informational only."
                )
            }
        }
        self.last_pipeline = result
        return result

    async def _find_active_shift(self, now):
        return await self.shift_service.get_active_shift(now)

    async def _get_scheduled_employees(self, active_shift, date):
        return await self.shift_service.get_shift_employees(active_shift.id, date)

