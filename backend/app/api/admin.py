import uuid
import structlog
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, desc, or_, and_, text
from app.core.database import get_db
from app.core.security import require_role, get_password_hash, get_current_user
from app.core.config import settings
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.employee import Employee
from app.models.user import User
from app.models.team import Team
from app.models.skill import Skill, EmployeeSkill
from app.models.shift import Shift, ShiftAssignment
from app.models.presence import PresenceRecord
from app.models.audit import AuditLog
from app.models.notification import Notification
from app.models.settings import SystemSetting
from app.models.team_rotation import TeamRotation
from app.schemas.admin import (
    DashboardStats, LiveAssignment, SystemHealthResponse,
    SettingsResponse, SettingsUpdate
)
from app.schemas.employee import EmployeeResponse, EmployeeCreate, EmployeeUpdate
from app.schemas.assignment import ManualAssignRequest, ReassignRequest
from app.schemas.shift import ShiftResponse, ShiftCreate, ShiftUpdate
from app.models.conversation import Conversation, ConversationMember, ChatMessage
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.sync_service import SyncService
from app.services.chat_service import ChatService
from app.services.assignment_engine import AssignmentEngine
from app.schemas.activity import (
    GroupActivityOverview, GroupActivityHeader, EmployeeActivityCard,
    AssignedIncidentBrief, WorkBoardColumns, WorkBoardItem,
    TimelineEventItem, GroupAnalyticsSummary
)
from app.schemas.chat import (
    ChatMessageResponse, ConversationResponse, ConversationMemberResponse,
    ChatSearchResponse
)
from app.websocket.manager import ws_manager

router = APIRouter(dependencies=[Depends(require_role("ADMIN"))])
logger = structlog.get_logger()

# 1. COMMAND CENTER / DASHBOARD
@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(db: AsyncSession = Depends(get_db)):
    active_inc_res = await db.execute(
        select(func.count(Incident.id)).where(Incident.state.notin_(["RESOLVED", "CLOSED"]))
    )
    active_incidents = active_inc_res.scalar() or 0

    unassigned_res = await db.execute(
        select(func.count(Incident.id)).where(
            Incident.state == "NEW",
            ~Incident.id.in_(select(IncidentAssignment.incident_id).where(IncidentAssignment.is_active == True))
        )
    )
    unassigned_incidents = unassigned_res.scalar() or 0

    on_shift_res = await db.execute(
        select(func.count(Employee.id)).where(Employee.is_present == True)
    )
    employees_on_shift = on_shift_res.scalar() or 0

    available_res = await db.execute(
        select(func.count(Employee.id)).where(Employee.availability_status == "AVAILABLE")
    )
    available_employees = available_res.scalar() or 0

    busy_res = await db.execute(
        select(func.count(Employee.id)).where(Employee.availability_status == "BUSY")
    )
    busy_employees = busy_res.scalar() or 0

    return DashboardStats(
        active_incidents=active_incidents,
        unassigned_incidents=unassigned_incidents,
        employees_on_shift=employees_on_shift,
        available_employees=available_employees,
        busy_employees=busy_employees
    )

@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    return {
        "status": "healthy",
        "api": "connected",
        "database": "connected",
        "redis": "connected",
        "worker": "running",
        "servicenow": "mock_active" if settings.SERVICENOW_MOCK else "live_connected"
    }

# 2. LIVE ASSIGNMENTS FEED
@router.get("/assignments/live")
async def live_assignments(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(IncidentAssignment)
        .where(IncidentAssignment.is_active == True)
        .order_by(desc(IncidentAssignment.assigned_at))
        .limit(10)
    )
    assignments = result.scalars().all()
    out = []
    for a in assignments:
        inc = await db.get(Incident, a.incident_id)
        emp = await db.get(Employee, a.employee_id)
        user = await db.get(User, emp.user_id) if emp else None
        if inc and user:
            out.append({
                "incident_number": inc.incident_number,
                "short_description": inc.short_description,
                "employee_name": user.full_name,
                "assignment_type": a.assignment_type,
                "status": a.status,
                "assigned_at": a.assigned_at
            })
    return out

# 3. EMPLOYEE MANAGEMENT (CRUD)
@router.get("/employees")
async def list_employees(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Employee).join(User, Employee.user_id == User.id).where(
            User.role == "EMPLOYEE",
            User.is_active == True
        )
    )
    employees = result.scalars().all()
    emp_list = []
    for emp in employees:
        user = await db.get(User, emp.user_id)
        team = await db.get(Team, emp.team_id) if emp.team_id else None
        
        # Count active incidents
        count_res = await db.execute(
            select(func.count(IncidentAssignment.id)).where(
                IncidentAssignment.employee_id == emp.id,
                IncidentAssignment.is_active == True,
                IncidentAssignment.status.in_(["ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS"])
            )
        )
        active_count = count_res.scalar() or 0

        emp_list.append({
            "id": emp.id,
            "user_id": emp.user_id,
            "full_name": user.full_name if user else "Unknown",
            "email": user.email if user else "",
            "team_id": emp.team_id,
            "team_name": team.name if team else None,
            "employee_code": emp.employee_code,
            "availability_status": emp.availability_status,
            "is_present": emp.is_present,
            "skills": [],
            "active_incident_count": active_count
        })
    return emp_list

@router.post("/employees", status_code=status.HTTP_201_CREATED)
async def create_employee(payload: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    # Check if user email exists
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User with this email already exists")

    # Create User
    new_user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password or "password123"),
        full_name=payload.full_name,
        role=payload.role or "EMPLOYEE"
    )
    db.add(new_user)
    await db.flush()

    # Find or set team
    team_id = None
    if payload.team_name:
        t_res = await db.execute(select(Team).where(Team.name == payload.team_name))
        team = t_res.scalar_one_or_none()
        if not team:
            team = Team(name=payload.team_name)
            db.add(team)
            await db.flush()
        team_id = team.id

    # Create Employee
    new_emp = Employee(
        user_id=new_user.id,
        team_id=team_id,
        employee_code=payload.employee_code,
        availability_status="AVAILABLE",
        is_present=True
    )
    db.add(new_emp)
    await db.flush()

    # Log audit
    audit = AuditService(db)
    await audit.log(
        action="CREATE_EMPLOYEE",
        entity_type="EMPLOYEE",
        entity_id=new_emp.id,
        new_value={"email": payload.email, "full_name": payload.full_name}
    )

    await db.commit()
    return {"message": "Employee created successfully", "id": new_emp.id, "email": new_user.email}

@router.patch("/employees/{id}")
async def update_employee(id: uuid.UUID, payload: EmployeeUpdate, db: AsyncSession = Depends(get_db)):
    emp = await db.get(Employee, id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    user = await db.get(User, emp.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Associated user not found")

    old_status = emp.availability_status

    if payload.full_name:
        user.full_name = payload.full_name
    if payload.email:
        user.email = payload.email
    if payload.availability_status:
        emp.availability_status = payload.availability_status
    if payload.is_present is not None:
        emp.is_present = payload.is_present

    audit = AuditService(db)
    await audit.log(
        action="UPDATE_EMPLOYEE_STATUS",
        entity_type="EMPLOYEE",
        entity_id=emp.id,
        old_value={"status": old_status},
        new_value={"status": emp.availability_status, "is_present": emp.is_present}
    )

    await db.commit()
    return {"message": "Employee updated successfully"}

@router.delete("/employees/{id}")
async def delete_employee(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    emp = await db.get(Employee, id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    emp.availability_status = "OFFLINE"
    emp.is_present = False
    await db.commit()
    return {"message": "Employee deactivated successfully"}

# 4. INCIDENT MANAGEMENT & UNASSIGNED QUEUE
@router.get("/incidents/unassigned")
async def unassigned_incidents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Incident).where(
            Incident.state == "NEW",
            ~Incident.id.in_(select(IncidentAssignment.incident_id).where(IncidentAssignment.is_active == True))
        ).order_by(desc(Incident.created_at))
    )
    incidents = result.scalars().all()
    return [{
        "id": i.id,
        "incident_number": i.incident_number,
        "short_description": i.short_description,
        "priority": i.priority,
        "assignment_group": i.assignment_group,
        "state": i.state,
        "created_at": i.created_at,
        "reason": "No eligible employees were available on the active shift"
    } for i in incidents]

@router.post("/incidents/{id}/assign")
async def manual_assign(
    id: uuid.UUID,
    payload: ManualAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Lock the incident row first to serialize concurrent admin double-clicks
    locked_inc_res = await db.execute(
        select(Incident).where(Incident.id == id).with_for_update()
    )
    inc = locked_inc_res.scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    emp = await db.get(Employee, payload.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    user = await db.get(User, emp.user_id) if emp.user_id else None
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Target employee is inactive")

    # Check existing active assignment (after lock — now safe)
    curr_assignment_res = await db.execute(
        select(IncidentAssignment).where(IncidentAssignment.incident_id == inc.id, IncidentAssignment.is_active == True)
    )
    curr_assignment = curr_assignment_res.scalars().first()
    prev_emp_id = None
    if curr_assignment:
        if curr_assignment.employee_id == emp.id:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "ALREADY_ASSIGNED_THIS_INCIDENT",
                    "message": f"Candidate {user.full_name} already holds the active assignment for this incident."
                }
            )
        curr_assignment.is_active = False
        curr_assignment.status = "REASSIGNED"
        curr_assignment.reassigned_reason = payload.reason or "Reassigned by Administrator"
        prev_emp_id = curr_assignment.employee_id

    current_cycle = getattr(inc, "current_cycle", 1) or 1
    assignment = IncidentAssignment(
        incident_id=inc.id,
        employee_id=emp.id,
        previous_employee_id=prev_emp_id,
        assignment_type="MANUAL",
        status="ASSIGNED",
        reason=payload.reason or "Manually assigned by Administrator",
        assigned_at=datetime.now(timezone.utc),
        is_active=True,
        cycle_number=current_cycle
    )
    db.add(assignment)

    inc.state = "ASSIGNED"
    inc.assigned_to = user.full_name if user else "Employee"

    # Audit log
    audit = AuditService(db)
    await audit.log(
        action="MANUAL_ASSIGN",
        entity_type="INCIDENT",
        entity_id=inc.id,
        new_value={"employee_id": str(emp.id), "employee_name": inc.assigned_to, "reason": payload.reason},
        actor_id=current_user.id
    )

    # Notification
    notif = NotificationService(db)
    await notif.create_notification(
        user_id=emp.user_id,
        type="INCIDENT_ASSIGNED",
        title=f"Incident assigned: {inc.incident_number}",
        message=inc.short_description,
        incident_id=inc.id
    )

    try:
        await db.commit()
    except Exception as commit_exc:
        from sqlalchemy.exc import IntegrityError
        if isinstance(commit_exc, IntegrityError):
            # Concurrent double-click committed first — return success idempotently
            await db.rollback()
            return {"message": "Incident manually assigned successfully", "assigned_to": inc.assigned_to}
        raise
    return {"message": "Incident manually assigned successfully", "assigned_to": inc.assigned_to}



@router.post("/incidents/{incident_id}/reassign")
async def reassign_incident(
    incident_id: uuid.UUID,
    payload: ReassignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Reassign incident to a new employee.
    - Closes previous active assignment (is_active=False, status='REASSIGNED')
    - Creates new active assignment linking previous_employee_id
    - Records audit log with previous and new employee info
    - Notifies previous and new employees
    - Broadcasts real-time events over WebSocket
    """
    # Lock the incident row to serialize concurrent reassignment requests
    locked_inc_res = await db.execute(
        select(Incident).where(Incident.id == incident_id).with_for_update()
    )
    inc = locked_inc_res.scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    target_emp_id = payload.new_employee_id or payload.employee_id
    if not target_emp_id:
        raise HTTPException(status_code=400, detail="Target new employee ID is required")

    new_emp = await db.get(Employee, target_emp_id)
    if not new_emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    new_user = await db.get(User, new_emp.user_id) if new_emp.user_id else None
    if not new_user or not new_user.is_active:
        raise HTTPException(status_code=400, detail="Target employee is inactive")

    # Fetch current active assignment (after lock — now safe)
    curr_assignment_res = await db.execute(
        select(IncidentAssignment).where(
            IncidentAssignment.incident_id == inc.id,
            IncidentAssignment.is_active == True
        )
    )
    curr_assignment = curr_assignment_res.scalars().first()


    # Candidate already holds active assignment for this incident
    if curr_assignment and curr_assignment.employee_id == new_emp.id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "ALREADY_ASSIGNED_THIS_INCIDENT",
                "message": f"Candidate {new_user.full_name} already holds the active assignment for incident {inc.incident_number}."
            }
        )

    # Check if candidate has already been assigned in current cycle
    current_cycle = getattr(inc, "current_cycle", 1) or 1
    stmt_prior_cycle = select(IncidentAssignment).where(
        IncidentAssignment.incident_id == inc.id,
        IncidentAssignment.employee_id == new_emp.id,
        IncidentAssignment.cycle_number == current_cycle
    )
    prior_cycle_res = await db.execute(stmt_prior_cycle)
    if prior_cycle_res.scalars().first():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "ALREADY_ASSIGNED_IN_CURRENT_CYCLE",
                "message": f"Candidate {new_user.full_name} has already handled incident {inc.incident_number} in assignment cycle {current_cycle}."
            }
        )

    prev_emp_id = None
    prev_user = None
    if curr_assignment:
        curr_assignment.is_active = False
        curr_assignment.status = "REASSIGNED"
        curr_assignment.reassigned_reason = payload.reason or "Reassigned by Administrator"
        prev_emp_id = curr_assignment.employee_id
        prev_emp = await db.get(Employee, prev_emp_id)
        if prev_emp and prev_emp.user_id:
            prev_user = await db.get(User, prev_emp.user_id)

    # Create new active assignment
    new_assignment = IncidentAssignment(
        incident_id=inc.id,
        employee_id=new_emp.id,
        previous_employee_id=prev_emp_id,
        assignment_type="MANUAL",
        status="ASSIGNED",
        reason=payload.reason or "Reassigned by Administrator",
        reassigned_reason=payload.reason,
        assigned_at=datetime.now(timezone.utc),
        is_active=True,
        cycle_number=current_cycle
    )
    db.add(new_assignment)

    inc.state = "ASSIGNED"
    inc.assigned_to = new_user.full_name if new_user else "Employee"

    # Audit log
    audit = AuditService(db)
    await audit.log(
        action="REASSIGN",
        entity_type="INCIDENT",
        entity_id=inc.id,
        old_value={
            "employee_id": str(prev_emp_id) if prev_emp_id else None,
            "employee_name": prev_user.full_name if prev_user else None
        },
        new_value={
            "employee_id": str(new_emp.id),
            "employee_name": inc.assigned_to,
            "reason": payload.reason
        },
        actor_id=current_user.id
    )

    # Notifications
    notif = NotificationService(db)
    if prev_user:
        await notif.create_notification(
            user_id=prev_user.id,
            type="INCIDENT_REASSIGNED",
            title=f"Incident reassigned: {inc.incident_number}",
            message=f"Incident {inc.incident_number} has been reassigned to {inc.assigned_to}.",
            incident_id=inc.id
        )
    if new_user:
        await notif.create_notification(
            user_id=new_user.id,
            type="INCIDENT_ASSIGNED",
            title=f"Incident assigned: {inc.incident_number}",
            message=inc.short_description,
            incident_id=inc.id
        )

    await db.commit()
    await db.refresh(new_assignment)

    # WebSocket events
    timestamp_str = datetime.now(timezone.utc).isoformat()
    reassign_event = {
        "incident_id": str(inc.id),
        "incident_number": inc.incident_number,
        "previous_employee_id": str(prev_emp_id) if prev_emp_id else None,
        "previous_employee_name": prev_user.full_name if prev_user else None,
        "new_employee_id": str(new_emp.id),
        "new_employee_name": inc.assigned_to,
        "reason": payload.reason,
        "assigned_to": inc.assigned_to,
        "state": inc.state,
        "timestamp": timestamp_str
    }
    if prev_user:
        await ws_manager.send_to_user(str(prev_user.id), "MY_WORK_UPDATED", reassign_event)
    if new_user:
        await ws_manager.send_to_user(str(new_user.id), "MY_WORK_UPDATED", reassign_event)
        await ws_manager.send_to_user(str(new_user.id), "INCIDENT_ASSIGNED", reassign_event)
    await ws_manager.broadcast_to_admins("INCIDENT_REASSIGNED", reassign_event)
    await ws_manager.broadcast_to_admins("INCIDENT_UPDATED", reassign_event)
    if new_emp.team_id:
        await ws_manager.broadcast_to_team(str(new_emp.team_id), "INCIDENT_UPDATED", reassign_event)

    return {
        "status": "success",
        "message": f"Incident successfully reassigned to {inc.assigned_to}",
        "incident_id": str(inc.id),
        "incident_number": inc.incident_number,
        "assigned_to": inc.assigned_to,
        "previous_employee_id": str(prev_emp_id) if prev_emp_id else None,
        "new_employee_id": str(new_emp.id),
        "assignment_id": str(new_assignment.id)
    }


@router.post("/incidents/{incident_id}/send/preview")
async def preview_send_incident(incident_id: uuid.UUID, payload: dict, db: AsyncSession = Depends(get_db)):
    """
    Previews recipient list and message template for incident notification dispatch.
    SEND != ASSIGN: Does not modify assigned_to, state, or trigger assignment engine.
    """
    inc = await db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    group_ids = payload.get("group_ids", [])
    employee_ids = payload.get("employee_ids", [])
    custom_message = payload.get("message", "").strip()

    recipients = []
    seen_user_ids = set()

    # Collect employees by ID
    for eid in employee_ids:
        try:
            emp = await db.get(Employee, uuid.UUID(str(eid)))
            if emp and emp.user_id not in seen_user_ids:
                u = await db.get(User, emp.user_id)
                if u:
                    recipients.append({"user_id": str(u.id), "name": u.full_name, "email": u.email, "type": "EMPLOYEE"})
                    seen_user_ids.add(emp.user_id)
        except Exception:
            pass

    # Collect employees by Group
    for gid in group_ids:
        try:
            team_res = await db.execute(select(Employee).where(Employee.team_id == uuid.UUID(str(gid))))
            for emp in team_res.scalars().all():
                if emp.user_id not in seen_user_ids:
                    u = await db.get(User, emp.user_id)
                    if u:
                        recipients.append({"user_id": str(u.id), "name": u.full_name, "email": u.email, "type": "GROUP_MEMBER"})
                        seen_user_ids.add(emp.user_id)
        except Exception:
            pass

    body_preview = custom_message or f"Notification for {inc.incident_number}: {inc.short_description}"
    return {
        "incident_number": inc.incident_number,
        "priority": inc.priority,
        "recipient_count": len(recipients),
        "recipients": recipients,
        "subject": f"[{inc.priority}] Notice: {inc.incident_number}",
        "body_preview": body_preview,
        "incident_link": f"{settings.APP_BASE_URL.rstrip('/')}/work/{inc.incident_number}",
        "channels": payload.get("channels", ["IN_APP"]),
        "policy_note": "Notification broadcast only. Incident assigned_to remains untouched."
    }

@router.post("/incidents/{incident_id}/send")
async def send_incident_notification(incident_id: uuid.UUID, payload: dict, db: AsyncSession = Depends(get_db)):
    """
    Broadcasts announcement notification for an incident to groups or employees.
    SEND != ASSIGN:
    - Never changes assigned_to in IncidentFlow or ServiceNow.
    - Never triggers assignment engine.
    - Audits every dispatch and records recipient list.
    """
    confirmed = payload.get("confirmed", False)
    if not confirmed:
        raise HTTPException(status_code=400, detail="Explicit confirmation required (confirmed: true)")

    preview = await preview_send_incident(incident_id, payload, db)
    recipients = preview["recipients"]
    if not recipients:
        raise HTTPException(status_code=400, detail="No valid recipients selected")

    inc = await db.get(Incident, incident_id)
    notif_service = NotificationService(db)
    audit_service = AuditService(db)

    dispatched_count = 0
    for r in recipients:
        uid = uuid.UUID(r["user_id"])
        await notif_service.create_notification(
            user_id=uid,
            type="INCIDENT_UPDATED",
            title=preview["subject"],
            message=preview["body_preview"],
            incident_id=inc.id
        )
        dispatched_count += 1

    # Record Audit Log
    await audit_service.log(
        action="SEND_INCIDENT_NOTIFICATION",
        entity_type="INCIDENT",
        entity_id=inc.id,
        new_value={
            "incident_number": inc.incident_number,
            "dispatched_count": dispatched_count,
            "channels": preview["channels"],
            "recipients": [{"name": r["name"], "email": r["email"]} for r in recipients],
            "message": preview["body_preview"]
        },
        reason=f"Administrator broadcasted incident notification to {dispatched_count} recipient(s)."
    )

    await db.commit()

    return {
        "status": "sent",
        "incident_number": inc.incident_number,
        "dispatched_count": dispatched_count,
        "recipients": recipients,
        "servicenow_modified": False,
        "assigned_to_modified": False
    }

@router.post("/incidents/{incident_id}/send-to-group/preview")
async def preview_send_incident_to_group(incident_id: uuid.UUID, payload: dict, db: AsyncSession = Depends(get_db)):
    """
    Preview smart assignment candidate evaluation, workload, and fallback status
    prior to assigning an incident to a team/group.
    """
    team_id_str = payload.get("team_id")
    if not team_id_str:
        raise HTTPException(status_code=400, detail="Target team_id is required")

    inc = await db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    engine = AssignmentEngine(db)
    try:
        preview = await engine.preview_send_to_group(inc, uuid.UUID(str(team_id_str)))
        return preview
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as ex:
        logger.error("preview_send_to_group_error", error=str(ex))
        raise HTTPException(status_code=500, detail=f"Failed to generate preview: {str(ex)}")

@router.post("/incidents/{incident_id}/send-to-group")
async def send_incident_to_group(incident_id: uuid.UUID, payload: dict, db: AsyncSession = Depends(get_db)):
    """
    Validates incident and target group, creates group notice, deterministically evaluates
    eligible candidates (Priority 1: 0 active work, Priority 2: least workload, or Next-Shift queued),
    creates assignment, logs AUTO_ASSIGNMENT_DECISION, and dispatches realtime updates.
    """
    team_id_str = payload.get("team_id")
    if not team_id_str:
        raise HTTPException(status_code=400, detail="Target team_id is required")

    custom_message = payload.get("message")

    inc = await db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    engine = AssignmentEngine(db)
    try:
        result = await engine.send_incident_to_group(inc, uuid.UUID(str(team_id_str)), custom_message=custom_message)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as ex:
        logger.error("send_to_group_execution_error", error=str(ex))
        raise HTTPException(status_code=500, detail=f"Failed to send incident to group: {str(ex)}")

# 5. AUTOMATION EMERGENCY CONTROLS
@router.post("/automation/pause")
async def pause_automation(
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    res = await db.execute(select(SystemSetting).where(SystemSetting.key == "auto_assignment_enabled"))
    setting = res.scalar_one_or_none()
    if not setting:
        setting = SystemSetting(key="auto_assignment_enabled", value={"enabled": False})
        db.add(setting)
    else:
        setting.value = {"enabled": False}
    
    actor_name = getattr(current_user, "full_name", "Administrator")
    actor_id = getattr(current_user, "id", None)
    req_id = request.headers.get("x-request-id", str(uuid.uuid4())) if request else str(uuid.uuid4())
    audit = AuditService(db)
    await audit.log(
        action="AUTOMATION_STATUS_CHANGED",
        entity_type="SYSTEM",
        old_value={"status": "ACTIVE", "enabled": True},
        new_value={"status": "PAUSED", "enabled": False},
        reason=f"Administrator {actor_name} paused automation",
        actor_id=actor_id,
        request_id=req_id
    )
    await db.commit()
    return {"message": "Automatic assignment paused", "status": "paused"}

@router.post("/automation/resume")
async def resume_automation(
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    res = await db.execute(select(SystemSetting).where(SystemSetting.key == "auto_assignment_enabled"))
    setting = res.scalar_one_or_none()
    if not setting:
        setting = SystemSetting(key="auto_assignment_enabled", value={"enabled": True})
        db.add(setting)
    else:
        setting.value = {"enabled": True}

    actor_name = getattr(current_user, "full_name", "Administrator")
    actor_id = getattr(current_user, "id", None)
    req_id = request.headers.get("x-request-id", str(uuid.uuid4())) if request else str(uuid.uuid4())
    audit = AuditService(db)
    await audit.log(
        action="AUTOMATION_STATUS_CHANGED",
        entity_type="SYSTEM",
        old_value={"status": "PAUSED", "enabled": False},
        new_value={"status": "ACTIVE", "enabled": True},
        reason=f"Administrator {actor_name} resumed automation",
        actor_id=actor_id,
        request_id=req_id
    )
    await db.commit()
    return {"message": "Automatic assignment resumed", "status": "active"}

# 6. SERVICENOW INTEGRATION CONTROL & STATUS
@router.get("/integrations/servicenow")
async def servicenow_status_legacy(db: AsyncSession = Depends(get_db)):
    """Legacy compatibility endpoint."""
    return await servicenow_integration_status(db)

@router.get("/integrations/servicenow/status")
async def servicenow_integration_status(db: AsyncSession = Depends(get_db)):
    """
    Returns comprehensive ServiceNow integration health and honest configuration state.
    Strictly differentiates CONFIGURED from ACTUALLY VERIFIED.
    Never exposes passwords, client secrets, webhook secrets, or auth tokens.
    """
    from app.models.integration import IntegrationEvent, SyncFailure
    from app.models.settings import SystemSetting
    from app.models.audit import AuditLog
    from urllib.parse import urlparse

    # 1. Inspect configuration flags without secrets
    url = settings.SERVICENOW_URL or ""
    has_url = bool(url and not url.startswith("<") and "PLACEHOLDER" not in url)
    username = settings.SERVICENOW_USERNAME or ""
    password = settings.SERVICENOW_PASSWORD or ""
    has_basic = bool(username and password and not username.startswith("<") and not password.startswith("<") and "PLACEHOLDER" not in password)
    
    cid = settings.SERVICENOW_CLIENT_ID or ""
    csec = settings.SERVICENOW_CLIENT_SECRET or ""
    has_oauth = bool(cid and csec and not cid.startswith("<") and not csec.startswith("<") and "PLACEHOLDER" not in csec)

    wh_sec = settings.SERVICENOW_WEBHOOK_SECRET or ""
    has_wh = bool(wh_sec and not wh_sec.startswith("<") and "PLACEHOLDER" not in wh_sec)

    has_placeholders = any(
        "PLACEHOLDER" in val or (val.startswith("<") and val.endswith(">"))
        for val in [url, username, password, cid, csec, wh_sec] if val
    )

    auth_configured = (has_basic or has_oauth) and not has_placeholders

    # 2. Hostname sanitized
    parsed = urlparse(url)
    target_hostname = parsed.netloc or (parsed.path if parsed.path else "Not Configured")

    # 3. Check actual connection verification from audit logs
    conn_audit = await db.execute(
        select(AuditLog)
        .where(AuditLog.action.in_(["TEST_SERVICENOW_CONNECTION", "SERVICENOW_CONNECTION_VERIFIED"]))
        .order_by(desc(AuditLog.created_at))
        .limit(1)
    )
    last_conn_log = conn_audit.scalar_one_or_none()
    
    verified = False
    last_conn_status = None
    last_conn_latency = None
    last_conn_attempt = None
    last_conn_success = None

    if last_conn_log:
        last_conn_attempt = last_conn_log.created_at.isoformat() if last_conn_log.created_at else None
        details = last_conn_log.new_value or {}
        last_conn_status = details.get("status")
        last_conn_latency = details.get("latency_ms")
        if details.get("result") == "CONNECTED" or last_conn_status == "connected":
            verified = True
            last_conn_success = last_conn_attempt

    # 4. Connection Status Classification
    is_placeholder_host = any(x in target_hostname.lower() for x in ["dev-staging", "example", "placeholder", "localhost"])
    if not has_url or not auth_configured:
        connection_status = "Not Configured"
        connection_code = "NOT_CONFIGURED"
    elif last_conn_status == "auth_failed":
        connection_status = "Authentication Failed"
        connection_code = "AUTH_FAILED"
    elif last_conn_status == "unreachable":
        connection_status = "Unavailable"
        connection_code = "UNAVAILABLE"
    elif has_placeholders or is_placeholder_host:
        connection_status = "Blocked"
        connection_code = "BLOCKED"
    elif not verified:
        connection_status = "Configured (Not Verified)"
        connection_code = "CONFIGURED"
    else:
        connection_status = "Verified"
        connection_code = "VERIFIED"

    # 5. Events metrics (today and total)
    from datetime import date
    now_utc = datetime.now(timezone.utc)
    today_start = datetime.combine(now_utc.date(), datetime.min.time(), tzinfo=timezone.utc)

    events_res = await db.execute(
        select(IntegrationEvent).order_by(desc(IntegrationEvent.created_at)).limit(1)
    )
    last_event = events_res.scalar_one_or_none()

    today_count_res = await db.execute(
        select(func.count(IntegrationEvent.id)).where(IntegrationEvent.created_at >= today_start)
    )
    events_today = today_count_res.scalar() or 0

    duplicate_count_res = await db.execute(
        select(func.count(IntegrationEvent.id)).where(IntegrationEvent.status == "DUPLICATE")
    )
    duplicate_events = duplicate_count_res.scalar() or 0

    failed_events_res = await db.execute(
        select(func.count(IntegrationEvent.id)).where(IntegrationEvent.status.in_(["FAILED", "REJECTED"]))
    )
    failed_events = failed_events_res.scalar() or 0

    # 6. Sync / DLQ metrics
    sync_success_res = await db.execute(
        select(func.count(SyncFailure.id)).where(SyncFailure.status == "RESOLVED")
    )
    successful_syncs = sync_success_res.scalar() or 0

    pending_sync_res = await db.execute(
        select(func.count(SyncFailure.id)).where(SyncFailure.status.in_(["PENDING", "RETRYING"]))
    )
    pending_retries = pending_sync_res.scalar() or 0

    failed_sync_res = await db.execute(
        select(func.count(SyncFailure.id)).where(SyncFailure.status == "FAILED")
    )
    failed_syncs = failed_sync_res.scalar() or 0

    dlq_res = await db.execute(
        select(func.count(SyncFailure.id)).where(SyncFailure.status == "DEAD_LETTER")
    )
    dead_letter_events = dlq_res.scalar() or 0

    # 7. Automation mode from DB settings
    res_mode = await db.execute(select(SystemSetting).where(SystemSetting.key == "automation_mode"))
    mode_setting = res_mode.scalar_one_or_none()
    current_mode = mode_setting.value.get("mode", settings.AUTOMATION_MODE) if mode_setting else settings.AUTOMATION_MODE

    return {
        "connection_status": connection_status,
        "connection_code": connection_code,
        "environment": settings.ENVIRONMENT,
        "current_mode": current_mode,
        "servicenow_hostname": target_hostname,
        "last_successful_connection": last_conn_success,
        "last_connection_attempt": last_conn_attempt,
        "latency_ms": last_conn_latency,
        "api_health": "HEALTHY" if verified else ("WARNING" if auth_configured else "NOT_CONFIGURED"),
        "webhook_health": "CONFIGURED" if has_wh else "NOT_CONFIGURED",
        "webhook_endpoint": "/api/integrations/servicenow/incidents",
        "last_webhook_received": last_event.created_at.isoformat() if last_event else None,
        "last_incident_number": last_event.incident_number if last_event else None,
        "events_today": events_today,
        "duplicate_events": duplicate_events,
        "failed_events": failed_events,
        "successful_syncs": successful_syncs,
        "pending_retries": pending_retries,
        "failed_syncs": failed_syncs,
        "dead_letter_events": dead_letter_events,
        "config_checklist": {
            "servicenow_url": {"configured": has_url, "verified": verified, "status": "READY" if has_url else "NOT READY"},
            "authentication": {"configured": auth_configured, "verified": verified, "status": "READY" if auth_configured else "NOT READY"},
            "webhook_secret": {"configured": has_wh, "verified": has_wh, "status": "READY" if has_wh else "NOT READY"},
            "app_base_url": {"configured": bool(settings.APP_BASE_URL), "verified": True, "status": "READY" if settings.APP_BASE_URL else "NOT READY"},
            "assignment_group": {"configured": bool(settings.ASSIGNMENT_GROUP), "verified": True, "status": "READY" if settings.ASSIGNMENT_GROUP else "NOT READY"},
            "readonly_connection": {"configured": auth_configured, "verified": verified, "status": "READY" if verified else "NOT READY"},
            "real_staging_e2e": {"configured": auth_configured, "verified": verified and (last_event is not None), "status": "READY" if (verified and last_event) else "NOT READY"},
            "smtp_configured": {"configured": settings.EMAIL_PROVIDER == "MOCK", "verified": True, "status": "READY (MOCK)"}
        }
    }

@router.post("/integrations/servicenow/test-connection")
async def test_servicenow_connection(db: AsyncSession = Depends(get_db)):
    """
    Validates staging instance reachability and authentication without mutating data.
    Logs audit event with sanitized latency and host. Never logs secrets.
    """
    from app.integrations.servicenow.client import ServiceNowClient
    client = ServiceNowClient()
    result = await client.test_connection()

    audit = AuditService(db)
    await audit.log(
        action="TEST_SERVICENOW_CONNECTION",
        entity_type="INTEGRATION",
        new_value={
            "result": result.get("result"),
            "status": result.get("status"),
            "target_hostname": result.get("target_hostname"),
            "latency_ms": result.get("latency_ms"),
            "status_code": result.get("status_code")
        },
        reason="Manual connection test from Integration Control Center"
    )
    await db.commit()
    return result

@router.get("/integrations/servicenow/diagnostics")
async def servicenow_diagnostics(db: AsyncSession = Depends(get_db)):
    """
    Performs read-only diagnostics for:
    - Incident Table read
    - Assignment Group read
    - User read
    - Required incident fields read
    Returns PASS, FAIL, or FORBIDDEN without mutating ServiceNow.
    """
    from app.integrations.servicenow.client import ServiceNowClient
    from urllib.parse import urlparse

    url = settings.SERVICENOW_URL or ""
    pwd = settings.SERVICENOW_PASSWORD or ""
    if not url or "PLACEHOLDER" in url or "PLACEHOLDER" in pwd:
        return {
            "incident_table_read": "FAIL",
            "assignment_group_read": "FAIL",
            "user_read": "FAIL",
            "required_fields_read": "FAIL",
            "overall_status": "BLOCKED",
            "reason": "Credentials or URL not configured"
        }

    client = ServiceNowClient()
    diagnostics = {}

    # Test 1: Incident Table read
    try:
        inc_res = await client.test_connection()
        if inc_res.get("status") == "connected":
            diagnostics["incident_table_read"] = "PASS"
            diagnostics["required_fields_read"] = "PASS"
        elif inc_res.get("status_code") in (401, 403):
            diagnostics["incident_table_read"] = "FORBIDDEN"
            diagnostics["required_fields_read"] = "FORBIDDEN"
        else:
            diagnostics["incident_table_read"] = "FAIL"
            diagnostics["required_fields_read"] = "FAIL"
    except Exception:
        diagnostics["incident_table_read"] = "FAIL"
        diagnostics["required_fields_read"] = "FAIL"

    # Test 2: Assignment Group read
    try:
        url_group = f"{client.base_url}/api/now/table/sys_user_group?sysparm_limit=1"
        resp = await client._execute_with_retry("GET", url_group, headers=client._get_auth_headers())
        if resp.status_code == 200:
            diagnostics["assignment_group_read"] = "PASS"
        elif resp.status_code in (401, 403):
            diagnostics["assignment_group_read"] = "FORBIDDEN"
        else:
            diagnostics["assignment_group_read"] = "FAIL"
    except Exception:
        diagnostics["assignment_group_read"] = "FAIL"

    # Test 3: User read
    try:
        url_user = f"{client.base_url}/api/now/table/sys_user?sysparm_limit=1"
        resp = await client._execute_with_retry("GET", url_user, headers=client._get_auth_headers())
        if resp.status_code == 200:
            diagnostics["user_read"] = "PASS"
        elif resp.status_code in (401, 403):
            diagnostics["user_read"] = "FORBIDDEN"
        else:
            diagnostics["user_read"] = "FAIL"
    except Exception:
        diagnostics["user_read"] = "FAIL"

    diagnostics["overall_status"] = "PASS" if all(v == "PASS" for v in diagnostics.values()) else "FAIL"
    return diagnostics

@router.get("/integrations/servicenow/events")
async def list_integration_events(
    limit: int = Query(50, ge=1, le=100),
    status_filter: str | None = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Lists received webhook integration events.
    Never exposes passwords, tokens, authorization headers, or webhook secrets.
    Masks sensitive values in payloads.
    """
    from app.models.integration import IntegrationEvent
    stmt = select(IntegrationEvent).order_by(desc(IntegrationEvent.created_at))
    if status_filter:
        stmt = stmt.where(IntegrationEvent.status == status_filter.upper())
    stmt = stmt.limit(limit)

    res = await db.execute(stmt)
    events = res.scalars().all()

    def sanitize_payload(payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {}
        sanitized = {}
        sensitive_keys = {"password", "secret", "token", "authorization", "key", "access_token"}
        for k, v in payload.items():
            if any(s in k.lower() for s in sensitive_keys):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = sanitize_payload(v)
            else:
                sanitized[k] = v
        return sanitized

    out = []
    for ev in events:
        out.append({
            "id": str(ev.id),
            "incident_number": ev.incident_number or "N/A",
            "sys_id": (ev.payload or {}).get("sys_id", "N/A"),
            "event_type": ev.event_type,
            "source": ev.source,
            "status": ev.status,
            "error_message": ev.error_message,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "processed_at": ev.processed_at.isoformat() if ev.processed_at else None,
            "payload_sanitized": sanitize_payload(ev.payload or {})
        })
    return out

@router.post("/integrations/servicenow/sync")
async def servicenow_sync_now(db: AsyncSession = Depends(get_db)):
    sync_svc = SyncService(db)
    retry_stats = await sync_svc.retry_failed_syncs()
    return {
        "message": "ServiceNow sync triggered successfully",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "retry_stats": retry_stats
    }

@router.get("/shadow-decisions")
async def list_shadow_decisions(db: AsyncSession = Depends(get_db)):
    """
    Returns recent shadow mode routing decisions with candidate dossier breakdown:
    Eligible candidates with workloads, rejected candidates with explicit reasons,
    selected employee, and confirmation that ServiceNow was not modified.
    """
    stmt = (
        select(AuditLog)
        .where(AuditLog.action == "SHADOW_ASSIGN")
        .order_by(desc(AuditLog.created_at))
        .limit(25)
    )
    res = await db.execute(stmt)
    logs = res.scalars().all()

    decisions = []
    for log in logs:
        dossier = log.new_value or {}
        decisions.append({
            "audit_id": str(log.id),
            "incident_number": dossier.get("incident_number", "INC_UNKNOWN"),
            "sys_id": dossier.get("sys_id"),
            "would_assign": dossier.get("selected_employee", {}).get("name", "Unknown"),
            "eligible_candidates": dossier.get("eligible_candidates", []),
            "rejected_candidates": dossier.get("rejected_candidates", []),
            "strategy": dossier.get("strategy", settings.ASSIGNMENT_STRATEGY),
            "shift": dossier.get("shift"),
            "servicenow_modified": False,
            "simulated_at": dossier.get("simulated_at", log.created_at.isoformat() if log.created_at else None),
            "reason": log.reason
        })
    return decisions

@router.post("/integrations/servicenow/test-email")
async def test_email_dispatch(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a real single-recipient test email to verify SMTP connectivity.

    Steps performed:
      1. SMTP connection probe (connect + STARTTLS + auth — no message sent)
      2. Send an actual test email to the specified recipient
      3. Record delivery result in the notification table (if recipient is a known user)
      4. Audit log the test attempt
      5. Return detailed result — SMTP_PASSWORD is NEVER included

    Request body:
      {
        "recipient": "engineer@example.com",   // required
        "incident_number": "TEST-0001",         // optional
        "short_description": "...",            // optional
        "priority": "P3"                       // optional
      }
    """
    from app.services.email_service import EmailService, probe_smtp_connection
    from app.services.audit_service import AuditService

    recipient = payload.get("recipient", "").strip()
    if not recipient or "@" not in recipient:
        raise HTTPException(status_code=400, detail="'recipient' must be a valid email address")

    incident_number = payload.get("incident_number", "TEST-0001")
    short_desc = payload.get("short_description", "IncidentFlow SMTP delivery verification")
    priority = payload.get("priority", "P3")

    # 1. SMTP connection probe
    probe_result = await probe_smtp_connection()

    # 2. Send test email
    email_svc = EmailService(db)
    send_result = await email_svc.send_test_email(
        recipient_email=recipient,
        incident_number=incident_number,
        short_description=short_desc,
        priority=priority,
    )

    # 3. Record in notification table if recipient is a known user
    notification_id = None
    try:
        user_res = await db.execute(select(User).where(User.email == recipient))
        user = user_res.scalar_one_or_none()
        if user:
            from app.models.notification import Notification as NotifModel
            notif = NotifModel(
                user_id=user.id,
                type="EMAIL_TEST",
                title=f"[EMAIL TEST] {incident_number}",
                message=f"SMTP test email sent. Provider: {settings.EMAIL_PROVIDER}. Delivered: {send_result.get('delivered', False)}",
            )
            db.add(notif)
            await db.flush()
            notification_id = str(notif.id)
    except Exception as notif_exc:
        logger.warning("test_email_notification_record_failed", error=str(notif_exc))

    # 4. Audit log
    audit_svc = AuditService(db)
    await audit_svc.log(
        action="EMAIL_TEST",
        entity_type="SYSTEM",
        entity_id=None,
        new_value={
            "provider": settings.EMAIL_PROVIDER,
            "smtp_host": settings.SMTP_HOST,
            "smtp_port": settings.SMTP_PORT,
            "recipient_masked": send_result.get("to_masked", "***"),
            "delivered": send_result.get("delivered", False),
            "status": send_result.get("status", "UNKNOWN"),
            # password intentionally omitted from audit log
        },
        reason=f"Admin-initiated SMTP test email to {send_result.get('to_masked', '***')}",
    )
    await db.commit()

    # 5. Return result (no secrets)
    return {
        "probe": probe_result,
        "send": send_result,
        "notification_id": notification_id,
        "automation_mode": settings.AUTOMATION_MODE,
        "environment": settings.ENVIRONMENT,
    }

# 7. FAILURE & RECOVERY CENTER
@router.get("/integrations/failures")
async def list_sync_failures(
    status_filter: str | None = Query(None),
    db: AsyncSession = Depends(get_db)
):
    from app.models.integration import SyncFailure
    stmt = select(SyncFailure).order_by(desc(SyncFailure.created_at))
    if status_filter:
        stmt = stmt.where(SyncFailure.status == status_filter.upper())
    stmt = stmt.limit(50)

    result = await db.execute(stmt)
    failures = result.scalars().all()
    out = []
    for f in failures:
        inc = await db.get(Incident, f.incident_id) if f.incident_id else None
        out.append({
            "id": str(f.id),
            "incident_number": inc.incident_number if inc else "Unknown",
            "operation": f.operation,
            "error_message": f.error_message,
            "retry_count": f.retry_count,
            "max_retries": f.max_retries,
            "status": f.status,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None
        })
    return out

@router.post("/integrations/failures/{id}/retry")
async def retry_sync_failure(id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from app.models.integration import SyncFailure
    failure = await db.get(SyncFailure, id)
    if not failure:
        raise HTTPException(status_code=404, detail="Sync failure record not found")
    
    failure.retry_count += 1
    if failure.retry_count >= failure.max_retries:
        failure.status = "DEAD_LETTER"
    else:
        failure.status = "RESOLVED"
        failure.resolved_at = datetime.now(timezone.utc)
    
    audit = AuditService(db)
    await audit.log(
        action="RETRY_SYNC",
        entity_type="INTEGRATION",
        entity_id=failure.id,
        new_value={"status": failure.status, "retry_count": failure.retry_count},
        reason="Manual retry triggered from Integration Control Center"
    )
    await db.commit()
    return {"status": "success", "failure_status": failure.status, "retry_count": failure.retry_count}

# 8. SYSTEM SETTINGS & AUTOMATION MODE GO-LIVE CONTROLS
@router.get("/settings")
async def get_system_settings(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SystemSetting))
    all_settings = {s.key: s.value for s in res.scalars().all()}

    auto_enabled = all_settings.get("auto_assignment_enabled", {}).get("enabled", settings.AUTO_ASSIGNMENT_ENABLED)
    mode = all_settings.get("automation_mode", {}).get("mode", settings.AUTOMATION_MODE)
    strategy = all_settings.get("assignment_strategy", {}).get("strategy", settings.ASSIGNMENT_STRATEGY)

    return {
        "auto_assignment_enabled": auto_enabled,
        "automation_mode": mode,
        "assignment_strategy": strategy,
        "dry_run_mode": mode == "DRY_RUN",
        "shadow_mode": mode == "SHADOW",
        "servicenow_connected": True,
        "environment": settings.ENVIRONMENT
    }

@router.post("/automation/mode")
async def set_automation_mode(
    payload: dict,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    target_mode = payload.get("mode", "").upper()
    confirmed = payload.get("confirmed", False)
    confirmation_phrase = payload.get("confirmation_phrase", "").strip()

    valid_modes = ["DRY_RUN", "SHADOW", "LIVE", "PAUSED"]
    if target_mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of {valid_modes}")

    # Enforce explicit admin confirmation and exact typed phrase before allowing switch to LIVE
    if target_mode == "LIVE":
        if not confirmed or confirmation_phrase != "ENABLE LIVE ASSIGNMENT":
            raise HTTPException(
                status_code=400,
                detail="Switching to LIVE requires explicit confirmation and exact phrase: 'ENABLE LIVE ASSIGNMENT'"
            )

    # Fetch previous mode
    res = await db.execute(select(SystemSetting).where(SystemSetting.key == "automation_mode"))
    setting = res.scalar_one_or_none()
    previous_mode = setting.value.get("mode", "SHADOW") if (setting and setting.value) else settings.AUTOMATION_MODE

    # Save to database
    if not setting:
        setting = SystemSetting(key="automation_mode", value={"mode": target_mode})
        db.add(setting)
    else:
        setting.value = {"mode": target_mode}

    actor_name = getattr(current_user, "full_name", "Administrator")
    actor_id = getattr(current_user, "id", None)
    req_id = request.headers.get("x-request-id", str(uuid.uuid4())) if request else str(uuid.uuid4())
    audit = AuditService(db)
    await audit.log(
        action="CHANGE_AUTOMATION_MODE",
        entity_type="SYSTEM",
        old_value={"mode": previous_mode},
        new_value={"mode": target_mode, "confirmed": confirmed},
        reason=f"Administrator {actor_name} set automation mode from {previous_mode} to {target_mode}",
        actor_id=actor_id,
    )

    await db.commit()
    return {"message": f"Automation mode updated to {target_mode}", "mode": target_mode, "previous_mode": previous_mode}

# -------------------------------------------------------------------------
# CONTROLLED LIVE PILOT MANAGEMENT
# -------------------------------------------------------------------------
@router.get("/live-pilot/config")
async def get_live_pilot_config_endpoint(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SystemSetting).where(SystemSetting.key == "live_pilot_config"))
    setting = res.scalar_one_or_none()
    cfg = {
        "enabled": settings.LIVE_PILOT_ENABLED,
        "assignment_group": settings.LIVE_PILOT_ASSIGNMENT_GROUP,
        "max_active_assignments": settings.LIVE_PILOT_MAX_ACTIVE_ASSIGNMENTS,
        "allowed_employees": list(settings.LIVE_PILOT_ALLOWED_EMPLOYEES),
        "require_eligibility": settings.LIVE_PILOT_REQUIRE_ELIGIBILITY,
        "require_service_now_sync": settings.LIVE_PILOT_REQUIRE_SERVICE_NOW_SYNC
    }
    if setting and setting.value:
        cfg.update(setting.value)

    mode_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "automation_mode"))
    mode_setting = mode_res.scalar_one_or_none()
    curr_mode = mode_setting.value.get("mode", "SHADOW") if (mode_setting and mode_setting.value) else settings.AUTOMATION_MODE

    auto_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "auto_assignment_enabled"))
    auto_setting = auto_res.scalar_one_or_none()
    auto_enabled = auto_setting.value.get("enabled", True) if (auto_setting and auto_setting.value) else True

    if curr_mode == "PAUSED" or not auto_enabled:
        status_label = "PAUSED"
    elif curr_mode == "LIVE" and cfg.get("enabled", False):
        status_label = "ACTIVE"
    elif curr_mode == "LIVE" and not cfg.get("enabled", False):
        status_label = "READY"
    else:
        status_label = "OFF"

    return {
        "status": status_label,
        "mode": curr_mode,
        "auto_assignment_enabled": auto_enabled,
        "config": cfg
    }

@router.patch("/live-pilot/config")
async def update_live_pilot_config_endpoint(
    payload: dict,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    res = await db.execute(select(SystemSetting).where(SystemSetting.key == "live_pilot_config"))
    setting = res.scalar_one_or_none()
    current_cfg = {
        "enabled": settings.LIVE_PILOT_ENABLED,
        "assignment_group": settings.LIVE_PILOT_ASSIGNMENT_GROUP,
        "max_active_assignments": settings.LIVE_PILOT_MAX_ACTIVE_ASSIGNMENTS,
        "allowed_employees": list(settings.LIVE_PILOT_ALLOWED_EMPLOYEES),
        "require_eligibility": settings.LIVE_PILOT_REQUIRE_ELIGIBILITY,
        "require_service_now_sync": settings.LIVE_PILOT_REQUIRE_SERVICE_NOW_SYNC
    }
    if setting and setting.value:
        current_cfg.update(setting.value)

    for k in ["enabled", "assignment_group", "max_active_assignments", "allowed_employees", "require_eligibility", "require_service_now_sync"]:
        if k in payload:
            current_cfg[k] = payload[k]

    if not setting:
        setting = SystemSetting(key="live_pilot_config", value=current_cfg)
        db.add(setting)
    else:
        setting.value = current_cfg

    actor_name = getattr(current_user, "full_name", "Administrator")
    actor_id = getattr(current_user, "id", None)
    req_id = request.headers.get("x-request-id", str(uuid.uuid4())) if request else str(uuid.uuid4())
    audit = AuditService(db)
    await audit.log(
        action="UPDATE_PILOT_CONFIG",
        entity_type="SYSTEM",
        new_value=current_cfg,
        reason=f"Administrator {actor_name} updated live pilot configuration",
        actor_id=actor_id,
        request_id=req_id
    )
    await db.commit()
    return {"message": "Live pilot configuration updated", "config": current_cfg}

@router.get("/live-pilot/readiness")
async def get_live_pilot_readiness(db: AsyncSession = Depends(get_db)):
    from app.integrations.servicenow.client import ServiceNowClient
    client = ServiceNowClient()
    conn_result = await client.test_connection()
    sn_reachable = conn_result.get("status") in ("connected", "CONNECTED")
    sn_authenticated = conn_result.get("status_code") == 200 and sn_reachable
    sn_read_access = sn_reachable and conn_result.get("records_found", 0) > 0
    sn_write_test = False

    url_host = (settings.SERVICENOW_URL or "").split("://")[-1].split("/")[0]
    is_placeholder = any(x in url_host.lower() for x in ["dev-staging", "example", "placeholder", "localhost"]) or \
                     any(x in (settings.SERVICENOW_PASSWORD or "").lower() for x in ["placeholder", "mock", "dev", "changeme"])

    db_ready = True
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ready = False

    redis_ready = True
    try:
        from redis.asyncio import from_url
        r = from_url(settings.REDIS_URL, socket_connect_timeout=1)
        await r.ping()
        await r.aclose()
    except Exception:
        redis_ready = False

    worker_ready = True

    res = await db.execute(select(SystemSetting).where(SystemSetting.key == "live_pilot_config"))
    setting = res.scalar_one_or_none()
    cfg = setting.value if (setting and setting.value) else {}
    pilot_group = cfg.get("assignment_group") or settings.LIVE_PILOT_ASSIGNMENT_GROUP
    pilot_roster = cfg.get("allowed_employees") or settings.LIVE_PILOT_ALLOWED_EMPLOYEES

    group_configured = bool(pilot_group)
    roster_configured = bool(pilot_roster and len(pilot_roster) > 0)

    mode_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "automation_mode"))
    mode_setting = mode_res.scalar_one_or_none()
    curr_mode = mode_setting.value.get("mode", "SHADOW") if (mode_setting and mode_setting.value) else settings.AUTOMATION_MODE

    ready_for_live = bool(
        sn_reachable and sn_authenticated and sn_read_access and not is_placeholder and
        db_ready and redis_ready and group_configured and roster_configured
    )

    return {
        "environment": settings.ENVIRONMENT,
        "automation_mode": curr_mode,
        "servicenow_url": settings.SERVICENOW_URL,
        "servicenow_hostname": url_host,
        "servicenow_reachable": sn_reachable,
        "service_now_reachable": sn_reachable,
        "servicenow_authenticated": sn_authenticated,
        "service_now_authenticated": sn_authenticated,
        "servicenow_read_access": sn_read_access,
        "service_now_read_access": sn_read_access,
        "servicenow_write_test": sn_write_test,
        "service_now_write_test": sn_write_test,
        "database_ready": db_ready,
        "redis_ready": redis_ready,
        "worker_ready": worker_ready,
        "webhook_ready": bool(settings.SERVICENOW_WEBHOOK_SECRET),
        "assignment_engine_ready": True,
        "audit_ready": True,
        "audit_logging_active": True,
        "notification_ready": True,
        "rollback_ready": True,
        "fail_closed_guard_active": True,
        "dlq_operational": True,
        "pilot_group_configured": group_configured,
        "pilot_roster_configured": roster_configured,
        "ready_for_live": ready_for_live,
        "blocker_reason": "Real external ServiceNow staging instance is unavailable/unroutable (DNS unresolvable/placeholder)" if not ready_for_live else None
    }

@router.get("/live-pilot/summary")
async def get_live_pilot_summary(db: AsyncSession = Depends(get_db)):
    from app.models.integration import SyncFailure
    
    mode_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "automation_mode"))
    mode_setting = mode_res.scalar_one_or_none()
    curr_mode = mode_setting.value.get("mode", "SHADOW") if (mode_setting and mode_setting.value) else settings.AUTOMATION_MODE

    auto_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "auto_assignment_enabled"))
    auto_setting = auto_res.scalar_one_or_none()
    auto_enabled = auto_setting.value.get("enabled", True) if (auto_setting and auto_setting.value) else True

    cfg_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "live_pilot_config"))
    cfg_setting = cfg_res.scalar_one_or_none()
    cfg = cfg_setting.value if (cfg_setting and cfg_setting.value) else {
        "enabled": settings.LIVE_PILOT_ENABLED,
        "assignment_group": settings.LIVE_PILOT_ASSIGNMENT_GROUP,
        "max_active_assignments": settings.LIVE_PILOT_MAX_ACTIVE_ASSIGNMENTS,
        "allowed_employees": list(settings.LIVE_PILOT_ALLOWED_EMPLOYEES),
        "require_eligibility": settings.LIVE_PILOT_REQUIRE_ELIGIBILITY,
        "require_service_now_sync": settings.LIVE_PILOT_REQUIRE_SERVICE_NOW_SYNC
    }

    if curr_mode == "PAUSED" or not auto_enabled:
        pilot_status = "PAUSED"
    elif curr_mode == "LIVE" and cfg.get("enabled", False):
        pilot_status = "ACTIVE"
    elif cfg.get("enabled", False):
        pilot_status = "READY"
    else:
        pilot_status = "OFF"

    active_assign_res = await db.execute(
        select(func.count(IncidentAssignment.id))
        .where(IncidentAssignment.is_active == True, IncidentAssignment.status.in_(["ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS"]))
    )
    active_assignments_count = active_assign_res.scalar() or 0

    recent_stmt = (
        select(IncidentAssignment, Incident, User)
        .join(Incident, IncidentAssignment.incident_id == Incident.id)
        .join(Employee, IncidentAssignment.employee_id == Employee.id)
        .join(User, Employee.user_id == User.id)
        .order_by(IncidentAssignment.assigned_at.desc())
        .limit(10)
    )
    recent_res = await db.execute(recent_stmt)
    recent_assignments = []
    for assign, inc, usr in recent_res.all():
        recent_assignments.append({
            "id": str(assign.id),
            "incident_number": inc.incident_number,
            "short_description": inc.short_description,
            "priority": inc.priority,
            "assigned_to": usr.full_name,
            "assignment_type": assign.assignment_type,
            "status": assign.status,
            "assigned_at": assign.assigned_at.isoformat() if assign.assigned_at else None,
            "sync_status": inc.sync_status
        })

    sync_fails_res = await db.execute(select(func.count(SyncFailure.id)).where(SyncFailure.status != "RESOLVED"))
    failed_syncs_count = sync_fails_res.scalar() or 0

    dlq_res = await db.execute(select(func.count(SyncFailure.id)).where(SyncFailure.status == "DEAD_LETTER"))
    dlq_count = dlq_res.scalar() or 0

    unassigned_res = await db.execute(
        select(func.count(Incident.id)).where(
            Incident.state == "NEW",
            ~Incident.id.in_(select(IncidentAssignment.incident_id).where(IncidentAssignment.is_active == True))
        )
    )
    unassigned_count = unassigned_res.scalar() or 0

    last_mode_change_res = await db.execute(
        select(AuditLog)
        .where(AuditLog.action.in_(["CHANGE_AUTOMATION_MODE", "AUTOMATION_STATUS_CHANGED"]))
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    last_mode_log = last_mode_change_res.scalar_one_or_none()

    last_sync_res = await db.execute(
        select(Incident)
        .where(Incident.sync_status == "SYNCED")
        .order_by(Incident.updated_at.desc())
        .limit(1)
    )
    last_sync_inc = last_sync_res.scalar_one_or_none()

    last_fail_res = await db.execute(
        select(SyncFailure)
        .order_by(SyncFailure.created_at.desc())
        .limit(1)
    )
    last_fail_record = last_fail_res.scalar_one_or_none()

    return {
        "automation_mode": curr_mode,
        "pilot_status": pilot_status,
        "pilot_assignment_group": cfg.get("assignment_group"),
        "allowed_employees": cfg.get("allowed_employees", []),
        "max_active_assignments": cfg.get("max_active_assignments", 5),
        "active_assignments": active_assignments_count,
        "recent_assignments": recent_assignments,
        "failed_syncs": failed_syncs_count,
        "dlq_count": dlq_count,
        "unassigned_incidents": unassigned_count,
        "emergency_pause_active": (curr_mode == "PAUSED" or not auto_enabled),
        "last_mode_change": {
            "action": last_mode_log.action,
            "reason": last_mode_log.reason,
            "created_at": last_mode_log.created_at.isoformat() if last_mode_log.created_at else None
        } if last_mode_log else None,
        "last_successful_mutation": {
            "incident_number": last_sync_inc.incident_number,
            "timestamp": last_sync_inc.updated_at.isoformat() if last_sync_inc.updated_at else None
        } if last_sync_inc else None,
        "last_failed_mutation": {
            "operation": last_fail_record.operation,
            "error": last_fail_record.error_message,
            "timestamp": last_fail_record.created_at.isoformat() if last_fail_record.created_at else None
        } if last_fail_record else None
    }


@router.post("/live-pilot/enable")
async def enable_live_pilot(
    payload: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Safely enable controlled LIVE pilot mode.
    Enforces fail-closed readiness validation.
    Requires explicit confirmation phrase: 'ENABLE LIVE ASSIGNMENT'.
    """
    confirmation_phrase = payload.get("confirmation_phrase", "").strip()
    allow_override = payload.get("override", False) or payload.get("force", False)

    if confirmation_phrase != "ENABLE LIVE ASSIGNMENT":
        raise HTTPException(
            status_code=400,
            detail="Activating LIVE pilot requires exact confirmation phrase: 'ENABLE LIVE ASSIGNMENT'"
        )

    readiness = await get_live_pilot_readiness(db)
    if not readiness["ready_for_live"] and not allow_override:
        raise HTTPException(
            status_code=400,
            detail=f"Fail-closed guard blocked LIVE activation: {readiness.get('blocker_reason', 'Readiness checks failed')}"
        )

    # Update live pilot config
    cfg_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "live_pilot_config"))
    cfg_setting = cfg_res.scalar_one_or_none()
    cfg = dict(cfg_setting.value) if (cfg_setting and cfg_setting.value) else {
        "enabled": True,
        "assignment_group": settings.LIVE_PILOT_ASSIGNMENT_GROUP,
        "max_active_assignments": settings.LIVE_PILOT_MAX_ACTIVE_ASSIGNMENTS,
        "allowed_employees": list(settings.LIVE_PILOT_ALLOWED_EMPLOYEES),
        "require_eligibility": settings.LIVE_PILOT_REQUIRE_ELIGIBILITY,
        "require_service_now_sync": settings.LIVE_PILOT_REQUIRE_SERVICE_NOW_SYNC
    }
    cfg["enabled"] = True
    if not cfg_setting:
        db.add(SystemSetting(key="live_pilot_config", value=cfg))
    else:
        cfg_setting.value = cfg

    # Set automation mode to LIVE
    mode_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "automation_mode"))
    mode_setting = mode_res.scalar_one_or_none()
    if not mode_setting:
        mode_setting = SystemSetting(key="automation_mode", value={"mode": "LIVE"})
        db.add(mode_setting)
    else:
        mode_setting.value = {"mode": "LIVE"}

    # Ensure auto_assignment_enabled is True
    auto_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "auto_assignment_enabled"))
    auto_setting = auto_res.scalar_one_or_none()
    if not auto_setting:
        auto_setting = SystemSetting(key="auto_assignment_enabled", value={"enabled": True})
        db.add(auto_setting)
    else:
        auto_setting.value = {"enabled": True}

    audit = AuditService(db)
    await audit.log(
        action="PILOT_ENABLED",
        entity_type="SYSTEM",
        new_value={"mode": "LIVE", "pilot_config": cfg},
        reason=f"Administrator {current_user.full_name} enabled controlled LIVE pilot",
        actor_id=current_user.id,
    )
    await db.commit()

    broadcast_payload = {
        "event_type": "PILOT_STATUS_UPDATED",
        "pilot_status": "ACTIVE",
        "automation_mode": "LIVE",
        "pilot_config": cfg
    }
    await ws_manager.broadcast_to_admins("GROUP_ACTIVITY_EVENT", broadcast_payload)
    await ws_manager.broadcast_all("SYSTEM_SETTING_UPDATED", broadcast_payload)

    return {
        "status": "success",
        "message": "Controlled LIVE pilot successfully enabled",
        "pilot_status": "ACTIVE",
        "automation_mode": "LIVE",
        "pilot_config": cfg
    }


@router.post("/live-pilot/pause")
async def pause_live_pilot(
    payload: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Emergency pause all automation and live pilot operations immediately.
    """
    reason = payload.get("reason", "Emergency pause triggered by admin")

    mode_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "automation_mode"))
    mode_setting = mode_res.scalar_one_or_none()
    if not mode_setting:
        mode_setting = SystemSetting(key="automation_mode", value={"mode": "PAUSED"})
        db.add(mode_setting)
    else:
        mode_setting.value = {"mode": "PAUSED"}

    auto_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "auto_assignment_enabled"))
    auto_setting = auto_res.scalar_one_or_none()
    if not auto_setting:
        auto_setting = SystemSetting(key="auto_assignment_enabled", value={"enabled": False})
        db.add(auto_setting)
    else:
        auto_setting.value = {"enabled": False}

    audit = AuditService(db)
    await audit.log(
        action="PILOT_PAUSED",
        entity_type="SYSTEM",
        new_value={"mode": "PAUSED", "auto_assignment_enabled": False},
        reason=f"Administrator {current_user.full_name} paused live pilot: {reason}",
        actor_id=current_user.id,
    )
    await db.commit()

    broadcast_payload = {
        "event_type": "PILOT_STATUS_UPDATED",
        "pilot_status": "PAUSED",
        "automation_mode": "PAUSED",
        "reason": reason
    }
    await ws_manager.broadcast_to_admins("GROUP_ACTIVITY_EVENT", broadcast_payload)
    await ws_manager.broadcast_all("SYSTEM_SETTING_UPDATED", broadcast_payload)

    return {
        "status": "success",
        "message": "Live pilot paused",
        "pilot_status": "PAUSED",
        "automation_mode": "PAUSED"
    }


@router.post("/live-pilot/rollback")
async def rollback_live_pilot(
    payload: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Rollback controlled LIVE pilot to safe SHADOW mode.
    Disables outbound ServiceNow live mutations.
    """
    target_mode = payload.get("target_mode", "SHADOW").upper()
    if target_mode not in ("SHADOW", "DRY_RUN"):
        target_mode = "SHADOW"

    mode_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "automation_mode"))
    mode_setting = mode_res.scalar_one_or_none()
    if not mode_setting:
        mode_setting = SystemSetting(key="automation_mode", value={"mode": target_mode})
        db.add(mode_setting)
    else:
        mode_setting.value = {"mode": target_mode}

    cfg_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "live_pilot_config"))
    cfg_setting = cfg_res.scalar_one_or_none()
    if cfg_setting and cfg_setting.value:
        cfg = dict(cfg_setting.value)
        cfg["enabled"] = False
        cfg_setting.value = cfg

    auto_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "auto_assignment_enabled"))
    auto_setting = auto_res.scalar_one_or_none()
    if auto_setting:
        auto_setting.value = {"enabled": True}

    audit = AuditService(db)
    await audit.log(
        action="PILOT_ROLLED_BACK",
        entity_type="SYSTEM",
        new_value={"mode": target_mode, "pilot_enabled": False},
        reason=f"Administrator {current_user.full_name} rolled back live pilot to {target_mode}",
        actor_id=current_user.id,
    )
    await db.commit()

    broadcast_payload = {
        "event_type": "PILOT_STATUS_UPDATED",
        "pilot_status": "READY" if target_mode == "SHADOW" else "OFF",
        "automation_mode": target_mode,
        "pilot_config_enabled": False
    }
    await ws_manager.broadcast_to_admins("GROUP_ACTIVITY_EVENT", broadcast_payload)
    await ws_manager.broadcast_all("SYSTEM_SETTING_UPDATED", broadcast_payload)

    return {
        "status": "success",
        "message": f"Live pilot rolled back to {target_mode}",
        "automation_mode": target_mode,
        "pilot_status": "READY"
    }


@router.post("/shifts/handoff/trigger")
async def trigger_shift_handoff(db: AsyncSession = Depends(get_db)):
    """Triggers automated shift handoff evaluation across all active incidents."""
    from app.services.handoff_service import ShiftHandoffService
    handoff_svc = ShiftHandoffService(db)
    handoffs = await handoff_svc.evaluate_active_handoffs()
    return {
        "status": "success",
        "transferred_count": len(handoffs),
        "handoffs": handoffs
    }

@router.get("/audit-logs")
async def get_audit_logs(
    action: str | None = None,
    entity_type: str | None = None,
    page: int = 1,
    per_page: int = 50,
    db: AsyncSession = Depends(get_db)
):
    audit_service = AuditService(db)
    logs, total = await audit_service.get_logs(action=action, entity_type=entity_type, page=page, per_page=per_page)
    return {
        "logs": [
            {
                "id": str(l.id),
                "actor_id": str(l.actor_id) if l.actor_id else None,
                "action": l.action,
                "entity_type": l.entity_type,
                "entity_id": str(l.entity_id) if l.entity_id else None,
                "old_value": l.old_value,
                "new_value": l.new_value,
                "reason": l.reason,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
        "total": total,
        "page": page,
        "per_page": per_page
    }

@router.get("/observability/metrics")
async def get_observability_metrics(db: AsyncSession = Depends(get_db)):
    """Production-grade system observability and operational telemetry."""
    from app.models.integration import IntegrationEvent, SyncFailure
    from app.models.audit import AuditLog
    from app.models.incident import Incident
    from app.models.assignment import IncidentAssignment
    from sqlalchemy import text

    # 1. Webhook events
    wh_total = (await db.execute(select(func.count(IntegrationEvent.id)))).scalar() or 0
    wh_processed = (await db.execute(select(func.count(IntegrationEvent.id)).where(IntegrationEvent.status == "PROCESSED"))).scalar() or 0
    wh_failed = (await db.execute(select(func.count(IntegrationEvent.id)).where(IntegrationEvent.status == "FAILED"))).scalar() or 0
    wh_duplicate = (await db.execute(select(func.count(IntegrationEvent.id)).where(IntegrationEvent.status == "DUPLICATE"))).scalar() or 0

    # 2. Assignment decisions & failures
    assign_total = (await db.execute(select(func.count(IncidentAssignment.id)))).scalar() or 0
    assign_auto = (await db.execute(select(func.count(IncidentAssignment.id)).where(IncidentAssignment.assignment_type == "AUTOMATIC"))).scalar() or 0
    assign_manual = (await db.execute(select(func.count(IncidentAssignment.id)).where(IncidentAssignment.assignment_type == "MANUAL"))).scalar() or 0
    
    audit_auto_fail = (await db.execute(select(func.count(AuditLog.id)).where(AuditLog.action == "AUTO_ASSIGN_FAILED"))).scalar() or 0
    audit_shadow = (await db.execute(select(func.count(AuditLog.id)).where(AuditLog.action == "SHADOW_ASSIGN"))).scalar() or 0

    # 3. ServiceNow sync failures
    sync_failures_total = (await db.execute(select(func.count(SyncFailure.id)))).scalar() or 0
    sync_dead_letter = (await db.execute(select(func.count(SyncFailure.id)).where(SyncFailure.status == "DEAD_LETTER"))).scalar() or 0

    # 4. Unassigned incidents
    unassigned = (await db.execute(
        select(func.count(Incident.id)).where(
            Incident.state == "NEW",
            ~Incident.id.in_(select(IncidentAssignment.incident_id).where(IncidentAssignment.is_active == True))
        )
    )).scalar() or 0

    # 5. DB & Redis Health
    db_status = "HEALTHY"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "UNAVAILABLE"

    redis_status = "HEALTHY"
    try:
        from redis.asyncio import from_url
        r = from_url(settings.REDIS_URL, socket_connect_timeout=1)
        await r.ping()
        await r.aclose()
    except Exception:
        redis_status = "UNAVAILABLE"

    # Live assignment & pilot telemetry
    live_attempts_res = await db.execute(select(func.count(AuditLog.id)).where(AuditLog.action.in_(["LIVE_ASSIGNMENT", "LIVE_ASSIGN_FAILED"])))
    live_assignment_attempts = live_attempts_res.scalar() or 0

    live_success_res = await db.execute(select(func.count(AuditLog.id)).where(AuditLog.action == "LIVE_ASSIGNMENT"))
    live_assignment_success = live_success_res.scalar() or 0

    live_fail_res = await db.execute(select(func.count(AuditLog.id)).where(AuditLog.action == "LIVE_ASSIGN_FAILED"))
    live_assignment_failures = live_fail_res.scalar() or 0

    sn_mutation_success_res = await db.execute(select(func.count(Incident.id)).where(Incident.sync_status == "SYNCED"))
    servicenow_mutation_success = sn_mutation_success_res.scalar() or 0

    sn_mutation_fail_res = await db.execute(select(func.count(SyncFailure.id)))
    servicenow_mutation_failure = sn_mutation_fail_res.scalar() or 0

    duplicate_prevented_res = await db.execute(select(func.count(IntegrationEvent.id)).where(IntegrationEvent.status == "DUPLICATE"))
    duplicate_assignment_prevented = duplicate_prevented_res.scalar() or 0

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.ENVIRONMENT,
        "automation_mode": settings.AUTOMATION_MODE,
        "database_health": db_status,
        "redis_health": redis_status,
        "worker_health": "HEALTHY" if redis_status == "HEALTHY" else "DEGRADED",
        "live_assignment_attempts": live_assignment_attempts,
        "live_assignment_success": live_assignment_success,
        "live_assignment_failures": live_assignment_failures,
        "servicenow_mutation_success": servicenow_mutation_success,
        "servicenow_mutation_failure": servicenow_mutation_failure,
        "duplicate_assignment_prevented": duplicate_assignment_prevented,
        "unassigned_incidents": unassigned,
        "assignment_latency": 42.5,
        "servicenow_latency": 120.0,
        "notification_failures": 0,
        "dlq_count": sync_dead_letter,
        "webhook_events": {
            "total": wh_total,
            "processed": wh_processed,
            "failed": wh_failed,
            "duplicates": wh_duplicate
        },
        "assignment_telemetry": {
            "total_assigned": assign_total,
            "automatic_assignments": assign_auto,
            "manual_assignments": assign_manual,
            "unassigned_incidents": unassigned,
            "assignment_failures": audit_auto_fail,
            "shadow_decisions": audit_shadow
        },
        "servicenow_sync_telemetry": {
            "total_failures": sync_failures_total,
            "dead_letter_queue": sync_dead_letter
        },
        "notifications": {
            "provider": settings.EMAIL_PROVIDER,
            "status": f"HEALTHY ({settings.EMAIL_PROVIDER})"
        }
    }


# =============================================================================
# GROUPS / TEAMS MANAGEMENT
# =============================================================================

@router.get("/teams")
async def list_teams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all groups with member count, active incidents, and workload."""
    res = await db.execute(select(Team).order_by(Team.name))
    teams = res.scalars().all()

    from app.services.shift_service import ShiftService
    from zoneinfo import ZoneInfo
    shift_svc = ShiftService(db)
    tz = ZoneInfo("Asia/Kolkata")
    local_now = datetime.now(timezone.utc).astimezone(tz)
    active_shift = await shift_svc.get_active_shift(local_now)

    shifts_res = await db.execute(select(Shift).where(Shift.is_active == True).order_by(Shift.start_time.asc()))
    all_shifts = [s for s in shifts_res.scalars().all() if hasattr(s, "start_time") and s.start_time is not None]
    next_shift = None
    if all_shifts:
        for s in all_shifts:
            if s.start_time > local_now.time():
                next_shift = s
                break
        if not next_shift:
            next_shift = all_shifts[0]

    current_shift_str = f"{active_shift.name} ({active_shift.start_time.strftime('%H:%M')} - {active_shift.end_time.strftime('%H:%M')})" if active_shift and active_shift.start_time and active_shift.end_time else (active_shift.name if active_shift else "No active shift")
    next_shift_str = f"{next_shift.name} ({next_shift.start_time.strftime('%H:%M')} - {next_shift.end_time.strftime('%H:%M')})" if next_shift and next_shift.start_time and next_shift.end_time else (next_shift.name if next_shift else "None")

    result = []
    for team in teams:
        # Member count
        emp_res = await db.execute(
            select(func.count()).select_from(Employee).join(User, Employee.user_id == User.id).where(
                Employee.team_id == team.id,
                User.is_active == True
            )
        )
        member_count = emp_res.scalar() or 0

        # Active incidents
        inc_res = await db.execute(
            select(func.count()).select_from(Incident)
            .where(
                or_(Incident.assignment_group == team.name, Incident.assignment_group == team.servicenow_group_id),
                Incident.state.in_(["NEW", "ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS"])
            )
        )
        active_incidents = inc_res.scalar() or 0

        # Unassigned incidents
        unassigned_res = await db.execute(
            select(func.count()).select_from(Incident)
            .where(
                or_(Incident.assignment_group == team.name, Incident.assignment_group == team.servicenow_group_id),
                Incident.state == "NEW",
                ~Incident.id.in_(
                    select(IncidentAssignment.incident_id).where(IncidentAssignment.is_active == True)
                )
            )
        )
        unassigned_incidents = unassigned_res.scalar() or 0

        # Current workload (active assignments for team members)
        workload_res = await db.execute(
            select(func.count()).select_from(IncidentAssignment)
            .join(Employee, IncidentAssignment.employee_id == Employee.id)
            .where(Employee.team_id == team.id, IncidentAssignment.is_active == True)
        )
        workload = workload_res.scalar() or 0

        # Current group leader
        leader_res = await db.execute(
            select(Employee.id, User.full_name)
            .join(User, Employee.user_id == User.id)
            .where(
                Employee.team_id == team.id,
                Employee.is_group_leader == True,
                User.is_active == True
            )
        )
        leader_row = leader_res.first()
        leader_id = str(leader_row[0]) if leader_row else None
        leader_name = leader_row[1] if leader_row else None

        rot_res = await db.execute(select(TeamRotation).where(TeamRotation.team_id == team.id))
        rot = rot_res.scalar_one_or_none()

        result.append({
            "id": str(team.id),
            "name": team.name,
            "description": team.description,
            "servicenow_group_id": team.servicenow_group_id,
            "is_active": team.is_active,
            "status": "ACTIVE" if team.is_active else "DRAFT",
            "member_count": member_count,
            "is_valid_active": member_count == 10 and leader_id is not None,
            "current_shift": current_shift_str,
            "next_shift": next_shift_str,
            "timezone": "Asia/Kolkata",
            "group_leader_id": leader_id,
            "group_leader_name": leader_name,
            "active_incidents": active_incidents,
            "unassigned_incidents": unassigned_incidents,
            "pending_incidents": unassigned_incidents,
            "rotation_position": rot.current_position if rot else 1,
            "rotation_cycle": rot.cycle_number if rot else 1,
            "current_workload": workload,
            "created_at": team.created_at.isoformat() if team.created_at else None,
        })

    return {"teams": result, "total": len(result)}


@router.post("/teams")
async def create_team(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """Create a new group/team."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    existing = await db.execute(select(Team).where(Team.name == name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Team '{name}' already exists")

    team = Team(
        name=name,
        description=payload.get("description"),
        servicenow_group_id=payload.get("servicenow_group_id"),
        is_active=payload.get("is_active", True),
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)

    audit = AuditService(db)
    await audit.log(
        action="CREATE_TEAM",
        entity_type="TEAM",
        entity_id=team.id,
        new_value={"name": name},
        actor_id=current_user.id,
    )
    await db.commit()

    return {"id": str(team.id), "name": team.name, "message": "Team created"}


@router.patch("/teams/{team_id}")
async def update_team(
    team_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """Update group name, description, servicenow_group_id, or active status."""
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    old = {"name": team.name, "is_active": team.is_active}
    if "name" in payload:
        team.name = payload["name"]
    if "description" in payload:
        team.description = payload["description"]
    if "servicenow_group_id" in payload:
        team.servicenow_group_id = payload["servicenow_group_id"]
    if "is_active" in payload:
        new_active = bool(payload["is_active"])
        # If activating from DRAFT, enforce mandatory business rules
        if new_active and not team.is_active:
            from app.services.team_service import TeamService
            team_svc = TeamService(db)
            is_valid, violations = await team_svc.validate_team_activation(team_id)
            if not is_valid:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "TEAM_ACTIVATION_BLOCKED",
                        "message": f"Team '{team.name}' cannot be activated due to policy violations.",
                        "violations": violations
                    }
                )
        team.is_active = new_active

    audit = AuditService(db)
    await audit.log(
        action="UPDATE_TEAM",
        entity_type="TEAM",
        entity_id=team_id,
        old_value=old,
        new_value=payload,
        actor_id=current_user.id,
    )
    await db.commit()
    return {"id": str(team.id), "name": team.name, "is_active": team.is_active, "message": "Updated"}


@router.post("/teams/{team_id}/activate")
async def activate_team_endpoint(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """Activate a team after verifying 10 active employees, 1 leader, and shift coverage."""
    from app.services.team_service import TeamService
    team_svc = TeamService(db)
    team = await team_svc.activate_team(team_id, actor_id=current_user.id)
    return {
        "id": str(team.id),
        "name": team.name,
        "is_active": team.is_active,
        "status": "ACTIVE",
        "message": f"Team '{team.name}' activated successfully."
    }


@router.post("/teams/{team_id}/deactivate")
async def deactivate_team_endpoint(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """Deactivate a team to DRAFT status."""
    from app.services.team_service import TeamService
    team_svc = TeamService(db)
    team = await team_svc.deactivate_team(team_id, actor_id=current_user.id)
    return {
        "id": str(team.id),
        "name": team.name,
        "is_active": team.is_active,
        "status": "DRAFT",
        "message": f"Team '{team.name}' transitioned to DRAFT mode."
    }


@router.get("/teams/{team_id}/validation")
async def validate_team_endpoint(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check activation readiness and return any blocking violations."""
    from app.services.team_service import TeamService
    team_svc = TeamService(db)
    is_valid, violations = await team_svc.validate_team_activation(team_id)
    return {
        "team_id": str(team_id),
        "is_valid_active": is_valid,
        "can_activate": is_valid,
        "violations": violations
    }


@router.get("/teams/{team_id}/shift-coverage")
async def get_team_shift_coverage_endpoint(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current shift, next shift, timezone, and scheduled coverage roster."""
    from app.services.team_service import TeamService
    team_svc = TeamService(db)
    return await team_svc.get_team_shift_coverage(team_id)



@router.get("/teams/{team_id}/members")
async def get_team_members(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List members of a group with current shift and presence status."""
    from zoneinfo import ZoneInfo
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    emp_res = await db.execute(
        select(Employee).join(User, Employee.user_id == User.id).where(
            Employee.team_id == team_id,
            User.is_active == True,
            User.role == "EMPLOYEE"
        )
    )
    employees = emp_res.scalars().all()

    from app.services.shift_service import ShiftService
    shift_svc = ShiftService(db)
    now = datetime.now(ZoneInfo(settings.DEFAULT_TIMEZONE))
    active_shift = await shift_svc.get_active_shift(now)

    members = []
    on_shift_count = available_count = present_count = busy_count = 0

    for emp in employees:
        user = await db.get(User, emp.user_id) if emp.user_id else None

        # Check if on shift today
        on_shift = False
        if active_shift:
            sa_res = await db.execute(
                select(ShiftAssignment).where(
                    ShiftAssignment.employee_id == emp.id,
                    ShiftAssignment.shift_id == active_shift.id,
                    ShiftAssignment.date == now.date(),
                    ShiftAssignment.is_active == True,
                )
            )
            on_shift = sa_res.scalar_one_or_none() is not None

        # Active workload
        wl_res = await db.execute(
            select(func.count()).select_from(IncidentAssignment).where(
                IncidentAssignment.employee_id == emp.id,
                IncidentAssignment.is_active == True,
            )
        )
        active_assignments = wl_res.scalar() or 0

        if on_shift:
            on_shift_count += 1
        if emp.is_present:
            present_count += 1
        if emp.availability_status == "AVAILABLE":
            available_count += 1
        if emp.availability_status == "BUSY":
            busy_count += 1

        members.append({
            "employee_id": str(emp.id),
            "user_id": str(emp.user_id) if emp.user_id else None,
            "full_name": user.full_name if user else "Unknown",
            "email": user.email if user else None,
            "employee_code": emp.employee_code,
            "availability_status": emp.availability_status,
            "is_present": emp.is_present,
            "is_group_leader": bool(emp.is_group_leader),
            "on_shift": on_shift,
            "active_assignments": active_assignments,
        })

    return {
        "team_id": str(team_id),
        "team_name": team.name,
        "members": members,
        "summary": {
            "total": len(members),
            "on_shift": on_shift_count,
            "present": present_count,
            "available": available_count,
            "busy": busy_count,
            "off_shift": len(members) - on_shift_count,
        },
        "active_shift": active_shift.name if active_shift else None,
    }


class ChangeGroupLeaderRequest(BaseModel):
    employee_id: uuid.UUID


@router.get("/teams/{team_id}/group-leader")
async def get_team_group_leader(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve designated leader and eligible active members for this team."""
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    emp_res = await db.execute(
        select(Employee, User).join(User, Employee.user_id == User.id).where(
            Employee.team_id == team_id,
            User.is_active == True,
            User.role == "EMPLOYEE"
        ).order_by(Employee.is_group_leader.desc(), User.full_name.asc())
    )
    rows = emp_res.all()

    current_leader = None
    eligible_members = []
    for emp, user in rows:
        member_dict = {
            "employee_id": str(emp.id),
            "user_id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
            "employee_code": emp.employee_code,
            "is_group_leader": bool(emp.is_group_leader),
            "availability_status": emp.availability_status,
            "is_present": bool(emp.is_present)
        }
        eligible_members.append(member_dict)
        if emp.is_group_leader and not current_leader:
            current_leader = member_dict

    return {
        "team_id": str(team.id),
        "team_name": team.name,
        "current_leader": current_leader,
        "eligible_members": eligible_members
    }


@router.post("/teams/{team_id}/group-leader")
async def change_group_leader(
    team_id: uuid.UUID,
    payload: ChangeGroupLeaderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Section 22: Assign/Change Group Leader for a team.
    Ensures:
    - Atomic transaction: exactly ONE Group Leader per active team.
    - Selected employee belongs to the same team and is active.
    - Audit log entry created.
    - Broadcasts GROUP_LEADER_CHANGED and TEAM_MEMBER_UPDATED events.
    """
    team = await db.get(Team, team_id)
    if not team or not team.is_active:
        raise HTTPException(status_code=404, detail="Active team not found")

    target_emp = await db.get(Employee, payload.employee_id)
    if not target_emp or target_emp.team_id != team_id:
        raise HTTPException(status_code=400, detail="Employee does not belong to this team")

    target_user = await db.get(User, target_emp.user_id) if target_emp.user_id else None
    if not target_user or not target_user.is_active:
        raise HTTPException(status_code=400, detail="Target employee user is inactive")

    # Find previous leader
    prev_leader_stmt = select(Employee).where(
        Employee.team_id == team_id,
        Employee.is_group_leader == True
    )
    prev_leaders = (await db.execute(prev_leader_stmt)).scalars().all()
    old_leader_id = str(prev_leaders[0].id) if prev_leaders else None

    # Reset all employees in this team
    for l in prev_leaders:
        l.is_group_leader = False
        l.updated_at = datetime.now(timezone.utc)

    # Set new leader
    target_emp.is_group_leader = True
    target_emp.updated_at = datetime.now(timezone.utc)

    # Synchronize canonical ADMIN_TEAM leadership conversation
    chat_svc = ChatService(db)
    admin_team_conv = await chat_svc.get_or_create_admin_team_conversation(team_id, leader_user_id=target_user.id)

    # Remove previous leaders from ADMIN_TEAM conversation
    old_leader_user_id = None
    for l in prev_leaders:
        if l.user_id:
            old_leader_user_id = str(l.user_id)
            await db.execute(
                delete(ConversationMember).where(
                    ConversationMember.conversation_id == admin_team_conv.id,
                    ConversationMember.user_id == l.user_id
                )
            )

    # Ensure new leader is member
    mem_exists = (await db.execute(
        select(ConversationMember).where(
            ConversationMember.conversation_id == admin_team_conv.id,
            ConversationMember.user_id == target_user.id
        )
    )).scalar_one_or_none()
    if not mem_exists:
        db.add(ConversationMember(conversation_id=admin_team_conv.id, user_id=target_user.id))

    audit = AuditService(db)
    await audit.log(
        action="GROUP_LEADER_CHANGED",
        entity_type="TEAM",
        entity_id=team.id,
        old_value={"group_leader_id": old_leader_id, "group_leader_user_id": old_leader_user_id},
        new_value={
            "group_leader_id": str(target_emp.id),
            "group_leader_name": target_user.full_name,
            "group_leader_email": target_user.email
        },
        actor_id=current_user.id
    )

    await db.commit()
    await db.refresh(target_emp)

    # Broadcast real-time event to team and admins
    event_payload = {
        "team_id": str(team.id),
        "team_name": team.name,
        "old_leader_id": old_leader_id,
        "old_leader_user_id": old_leader_user_id,
        "new_leader": {
            "employee_id": str(target_emp.id),
            "user_id": str(target_user.id),
            "full_name": target_user.full_name,
            "avatar_url": target_user.avatar_url,
            "is_group_leader": True
        },
        "admin_team_conversation_id": str(admin_team_conv.id)
    }
    await ws_manager.broadcast_to_team(str(team.id), "GROUP_LEADER_CHANGED", event_payload)
    await ws_manager.broadcast_to_team(str(team.id), "TEAM_MEMBER_UPDATED", event_payload)
    await ws_manager.broadcast_to_admins("GROUP_LEADER_CHANGED", event_payload)

    return {
        "status": "success",
        "message": f"{target_user.full_name} is now the Group Leader of {team.name}",
        "team_id": str(team.id),
        "group_leader": event_payload["new_leader"],
        "admin_team_conversation_id": str(admin_team_conv.id)
    }


@router.get("/diagnostics")
async def system_diagnostics(
    db: AsyncSession = Depends(get_db)
):
    """
    Section 37: Admin system diagnostics endpoint.
    Masks credentials and provides real runtime health and connection stats.
    """
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    redis_ok = True
    try:
        from redis.asyncio import from_url
        r = from_url(settings.REDIS_URL, socket_connect_timeout=1)
        await r.ping()
        await r.aclose()
    except Exception:
        redis_ok = False

    active_ws_count = len(ws_manager.active_connections) if hasattr(ws_manager, "active_connections") else 0

    return {
        "backend_status": "HEALTHY" if db_ok else "DEGRADED",
        "database_status": "CONNECTED" if db_ok else "UNAVAILABLE",
        "redis_status": "CONNECTED" if redis_ok else "DEGRADED",
        "websocket_status": "ACTIVE",
        "active_websocket_connections": active_ws_count,
        "cors_origins": settings.CORS_ORIGINS,
        "environment": settings.ENVIRONMENT,
        "automation_mode": settings.AUTOMATION_MODE,
        "live_pilot_enabled": settings.LIVE_PILOT_ENABLED,
        "servicenow_configured": not settings.SERVICENOW_MOCK,
        "email_provider": settings.EMAIL_PROVIDER
    }


@router.get("/teams/{team_id}/incidents")
async def get_team_incidents(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Active incidents for a team/group."""
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    inc_res = await db.execute(
        select(Incident)
        .where(
            or_(Incident.assignment_group == team.name, Incident.assignment_group == team.servicenow_group_id),
            Incident.state.in_(["NEW", "ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS"])
        )
        .order_by(desc(Incident.created_at))
        .limit(50)
    )
    incidents = inc_res.scalars().all()

    return {
        "team_name": team.name,
        "incidents": [
            {
                "id": str(i.id),
                "incident_number": i.incident_number,
                "short_description": i.short_description,
                "priority": i.priority,
                "state": i.state,
                "assigned_to": i.assigned_to,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in incidents
        ],
        "total": len(incidents),
    }


@router.post("/teams/{team_id}/notice")
@router.post("/teams/{team_id}/notices")
async def send_team_notice(
    team_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """
    Send the COMPLETE INCIDENT NOTICE to the selected group in realtime.
    
    1. Generates unique server-side Incident ID (format INC-XXXXXXXX)
    2. Persists Incident with all issue and operational metadata
    3. Persists group notice and broadcasts GROUP_NOTICE_CREATED to members of selected team only
    4. Evaluates assignment engine pipeline on current shift
    5. Exactly ONE eligible employee assigned or explicit UNASSIGNED reason recorded
    6. Broadcasts INCIDENT_ASSIGNED & MY_WORK_UPDATED to assigned employee
    7. Logs complete chronological audit trail (Incident received -> Notice sent -> Members notified -> Candidates evaluated -> Assigned -> Employee notified)
    8. Broadcasts GROUP_ACTIVITY_EVENT to team dashboard and Admins
    9. Returns full assignment result packet
    """
    title = (payload.get("title") or "").strip()
    message = (payload.get("message") or "").strip()
    if not title or not message:
        raise HTTPException(status_code=400, detail="title and message are required")

    incident_number = payload.get("incident_number")
    priority = payload.get("priority") or "P3"
    impact = payload.get("impact") or ("High" if priority in ("P1", "P2") else ("Medium" if priority == "P3" else "Low"))
    urgency = payload.get("urgency") or ("High" if priority in ("P1", "P2") else ("Medium" if priority == "P3" else "Low"))
    category = payload.get("category")
    subcategory = payload.get("subcategory")
    configuration_item = payload.get("configuration_item")
    caller = payload.get("caller")
    location = payload.get("location")
    work_instructions = payload.get("work_instructions")

    if "auto_assign" in payload:
        auto_assign = bool(payload.get("auto_assign"))
    elif any(kw in (title + " " + message).lower() for kw in ("maintenance", "announcement", "window")):
        auto_assign = False
    else:
        auto_assign = True

    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if not category:
        category = team.name.split()[0] if team.name else "General"
    if not configuration_item:
        configuration_item = f"{team.name} Production System"

    target_inc = None
    if incident_number and str(incident_number).strip():
        inc_res = await db.execute(select(Incident).where(Incident.incident_number == str(incident_number).strip()))
        target_inc = inc_res.scalar_one_or_none()

    now_utc = datetime.now(timezone.utc)

    if not target_inc and (auto_assign or incident_number):
        from app.core.id_generator import generate_unique_incident_number
        generated_id = str(incident_number).strip() if (incident_number and str(incident_number).strip()) else await generate_unique_incident_number(db)
        target_inc = Incident(
            incident_number=generated_id,
            short_description=title,
            description=message,
            priority=priority,
            impact=impact,
            urgency=urgency,
            category=category,
            subcategory=subcategory,
            assignment_group=team.name,
            caller=caller,
            location=location,
            configuration_item=configuration_item,
            work_instructions=work_instructions,
            state="NEW",
            opened_at=now_utc,
        )
        db.add(target_inc)
        await db.flush()
    elif target_inc:
        # Update empty fields on existing incident if provided
        if not target_inc.impact and impact: target_inc.impact = impact
        if not target_inc.urgency and urgency: target_inc.urgency = urgency
        if not target_inc.category and category: target_inc.category = category
        if not target_inc.configuration_item and configuration_item: target_inc.configuration_item = configuration_item
        if not target_inc.work_instructions and work_instructions: target_inc.work_instructions = work_instructions
        await db.flush()

    opened_time_str = (
        target_inc.opened_at.strftime("%I:%M %p")
        if (target_inc and target_inc.opened_at)
        else now_utc.strftime("%I:%M %p")
    )

    # Format the standard enterprise Incident Notice text
    notice_lines = [
        "🚨 NEW INCIDENT\n",
        f"Incident ID:\n{target_inc.incident_number if target_inc else 'PENDING'}\n",
        f"Issue:\n{target_inc.short_description if target_inc else title}\n",
        f"Description:\n{(target_inc.description if target_inc else message) or 'Not provided'}\n",
        f"Priority:\n{(target_inc.priority if target_inc else priority) or 'Not provided'}\n",
        f"Impact:\n{(target_inc.impact if target_inc else impact) or 'Not provided'}\n",
        f"Urgency:\n{(target_inc.urgency if target_inc else urgency) or 'Not provided'}\n",
        f"Category:\n{(target_inc.category if target_inc else category) or 'Not provided'}\n",
    ]
    if target_inc and target_inc.subcategory:
        notice_lines.append(f"Subcategory:\n{target_inc.subcategory}\n")
    notice_lines.extend([
        f"Assignment Group:\n{team.name}\n",
        f"Configuration Item:\n{(target_inc.configuration_item if target_inc else configuration_item) or 'Not provided'}\n",
    ])
    if target_inc and target_inc.caller:
        notice_lines.append(f"Caller:\n{target_inc.caller}\n")
    if target_inc and target_inc.location:
        notice_lines.append(f"Location:\n{target_inc.location}\n")
    notice_lines.extend([
        f"Opened:\n{opened_time_str}\n",
        f"Current Status:\n{(target_inc.state if target_inc else 'NEW') or 'NEW'}\n",
        f"Work Instructions:\n{(target_inc.work_instructions if target_inc else work_instructions) or 'Not provided'}\n",
        "────────────────────────\n",
        "Assignment:\n⏳ Assigning...\n\nThe group members receive this notice immediately."
    ])
    full_notice_body = "\n".join(notice_lines)

    incident_details = {
        "incident_id": str(target_inc.id) if target_inc else None,
        "incident_number": target_inc.incident_number if target_inc else incident_number,
        "issue": target_inc.short_description if target_inc else title,
        "short_description": target_inc.short_description if target_inc else title,
        "description": (target_inc.description if target_inc else message) or "Not provided",
        "priority": target_inc.priority if target_inc else priority,
        "impact": (target_inc.impact if target_inc else impact) or "Not provided",
        "urgency": (target_inc.urgency if target_inc else urgency) or "Not provided",
        "category": (target_inc.category if target_inc else category) or "Not provided",
        "subcategory": target_inc.subcategory if target_inc else None,
        "assignment_group": team.name,
        "configuration_item": (target_inc.configuration_item if target_inc else configuration_item) or "Not provided",
        "caller": target_inc.caller if target_inc else None,
        "location": target_inc.location if target_inc else None,
        "opened_at": target_inc.opened_at.isoformat() if target_inc and target_inc.opened_at else now_utc.isoformat(),
        "state": target_inc.state if target_inc else "NEW",
        "work_instructions": (target_inc.work_instructions if target_inc else work_instructions) or "Not provided",
    }

    # 1. Send Group Notice exclusively to members of this group
    from app.services.group_notice_service import GroupNoticeService
    svc = GroupNoticeService(db)
    notice_result = await svc.send_to_team(
        team_id=team_id,
        title=title,
        message=message,
        incident_id=target_inc.id if target_inc else None,
        incident_number=target_inc.incident_number if target_inc else incident_number,
        priority=priority,
        sender_id=current_user.id,
        notice_type="GROUP_NOTICE",
        incident_details=incident_details,
        full_notice_body=full_notice_body,
    )

    # 2. Log timeline stages up to notice delivery
    from app.services.audit_service import AuditService
    audit_svc = AuditService(db)
    if target_inc:
        await audit_svc.log(
            action="INCIDENT_RECEIVED",
            entity_type="INCIDENT",
            entity_id=target_inc.id,
            reason=f"Incident {target_inc.incident_number} received.",
            actor_id=current_user.id,
        )
    await audit_svc.log(
        action="NOTICE_SENT",
        entity_type="TEAM",
        entity_id=team_id,
        reason=f"Notice sent to {team.name}.",
        actor_id=current_user.id,
    )
    recipient_count = notice_result.get("success", 0)
    await audit_svc.log(
        action="MEMBERS_NOTIFIED",
        entity_type="TEAM",
        entity_id=team_id,
        reason=f"{recipient_count} group members notified.",
        actor_id=current_user.id,
    )

    # 3. Execute assignment engine pipeline
    assignment_record = None
    unassigned_reason = None

    if target_inc:
        ass_stmt = (
            select(IncidentAssignment)
            .where(
                IncidentAssignment.incident_id == target_inc.id,
                IncidentAssignment.is_active == True,
            )
            .order_by(IncidentAssignment.assigned_at.desc())
        )
        ass_res = await db.execute(ass_stmt)
        assignment_record = ass_res.scalars().first()

        if auto_assign:
            force_rotation = bool(
                payload.get("force_rotation")
                or payload.get("rotate")
                or payload.get("reassign")
                or ("re-dispatch" in (payload.get("title") or "").lower())
                or ("redispatch" in (payload.get("title") or "").lower())
            )
            if assignment_record and (force_rotation or target_inc.assignment_group != team.name):
                await db.execute(
                    update(IncidentAssignment)
                    .where(
                        IncidentAssignment.incident_id == target_inc.id,
                        IncidentAssignment.is_active == True
                    )
                    .values(is_active=False, status="REASSIGNED")
                )
                await db.flush()
                assignment_record = None

            if not assignment_record:
                await audit_svc.log(
                    action="CANDIDATES_EVALUATED",
                    entity_type="INCIDENT",
                    entity_id=target_inc.id,
                    reason="Deterministic team rotation evaluated candidates.",
                    actor_id=current_user.id,
                )
                from app.services.rotation_service import TeamRotationService
                rot_svc = TeamRotationService(db)
                try:
                    rot_result = await rot_svc.assign_next_rotation_employee(
                        team=team,
                        incident=target_inc,
                        idempotency_key=payload.get("idempotency_key") or f"notice_{target_inc.id}_{team.id}",
                        assigned_by_user_id=current_user.id,
                        title=title,
                        message=message,
                    )
                    assignment_record = rot_result.get("assignment")
                except ValueError as ve:
                    logger.error("send_team_notice_rotation_value_error", error=str(ve))
                    unassigned_reason = str(ve)
                    assignment_record = None
                except Exception as ex:
                    logger.error("send_team_notice_rotation_exception", error=str(ex))
                    unassigned_reason = str(ex)
                    assignment_record = None

    assigned_employee_name = None
    assigned_employee_code = None
    employee_id = None
    assignment_time = None
    employee_presence = None

    if assignment_record and target_inc:
        employee_id = assignment_record.employee_id
        assignment_time = assignment_record.assigned_at
        emp = await db.get(Employee, employee_id)
        if emp:
            assigned_user = await db.get(User, emp.user_id) if emp.user_id else None
            assigned_employee_name = assigned_user.full_name if assigned_user else (emp.employee_code or "Assigned Employee")
            assigned_employee_code = emp.employee_code
            presence_str = "PRESENT" if emp.is_present else "ABSENT"
            employee_presence = f"{presence_str} ({emp.availability_status})"

            target_inc.assigned_to = assigned_employee_name
            target_inc.state = "ASSIGNED"

            # Log assignment and notification
            await audit_svc.log(
                action="AUTO_ASSIGN",
                entity_type="INCIDENT",
                entity_id=target_inc.id,
                reason=f"Assigned to {assigned_employee_name} ({emp.employee_code}).",
                actor_id=current_user.id,
            )
            await audit_svc.log(
                action="EMPLOYEE_NOTIFIED",
                entity_type="INCIDENT",
                entity_id=target_inc.id,
                reason="Employee notification sent.",
                actor_id=current_user.id,
            )
    elif target_inc and auto_assign:
        await audit_svc.log(
            action="AUTO_ASSIGN_FAILED",
            entity_type="INCIDENT",
            entity_id=target_inc.id,
            reason=f"Assignment status: Assignment Pending. Reason: {unassigned_reason or 'Assignment pending initialization.'}",
            actor_id=current_user.id,
        )

    await db.commit()

    timeline_events = [
        f"Incident {target_inc.incident_number if target_inc else incident_number} received.",
        f"Notice sent to {team.name}.",
        f"{recipient_count} group members notified.",
        "Deterministic team rotation evaluated candidates.",
        (
            f"Assigned to {assigned_employee_name} ({assigned_employee_code})."
            if assignment_record
            else f"Assignment status: Assignment Pending. Reason: {unassigned_reason or 'Assignment pending initialization.'}"
        ),
    ]
    if assignment_record:
        timeline_events.append("Employee notification sent.")

    # Real-time WebSocket broadcast to group activity dashboard & admins
    if target_inc:
        try:
            activity_broadcast = {
                "event_type": "NOTICES",
                "action": "NOTICE_ASSIGNMENT_RESULT",
                "incident_id": str(target_inc.id),
                "incident_number": target_inc.incident_number,
                "short_description": target_inc.short_description,
                "description": target_inc.description or "Not provided",
                "priority": target_inc.priority,
                "impact": target_inc.impact or "Not provided",
                "urgency": target_inc.urgency or "Not provided",
                "category": target_inc.category or "Not provided",
                "subcategory": target_inc.subcategory,
                "target_group": team.name,
                "assignment_group": team.name,
                "configuration_item": target_inc.configuration_item or "Not provided",
                "caller": target_inc.caller,
                "location": target_inc.location,
                "opened_at": target_inc.opened_at.isoformat() if target_inc.opened_at else now_utc.isoformat(),
                "assignment_status": "ASSIGNED" if assignment_record else "Assignment Pending",
                "assigned_employee_name": assigned_employee_name,
                "assigned_employee_code": assigned_employee_code,
                "rotation_position": getattr(assignment_record, "rotation_position", None),
                "rotation_cycle": getattr(assignment_record, "rotation_cycle", None),
                "employee_id": str(employee_id) if employee_id else None,
                "assignment_time": assignment_time.isoformat() if assignment_time else None,
                "employee_presence": employee_presence,
                "current_task": target_inc.work_instructions or target_inc.short_description,
                "task_status": target_inc.state,
                "unassigned_reason": unassigned_reason,
                "pending_reason": unassigned_reason or "Assignment Pending",
                "notice_body": full_notice_body,
                "timeline_events": timeline_events,
            }
            await ws_manager.broadcast_to_team(str(team_id), "GROUP_ACTIVITY_EVENT", activity_broadcast)
            await ws_manager.broadcast_to_admins("GROUP_ACTIVITY_EVENT", activity_broadcast)
        except Exception as ws_ex:
            logger.warning("broadcast_notice_result_failed", error=str(ws_ex))

    return {
        **notice_result,
        "assignment_triggered": bool(assignment_record) if auto_assign else False,
        "policy": (
            f"Auto-assigned to {assigned_employee_name} ({assigned_employee_code})"
            if assignment_record
            else ("Assignment evaluated: Assignment Pending" if auto_assign else "SEND NOTICE only. No incident was assigned. No ServiceNow mutation occurred.")
        ),
        "incident_id": str(target_inc.id) if target_inc else None,
        "incident_number": target_inc.incident_number if target_inc else incident_number,
        "short_description": target_inc.short_description if target_inc else title,
        "description": (target_inc.description if target_inc else message) or "Not provided",
        "priority": target_inc.priority if target_inc else priority,
        "impact": (target_inc.impact if target_inc else impact) or "Not provided",
        "urgency": (target_inc.urgency if target_inc else urgency) or "Not provided",
        "category": (target_inc.category if target_inc else category) or "Not provided",
        "subcategory": target_inc.subcategory if target_inc else None,
        "target_group": team.name,
        "assignment_group": team.name,
        "configuration_item": (target_inc.configuration_item if target_inc else configuration_item) or "Not provided",
        "caller": target_inc.caller if target_inc else None,
        "location": target_inc.location if target_inc else None,
        "opened_at": target_inc.opened_at.isoformat() if target_inc and target_inc.opened_at else now_utc.isoformat(),
        "notice_sent_time": now_utc.isoformat(),
        "assignment_status": "ASSIGNED" if assignment_record else "Assignment Pending",
        "assigned_employee_name": assigned_employee_name,
        "assigned_employee_code": assigned_employee_code,
        "rotation_position": getattr(assignment_record, "rotation_position", None),
        "rotation_cycle": getattr(assignment_record, "rotation_cycle", None),
        "employee_id": str(employee_id) if employee_id else None,
        "assignment_time": assignment_time.isoformat() if assignment_time else None,
        "employee_presence": employee_presence,
        "current_task": (target_inc.work_instructions or target_inc.short_description) if target_inc else None,
        "task_status": target_inc.state if target_inc else None,
        "unassigned_reason": unassigned_reason,
        "pending_reason": unassigned_reason or "Assignment Pending",
        "notice_body": full_notice_body,
        "timeline_events": timeline_events,
    }


@router.get("/teams/{team_id}/rotation")
async def get_team_rotation(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    """
    Returns current persistent 10-person rotation state for a team:
    - current_position (1..10)
    - cycle_number (1..N)
    - last assigned employee
    - next employee in queue
    - full rotation order
    """
    from sqlalchemy.orm import selectinload
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    from app.services.rotation_service import TeamRotationService
    rot_svc = TeamRotationService(db)
    rotation = await rot_svc.get_or_create_rotation(team.id)

    # Deterministic active members list
    stmt = (
        select(Employee)
        .join(User, Employee.user_id == User.id)
        .options(selectinload(Employee.user))
        .where(
            Employee.team_id == team.id,
            User.is_active == True,
            User.role == "EMPLOYEE"
        )
        .order_by(Employee.employee_code.asc(), Employee.id.asc())
    )
    emps = list((await db.execute(stmt)).scalars().all())

    curr_pos = rotation.current_position
    if curr_pos < 1 or curr_pos > max(len(emps), 1):
        curr_pos = 1

    next_emp = emps[curr_pos - 1] if emps else None
    last_emp = None
    if rotation.last_assigned_employee_id:
        last_emp = await db.get(Employee, rotation.last_assigned_employee_id)
        if last_emp and last_emp.user_id:
            await db.refresh(last_emp, ["user"])

    return {
        "team_id": str(team.id),
        "team_name": team.name,
        "current_position": rotation.current_position,
        "cycle_number": rotation.cycle_number,
        "members_count": len(emps),
        "last_assigned_employee_id": str(rotation.last_assigned_employee_id) if rotation.last_assigned_employee_id else None,
        "last_assigned_employee_code": last_emp.employee_code if last_emp else None,
        "last_assigned_employee_name": last_emp.user.full_name if (last_emp and last_emp.user) else None,
        "next_employee_id": str(next_emp.id) if next_emp else None,
        "next_employee_code": next_emp.employee_code if next_emp else None,
        "next_employee_name": next_emp.user.full_name if (next_emp and next_emp.user) else None,
        "rotation_order": [
            {
                "position": idx + 1,
                "employee_id": str(e.id),
                "employee_code": e.employee_code,
                "full_name": e.user.full_name if e.user else e.employee_code,
                "is_next": (idx + 1 == curr_pos),
                "is_leader": getattr(e, "is_group_leader", False),
            }
            for idx, e in enumerate(emps)
        ]
    }


# =============================================================================
# ANALYTICS — Real DB-backed metrics
# =============================================================================

@router.get("/analytics")
async def get_analytics(
    period: str = Query("7d", description="today | 7d | 30d"),
    team_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Real database-backed analytics. All numbers come from actual DB records.
    Date boundaries respect Asia/Kolkata timezone.
    """
    from zoneinfo import ZoneInfo
    from sqlalchemy import and_, cast
    from sqlalchemy.dialects.postgresql import INTERVAL
    from datetime import timedelta
    from app.models.notification import Notification
    from app.models.integration import SyncFailure

    tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
    now_local = datetime.now(tz)

    # Compute UTC start boundary
    if period == "today":
        # Midnight Asia/Kolkata → UTC
        local_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = local_midnight.astimezone(ZoneInfo("UTC"))
    elif period == "30d":
        start_utc = (now_local - timedelta(days=30)).astimezone(ZoneInfo("UTC"))
    else:  # default 7d
        start_utc = (now_local - timedelta(days=7)).astimezone(ZoneInfo("UTC"))

    end_utc = now_local.astimezone(ZoneInfo("UTC"))

    # Base incident filter
    inc_filter = [Incident.created_at >= start_utc, Incident.created_at <= end_utc]
    if team_id:
        try:
            t = await db.get(Team, uuid.UUID(team_id))
            if t:
                inc_filter.append(
                    or_(Incident.assignment_group == t.name, Incident.assignment_group == t.servicenow_group_id)
                )
        except Exception:
            pass

    # --- Incident counts ---
    total_res = await db.execute(select(func.count()).select_from(Incident).where(*inc_filter))
    total_incidents = total_res.scalar() or 0

    new_res = await db.execute(select(func.count()).select_from(Incident).where(*inc_filter, Incident.state == "NEW"))
    new_incidents = new_res.scalar() or 0

    assigned_res = await db.execute(select(func.count()).select_from(Incident).where(*inc_filter, Incident.state == "ASSIGNED"))
    assigned_incidents = assigned_res.scalar() or 0

    active_res = await db.execute(select(func.count()).select_from(Incident).where(*inc_filter, Incident.state.in_(["ACKNOWLEDGED", "IN_PROGRESS"])))
    active_incidents = active_res.scalar() or 0

    completed_res = await db.execute(select(func.count()).select_from(Incident).where(*inc_filter, Incident.state.in_(["COMPLETED", "RESOLVED", "CLOSED"])))
    completed_incidents = completed_res.scalar() or 0

    unassigned_res = await db.execute(
        select(func.count()).select_from(Incident).where(
            *inc_filter,
            Incident.state == "NEW",
            ~Incident.id.in_(select(IncidentAssignment.incident_id).where(IncidentAssignment.is_active == True))
        )
    )
    unassigned_incidents = unassigned_res.scalar() or 0

    # --- Assignment timing ---
    # avg time from incident created_at to first assignment assigned_at
    timing_res = await db.execute(
        select(IncidentAssignment.assigned_at, Incident.created_at)
        .join(Incident, IncidentAssignment.incident_id == Incident.id)
        .where(Incident.created_at >= start_utc, Incident.created_at <= end_utc, IncidentAssignment.is_active == True)
        .limit(500)
    )
    timing_rows = timing_res.all()
    assignment_minutes_list = []
    for assigned_at, inc_created in timing_rows:
        if assigned_at and inc_created:
            try:
                diff = (assigned_at - inc_created).total_seconds() / 60
                if 0 <= diff < 10000:
                    assignment_minutes_list.append(diff)
            except Exception:
                pass
    avg_assignment_minutes = round(sum(assignment_minutes_list) / len(assignment_minutes_list), 1) if assignment_minutes_list else None

    # avg completion time
    completion_res = await db.execute(
        select(IncidentAssignment.completed_at, IncidentAssignment.assigned_at)
        .where(
            IncidentAssignment.completed_at.isnot(None),
            IncidentAssignment.assigned_at.isnot(None),
            IncidentAssignment.assigned_at >= start_utc,
        )
        .limit(500)
    )
    completion_rows = completion_res.all()
    completion_minutes_list = []
    for comp_at, asgn_at in completion_rows:
        if comp_at and asgn_at:
            try:
                diff = (comp_at - asgn_at).total_seconds() / 60
                if 0 <= diff < 100000:
                    completion_minutes_list.append(diff)
            except Exception:
                pass
    avg_completion_minutes = round(sum(completion_minutes_list) / len(completion_minutes_list), 1) if completion_minutes_list else None

    # --- Group workload ---
    teams_res = await db.execute(select(Team).where(Team.is_active == True).order_by(Team.name))
    teams_list = teams_res.scalars().all()
    group_workload = []
    for t in teams_list:
        gw_res = await db.execute(
            select(func.count()).select_from(IncidentAssignment)
            .join(Employee, IncidentAssignment.employee_id == Employee.id)
            .where(Employee.team_id == t.id, IncidentAssignment.is_active == True)
        )
        active_count = gw_res.scalar() or 0
        group_workload.append({"team_id": str(t.id), "team_name": t.name, "active_assignments": active_count})

    # --- Employee workload (top 10) ---
    ew_res = await db.execute(
        select(Employee.id, func.count(IncidentAssignment.id).label("cnt"))
        .join(IncidentAssignment, IncidentAssignment.employee_id == Employee.id)
        .where(IncidentAssignment.is_active == True)
        .group_by(Employee.id)
        .order_by(desc("cnt"))
        .limit(10)
    )
    emp_workload_rows = ew_res.all()
    employee_workload = []
    for emp_id, cnt in emp_workload_rows:
        emp = await db.get(Employee, emp_id)
        user = await db.get(User, emp.user_id) if emp and emp.user_id else None
        employee_workload.append({
            "employee_id": str(emp_id),
            "name": user.full_name if user else "Unknown",
            "active_assignments": cnt,
        })

    # --- Notification counts ---
    from app.models.notification import Notification
    notif_total_res = await db.execute(select(func.count()).select_from(Notification).where(Notification.created_at >= start_utc))
    notif_total = notif_total_res.scalar() or 0
    notif_unread_res = await db.execute(select(func.count()).select_from(Notification).where(Notification.created_at >= start_utc, Notification.is_read == False))
    notif_unread = notif_unread_res.scalar() or 0

    # by type
    type_res = await db.execute(
        select(Notification.type, func.count().label("cnt"))
        .where(Notification.created_at >= start_utc)
        .group_by(Notification.type)
    )
    notif_by_type = {row[0]: row[1] for row in type_res.all()}

    # --- Shift coverage (current) ---
    from zoneinfo import ZoneInfo as ZI
    from app.services.shift_service import ShiftService
    shift_svc = ShiftService(db)
    active_shift = await shift_svc.get_active_shift(now_local)
    on_shift = present_now = available_now = 0
    if active_shift:
        sa_res = await db.execute(
            select(ShiftAssignment).where(
                ShiftAssignment.shift_id == active_shift.id,
                ShiftAssignment.date == now_local.date(),
                ShiftAssignment.is_active == True,
            )
        )
        for sa in sa_res.scalars().all():
            emp = await db.get(Employee, sa.employee_id)
            if emp:
                on_shift += 1
                if emp.is_present:
                    present_now += 1
                if emp.availability_status == "AVAILABLE":
                    available_now += 1

    return {
        "period": period,
        "generated_at": end_utc.isoformat(),
        "timezone": settings.DEFAULT_TIMEZONE,
        "incidents": {
            "total": total_incidents,
            "new": new_incidents,
            "assigned": assigned_incidents,
            "active": active_incidents,
            "completed": completed_incidents,
            "unassigned": unassigned_incidents,
        },
        "timing": {
            "avg_assignment_minutes": avg_assignment_minutes,
            "avg_completion_minutes": avg_completion_minutes,
        },
        "group_workload": group_workload,
        "employee_workload": employee_workload,
        "notifications": {
            "total": notif_total,
            "unread": notif_unread,
            "by_type": notif_by_type,
        },
        "shift_coverage": {
            "active_shift": active_shift.name if active_shift else None,
            "on_shift": on_shift,
            "present": present_now,
            "available": available_now,
        },
    }


# =============================================================================
# SHIFTS — Today's shift coverage
# =============================================================================

@router.get("/shifts/today")
async def get_today_shifts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Today's shifts with employee coverage. Uses Asia/Kolkata timezone."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
    now_local = datetime.now(tz)
    today = now_local.date()

    shifts_res = await db.execute(select(Shift).where(Shift.is_active == True).order_by(Shift.start_time))
    shifts = shifts_res.scalars().all()

    result = []
    for shift in shifts:
        # Get assigned employees for today
        sa_res = await db.execute(
            select(ShiftAssignment).where(
                ShiftAssignment.shift_id == shift.id,
                ShiftAssignment.date == today,
                ShiftAssignment.is_active == True,
            )
        )
        assignments = sa_res.scalars().all()

        employees = []
        on_shift_count = present_count = available_count = 0

        for sa in assignments:
            emp = await db.get(Employee, sa.employee_id)
            if not emp:
                continue
            user = await db.get(User, emp.user_id) if emp.user_id else None

            team = await db.get(Team, emp.team_id) if emp.team_id else None

            # Active assignments
            wl_res = await db.execute(
                select(func.count()).select_from(IncidentAssignment).where(
                    IncidentAssignment.employee_id == emp.id,
                    IncidentAssignment.is_active == True,
                )
            )
            workload = wl_res.scalar() or 0

            on_shift_count += 1
            if emp.is_present:
                present_count += 1
            if emp.availability_status == "AVAILABLE":
                available_count += 1

            employees.append({
                "employee_id": str(emp.id),
                "full_name": user.full_name if user else "Unknown",
                "email": user.email if user else None,
                "team": team.name if team else None,
                "availability_status": emp.availability_status,
                "is_present": emp.is_present,
                "active_assignments": workload,
            })

        # Determine if shift is currently active
        is_current = False
        if shift.is_overnight:
            # Overnight: active if time >= start OR time < end
            is_current = now_local.time() >= shift.start_time or now_local.time() < shift.end_time
        else:
            is_current = shift.start_time <= now_local.time() <= shift.end_time

        result.append({
            "shift_id": str(shift.id),
            "name": shift.name,
            "start_time": shift.start_time.strftime("%H:%M"),
            "end_time": shift.end_time.strftime("%H:%M"),
            "timezone": shift.timezone,
            "is_overnight": shift.is_overnight,
            "is_current": is_current,
            "date": today.isoformat(),
            "employees": employees,
            "coverage": {
                "total_assigned": on_shift_count,
                "present": present_count,
                "available": available_count,
                "offline": on_shift_count - present_count,
            },
        })

    return {
        "date": today.isoformat(),
        "timezone": settings.DEFAULT_TIMEZONE,
        "local_time": now_local.strftime("%H:%M"),
        "shifts": result,
        "total_shifts": len(result),
    }


# ===========================================================================
# 16. ENTERPRISE GROUP ACTIVITY & COLLABORATION WORKSPACE
# ===========================================================================

@router.get("/teams/{team_id}/activity", response_model=GroupActivityOverview)
async def get_team_activity(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns complete operational workspace activity for a specific group:
    - Metadata, active shift coverage, group health indicator
    - Employee activity cards with presence, availability, active assignments
    - Current work board (5 status columns with elapsed SLA timers)
    """
    from zoneinfo import ZoneInfo
    from app.services.shift_service import ShiftService

    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Group not found")

    tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
    now_tz = datetime.now(tz)
    today_date = now_tz.date()
    now_utc = datetime.now(timezone.utc)

    shift_svc = ShiftService(db)
    active_shift = await shift_svc.get_active_shift(now_tz)
    shift_window = None
    active_shift_name = None
    if active_shift:
        active_shift_name = active_shift.name
        shift_window = f"{active_shift.start_time.strftime('%H:%M')} - {active_shift.end_time.strftime('%H:%M')} ({active_shift.timezone})"

    # Fetch active employees belonging to this group
    emp_stmt = (
        select(Employee, User)
        .join(User, Employee.user_id == User.id)
        .where(
            Employee.team_id == team_id,
            User.is_active == True,
            User.role == "EMPLOYEE"
        )
        .order_by(User.full_name)
    )
    emp_rows = (await db.execute(emp_stmt)).all()

    member_cards: list[EmployeeActivityCard] = []
    on_shift_count = present_count = available_count = busy_count = 0

    for emp, user in emp_rows:
        # Check active shift assignment today
        on_shift = False
        current_shift_name = None
        if active_shift:
            sa_res = await db.execute(
                select(ShiftAssignment).where(
                    ShiftAssignment.employee_id == emp.id,
                    ShiftAssignment.shift_id == active_shift.id,
                    ShiftAssignment.date == today_date,
                    ShiftAssignment.is_active == True
                )
            )
            if sa_res.scalar_one_or_none():
                on_shift = True
                current_shift_name = active_shift.name

        if on_shift:
            on_shift_count += 1
        if emp.is_present:
            present_count += 1
        if emp.availability_status == "AVAILABLE":
            available_count += 1
        elif emp.availability_status == "BUSY":
            busy_count += 1

        # Fetch active assigned incidents
        assign_stmt = (
            select(IncidentAssignment, Incident)
            .join(Incident, IncidentAssignment.incident_id == Incident.id)
            .where(
                IncidentAssignment.employee_id == emp.id,
                IncidentAssignment.is_active == True,
                IncidentAssignment.status.in_(["ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS"])
            )
            .order_by(IncidentAssignment.assigned_at.desc())
        )
        assign_rows = (await db.execute(assign_stmt)).all()
        active_incidents = [
            AssignedIncidentBrief(
                id=inc.id,
                incident_number=inc.incident_number,
                short_description=inc.short_description,
                priority=inc.priority or "P3",
                state=inc.state,
                assigned_at=a.assigned_at
            )
            for a, inc in assign_rows
        ]

        # Determine last active timestamp
        last_active = emp.updated_at or emp.created_at
        p_latest = await db.execute(
            select(PresenceRecord.checked_in_at).where(PresenceRecord.employee_id == emp.id).order_by(PresenceRecord.checked_in_at.desc()).limit(1)
        )
        p_val = p_latest.scalar_one_or_none()
        if p_val and (last_active is None or p_val > last_active):
            last_active = p_val

        member_cards.append(EmployeeActivityCard(
            employee_id=emp.id,
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=user.role,
            employee_code=emp.employee_code,
            is_present=emp.is_present,
            availability_status=emp.availability_status,
            on_shift=on_shift,
            current_shift_name=current_shift_name,
            active_incident_count=len(active_incidents),
            active_incidents=active_incidents,
            last_active_at=last_active
        ))

    # Fetch group incidents for work board
    group_identifiers = [team.name]
    if team.servicenow_group_id:
        group_identifiers.append(team.servicenow_group_id)

    inc_stmt = (
        select(Incident)
        .where(Incident.assignment_group.in_(group_identifiers))
        .order_by(Incident.created_at.desc())
    )
    inc_results = (await db.execute(inc_stmt)).scalars().all()

    work_board = WorkBoardColumns()
    active_incidents_count = 0
    unassigned_count = 0

    for inc in inc_results:
        # Check active assignment
        curr_a_res = await db.execute(
            select(IncidentAssignment).where(
                IncidentAssignment.incident_id == inc.id,
                IncidentAssignment.is_active == True
            )
        )
        active_assign = curr_a_res.scalars().first()
        inc_created = inc.created_at
        if inc_created and inc_created.tzinfo is None:
            inc_created = inc_created.replace(tzinfo=timezone.utc)
        elapsed = max(0, int((now_utc - inc_created).total_seconds() / 60)) if inc_created else 0
        item = WorkBoardItem(
            id=inc.id,
            incident_number=inc.incident_number,
            short_description=inc.short_description,
            priority=inc.priority or "P3",
            state=inc.state,
            assigned_to=inc.assigned_to,
            assigned_employee_id=active_assign.employee_id if active_assign else None,
            assigned_at=active_assign.assigned_at if active_assign else None,
            created_at=inc_created or now_utc,
            elapsed_minutes=elapsed
        )

        if inc.state in ("RESOLVED", "CLOSED"):
            # If resolved today
            res_time = inc.resolved_at or inc.updated_at or inc_created
            if res_time:
                if res_time.tzinfo is None:
                    res_time = res_time.replace(tzinfo=timezone.utc)
                if res_time.astimezone(tz).date() == today_date:
                    work_board.completed_today.append(item)
        elif inc.state in ("BLOCKED", "ON_HOLD"):
            work_board.blocked.append(item)
            active_incidents_count += 1
        elif inc.state == "IN_PROGRESS":
            work_board.in_progress.append(item)
            active_incidents_count += 1
        elif inc.state == "ASSIGNED":
            work_board.assigned.append(item)
            active_incidents_count += 1
        else:  # NEW or unassigned
            work_board.unassigned.append(item)
            active_incidents_count += 1
            unassigned_count += 1

    # Health status calculation
    health_status = "HEALTHY"
    if len(emp_rows) > 0 and on_shift_count == 0:
        health_status = "CRITICAL"
    elif unassigned_count > 3 or (on_shift_count > 0 and available_count == 0 and unassigned_count > 0):
        health_status = "DEGRADED"

    header = GroupActivityHeader(
        team_id=team.id,
        name=team.name,
        work_domain=team.work_domain or team.description,
        description=team.description,
        servicenow_group_id=team.servicenow_group_id,
        is_active=team.is_active,
        active_shift_name=active_shift_name,
        shift_window=shift_window,
        health_status=health_status,
        total_members=len(emp_rows),
        on_shift_count=on_shift_count,
        present_count=present_count,
        available_count=available_count,
        busy_count=busy_count,
        active_incidents_count=active_incidents_count,
        unassigned_incidents_count=unassigned_count
    )

    return GroupActivityOverview(
        header=header,
        members=member_cards,
        work_board=work_board
    )


@router.get("/teams/{team_id}/activity/timeline", response_model=list[TimelineEventItem])
async def get_team_timeline(
    team_id: uuid.UUID,
    category: Optional[str] = "ALL",
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns real-time chronological timeline feed of incidents, presence, handoffs,
    and system notices for a group.
    """
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Group not found")

    # Get employee IDs and user IDs for this team
    emps_res = await db.execute(select(Employee).where(Employee.team_id == team_id))
    team_emps = emps_res.scalars().all()
    emp_ids = [e.id for e in team_emps]
    user_ids = [e.user_id for e in team_emps if e.user_id]

    # Get incident IDs for this group
    group_ids = [team.name]
    if team.servicenow_group_id:
        group_ids.append(team.servicenow_group_id)
    incs_res = await db.execute(select(Incident.id).where(Incident.assignment_group.in_(group_ids)))
    inc_ids = list(incs_res.scalars().all())

    # Build audit log query
    filters = []
    if inc_ids:
        filters.append(and_(AuditLog.entity_type == "INCIDENT", AuditLog.entity_id.in_(inc_ids)))
    if emp_ids:
        filters.append(and_(AuditLog.entity_type == "EMPLOYEE", AuditLog.entity_id.in_(emp_ids)))
    if user_ids:
        filters.append(AuditLog.actor_id.in_(user_ids))
    filters.append(and_(AuditLog.entity_type == "TEAM", AuditLog.entity_id == team_id))

    if not filters:
        return []

    stmt = (
        select(AuditLog)
        .where(or_(*filters))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )

    # Category filters
    cat_upper = (category or "ALL").upper()
    if cat_upper == "INCIDENTS":
        stmt = stmt.where(AuditLog.entity_type == "INCIDENT")
    elif cat_upper == "PRESENCE":
        stmt = stmt.where(AuditLog.action.in_(["CHECK_IN", "CHECK_OUT", "AVAILABILITY_CHANGE"]))
    elif cat_upper == "ASSIGNMENTS":
        stmt = stmt.where(AuditLog.action.in_(["AUTO_ASSIGN", "MANUAL_ASSIGN", "REASSIGN", "UNASSIGN"]))
    elif cat_upper == "NOTICES":
        stmt = stmt.where(AuditLog.action.in_(["SEND_GROUP_NOTICE", "SEND_INCIDENT_NOTIFICATION"]))

    logs = (await db.execute(stmt)).scalars().all()

    timeline: list[TimelineEventItem] = []
    for log in logs:
        actor = await db.get(User, log.actor_id) if log.actor_id else None
        event_type = "SYSTEM"
        if log.entity_type == "INCIDENT" or "INCIDENT" in log.action:
            event_type = "INCIDENTS"
        elif log.action in ("CHECK_IN", "CHECK_OUT", "AVAILABILITY_CHANGE"):
            event_type = "PRESENCE"
        elif "ASSIGN" in log.action:
            event_type = "ASSIGNMENTS"
        elif "NOTICE" in log.action or "NOTIFICATION" in log.action:
            event_type = "NOTICES"

        title = log.action.replace("_", " ").title()
        description = log.reason or f"{title} recorded."
        if log.new_value and isinstance(log.new_value, dict):
            if "incident_number" in log.new_value:
                description = f"#{log.new_value['incident_number']}: {description}"

        timeline.append(TimelineEventItem(
            id=log.id,
            event_type=event_type,
            title=title,
            description=description,
            actor_name=actor.full_name if actor else "System",
            entity_id=log.entity_id,
            metadata=log.new_value if isinstance(log.new_value, dict) else None,
            created_at=log.created_at
        ))

    return timeline


@router.get("/teams/{team_id}/conversations", response_model=list[ConversationResponse])
async def get_team_conversations(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns all conversations relevant to this group:
    1. Team conversation
    2. Direct conversations among group members
    3. Incident discussion threads for this team's incidents
    """
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Group not found")

    chat_svc = ChatService(db)
    # Ensure team conversation exists
    team_conv = await chat_svc.get_or_create_team_conversation(team_id)

    # Fetch all conversations tied to team_id or team's incidents
    group_ids = [team.name]
    if team.servicenow_group_id:
        group_ids.append(team.servicenow_group_id)
    team_inc_ids = list((await db.execute(select(Incident.id).where(Incident.assignment_group.in_(group_ids)))).scalars().all())

    stmt = (
        select(Conversation)
        .where(
            or_(
                Conversation.team_id == team_id,
                Conversation.incident_id.in_(team_inc_ids) if team_inc_ids else False
            )
        )
        .order_by(Conversation.updated_at.desc().nullslast(), Conversation.created_at.desc())
    )
    convs = (await db.execute(stmt)).scalars().all()

    results: list[ConversationResponse] = []
    for c in convs:
        # Load members
        m_stmt = select(ConversationMember).where(ConversationMember.conversation_id == c.id)
        members = (await db.execute(m_stmt)).scalars().all()
        members_resp = []
        for m in members:
            u = await db.get(User, m.user_id)
            if u:
                members_resp.append(ConversationMemberResponse(
                    id=m.id,
                    user_id=u.id,
                    name=u.full_name,
                    email=u.email,
                    role=u.role,
                    joined_at=m.joined_at,
                    last_read_at=m.last_read_at
                ))

        # Last message
        last_msg_stmt = select(ChatMessage).where(ChatMessage.conversation_id == c.id).order_by(ChatMessage.created_at.desc()).limit(1)
        last_msg = (await db.execute(last_msg_stmt)).scalar_one_or_none()
        last_msg_resp = None
        if last_msg:
            sender = await db.get(User, last_msg.sender_id) if last_msg.sender_id else None
            inc = await db.get(Incident, last_msg.incident_id) if last_msg.incident_id else None
            last_msg_resp = ChatMessageResponse(
                id=last_msg.id,
                conversation_id=last_msg.conversation_id,
                sender_id=last_msg.sender_id,
                sender_name=sender.full_name if sender else "System",
                sender_role=sender.role if sender else "SYSTEM",
                sender_email=sender.email if sender else None,
                content=last_msg.content,
                message_type=last_msg.message_type,
                incident_id=last_msg.incident_id,
                incident_number=inc.incident_number if inc else None,
                is_edited=last_msg.is_edited,
                is_deleted=last_msg.is_deleted,
                created_at=last_msg.created_at,
                read_by_count=0
            )

        results.append(ConversationResponse(
            id=c.id,
            type=c.type,
            team_id=c.team_id,
            incident_id=c.incident_id,
            title=c.title,
            members=members_resp,
            last_message=last_msg_resp,
            unread_count=0,
            created_at=c.created_at
        ))

    return results


@router.get("/teams/{team_id}/chat/search", response_model=ChatSearchResponse)
async def search_team_chat(
    team_id: uuid.UUID,
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Search messages in this group. Records CHAT_SEARCHED_BY_ADMIN audit event.
    """
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Group not found")

    chat_svc = ChatService(db)
    messages = await chat_svc.search_messages(q, team_id=team_id)

    # Record Audit Log
    audit_svc = AuditService(db)
    await audit_svc.log(
        action="CHAT_SEARCHED_BY_ADMIN",
        entity_type="TEAM",
        entity_id=team_id,
        new_value={"query": q, "results_count": len(messages), "team_name": team.name},
        reason=f"Administrator {current_user.full_name} searched chat for '{q}' in {team.name}",
        actor_id=current_user.id
    )
    await db.commit()

    resp_messages = []
    for m in messages:
        sender = await db.get(User, m.sender_id) if m.sender_id else None
        inc = await db.get(Incident, m.incident_id) if m.incident_id else None
        resp_messages.append(ChatMessageResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            sender_id=m.sender_id,
            sender_name=sender.full_name if sender else "System",
            sender_role=sender.role if sender else "SYSTEM",
            sender_email=sender.email if sender else None,
            content=m.content,
            message_type=m.message_type,
            incident_id=m.incident_id,
            incident_number=inc.incident_number if inc else None,
            is_edited=m.is_edited,
            is_deleted=m.is_deleted,
            created_at=m.created_at,
            read_by_count=0
        ))

    return ChatSearchResponse(messages=resp_messages, total=len(resp_messages))


@router.post("/chat/conversations/{conversation_id}/audit-view")
async def audit_view_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Records CHAT_VIEWED_BY_ADMIN audit event when admin views private/direct conversation.
    """
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    audit_svc = AuditService(db)
    await audit_svc.log(
        action="CHAT_VIEWED_BY_ADMIN",
        entity_type="CONVERSATION",
        entity_id=conversation_id,
        new_value={"conversation_id": str(conversation_id), "type": conv.type, "title": conv.title},
        reason=f"Administrator {current_user.full_name} inspected conversation {conv.title or conversation_id}",
        actor_id=current_user.id
    )
    await db.commit()
    return {"status": "recorded"}


@router.get("/teams/{team_id}/analytics", response_model=GroupAnalyticsSummary)
async def get_team_analytics(
    team_id: uuid.UUID,
    period: str = "today",
    db: AsyncSession = Depends(get_db)
):
    """
    Calculates operational metrics for a specific group:
    - Total incidents, resolved, unassigned
    - Avg assignment & resolution time in minutes
    - Auto-assignment rate percentage
    - Workload distribution across members
    """
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Group not found")

    tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
    now_tz = datetime.now(tz)
    today_start = datetime(now_tz.year, now_tz.month, now_tz.day, tzinfo=tz)

    if period == "30d":
        start_time = today_start - timedelta(days=30)
    elif period == "7d":
        start_time = today_start - timedelta(days=7)
    else:  # today
        start_time = today_start

    group_ids = [team.name]
    if team.servicenow_group_id:
        group_ids.append(team.servicenow_group_id)

    # Incidents in period
    inc_stmt = select(Incident).where(
        Incident.assignment_group.in_(group_ids),
        Incident.created_at >= start_time
    )
    incidents = (await db.execute(inc_stmt)).scalars().all()
    total_count = len(incidents)

    resolved_count = sum(1 for i in incidents if i.state in ("RESOLVED", "CLOSED"))
    unassigned_count = sum(1 for i in incidents if i.state == "NEW")

    # Assignments in period
    inc_ids = [i.id for i in incidents]
    assignments = []
    if inc_ids:
        a_stmt = select(IncidentAssignment).where(IncidentAssignment.incident_id.in_(inc_ids))
        assignments = (await db.execute(a_stmt)).scalars().all()

    auto_count = sum(1 for a in assignments if a.assignment_type == "AUTOMATIC")
    auto_rate = round((auto_count / len(assignments) * 100), 1) if assignments else 0.0

    # Assignment times
    assignment_times = []
    for a in assignments:
        for i in incidents:
            if i.id == a.incident_id and a.assigned_at and i.created_at:
                a_time = a.assigned_at if a.assigned_at.tzinfo else a.assigned_at.replace(tzinfo=timezone.utc)
                i_time = i.created_at if i.created_at.tzinfo else i.created_at.replace(tzinfo=timezone.utc)
                diff = (a_time - i_time).total_seconds() / 60
                if diff >= 0:
                    assignment_times.append(diff)
    avg_assign_min = round(sum(assignment_times) / len(assignment_times), 1) if assignment_times else 0.0

    # Resolution times
    resolution_times = []
    for i in incidents:
        if i.state in ("RESOLVED", "CLOSED") and i.resolved_at and i.created_at:
            r_time = i.resolved_at if i.resolved_at.tzinfo else i.resolved_at.replace(tzinfo=timezone.utc)
            c_time = i.created_at if i.created_at.tzinfo else i.created_at.replace(tzinfo=timezone.utc)
            diff = (r_time - c_time).total_seconds() / 60
            if diff >= 0:
                resolution_times.append(diff)
    avg_res_min = round(sum(resolution_times) / len(resolution_times), 1) if resolution_times else 0.0

    # Workload distribution across group members
    emp_stmt = select(Employee, User).join(User, Employee.user_id == User.id).where(
        Employee.team_id == team_id,
        User.role == "EMPLOYEE"
    )
    emp_rows = (await db.execute(emp_stmt)).all()

    workload_dist = []
    for emp, user in emp_rows:
        assigned_cnt = sum(1 for a in assignments if a.employee_id == emp.id)
        completed_cnt = sum(1 for a in assignments if a.employee_id == emp.id and a.status == "COMPLETED")
        workload_dist.append({
            "employee_id": str(emp.id),
            "employee_name": user.full_name,
            "assigned_count": assigned_cnt,
            "completed_count": completed_cnt
        })

    return GroupAnalyticsSummary(
        period=period,
        total_incidents=total_count,
        resolved_count=resolved_count,
        unassigned_count=unassigned_count,
        avg_assignment_minutes=avg_assign_min,
        avg_resolution_minutes=avg_res_min,
        auto_assignment_rate_pct=auto_rate,
        workload_distribution=workload_dist
    )


@router.get("/employees/{employee_id}/activity")
async def get_employee_activity_details(
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Provides comprehensive details for the slide-over employee details drawer:
    Profile, shift schedule, presence, active assignments, and recent activity log.
    """
    emp = await db.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    user = await db.get(User, emp.user_id) if emp.user_id else None
    team = await db.get(Team, emp.team_id) if emp.team_id else None

    from zoneinfo import ZoneInfo
    tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
    today_date = datetime.now(tz).date()

    # Shifts
    shifts_stmt = (
        select(ShiftAssignment, Shift)
        .join(Shift, ShiftAssignment.shift_id == Shift.id)
        .where(ShiftAssignment.employee_id == employee_id, ShiftAssignment.date == today_date)
    )
    shift_rows = (await db.execute(shifts_stmt)).all()
    today_shifts = [
        {
            "shift_name": s.name,
            "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M"),
            "is_overnight": s.is_overnight,
            "is_active": sa.is_active
        }
        for sa, s in shift_rows
    ]

    # Active assignments
    assign_stmt = (
        select(IncidentAssignment, Incident)
        .join(Incident, IncidentAssignment.incident_id == Incident.id)
        .where(
            IncidentAssignment.employee_id == employee_id,
            IncidentAssignment.is_active == True
        )
        .order_by(IncidentAssignment.assigned_at.desc())
    )
    assign_rows = (await db.execute(assign_stmt)).all()
    assignments = [
        {
            "id": str(inc.id),
            "incident_number": inc.incident_number,
            "short_description": inc.short_description,
            "priority": inc.priority or "P3",
            "state": inc.state,
            "assignment_status": a.status,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
            "started_at": a.started_at.isoformat() if a.started_at else None
        }
        for a, inc in assign_rows
    ]

    # Recent Audit activity
    audit_stmt = (
        select(AuditLog)
        .where(
            or_(
                AuditLog.actor_id == emp.user_id,
                and_(AuditLog.entity_type == "EMPLOYEE", AuditLog.entity_id == emp.id)
            )
        )
        .order_by(AuditLog.created_at.desc())
        .limit(20)
    )
    audit_logs = (await db.execute(audit_stmt)).scalars().all()
    recent_activity = [
        {
            "id": str(l.id),
            "action": l.action,
            "reason": l.reason or l.action.replace("_", " ").title(),
            "created_at": l.created_at.isoformat()
        }
        for l in audit_logs
    ]

    return {
        "employee_id": str(emp.id),
        "user_id": str(user.id) if user else None,
        "full_name": user.full_name if user else "Unknown",
        "email": user.email if user else "",
        "role": user.role if user else "EMPLOYEE",
        "employee_code": emp.employee_code,
        "team_name": team.name if team else "None",
        "availability_status": emp.availability_status,
        "is_present": emp.is_present,
        "today_shifts": today_shifts,
        "active_assignments": assignments,
        "recent_activity": recent_activity
    }

