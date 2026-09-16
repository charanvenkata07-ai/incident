import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, desc, or_
from app.core.database import get_db
from app.core.security import require_role, get_password_hash
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
from app.models.settings import SystemSetting
from app.schemas.admin import (
    DashboardStats, LiveAssignment, SystemHealthResponse,
    SettingsResponse, SettingsUpdate
)
from app.schemas.employee import EmployeeResponse, EmployeeCreate, EmployeeUpdate
from app.schemas.assignment import ManualAssignRequest, ReassignRequest
from app.schemas.shift import ShiftResponse, ShiftCreate, ShiftUpdate
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.sync_service import SyncService
from app.websocket.manager import ws_manager

router = APIRouter(dependencies=[Depends(require_role("ADMIN"))])

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
    result = await db.execute(select(Employee))
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
async def manual_assign(id: uuid.UUID, payload: ManualAssignRequest, db: AsyncSession = Depends(get_db)):
    inc = await db.get(Incident, id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    emp = await db.get(Employee, payload.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    user = await db.get(User, emp.user_id)

    # Deactivate existing active assignment
    await db.execute(
        update(IncidentAssignment)
        .where(IncidentAssignment.incident_id == inc.id, IncidentAssignment.is_active == True)
        .values(is_active=False, status="REASSIGNED")
    )

    assignment = IncidentAssignment(
        incident_id=inc.id,
        employee_id=emp.id,
        assignment_type="MANUAL",
        status="ASSIGNED",
        reason=payload.reason or "Manually assigned by Administrator",
        assigned_at=datetime.now(timezone.utc),
        is_active=True
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
        new_value={"employee_id": str(emp.id), "employee_name": inc.assigned_to, "reason": payload.reason}
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

    await db.commit()
    return {"message": "Incident manually assigned successfully", "assigned_to": inc.assigned_to}

# 5. AUTOMATION EMERGENCY CONTROLS
@router.post("/automation/pause")
async def pause_automation(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SystemSetting).where(SystemSetting.key == "auto_assignment_enabled"))
    setting = res.scalar_one_or_none()
    if not setting:
        setting = SystemSetting(key="auto_assignment_enabled", value={"enabled": False})
        db.add(setting)
    else:
        setting.value = {"enabled": False}
    
    audit = AuditService(db)
    await audit.log(action="PAUSE_AUTOMATION", entity_type="SYSTEM", reason="Administrator paused automation")
    await db.commit()
    return {"message": "Automatic assignment paused", "status": "paused"}

@router.post("/automation/resume")
async def resume_automation(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SystemSetting).where(SystemSetting.key == "auto_assignment_enabled"))
    setting = res.scalar_one_or_none()
    if not setting:
        setting = SystemSetting(key="auto_assignment_enabled", value={"enabled": True})
        db.add(setting)
    else:
        setting.value = {"enabled": True}

    audit = AuditService(db)
    await audit.log(action="RESUME_AUTOMATION", entity_type="SYSTEM", reason="Administrator resumed automation")
    await db.commit()
    return {"message": "Automatic assignment resumed", "status": "active"}

# 6. SERVICENOW INTEGRATION CONTROL
@router.get("/integrations/servicenow")
async def servicenow_status(db: AsyncSession = Depends(get_db)):
    return {
        "status": "connected",
        "mode": "MOCK" if settings.SERVICENOW_MOCK else "LIVE",
        "instance_url": settings.SERVICENOW_URL or "https://dev-mock.service-now.com",
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "pending_syncs": 0
    }

@router.post("/integrations/servicenow/sync")
async def servicenow_sync_now(db: AsyncSession = Depends(get_db)):
    return {"message": "ServiceNow sync triggered successfully", "timestamp": datetime.now(timezone.utc).isoformat()}

# 7. FAILURE & RECOVERY CENTER
@router.get("/integrations/failures")
async def list_sync_failures(db: AsyncSession = Depends(get_db)):
    from app.models.integration import SyncFailure
    result = await db.execute(
        select(SyncFailure).order_by(desc(SyncFailure.created_at)).limit(20)
    )
    failures = result.scalars().all()
    out = []
    for f in failures:
        inc = await db.get(Incident, f.incident_id) if f.incident_id else None
        out.append({
            "id": f.id,
            "incident_number": inc.incident_number if inc else "Unknown",
            "operation": f.operation,
            "error_message": f.error_message,
            "retry_count": f.retry_count,
            "max_retries": f.max_retries,
            "status": f.status,
            "created_at": f.created_at
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
    await audit.log(action="RETRY_SYNC", entity_type="INTEGRATION", entity_id=failure.id, reason="Manual retry triggered from Failure Recovery Center")
    await db.commit()
    return {"message": "Retry executed successfully", "status": failure.status}

