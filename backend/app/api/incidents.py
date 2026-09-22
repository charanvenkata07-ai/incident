import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.audit import AuditLog
from app.services.audit_service import AuditService
from app.services.sync_service import SyncService
from app.websocket.manager import ws_manager
from datetime import datetime, timezone



router = APIRouter()

async def _get_incident_team_id(db: AsyncSession, inc: Optional[Incident], current_user: User) -> Optional[uuid.UUID]:
    if inc and inc.assignment_group:
        t_res = await db.execute(select(Team.id).where(Team.name == inc.assignment_group))
        team_id = t_res.scalar_one_or_none()
        if team_id:
            return team_id
    emp_res = await db.execute(select(Employee.team_id).where(Employee.user_id == current_user.id))
    return emp_res.scalar_one_or_none()

async def _verify_assignment_access(incident_id: str, current_user: User, db: AsyncSession) -> IncidentAssignment:
    """Helper to verify that active assignment exists and current_user has authorization to modify it."""
    inc_uuid = None
    try:
        inc_uuid = incident_id if isinstance(incident_id, uuid.UUID) else uuid.UUID(str(incident_id))
    except Exception:
        inc_res = await db.execute(select(Incident).where(Incident.incident_number == str(incident_id)))
        inc_obj = inc_res.scalar_one_or_none()
        if inc_obj:
            inc_uuid = inc_obj.id
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    emp = None
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        emp_res = await db.execute(select(Employee).where(Employee.user_id == current_user.id))
        emp = emp_res.scalar_one_or_none()
        if not emp:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: Employee profile not found")

    # Look up active assignment (scoped to employee if non-admin)
    query = select(IncidentAssignment).where(
        IncidentAssignment.incident_id == inc_uuid,
        IncidentAssignment.is_active == True
    )
    if emp:
        query = query.where(IncidentAssignment.employee_id == emp.id)
    result = await db.execute(query)
    assignment = result.scalars().first()

    if not assignment:
        completed_query = select(IncidentAssignment).where(
            IncidentAssignment.incident_id == inc_uuid
        )
        if emp:
            completed_query = completed_query.where(IncidentAssignment.employee_id == emp.id)
        completed_res = await db.execute(
            completed_query.order_by(IncidentAssignment.assigned_at.desc())
        )
        latest_assignment = completed_res.scalars().first()
        if latest_assignment and latest_assignment.status == 'COMPLETED':
            assignment = latest_assignment

    if not assignment and emp:
        # If in SHADOW mode, and this user was the recommended candidate, provision shadow assignment on explicit action
        inc = await db.get(Incident, inc_uuid)
        if inc:
            shadow_log = await db.execute(
                select(AuditLog).where(
                    AuditLog.action == 'SHADOW_ASSIGN',
                    AuditLog.entity_id == inc.id
                ).order_by(AuditLog.created_at.desc())
            )
            latest_shadow = shadow_log.scalars().first()
            if latest_shadow and latest_shadow.new_value and latest_shadow.new_value.get("recommended") == str(emp.id):
                assignment = IncidentAssignment(
                    incident_id=inc.id,
                    employee_id=emp.id,
                    assignment_type="SHADOW",
                    status="ASSIGNED",
                    reason="Shadow candidate accepted assignment",
                    assigned_at=datetime.now(timezone.utc),
                    is_active=True
                )
                db.add(assignment)
                inc.assigned_to = current_user.full_name
                await db.flush()

    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active assignment not found")


    if current_user.role not in ("ADMIN", "SUPERVISOR") and emp and assignment.employee_id != emp.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not assigned to this incident"
        )
    return assignment



@router.get("/{incident_number}")
async def get_incident(incident_number: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Incident).where(Incident.incident_number == incident_number))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        
    # IDOR check: Non-admin/supervisor users can only view incidents assigned to them
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        emp_res = await db.execute(select(Employee).where(Employee.user_id == current_user.id))
        emp = emp_res.scalar_one_or_none()
        if not emp:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: Not authorized to view this incident")

        assign_res = await db.execute(
            select(IncidentAssignment).where(
                IncidentAssignment.incident_id == incident.id,
                IncidentAssignment.employee_id == emp.id
            )
        )
        has_assignment = assign_res.scalars().first() is not None
        is_assigned_name = bool(
            incident.assigned_to and (
                incident.assigned_to.strip().lower() == current_user.full_name.strip().lower()
                or incident.assigned_to.strip().lower() == current_user.email.strip().lower()
            )
        )
        is_shadow_candidate = False
        if not (has_assignment or is_assigned_name):
            try:

                shadow_log = await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == 'SHADOW_ASSIGN',
                        AuditLog.entity_id == incident.id
                    ).order_by(AuditLog.created_at.desc())
                )
                latest_shadow = shadow_log.scalars().first()
                if latest_shadow and latest_shadow.new_value and latest_shadow.new_value.get("recommended") == str(emp.id):
                    is_shadow_candidate = True
            except Exception:
                pass

        if not (has_assignment or is_assigned_name or is_shadow_candidate):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: You are not assigned to this incident")

    audit_service = AuditService(db)
    timeline = await audit_service.get_entity_timeline('INCIDENT', incident.id)
    
    return {"incident": incident, "timeline": timeline}

@router.post("/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    assignment = await _verify_assignment_access(incident_id, current_user, db)
    inc = await db.get(Incident, assignment.incident_id)

    # Idempotent check: if already acknowledged, do not duplicate audit logs or broadcasts
    if assignment.status == 'ACKNOWLEDGED':
        if inc and inc.state != 'ACKNOWLEDGED':
            inc.state = 'ACKNOWLEDGED'
            await db.commit()
        return {
            "status": "success",
            "message": "Incident already acknowledged",
            "incident_number": inc.incident_number if inc else None,
            "state": "ACKNOWLEDGED",
            "assignment_status": "ACKNOWLEDGED",
            "timestamp": assignment.acknowledged_at.isoformat() if assignment.acknowledged_at else None
        }

    now = datetime.now(timezone.utc)
    assignment.status = 'ACKNOWLEDGED'
    assignment.acknowledged_at = now
    if inc:
        inc.state = 'ACKNOWLEDGED'

    audit_service = AuditService(db)
    await audit_service.log('INCIDENT_ACKNOWLEDGED', 'INCIDENT', assignment.incident_id, actor_id=current_user.id)
    
    await db.commit()

    event_payload = {
        "incident_id": str(assignment.incident_id),
        "incident_number": inc.incident_number if inc else None,
        "status": "ACKNOWLEDGED",
        "state": "ACKNOWLEDGED",
        "assignment_status": "ACKNOWLEDGED",
        "actor_name": current_user.full_name,
        "timestamp": assignment.acknowledged_at.isoformat()
    }
    await ws_manager.broadcast_all('INCIDENT_UPDATED', event_payload)
    await ws_manager.send_to_user(str(current_user.id), 'MY_WORK_UPDATED', event_payload)

    target_team_id = await _get_incident_team_id(db, inc, current_user)
    if target_team_id:
        await ws_manager.broadcast_to_team(str(target_team_id), 'GROUP_ACTIVITY_EVENT', {
            "event_type": "INCIDENT_STATUS_CHANGE",
            **event_payload
        })
    await ws_manager.broadcast_to_admins('GROUP_ACTIVITY_EVENT', {
        "event_type": "INCIDENT_STATUS_CHANGE",
        **event_payload
    })
    return {
        "status": "success",
        "incident_number": inc.incident_number if inc else None,
        "state": "ACKNOWLEDGED",
        "assignment_status": "ACKNOWLEDGED",
        "timestamp": assignment.acknowledged_at.isoformat()
    }

@router.post("/{incident_id}/start")
async def start_incident(incident_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    assignment = await _verify_assignment_access(incident_id, current_user, db)
        
    now = datetime.now(timezone.utc)
    assignment.status = 'IN_PROGRESS'
    assignment.started_at = now
    
    result_inc = await db.execute(select(Incident).where(Incident.id == assignment.incident_id))
    incident = result_inc.scalar_one_or_none()
    if incident:
        incident.state = 'IN_PROGRESS'
    
    audit_service = AuditService(db)
    await audit_service.log('INCIDENT_STARTED', 'INCIDENT', assignment.incident_id, actor_id=current_user.id)
    
    await db.commit()

    event_payload = {
        "incident_id": str(assignment.incident_id),
        "incident_number": incident.incident_number if incident else None,
        "status": "IN_PROGRESS",
        "actor_name": current_user.full_name,
        "timestamp": now.isoformat()
    }
    await ws_manager.broadcast_all('INCIDENT_UPDATED', event_payload)
    await ws_manager.send_to_user(str(current_user.id), 'MY_WORK_UPDATED', event_payload)

    target_team_id = await _get_incident_team_id(db, incident, current_user)
    if target_team_id:
        await ws_manager.broadcast_to_team(str(target_team_id), 'GROUP_ACTIVITY_EVENT', {
            "event_type": "INCIDENT_STATUS_CHANGE",
            **event_payload
        })
    await ws_manager.broadcast_to_admins('GROUP_ACTIVITY_EVENT', {
        "event_type": "INCIDENT_STATUS_CHANGE",
        **event_payload
    })
    return {"status": "success"}

@router.post("/{incident_id}/complete")
async def complete_incident(incident_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    assignment = await _verify_assignment_access(incident_id, current_user, db)
    if assignment.status == 'COMPLETED':
        result_inc = await db.execute(select(Incident).where(Incident.id == assignment.incident_id))
        incident = result_inc.scalar_one_or_none()
        return {
            "status": "success",
            "message": "Incident assignment is already completed",
            "incident_number": incident.incident_number if incident else None,
            "state": incident.state if incident else "RESOLVED",
            "assignment_status": "COMPLETED"
        }

    now = datetime.now(timezone.utc)
    assignment.status = 'COMPLETED'
    assignment.is_active = False
    assignment.completed_at = now
    
    result_inc = await db.execute(select(Incident).where(Incident.id == assignment.incident_id))
    incident = result_inc.scalar_one_or_none()
    if incident:
        incident.state = 'RESOLVED'
        incident.resolved_at = now
    
    audit_service = AuditService(db)
    await audit_service.log('INCIDENT_COMPLETED', 'INCIDENT', assignment.incident_id, actor_id=current_user.id)
    
    await db.commit()

    event_payload = {
        "incident_id": str(assignment.incident_id),
        "incident_number": incident.incident_number if incident else None,
        "status": "COMPLETED",
        "state": "RESOLVED",
        "assignment_status": "COMPLETED",
        "actor_name": current_user.full_name,
        "employee_name": current_user.full_name,
        "completed_at": now.isoformat(),
        "timestamp": now.isoformat()
    }
    await ws_manager.broadcast_all('INCIDENT_UPDATED', event_payload)
    await ws_manager.broadcast_all('INCIDENT_COMPLETED', event_payload)
    await ws_manager.broadcast_all('MY_WORK_UPDATED', event_payload)

    target_team_id = await _get_incident_team_id(db, incident, current_user)
    if target_team_id:
        await ws_manager.broadcast_to_team(str(target_team_id), 'GROUP_ACTIVITY_EVENT', {
            "event_type": "INCIDENT_STATUS_CHANGE",
            **event_payload
        })
    await ws_manager.broadcast_to_admins('GROUP_ACTIVITY_EVENT', {
        "event_type": "INCIDENT_STATUS_CHANGE",
        **event_payload
    })
    return {
        "status": "success",
        "message": "Incident completed successfully",
        "incident_number": incident.incident_number if incident else None,
        "state": "RESOLVED",
        "assignment_status": "COMPLETED"
    }

@router.get("/{incident_number}/lifecycle")
async def get_incident_lifecycle(incident_number: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Incident).where(Incident.incident_number == incident_number))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        emp_res = await db.execute(select(Employee).where(Employee.user_id == current_user.id))
        emp = emp_res.scalar_one_or_none()
        if not emp:
            raise HTTPException(status_code=403, detail="Not authorized")
        assign_res = await db.execute(select(IncidentAssignment).where(IncidentAssignment.incident_id == incident.id, IncidentAssignment.employee_id == emp.id))
        if not assign_res.scalars().first():
            raise HTTPException(status_code=403, detail="Not authorized")

    audit_res = await db.execute(
        select(AuditLog).where(
            (AuditLog.entity_type == "INCIDENT") & (AuditLog.entity_id == incident.id)
        ).order_by(AuditLog.created_at.asc())
    )
    audit_records = audit_res.scalars().all()

    lifecycle_stages = [
        {"stage": "RECEIVED", "timestamp": incident.created_at.isoformat() if incident.created_at else None, "completed": True},
        {"stage": "VALIDATED", "timestamp": incident.created_at.isoformat() if incident.created_at else None, "completed": True},
        {"stage": "PERSISTED", "timestamp": incident.created_at.isoformat() if incident.created_at else None, "completed": True},
    ]

    has_eval = any(a.action in ("AUTO_ASSIGN", "SHADOW_ASSIGN", "AUTO_ASSIGN_FAILED", "MANUAL_ASSIGN") for a in audit_records)
    eval_log = next((a for a in audit_records if a.action in ("AUTO_ASSIGN", "SHADOW_ASSIGN", "AUTO_ASSIGN_FAILED", "MANUAL_ASSIGN")), None)

    lifecycle_stages.append({
        "stage": "ELIGIBILITY_EVALUATED",
        "timestamp": eval_log.created_at.isoformat() if eval_log and eval_log.created_at else None,
        "completed": has_eval
    })

    has_cand = any(a.action in ("AUTO_ASSIGN", "SHADOW_ASSIGN") for a in audit_records)
    cand_log = next((a for a in audit_records if a.action in ("AUTO_ASSIGN", "SHADOW_ASSIGN")), None)

    lifecycle_stages.append({
        "stage": "CANDIDATE_SELECTED",
        "timestamp": cand_log.created_at.isoformat() if cand_log and cand_log.created_at else None,
        "completed": has_cand
    })

    has_shadow = any(a.action == "SHADOW_ASSIGN" for a in audit_records)
    shadow_log = next((a for a in audit_records if a.action == "SHADOW_ASSIGN"), None)

    lifecycle_stages.append({
        "stage": "SHADOW_RECORDED",
        "timestamp": shadow_log.created_at.isoformat() if shadow_log and shadow_log.created_at else None,
        "completed": has_shadow
    })

    # Future LIVE mode stages
    lifecycle_stages.extend([
        {"stage": "ASSIGNMENT_REQUESTED", "completed": False},
        {"stage": "SERVICENOW_SYNC_PENDING", "completed": False},
        {"stage": "SERVICENOW_ASSIGNED", "completed": False},
        {"stage": "EMPLOYEE_NOTIFIED", "completed": False}
    ])

    return {
        "incident_number": incident.incident_number,
        "current_state": incident.state,
        "sync_status": incident.sync_status,
        "servicenow_assigned": False,
        "lifecycle": lifecycle_stages,
        "audit_trail": [
            {
                "action": a.action,
                "timestamp": a.created_at.isoformat() if a.created_at else None,
                "reason": a.reason,
                "details": a.new_value
            }
            for a in audit_records
        ]
    }

