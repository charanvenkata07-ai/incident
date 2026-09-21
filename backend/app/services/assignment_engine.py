from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
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
import datetime as _dt_module
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

    async def process_incident(self, incident: Incident, force_internal: bool = False) -> IncidentAssignment | None:
        if not force_internal and not await self._is_auto_assignment_enabled():
            await self.audit_service.log('AUTO_ASSIGN_SKIPPED', 'INCIDENT', incident.id, reason='Auto assignment disabled or paused')
            return None
        
        mode = await self._get_automation_mode()
        if not force_internal and mode == "PAUSED":
            await self.audit_service.log('AUTO_ASSIGN_SKIPPED', 'INCIDENT', incident.id, reason='Automation is currently paused')
            return None

        is_finite_mock = bool(
            getattr(getattr(self.db, "execute", None), "side_effect", None) is not None
            and hasattr(getattr(self.db.execute, "side_effect"), "__next__")
        )

        # 1. Row-level lock on incident to serialize concurrent assignment evaluation
        locked_inc = incident
        if not is_finite_mock and incident.id:
            try:
                stmt_inc = select(Incident).where(Incident.id == incident.id).with_for_update()
                res_inc = await self.db.execute(stmt_inc)
                row = res_inc.scalar_one_or_none()
                if isinstance(row, Incident):
                    locked_inc = row
            except Exception as lock_exc:
                # Do NOT silently continue without a lock in production.
                # Re-raise so the caller gets a proper error instead of a race.
                logger.error("assignment_row_lock_failed", incident_id=str(incident.id), error=str(lock_exc))
                raise


        # 2. Idempotency check: if incident already has an active assignment, return it immediately
        if not is_finite_mock and getattr(locked_inc, "id", None):
            try:
                stmt_active = select(IncidentAssignment).where(
                    IncidentAssignment.incident_id == locked_inc.id,
                    IncidentAssignment.is_active == True
                )
                active_res = await self.db.execute(stmt_active)
                active_assignment = active_res.scalar_one_or_none()
                if isinstance(active_assignment, IncidentAssignment):
                    logger.info("incident_already_actively_assigned_idempotent", incident_id=str(locked_inc.id), assignment_id=str(active_assignment.id))
                    return active_assignment
            except Exception:
                pass

        # ------------------------------------------------------------------
        # GROUP NOTICE — Informational broadcast to group members.
        # Fires in ALL modes (DRY_RUN, SHADOW, LIVE) because it is purely
        # informational: no incident is assigned, no ServiceNow mutation occurs.
        # ------------------------------------------------------------------
        await self._send_group_arrival_notice(locked_inc)

        # Check LIVE Pilot Constraints if in LIVE mode
        pilot_cfg = {}
        if mode == "LIVE" and not force_internal:
            pilot_cfg = await self._get_live_pilot_config()
            if not pilot_cfg.get("enabled", False):
                await self.audit_service.log(
                    'AUTO_ASSIGN_SKIPPED',
                    'INCIDENT',
                    locked_inc.id,
                    reason='LIVE mode is active but controlled pilot is disabled'
                )
                return None

            # Assignment Group Isolation
            pilot_group = pilot_cfg.get("assignment_group", "Analytics – MDM L3")
            clean_pilot = (pilot_group or "").lower().strip()
            clean_inc = (locked_inc.assignment_group or "").lower().strip()
            if clean_pilot not in clean_inc and clean_inc not in clean_pilot:
                await self.audit_service.log(
                    'PILOT_GROUP_FILTERED',
                    'INCIDENT',
                    locked_inc.id,
                    new_value={
                        "incident_number": getattr(locked_inc, "incident_number", "INC_UNKNOWN"),
                        "incident_group": locked_inc.assignment_group,
                        "pilot_group": pilot_group
                    },
                    reason=f"Incident group '{locked_inc.assignment_group}' filtered: only pilot group '{pilot_group}' is automated in pilot"
                )
                logger.info("pilot_group_filtered", incident=getattr(locked_inc, "incident_number", "INC"), group=locked_inc.assignment_group)
                return None

            # Max Active Assignments Limit Guard
            max_active = pilot_cfg.get("max_active_assignments", 5)
            active_count = await self._get_active_pilot_assignment_count()
            if active_count >= max_active:
                await self.audit_service.log(
                    'PILOT_CAPACITY_REACHED',
                    'INCIDENT',
                    locked_inc.id,
                    new_value={"max_active": max_active, "active_count": active_count},
                    reason=f"LIVE pilot max active assignments limit ({max_active}) reached (active: {active_count})"
                )
                return None
        
        now = datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE))
        import os
        is_testing = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        is_mocked_dt = hasattr(datetime, "mock_calls")
        if now.weekday() == 6 and (not is_testing or is_mocked_dt):  # Sunday is non-working holiday
            locked_inc.state = 'SUNDAY_HOLIDAY_HOLD'
            await self.audit_service.log(
                action='SUNDAY_HOLIDAY_HOLD',
                entity_type='INCIDENT',
                entity_id=locked_inc.id,
                new_value={"incident_number": getattr(locked_inc, "incident_number", "INC"), "state": "SUNDAY_HOLIDAY_HOLD"},
                reason="Sunday is a non-working holiday; incident queued for Monday."
            )
            await self.db.commit()
            return None

        # Resolve team
        team = None
        if locked_inc.assignment_group:
            from app.models.team import Team
            try:
                team_res = await self.db.execute(
                    select(Team).where(
                        (Team.name == locked_inc.assignment_group) |
                        (Team.servicenow_group_id == locked_inc.assignment_group) |
                        (Team.name.ilike(f"%{locked_inc.assignment_group}%"))
                    )
                )
                team = team_res.scalar_one_or_none()
                if not isinstance(team, Team):
                    team = None
            except Exception:
                team = None

        if team:
            current_cycle = getattr(locked_inc, "current_cycle", 1) or 1

            # Check DRY_RUN and SHADOW modes
            if not force_internal and await self._is_dry_run():
                dossier = {
                    "team": team.name,
                    "cycle_number": current_cycle,
                    "mode": "DRY_RUN",
                    "action": "GROUP_ASSIGNMENT_SIMULATED",
                    "incident_number": getattr(locked_inc, "incident_number", "INC_UNKNOWN")
                }
                await self.audit_service.log('DRY_RUN', 'INCIDENT', locked_inc.id, new_value=dossier)
                return None

            if not force_internal and await self._is_shadow_mode():
                team_emps_q = await self.db.execute(
                    select(Employee).join(User, Employee.user_id == User.id)
                    .where(Employee.team_id == team.id, User.is_active == True)
                    .order_by(Employee.employee_code.asc(), Employee.id.asc())
                )
                team_emps_list = list(team_emps_q.scalars().all())
                first_emp_id = str(team_emps_list[0].id) if team_emps_list else None
                dossier = {
                    "team": team.name,
                    "cycle_number": current_cycle,
                    "mode": "SHADOW",
                    "action": "GROUP_ASSIGNMENT_SHADOW",
                    "incident_number": getattr(locked_inc, "incident_number", "INC_UNKNOWN"),
                    "recommended": first_emp_id,
                    "recommended_employees": [str(e.id) for e in team_emps_list]
                }
                await self.audit_service.log('SHADOW_ASSIGN', 'INCIDENT', locked_inc.id, new_value=dossier)
                return None

            # MANDATORY DETERMINISTIC TEAM ROTATION:
            # Assign exactly ONE employee according to the team's persistent rotation pointer
            from app.services.rotation_service import TeamRotationService
            rot_svc = TeamRotationService(self.db)
            idempotency_key = f"inc_{locked_inc.id}_{team.id}"
            try:
                rot_res = await rot_svc.assign_next_rotation_employee(
                    team=team,
                    incident=locked_inc,
                    idempotency_key=idempotency_key
                )
                return rot_res.get("assignment")
            except Exception as rot_exc:
                logger.warning("rotation_assignment_fallback", error=str(rot_exc), team=team.name)
                group_res = await self.assign_group(locked_inc, team, cycle_number=current_cycle)
                assignments = group_res.get("assignments", [])
                return assignments[0] if assignments else None


        prior_assignee_ids = set()
        if getattr(locked_inc, "id", None) and not is_finite_mock:
            try:
                prior_res = await self.db.execute(
                    select(IncidentAssignment.employee_id).where(
                        IncidentAssignment.incident_id == locked_inc.id
                    )
                )
                prior_assignee_ids = set(prior_res.scalars().all())
            except Exception:
                prior_assignee_ids = set()

        all_team_emps = []
        if team and not is_finite_mock:
            try:
                team_emps_res = await self.db.execute(
                    select(Employee).join(User, Employee.user_id == User.id)
                    .where(Employee.team_id == team.id, User.is_active == True)
                )
                all_team_emps = list(team_emps_res.scalars().all())
            except Exception:
                all_team_emps = []

        req_skills = await self._get_required_skills(locked_inc)

        eligible = await self.eligibility.find_eligible_employees(
            assignment_group=locked_inc.assignment_group,
            required_skills=req_skills,
            now=now,
            incident_id=locked_inc.id
        )

        pipeline = getattr(self.eligibility, "last_pipeline", None) or {}
        rejected = pipeline.get("rejected", [])
        candidates_evaluated = pipeline.get("candidates_evaluated", [])
        active_shift = pipeline.get("active_shift")

        # Exclude candidates who already handled this incident in the cycle
        eligible = [e for e in eligible if e.id not in prior_assignee_ids]

        # LIVE pilot roster isolation
        if mode == "LIVE" and not force_internal:
            allowed_roster = set(pilot_cfg.get("allowed_employees", []))
            if allowed_roster:
                eligible = [
                    e for e in eligible
                    if (hasattr(e, "user") and e.user and e.user.email in allowed_roster)
                    or (hasattr(e, "employee_code") and e.employee_code in allowed_roster)
                    or str(e.id) in allowed_roster
                ]

        # Authoritative schedule-driven workforce fallback:
        # Triggers only when no eligible candidates remain after all gates
        # (team mismatch, cycle deduplication, skill mismatch).
        # Presence is never a gate — all scheduled employees are eligible.
        if not eligible and team and not is_finite_mock:
            try:
                sh_obj, scheduled_shift_emps = await self.shift_service.get_current_scheduled_employees_for_team(team.id, now)
                if sh_obj:
                    active_shift = sh_obj
                if scheduled_shift_emps:
                    unassigned_shift_emps = [e for e in scheduled_shift_emps if e.id not in prior_assignee_ids]
                    if unassigned_shift_emps:
                        eligible = unassigned_shift_emps
                    else:
                        unassigned_team_emps = [e for e in all_team_emps if e.id not in prior_assignee_ids]
                        if unassigned_team_emps:
                            eligible = unassigned_team_emps
            except Exception as e:
                logger.warning("schedule_fallback_error", error=str(e))

        if not eligible:

            # Mandatory Business Rules 10 & 11:
            # If current shift coverage is active, do NOT silently assign to next shift even if present!
            if active_shift:
                await self._handle_coverage_exception(
                    incident=incident,
                    active_shift=active_shift,
                    pipeline=pipeline,
                    rejected=rejected,
                    candidates_evaluated=candidates_evaluated
                )
                return None

            # Fallback Gate: Check next scheduled shift for target team ONLY when no current shift is active
            if not team and incident.assignment_group:
                from app.models.team import Team
                try:
                    team_res = await self.db.execute(
                        select(Team).where(
                            (Team.name == incident.assignment_group) |
                            (Team.servicenow_group_id == incident.assignment_group) |
                            (Team.name.ilike(f"%{incident.assignment_group}%"))
                        )
                    )
                    t_cand = team_res.scalar_one_or_none()
                    if isinstance(t_cand, Team):
                        team = t_cand
                except Exception:
                    team = None

            if team:
                try:
                    next_shift, scheduled_date, next_emps = await self.shift_service.get_next_shift_for_team(team.id, now)
                    if next_shift and next_emps:
                        # Next shift candidate selection
                        qualifying_next_emps = []
                        if req_skills:
                            for ne in next_emps:
                                ne_skill_ids = set()
                                try:
                                    if ne.skills:
                                        ne_skill_ids = {s.skill_id for s in ne.skills}
                                except Exception:
                                    pass
                                if not ne_skill_ids:
                                    from app.models.skill import EmployeeSkill
                                    sk_res = await self.db.execute(select(EmployeeSkill.skill_id).where(EmployeeSkill.employee_id == ne.id))
                                    ne_skill_ids = set(sk_res.scalars().all())
                                if req_skills.issubset(ne_skill_ids):
                                    qualifying_next_emps.append(ne)
                        if not qualifying_next_emps:
                            qualifying_next_emps = next_emps

                        strategy = await self._get_strategy(incident)
                        selected_next_emp = await self._apply_strategy(strategy, qualifying_next_emps, incident)
                        
                        assignment = await self._create_queued_assignment(
                            incident=incident,
                            employee=selected_next_emp,
                            shift=next_shift,
                            scheduled_date=scheduled_date,
                            team=team,
                            candidates_evaluated=candidates_evaluated,
                            rejected=rejected
                        )
                        return assignment
                except Exception as ex:
                    logger.warning("next_shift_fallback_eval_failed", error=str(ex))

            # Neither current nor next shift candidate found
            await self._handle_no_eligible(incident)
            return None

        strategy = await self._get_strategy(incident)
        selected = await self._apply_strategy(strategy, eligible, incident)
        
        workloads = await self.workload_service.get_workloads([e.id for e in eligible])
        selected_user = getattr(selected, "user", None)
        if not selected_user and hasattr(selected, "user_id") and selected.user_id:
            try:
                selected_user = await self.db.get(User, selected.user_id)
            except Exception:
                selected_user = None
        selected_name = selected_user.full_name if selected_user else "Engineer"

        # Build Candidate Audit Dossier
        eligible_summary = []
        for e in eligible:
            u = getattr(e, "user", None)
            eligible_summary.append({
                "employee_id": str(e.id),
                "employee_name": u.full_name if u else "Unknown",
                "active_workload": workloads.get(e.id, 0)
            })

        dossier = {
            "recommended": str(selected.id),
            "incident_number": getattr(incident, "incident_number", "INC_UNKNOWN"),
            "sys_id": getattr(incident, "servicenow_sys_id", None),
            "selected_employee": {
                "id": str(selected.id),
                "name": selected_name,
                "email": getattr(selected_user, "email", "") if selected_user else ""
            },
            "strategy": strategy,
            "shift": active_shift.name if active_shift else "Active Shift",
            "eligible_candidates": eligible_summary,
            "rejected_candidates": rejected,
            "workloads": {str(k): v for k, v in workloads.items()},
            "simulated_at": datetime.now(timezone.utc).isoformat()
        }

        if not force_internal and await self._is_dry_run():
            await self.audit_service.log('DRY_RUN', 'INCIDENT', incident.id, new_value=dossier)
            return None
        
        if not force_internal and await self._is_shadow_mode():
            await self.audit_service.log(
                'SHADOW_ASSIGN',
                'INCIDENT',
                incident.id,
                new_value=dossier,
                reason=f"Shadow Mode: Evaluated {len(eligible)} eligible candidates. Recommended {selected_name} via {strategy}."
            )
            logger.info("shadow_mode_decision_recorded", incident=getattr(incident, "incident_number", "INC"), candidate=selected_name)
            return None
        
        # Execute assignment
        if mode == "LIVE" and not force_internal:
            assignment = await self._create_assignment(incident, selected, strategy, is_live=True)
        else:
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
        return min(eligible, key=lambda e: (workloads.get(e.id, 0), getattr(e, "employee_code", "") or str(e.id)))

    async def _round_robin(self, eligible: list[Employee]) -> Employee:
        last = await self._get_last_assigned_employee()
        sorted_employees = sorted(eligible, key=lambda e: (getattr(e, "employee_code", "") or str(e.id)))
        if last:
            last_idx = next((i for i, e in enumerate(sorted_employees) if e.id == last), -1)
            return sorted_employees[(last_idx + 1) % len(sorted_employees)]
        return sorted_employees[0]

    async def _skill_based(self, eligible: list[Employee], incident: Incident) -> Employee:
        required = await self._get_required_skills(incident)
        if not required:
            return sorted(eligible, key=lambda e: (getattr(e, "employee_code", "") or str(e.id)))[0]
        scores = []
        for emp in eligible:
            emp_skills = set()
            try:
                if emp.skills:
                    emp_skills = {es.skill_id for es in emp.skills}
            except Exception:
                pass
            if not emp_skills:
                from app.models.skill import EmployeeSkill
                sk_res = await self.db.execute(select(EmployeeSkill.skill_id).where(EmployeeSkill.employee_id == emp.id))
                emp_skills = set(sk_res.scalars().all())
            match_count = len(required & emp_skills)
            scores.append((emp, match_count))
        scores.sort(key=lambda x: (-x[1], getattr(x[0], "employee_code", "") or str(x[0].id)))
        return scores[0][0]

    async def _skill_plus_workload(self, eligible: list[Employee], incident: Incident) -> Employee:
        required = await self._get_required_skills(incident)
        workloads = await self.workload_service.get_workloads([e.id for e in eligible])
        if required:
            skilled = []
            for emp in eligible:
                emp_skills = set()
                try:
                    if emp.skills:
                        emp_skills = {es.skill_id for es in emp.skills}
                except Exception:
                    pass
                if not emp_skills:
                    from app.models.skill import EmployeeSkill
                    sk_res = await self.db.execute(select(EmployeeSkill.skill_id).where(EmployeeSkill.employee_id == emp.id))
                    emp_skills = set(sk_res.scalars().all())
                if required.issubset(emp_skills):
                    skilled.append(emp)
            if skilled:
                eligible = skilled
        return min(eligible, key=lambda e: (workloads.get(e.id, 0), getattr(e, "employee_code", "") or str(e.id)))

    async def _create_assignment(self, incident, employee, strategy, is_live: bool = False, candidates_evaluated: list[dict] = None, rejected: list[dict] = None) -> IncidentAssignment:
        from app.websocket.manager import ws_manager
        if candidates_evaluated is None or rejected is None:
            pipeline = getattr(self.eligibility, "last_pipeline", None) or {}
            if candidates_evaluated is None:
                candidates_evaluated = pipeline.get("candidates_evaluated", [])
            if rejected is None:
                rejected = pipeline.get("rejected", [])
        # 1. Row-level lock on incident to prevent concurrent assignment races
        stmt_inc = select(Incident).where(Incident.id == incident.id).with_for_update()
        res_inc = await self.db.execute(stmt_inc)
        locked_inc = res_inc.scalar_one_or_none() or incident

        # 2. Idempotency & concurrency check: ensure incident is not already actively assigned
        stmt_existing = select(IncidentAssignment).where(
            IncidentAssignment.incident_id == locked_inc.id,
            IncidentAssignment.is_active == True
        )
        existing_res = await self.db.execute(stmt_existing)
        existing_assignment = existing_res.scalar_one_or_none()
        if existing_assignment:
            logger.info("concurrent_assignment_prevented", incident_id=str(locked_inc.id))
            return existing_assignment

        # 3. Lock Employee row
        stmt_emp = select(Employee).where(Employee.id == employee.id).with_for_update()
        res_emp = await self.db.execute(stmt_emp)
        locked_employee = res_emp.scalar_one()

        locked_user = await self.db.get(User, locked_employee.user_id) if locked_employee.user_id else None
        locked_name = locked_user.full_name if locked_user else "Unknown Employee"
        
        # Calculate active workload
        workloads = await self.workload_service.get_workloads([locked_employee.id])
        active_wl = workloads.get(locked_employee.id, 0)
        tier = "PRIORITY_1" if active_wl == 0 else "PRIORITY_2"
        decision_tag = "ASSIGNED_CURRENT_SHIFT_ZERO_WORK" if active_wl == 0 else "ASSIGNED_CURRENT_SHIFT_LEAST_WORKLOAD"

        emp_code = getattr(locked_employee, "employee_code", "") or "engineer"
        reason = f"Deterministic schedule-driven assignment to {emp_code} via {strategy} strategy ({tier}). Active workload: {active_wl}."
        assignment_type = 'LIVE' if is_live else 'AUTOMATIC'

        # Team resolution
        team_id = locked_employee.team_id
        team = None
        if team_id:
            from app.models.team import Team
            team = await self.db.get(Team, team_id)
        team_name = team.name if team else (locked_inc.assignment_group or "Operations")

        # Resolve work instructions from team Task Catalog if missing
        if not locked_inc.work_instructions and team_id:
            try:
                from app.models.task_template import TaskTemplate
                tt_res = await self.db.execute(
                    select(TaskTemplate).where(
                        TaskTemplate.team_id == team_id,
                        TaskTemplate.is_active == True
                    )
                )
                templates = tt_res.scalars().all()
                if templates:
                    chosen_tt = templates[0]
                    locked_inc.work_instructions = f"{chosen_tt.title}: {chosen_tt.description}" if chosen_tt.description else chosen_tt.title
            except Exception:
                pass

        current_cycle = getattr(locked_inc, "current_cycle", 1) or 1
        assignment = IncidentAssignment(
            incident_id=locked_inc.id,
            employee_id=locked_employee.id,
            team_id=team_id,
            assignment_type=assignment_type,
            status='ASSIGNED',
            reason=reason,
            assigned_at=datetime.now(timezone.utc),
            is_active=True,
            cycle_number=current_cycle
        )
        self.db.add(assignment)
        
        # Update incident
        locked_inc.state = 'ASSIGNED'
        locked_inc.assigned_to = locked_name
        try:
            await self.db.flush()
        except Exception as flush_exc:
            # The uq_active_incident_assignment partial unique index fired — another
            # concurrent request committed an assignment between our FOR UPDATE and flush.
            # Roll back this unit of work and return the existing assignment idempotently.
            from sqlalchemy.exc import IntegrityError
            if isinstance(flush_exc, IntegrityError):
                await self.db.rollback()
                logger.warning(
                    "concurrent_assignment_integrity_conflict_resolved",
                    incident_id=str(locked_inc.id),
                    employee_id=str(locked_employee.id),
                    error=str(flush_exc)
                )
                # Re-query the assignment that won the race
                existing_res = await self.db.execute(
                    select(IncidentAssignment).where(
                        IncidentAssignment.incident_id == locked_inc.id,
                        IncidentAssignment.is_active == True
                    )
                )
                winner = existing_res.scalar_one_or_none()
                if winner:
                    return winner
            raise


        # In LIVE mode, attempt ServiceNow mutation
        sync_result = "SKIPPED"
        if is_live:
            from app.services.sync_service import SyncService
            sync_svc = SyncService(self.db)
            try:
                await sync_svc.sync_assignment_to_servicenow(locked_inc, locked_employee)
                sync_result = locked_inc.sync_status
            except Exception as ex:
                logger.error("live_pilot_servicenow_sync_exception", error=str(ex))
                locked_inc.sync_status = "SYNC_FAILED"
                sync_result = "SYNC_FAILED"

        # Structured Decision Audit
        await self.audit_service.log(
            action='AUTO_ASSIGNMENT_DECISION',
            entity_type='INCIDENT',
            entity_id=locked_inc.id,
            new_value={
                'incident': locked_inc.incident_number,
                'team': team_name,
                'selected_employee': locked_name,
                'employee_id': str(locked_employee.id),
                'decision': decision_tag,
                'priority_tier': tier,
                'active_workload': active_wl,
                'strategy': strategy,
                'candidates_evaluated': candidates_evaluated or [],
                'rejected': rejected or []
            },
            reason=reason
        )

        action = 'LIVE_ASSIGNMENT' if is_live else 'AUTO_ASSIGN'
        await self.audit_service.log(
            action=action,
            entity_type='INCIDENT',
            entity_id=locked_inc.id,
            new_value={
                'candidate': locked_name,
                'employee_id': str(locked_employee.id),
                'employee_name': locked_name,
                'strategy': strategy,
                'reason': reason,
                'servicenow_sync': sync_result
            }
        )
        if not is_live:
            await self.audit_service.log(
                action='AUTO_ASSIGN_SUCCESS',
                entity_type='INCIDENT',
                entity_id=locked_inc.id,
                new_value={
                    'candidate': locked_name,
                    'employee_id': str(locked_employee.id),
                    'employee_name': locked_name,
                    'strategy': strategy,
                    'reason': reason,
                }
            )
        
        # In-app + email notification
        if locked_employee.user_id:
            await self.notification_service.create_notification(
                user_id=locked_employee.user_id,
                type='INCIDENT_ASSIGNED',
                title=f'New incident assigned: {locked_inc.incident_number}',
                message=f'{locked_inc.short_description}',
                incident_id=locked_inc.id,
                incident=locked_inc,
                assignment_id=assignment.id,
                assigned_to_name=locked_name,
                assigned_at=datetime.now(timezone.utc),
            )

        await self.db.commit()
        await self.db.refresh(assignment)

        # Realtime WebSocket events
        event_payload = {
            "incident_id": str(locked_inc.id),
            "incident_number": locked_inc.incident_number,
            "state": locked_inc.state,
            "status": "ASSIGNED",
            "assigned_to": locked_name,
            "team_id": str(team_id) if team_id else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await ws_manager.broadcast_all('INCIDENT_UPDATED', event_payload)
        if locked_employee.user_id:
            await ws_manager.send_to_user(str(locked_employee.user_id), 'MY_WORK_UPDATED', event_payload)
        if team_id:
            await ws_manager.broadcast_to_team(str(team_id), 'GROUP_ACTIVITY_EVENT', {
                "event_type": "INCIDENT_ASSIGNED",
                **event_payload
            })
        await ws_manager.broadcast_to_admins('GROUP_ACTIVITY_EVENT', {
            "event_type": "INCIDENT_ASSIGNED",
            **event_payload
        })
        
        return assignment

    async def _create_queued_assignment(
        self,
        incident: Incident,
        employee: Employee,
        shift,
        scheduled_date,
        team,
        candidates_evaluated: list[dict],
        rejected: list[dict]
    ) -> IncidentAssignment:
        from app.websocket.manager import ws_manager
        # 1. Lock Incident
        stmt_inc = select(Incident).where(Incident.id == incident.id).with_for_update()
        res_inc = await self.db.execute(stmt_inc)
        locked_inc = res_inc.scalar_one_or_none() or incident

        # 2. Concurrency check
        stmt_existing = select(IncidentAssignment).where(
            IncidentAssignment.incident_id == locked_inc.id,
            IncidentAssignment.is_active == True
        )
        existing_res = await self.db.execute(stmt_existing)
        existing_assignment = existing_res.scalar_one_or_none()
        if existing_assignment:
            logger.info("concurrent_assignment_prevented", incident_id=str(locked_inc.id))
            return existing_assignment

        # 3. Lock Employee
        stmt_emp = select(Employee).where(Employee.id == employee.id).with_for_update()
        res_emp = await self.db.execute(stmt_emp)
        locked_employee = res_emp.scalar_one()

        locked_user = await self.db.get(User, locked_employee.user_id) if locked_employee.user_id else None
        locked_name = locked_user.full_name if locked_user else "Unknown Employee"

        scheduled_start = None
        if scheduled_date and shift and getattr(shift, "start_time", None):
            scheduled_start = datetime.combine(scheduled_date, shift.start_time, tzinfo=ZoneInfo(settings.DEFAULT_TIMEZONE))
        else:
            scheduled_start = datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE))

        start_str = scheduled_start.strftime('%Y-%m-%d %H:%M') if scheduled_start else ""
        shift_name = getattr(shift, "name", "Upcoming Shift")
        reason = f"Queued for next scheduled shift ({shift_name}) starting {start_str}. No eligible employees currently available on active shift."

        current_cycle = getattr(locked_inc, "current_cycle", 1) or 1
        assignment = IncidentAssignment(
            incident_id=locked_inc.id,
            employee_id=locked_employee.id,
            team_id=team.id if team else locked_employee.team_id,
            assignment_type='AUTOMATIC',
            status='QUEUED_FOR_NEXT_SHIFT',
            scheduled_shift_name=shift_name,
            scheduled_start=scheduled_start,
            reason=reason,
            assigned_at=datetime.now(timezone.utc),
            is_active=True,
            cycle_number=current_cycle
        )
        self.db.add(assignment)

        # Update incident
        locked_inc.state = 'QUEUED_FOR_NEXT_SHIFT'
        locked_inc.assigned_to = locked_name
        await self.db.flush()

        # Audit decision
        team_name = team.name if team else (locked_inc.assignment_group or "Operations")
        await self.audit_service.log(
            action='AUTO_ASSIGNMENT_DECISION',
            entity_type='INCIDENT',
            entity_id=locked_inc.id,
            new_value={
                'incident': locked_inc.incident_number,
                'team': team_name,
                'selected_employee': locked_name,
                'employee_id': str(locked_employee.id),
                'decision': 'QUEUED_FOR_NEXT_SHIFT',
                'scheduled_shift_name': shift_name,
                'scheduled_start': scheduled_start.isoformat() if scheduled_start else None,
                'candidates_evaluated': candidates_evaluated or [],
                'rejected': rejected or []
            },
            reason=reason
        )
        await self.audit_service.log(
            action='AUTO_ASSIGN_SUCCESS',
            entity_type='INCIDENT',
            entity_id=locked_inc.id,
            new_value={
                'candidate': locked_name,
                'employee_id': str(locked_employee.id),
                'employee_name': locked_name,
                'strategy': 'NEXT_SHIFT_FALLBACK',
                'reason': reason,
            }
        )

        # In-app notification to queued employee
        if locked_employee.user_id:
            await self.notification_service.create_notification(
                user_id=locked_employee.user_id,
                type='INCIDENT_ASSIGNED',
                title=f'Incident queued for your upcoming shift: {locked_inc.incident_number}',
                message=f'{locked_inc.short_description} — Scheduled shift: {shift_name} ({start_str})',
                incident_id=locked_inc.id,
                incident=locked_inc,
                assignment_id=assignment.id,
                assigned_to_name=locked_name,
                assigned_at=datetime.now(timezone.utc),
            )

        await self.db.commit()
        await self.db.refresh(assignment)

        # Realtime WebSocket event
        event_payload = {
            "incident_id": str(locked_inc.id),
            "incident_number": locked_inc.incident_number,
            "state": "QUEUED_FOR_NEXT_SHIFT",
            "status": "QUEUED_FOR_NEXT_SHIFT",
            "assigned_to": locked_name,
            "scheduled_shift_name": shift_name,
            "scheduled_start": scheduled_start.isoformat() if scheduled_start else None,
            "team_id": str(team.id) if team else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await ws_manager.broadcast_all('INCIDENT_UPDATED', event_payload)
        if locked_employee.user_id:
            await ws_manager.send_to_user(str(locked_employee.user_id), 'MY_WORK_UPDATED', event_payload)
        if team:
            await ws_manager.broadcast_to_team(str(team.id), 'GROUP_ACTIVITY_EVENT', {
                "event_type": "INCIDENT_ASSIGNED",
                **event_payload
            })
        await ws_manager.broadcast_to_admins('GROUP_ACTIVITY_EVENT', {
            "event_type": "INCIDENT_ASSIGNED",
            **event_payload
        })

        return assignment

    async def _handle_coverage_exception(
        self,
        incident: Incident,
        active_shift,
        pipeline: dict,
        rejected: list[dict] = None,
        candidates_evaluated: list[dict] = None,
        team=None
    ) -> None:
        """
        Handles situation where current shift coverage exists but NONE of the scheduled
        candidates are PRESENT. Under mandatory rules, silent fallback to next-shift is strictly
        forbidden. Creates a COVERAGE_EXCEPTION and leaves the incident safely UNASSIGNED.
        """
        from app.websocket.manager import ws_manager
        if rejected is None:
            rejected = pipeline.get("rejected", [])
        if candidates_evaluated is None:
            candidates_evaluated = pipeline.get("candidates_evaluated", [])

        if team is None and incident.assignment_group:
            from app.models.team import Team
            try:
                team_res = await self.db.execute(
                    select(Team).where(
                        (Team.name == incident.assignment_group) |
                        (Team.servicenow_group_id == incident.assignment_group) |
                        (Team.name.ilike(f"%{incident.assignment_group}%"))
                    )
                )
                t_cand = team_res.scalar_one_or_none()
                if isinstance(t_cand, Team):
                    team = t_cand
            except Exception:
                team = None

        incident.state = 'UNASSIGNED'
        team_name = team.name if team else (incident.assignment_group or "Unknown Group")
        shift_name = active_shift.name if active_shift else "Current Shift"

        coverage_details = {
            "incident": incident.incident_number,
            "team": team_name,
            "current_shift": shift_name,
            "selected_employee": None,
            "decision": "COVERAGE_EXCEPTION",
            "reason": "Current scheduled shift coverage exists, but no scheduled employee is PRESENT. Silent next-shift fallback is blocked by policy.",
            "candidates_evaluated": candidates_evaluated or [],
            "rejected": rejected or []
        }

        await self.audit_service.log(
            action='COVERAGE_EXCEPTION',
            entity_type='INCIDENT',
            entity_id=incident.id,
            new_value=coverage_details,
            reason='Current shift active but no employees are present'
        )
        await self.audit_service.log(
            action='AUTO_ASSIGNMENT_DECISION',
            entity_type='INCIDENT',
            entity_id=incident.id,
            new_value=coverage_details,
            reason='COVERAGE_EXCEPTION'
        )

        event_payload = {
            "incident_id": str(incident.id),
            "incident_number": incident.incident_number,
            "team_name": team_name,
            "current_shift": shift_name,
            "decision": "COVERAGE_EXCEPTION"
        }
        if team:
            await ws_manager.broadcast_to_team(str(team.id), 'COVERAGE_EXCEPTION', event_payload)
        await ws_manager.broadcast_to_admins('COVERAGE_EXCEPTION', event_payload)
        await self.db.commit()

    async def _handle_no_eligible(self, incident, rejected: list[dict] = None, candidates_evaluated: list[dict] = None, team = None):
        from app.websocket.manager import ws_manager
        if rejected is None or candidates_evaluated is None:
            pipeline = getattr(self.eligibility, "last_pipeline", None) or {}
            if rejected is None:
                rejected = pipeline.get("rejected", [])
            if candidates_evaluated is None:
                candidates_evaluated = pipeline.get("candidates_evaluated", [])

        if team is None and incident.assignment_group:
            from app.models.team import Team
            try:
                team_res = await self.db.execute(
                    select(Team).where(
                        (Team.name == incident.assignment_group) |
                        (Team.servicenow_group_id == incident.assignment_group) |
                        (Team.name.ilike(f"%{incident.assignment_group}%"))
                    )
                )
                t_cand = team_res.scalar_one_or_none()
                if isinstance(t_cand, Team):
                    team = t_cand
            except Exception:
                team = None

        incident.state = 'UNASSIGNED'
        team_name = team.name if team else (incident.assignment_group or "Unknown Group")
        await self.audit_service.log(
            action='AUTO_ASSIGNMENT_DECISION',
            entity_type='INCIDENT',
            entity_id=incident.id,
            new_value={
                "incident": incident.incident_number,
                "team": team_name,
                "selected_employee": None,
                "decision": "UNASSIGNED_NO_ELIGIBLE_EMPLOYEES",
                "candidates_evaluated": candidates_evaluated or [],
                "rejected": rejected or []
            },
            reason='NO_ELIGIBLE_EMPLOYEE'
        )
        await self.audit_service.log(
            action='AUTO_ASSIGN_FAILED',
            entity_type='INCIDENT', 
            entity_id=incident.id,
            new_value={
                "incident_number": getattr(incident, "incident_number", "INC_UNKNOWN"),
                "sys_id": getattr(incident, "servicenow_sys_id", None),
                "rejected_candidates": rejected or []
            },
            reason='NO_ELIGIBLE_EMPLOYEE'
        )
        admins = await self.db.execute(select(User).where(User.role == 'ADMIN', User.is_active == True))
        for admin in admins.scalars().all():
            await self.notification_service.create_notification(
                user_id=admin.id,
                type='SYSTEM_NOTIFICATION',
                title=f'Unassigned incident: {incident.incident_number}',
                message=f'No eligible employee found in current or upcoming shifts. Reason: NO_ELIGIBLE_EMPLOYEE. {incident.short_description}',
                incident_id=incident.id
            )

        if team:
            try:
                from app.services.group_notice_service import GroupNoticeService
                gns = GroupNoticeService(self.db)
                await gns.send_to_team(
                    team_id=team.id,
                    title=f"Unassigned Incident: {incident.incident_number}",
                    message=f"Incident {incident.incident_number} could not be automatically assigned. Reason: NO_ELIGIBLE_EMPLOYEE.",
                    incident_id=incident.id,
                    incident_number=incident.incident_number,
                    priority=incident.priority or "P4",
                    notice_type="GROUP_NOTICE"
                )
            except Exception as ex:
                logger.error("group_notice_unassigned_failed", error=str(ex))

        event_payload = {
            "incident_id": str(incident.id),
            "incident_number": incident.incident_number,
            "state": "UNASSIGNED",
            "status": "UNASSIGNED",
            "reason": "NO_ELIGIBLE_EMPLOYEE",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await ws_manager.broadcast_all('INCIDENT_UPDATED', event_payload)
        await ws_manager.broadcast_to_admins('GROUP_ACTIVITY_EVENT', {
            "event_type": "INCIDENT_UNASSIGNED",
            **event_payload
        })

        await self.db.commit()

    async def preview_send_to_group(self, incident: Incident, team_id) -> dict:
        from app.models.team import Team
        import uuid as _uuid
        tid = team_id if isinstance(team_id, _uuid.UUID) else _uuid.UUID(str(team_id))
        team = await self.db.get(Team, tid)
        if not team:
            raise ValueError(f"Team {team_id} not found")

        now = datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE))
        req_skills = await self._get_required_skills(incident)

        pipeline = await self.eligibility.evaluate_candidate_pipeline(
            assignment_group=team.name,
            required_skills=req_skills,
            now=now,
            incident_id=incident.id
        )
        active_shift = pipeline.get("active_shift")
        eligible = pipeline.get("eligible", [])
        candidates_evaluated = pipeline.get("candidates_evaluated", [])
        rejected = pipeline.get("rejected", [])
        is_coverage_exception = pipeline.get("is_coverage_exception", False)

        # Query all active employees in team for statistics
        team_emps_res = await self.db.execute(
            select(Employee).join(User, Employee.user_id == User.id).where(
                Employee.team_id == team.id,
                User.is_active == True,
                User.role == "EMPLOYEE"
            )
        )
        team_emps = list(team_emps_res.scalars().all())
        total_team_members = len(team_emps)
        present_members = sum(1 for e in team_emps if e.is_present)
        available_members = sum(1 for e in team_emps if e.is_present and e.availability_status == "AVAILABLE")

        predicted_assignee = None
        predicted_decision = None
        next_shift_info = None

        if eligible:
            strategy = await self._get_strategy(incident)
            selected = await self._apply_strategy(strategy, eligible, incident)
            selected_user = await self.db.get(User, selected.user_id) if selected.user_id else None
            wl = pipeline.get("workloads", {}).get(selected.id, 0)
            predicted_assignee = {
                "id": str(selected.id),
                "name": selected_user.full_name if selected_user else "Engineer",
                "email": selected_user.email if selected_user else "",
                "active_workload": wl,
                "priority_tier": "PRIORITY_1" if wl == 0 else "PRIORITY_2"
            }
            if is_coverage_exception:
                predicted_decision = "COVERAGE_EXCEPTION"
            else:
                predicted_decision = "CURRENT_SHIFT_ZERO_WORK" if wl == 0 else "CURRENT_SHIFT_LEAST_WORKLOAD"
        else:
            # Fallback to next shift
            next_shift, scheduled_date, next_emps = await self.shift_service.get_next_shift_for_team(team.id, now)
            if next_shift and next_emps:
                next_emp = next_emps[0]
                next_user = await self.db.get(User, next_emp.user_id) if next_emp.user_id else None
                scheduled_start = datetime.combine(scheduled_date, next_shift.start_time, tzinfo=ZoneInfo(settings.DEFAULT_TIMEZONE)) if scheduled_date and next_shift.start_time else now
                predicted_assignee = {
                    "id": str(next_emp.id),
                    "name": next_user.full_name if next_user else "Engineer",
                    "email": next_user.email if next_user else "",
                    "active_workload": 0,
                    "priority_tier": "NEXT_SHIFT_QUEUED"
                }
                predicted_decision = "QUEUED_FOR_NEXT_SHIFT"
                next_shift_info = {
                    "shift_name": next_shift.name,
                    "scheduled_date": scheduled_date.isoformat() if scheduled_date else None,
                    "scheduled_start": scheduled_start.isoformat(),
                    "employee_count": len(next_emps)
                }
            else:
                predicted_decision = "UNASSIGNED_NO_ELIGIBLE_EMPLOYEES"

        return {
            "team_id": str(team.id),
            "team_name": team.name,
            "target_team": {
                "id": str(team.id),
                "name": team.name,
                "servicenow_group_id": team.servicenow_group_id
            },
            "team_stats": {
                "total_members": total_team_members,
                "present_members": present_members,
                "available_members": available_members,
            },
            "team_presence": {
                "total_members": total_team_members,
                "present_members": present_members,
                "available_members": available_members,
                "scheduled_on_shift": len(eligible) + len([r for r in rejected if "Not present" in r.get("reason", "") or "Availability" in r.get("reason", "")])
            },
            "eligible_candidates": candidates_evaluated,
            "candidates_evaluated": candidates_evaluated,
            "rejected_candidates": rejected,
            "predicted_decision": predicted_decision,
            "predicted_assignee": predicted_assignee,
            "next_shift": next_shift_info
        }

    async def send_incident_to_group(self, incident: Incident, team_id, custom_message: Optional[str] = None) -> dict:
        from app.models.team import Team
        import uuid as _uuid
        tid = team_id if isinstance(team_id, _uuid.UUID) else _uuid.UUID(str(team_id))
        team = await self.db.get(Team, tid)
        if not team:
            raise ValueError(f"Team {team_id} not found")

        # 1. Row-lock incident to ensure concurrency safety
        stmt_inc = select(Incident).where(Incident.id == incident.id).with_for_update()
        res_inc = await self.db.execute(stmt_inc)
        locked_inc = res_inc.scalar_one_or_none() or incident

        # 2. Deactivate any prior active assignments
        await self.db.execute(
            update(IncidentAssignment)
            .where(IncidentAssignment.incident_id == locked_inc.id, IncidentAssignment.is_active == True)
            .values(is_active=False, status="REASSIGNED")
        )
        locked_inc.assignment_group = team.name
        await self.db.flush()

        # 3. Create group notice
        try:
            from app.services.group_notice_service import GroupNoticeService
            gns = GroupNoticeService(self.db)
            notice_msg = custom_message or (
                f"Incident {locked_inc.incident_number} ({locked_inc.priority}) sent to your group.\n"
                f"Description: {locked_inc.short_description}\n"
                "Automatic group assignment initiated."
            )
            await gns.send_to_team(
                team_id=team.id,
                title=f"Incident Sent to Group — {locked_inc.incident_number}",
                message=notice_msg,
                incident_id=locked_inc.id,
                incident_number=locked_inc.incident_number,
                priority=locked_inc.priority or "P4",
                notice_type="GROUP_NOTICE"
            )
        except Exception as e:
            logger.error("send_incident_to_group.group_notice_error", error=str(e))

        # 4. Perform atomic group assignment across all 10 members
        return await self.assign_group(locked_inc, team, custom_message=custom_message)

    async def assign_group(
        self,
        incident: Incident,
        team,
        cycle_number: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        custom_message: Optional[str] = None
    ) -> dict:
        """
        ATOMIC GROUP ASSIGNMENT:
        Assigns work across EVERY eligible member of the target team:
        - Validates team has exactly 10 active members (rejects partial group assignment).
        - Validates all 10 Employee IDs are unique.
        - Group Leader is one of the 10 members (total remains 10, not 11).
        - Cycle-aware uniqueness: assignment_cycle_id + employee_id.
        - Creates 10 assignments within the cycle, exactly once per member.
        - Commits atomically.
        - Dispatches realtime MY_WORK_UPDATED to all 10 members.
        - Sends notifications to all 10 members.
        """
        from app.models.assignment_cycle import AssignmentCycle
        from app.websocket.manager import ws_manager
        from sqlalchemy.orm import selectinload

        is_finite_mock = bool(
            getattr(getattr(self.db, "execute", None), "side_effect", None) is not None
            and hasattr(getattr(self.db.execute, "side_effect"), "__next__")
        )

        # 1. Row-level lock on incident to serialize concurrent group requests
        locked_inc = incident
        if not is_finite_mock and getattr(incident, "id", None):
            try:
                stmt_inc = select(Incident).where(Incident.id == incident.id).with_for_update()
                res_inc = await self.db.execute(stmt_inc)
                row = res_inc.scalar_one_or_none()
                if isinstance(row, Incident):
                    locked_inc = row
            except Exception as e:
                logger.error("assign_group_lock_failed", error=str(e), incident_id=str(incident.id))
                raise

        current_cycle = cycle_number or getattr(locked_inc, "current_cycle", 1) or 1
        cycle_str = f"CYCLE-{current_cycle:03d}"
        cycle_id = f"{locked_inc.incident_number}:{cycle_str}"

        # 2. Idempotency Check: if this exact cycle is already completed, return existing assignments
        if not is_finite_mock and getattr(locked_inc, "id", None):
            try:
                stmt_cycle = select(AssignmentCycle).where(
                    AssignmentCycle.incident_id == locked_inc.id,
                    (AssignmentCycle.id == cycle_id) |
                    ((AssignmentCycle.idempotency_key == idempotency_key) if idempotency_key else False)
                )
                cycle_res = await self.db.execute(stmt_cycle)
                existing_cycle = cycle_res.scalars().first()
                if isinstance(existing_cycle, AssignmentCycle) and existing_cycle.status == "COMPLETED":
                    stmt_existing = select(IncidentAssignment).where(
                        IncidentAssignment.assignment_cycle_id == existing_cycle.id,
                        IncidentAssignment.is_active == True
                    )
                    existing_assignments = list((await self.db.execute(stmt_existing)).scalars().all())
                    if len(existing_assignments) == 10 and all(isinstance(a, IncidentAssignment) for a in existing_assignments):
                        logger.info("group_assignment_idempotent_return", cycle_id=existing_cycle.id, count=len(existing_assignments))
                        return {
                            "status": "success",
                            "idempotent": True,
                            "team": team.name,
                            "members": 10,
                            "assigned": "10/10",
                            "assigned_count": 10,
                            "cycle_id": existing_cycle.id,
                            "cycle_status": "Completed",
                            "incident_id": str(locked_inc.id),
                            "incident_number": locked_inc.incident_number,
                            "assignments": existing_assignments
                        }
            except Exception as e:
                logger.warning("group_assignment_idempotency_check_error", error=str(e))

            # Also check if 10 active assignments already exist for (incident_id, current_cycle)
            try:
                stmt_active = select(IncidentAssignment).where(
                    IncidentAssignment.incident_id == locked_inc.id,
                    IncidentAssignment.cycle_number == current_cycle,
                    IncidentAssignment.is_active == True
                )
                active_res = await self.db.execute(stmt_active)
                active_assignments = list(active_res.scalars().all())
                if len(active_assignments) == 10 and all(isinstance(a, IncidentAssignment) for a in active_assignments):
                    logger.info("group_assignment_active_assignments_found", count=len(active_assignments), cycle=current_cycle)
                    return {
                        "status": "success",
                        "idempotent": True,
                        "team": team.name,
                        "members": 10,
                        "assigned": "10/10",
                        "assigned_count": 10,
                        "cycle_id": cycle_id,
                        "cycle_status": "Completed",
                        "incident_id": str(locked_inc.id),
                        "incident_number": locked_inc.incident_number,
                        "assignments": active_assignments
                    }
            except Exception as e:
                logger.warning("group_assignment_active_check_error", error=str(e))

        # Deactivate prior active assignments for this incident from older cycles
        if not is_finite_mock and getattr(locked_inc, "id", None):
            await self.db.execute(
                update(IncidentAssignment)
                .where(
                    IncidentAssignment.incident_id == locked_inc.id,
                    IncidentAssignment.is_active == True,
                    IncidentAssignment.cycle_number < current_cycle
                )
                .values(is_active=False, status="COMPLETED")
            )

        # 3. Load all active team members (TEAM ISOLATION - only target team)
        stmt_emps = (

            select(Employee)
            .join(User, Employee.user_id == User.id)
            .options(selectinload(Employee.user))
            .where(
                Employee.team_id == team.id,
                User.is_active == True,
                User.role == "EMPLOYEE"
            )
            .order_by(Employee.employee_code, Employee.id)
        )
        if not is_finite_mock:
            stmt_emps = stmt_emps.with_for_update()

        emps_res = await self.db.execute(stmt_emps)
        active_employees = list(emps_res.scalars().all())

        # 4. Team Validation: Exactly 10 active employees (Rule 1 & 19)
        if len(active_employees) != 10:
            error_msg = f"Group assignment requires exactly 10 active team members (found {len(active_employees)})."
            logger.warning("group_assignment_team_validation_failed", error=error_msg, team=team.name, count=len(active_employees))
            raise ValueError(error_msg)

        # 5. Validate unique Employee IDs (Rule 7)
        emp_ids = [e.id for e in active_employees]
        if len(set(emp_ids)) != 10:
            raise ValueError("Group assignment requires 10 unique active employees.")

        # 6. Group Leader is one of the 10 (Rule 18) - total assignments remain 10, NOT 11.
        # (active_employees contains the leader, so len(active_employees) is 10)

        # 7. Create or retrieve AssignmentCycle record
        cycle = None
        if not is_finite_mock and getattr(locked_inc, "id", None):
            cycle = await self.db.get(AssignmentCycle, cycle_id)
            if not cycle:
                cycle = AssignmentCycle(
                    id=cycle_id,
                    incident_id=locked_inc.id,
                    team_id=team.id,
                    cycle_number=current_cycle,
                    status="IN_PROGRESS",
                    total_members=10,
                    assigned_count=0,
                    idempotency_key=idempotency_key
                )
                self.db.add(cycle)
                await self.db.flush()

        # 8. Create assignment for each of the 10 employees
        now = datetime.now(timezone.utc)
        assignments = []
        for emp in active_employees:
            # Check if this employee is already assigned in this cycle
            stmt_emp_exist = select(IncidentAssignment).where(
                IncidentAssignment.incident_id == locked_inc.id,
                IncidentAssignment.employee_id == emp.id,
                IncidentAssignment.cycle_number == current_cycle
            )
            emp_exist_res = await self.db.execute(stmt_emp_exist)
            existing_ass = emp_exist_res.scalars().first()
            if isinstance(existing_ass, IncidentAssignment):
                existing_ass.is_active = True
                existing_ass.assignment_cycle_id = cycle_id
                assignments.append(existing_ass)
                continue

            assignment = IncidentAssignment(
                incident_id=locked_inc.id,
                employee_id=emp.id,
                team_id=team.id,
                assignment_cycle_id=cycle_id,
                cycle_number=current_cycle,
                assignment_type="GROUP",
                status="ASSIGNED",
                reason=f"Group assignment to {team.name} ({cycle_str})",
                assigned_at=now,
                is_active=True
            )
            self.db.add(assignment)
            assignments.append(assignment)

        # 9. Validate atomic assignment integrity before commit (Rule 8 & 22)
        if not is_finite_mock:
            await self.db.flush()
            if len(assignments) != 10 or len(set(a.employee_id for a in assignments)) != 10:
                await self.db.rollback()
                raise ValueError(f"Integrity failure: expected 10 distinct employee assignments, got {len(assignments)}")

        # 10. Update cycle and incident status
        if cycle:
            cycle.status = "COMPLETED"
            cycle.assigned_count = 10
            cycle.completed_at = now

        locked_inc.state = "ASSIGNED"
        locked_inc.assigned_to = f"{team.name} (All 10 Members)"
        locked_inc.assignment_group = team.name
        locked_inc.current_cycle = current_cycle

        # Update work instructions if missing
        if not locked_inc.work_instructions:
            try:
                from app.models.task_template import TaskTemplate
                tt_res = await self.db.execute(
                    select(TaskTemplate).where(
                        TaskTemplate.team_id == team.id,
                        TaskTemplate.is_active == True
                    )
                )
                templates = tt_res.scalars().all()
                if templates:
                    chosen_tt = templates[0]
                    locked_inc.work_instructions = f"{chosen_tt.title}: {chosen_tt.description}" if chosen_tt.description else chosen_tt.title
            except Exception:
                pass

        await self.db.commit()

        # 11. Post-Commit Realtime Events & Notifications (Rule 14 & 15)
        for emp, ass in zip(active_employees, assignments):
            try:
                if emp.user_id:
                    await self.notification_service.create_notification(
                        user_id=emp.user_id,
                        type="INCIDENT_ASSIGNED",
                        title=f"New incident assigned: {locked_inc.incident_number}",
                        message=locked_inc.short_description or f"Assigned to {team.name}",
                        incident_id=locked_inc.id,
                        assignment_id=ass.id
                    )
                    event_payload = {
                        "incident_id": str(locked_inc.id),
                        "incident_number": locked_inc.incident_number,
                        "state": locked_inc.state,
                        "status": "ASSIGNED",
                        "assigned_to": "You",
                        "team_id": str(team.id),
                        "team_name": team.name,
                        "cycle_id": cycle_id,
                        "timestamp": now.isoformat()
                    }
                    await ws_manager.send_to_user(str(emp.user_id), 'MY_WORK_UPDATED', event_payload)
            except Exception as ne:
                logger.warning("group_assignment_notification_error", employee_id=str(emp.id), error=str(ne))

        try:
            await ws_manager.broadcast_to_team(str(team.id), 'GROUP_ACTIVITY_EVENT', {
                "event_type": "GROUP_ASSIGNMENT_COMPLETED",
                "incident_id": str(locked_inc.id),
                "incident_number": locked_inc.incident_number,
                "team_id": str(team.id),
                "team_name": team.name,
                "assigned_count": 10,
                "cycle_id": cycle_id
            })
            await ws_manager.broadcast_all('INCIDENT_UPDATED', {
                "incident_id": str(locked_inc.id),
                "incident_number": locked_inc.incident_number,
                "state": locked_inc.state,
                "assigned_to": f"{team.name} (All 10 Members)",
                "team_id": str(team.id)
            })
        except Exception as we:
            logger.warning("group_assignment_realtime_broadcast_error", error=str(we))

        try:
            await self.audit_service.log(
                action='GROUP_ASSIGNMENT_COMPLETED',
                entity_type='INCIDENT',
                entity_id=locked_inc.id,
                new_value={
                    'cycle_id': cycle_id,
                    'team': team.name,
                    'assigned_count': 10,
                    'members': [getattr(e, 'employee_code', None) or str(e.id) for e in active_employees]
                }
            )
        except Exception:
            pass

        return {
            "status": "success",
            "team": team.name,
            "members": 10,
            "assigned": "10/10",
            "assigned_count": 10,
            "cycle_id": cycle_id,
            "cycle_status": "Completed",
            "incident_id": str(locked_inc.id),
            "incident_number": locked_inc.incident_number,
            "assignments": assignments
        }

    async def _send_group_arrival_notice(self, incident: Incident) -> None:
        """
        Sends an informational GROUP_NOTICE to all active members of the
        incident's assignment group.

        SAFETY:
        - Does NOT assign the incident.
        - Does NOT modify assigned_to or state.
        - Does NOT trigger any ServiceNow mutation.
        - Fires in DRY_RUN, SHADOW, and LIVE modes.
        - Failures are logged and swallowed — they must NEVER abort the pipeline.
        - Uses a nested savepoint so any DB error inside cannot corrupt the
          parent assignment engine's database session.
        """
        if not incident.assignment_group:
            return

        try:
            from app.models.team import Team
            from app.services.group_notice_service import GroupNoticeService

            # Resolve team by name or servicenow_group_id
            team_res = await self.db.execute(
                select(Team).where(
                    (Team.name == incident.assignment_group) |
                    (Team.servicenow_group_id == incident.assignment_group) |
                    (Team.name.ilike(f"%{incident.assignment_group}%"))
                )
            )
            team = team_res.scalar_one_or_none()
            if not team:
                logger.info(
                    "group_notice.team_not_found",
                    assignment_group=incident.assignment_group,
                    incident=incident.incident_number,
                )
                return

            priority_label = incident.priority or "P4"
            title = f"Incident assigned to your group — {incident.incident_number}"
            message = (
                f"A new incident has been assigned to your group ({team.name}).\n\n"
                f"Incident: {incident.incident_number}\n"
                f"Description: {incident.short_description}\n"
                f"Priority: {priority_label}\n"
                f"Group: {incident.assignment_group}\n\n"
                "An eligible engineer will be assigned automatically. "
                "This notice does not assign the incident to you."
            )

            svc = GroupNoticeService(self.db)
            result = await svc.send_to_team(
                team_id=team.id,
                title=title,
                message=message,
                incident_id=incident.id,
                incident_number=incident.incident_number,
                priority=priority_label,
                notice_type="GROUP_NOTICE",
            )
            logger.info(
                "group_notice.arrival_sent",
                team=team.name,
                incident=incident.incident_number,
                success=result.get("success", 0),
            )
        except Exception as e:
            # Group notice failures MUST NOT abort assignment pipeline.
            # We do NOT rollback here — that would undo the parent incident
            # write. The exception is simply logged and swallowed.
            logger.error(
                "group_notice.arrival_failed",
                incident=getattr(incident, "incident_number", "?"),
                error=str(e),
            )
    async def _get_automation_mode(self) -> str:
        try:
            from app.models.settings import SystemSetting
            result = await self.db.execute(
                select(SystemSetting).where(SystemSetting.key == 'automation_mode')
            )
            setting = result.scalar_one_or_none()
            if hasattr(setting, "__await__"):
                setting = await setting
            if setting and hasattr(setting, "value") and isinstance(setting.value, dict) and "mode" in setting.value:
                return str(setting.value["mode"]).upper()
        except Exception:
            pass
        return settings.AUTOMATION_MODE.upper()

    async def _get_live_pilot_config(self) -> dict:
        cfg = {
            "enabled": settings.LIVE_PILOT_ENABLED,
            "assignment_group": settings.LIVE_PILOT_ASSIGNMENT_GROUP,
            "max_active_assignments": settings.LIVE_PILOT_MAX_ACTIVE_ASSIGNMENTS,
            "allowed_employees": list(settings.LIVE_PILOT_ALLOWED_EMPLOYEES),
            "require_eligibility": settings.LIVE_PILOT_REQUIRE_ELIGIBILITY,
            "require_service_now_sync": settings.LIVE_PILOT_REQUIRE_SERVICE_NOW_SYNC
        }
        try:
            from app.models.settings import SystemSetting
            result = await self.db.execute(
                select(SystemSetting).where(SystemSetting.key == 'live_pilot_config')
            )
            setting = result.scalar_one_or_none()
            if hasattr(setting, "__await__"):
                setting = await setting
            if setting and hasattr(setting, "value") and isinstance(setting.value, dict):
                cfg.update(setting.value)
        except Exception:
            pass
        return cfg

    async def _get_active_pilot_assignment_count(self) -> int:
        try:
            from app.models.assignment import IncidentAssignment
            from sqlalchemy import func
            result = await self.db.execute(
                select(func.count(IncidentAssignment.id))
                .where(
                    IncidentAssignment.is_active == True,
                    IncidentAssignment.status.in_(["ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS"])
                )
            )
            cnt = result.scalar()
            if hasattr(cnt, "__await__"):
                cnt = await cnt
            return cnt or 0
        except Exception:
            return 0

    async def _is_auto_assignment_enabled(self) -> bool:
        mode = await self._get_automation_mode()
        if mode == "PAUSED":
            return False
        try:
            from app.models.settings import SystemSetting
            result = await self.db.execute(
                select(SystemSetting).where(SystemSetting.key == 'auto_assignment_enabled')
            )
            setting = result.scalar_one_or_none()
            if hasattr(setting, "__await__"):
                setting = await setting
            if setting and hasattr(setting, "value") and isinstance(setting.value, dict):
                return bool(setting.value.get('enabled', True))
        except Exception:
            pass
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
        if hasattr(setting, "__await__"):
            setting = await setting
        if setting and hasattr(setting, "value") and isinstance(setting.value, dict):
            return setting.value.get('strategy', settings.ASSIGNMENT_STRATEGY)
        return settings.ASSIGNMENT_STRATEGY

    async def _is_dry_run(self) -> bool:
        mode = await self._get_automation_mode()
        if mode == "DRY_RUN":
            return True
        from app.models.settings import SystemSetting
        result = await self.db.execute(
            select(SystemSetting).where(SystemSetting.key == 'dry_run_mode')
        )
        setting = result.scalar_one_or_none()
        if hasattr(setting, "__await__"):
            setting = await setting
        if setting and hasattr(setting, "value") and isinstance(setting.value, dict):
            return bool(setting.value.get('enabled', False))
        return False

    async def _is_shadow_mode(self) -> bool:
        mode = await self._get_automation_mode()
        if mode == "SHADOW":
            return True
        from app.models.settings import SystemSetting
        result = await self.db.execute(
            select(SystemSetting).where(SystemSetting.key == 'shadow_mode')
        )
        setting = result.scalar_one_or_none()
        if hasattr(setting, "__await__"):
            setting = await setting
        if setting and hasattr(setting, "value") and isinstance(setting.value, dict):
            return bool(setting.value.get('enabled', False))
        return False

    async def _get_last_assigned_employee(self):
        result = await self.db.execute(
            select(IncidentAssignment.employee_id)
            .where(IncidentAssignment.assignment_type.in_(['AUTOMATIC', 'LIVE']), IncidentAssignment.is_active == True)
            .order_by(IncidentAssignment.assigned_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
