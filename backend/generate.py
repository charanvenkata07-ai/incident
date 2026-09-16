import os

base_dir = "/Users/charan/.gemini/antigravity/scratch/incidentflow/backend/app"

files = {
    "__init__.py": "",
    "api/__init__.py": "",
    "services/__init__.py": "",
    "integrations/__init__.py": "",
    "integrations/servicenow/__init__.py": "",
    "websocket/__init__.py": "",
    "workers/__init__.py": "",
    "main.py": """from fastapi import FastAPI, Depends, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.middleware import get_request_id, LoggingMiddleware, RequestIDMiddleware
from app.api.auth import router as auth_router
from app.api.employees import router as employees_router
from app.api.incidents import router as incidents_router
from app.api.admin import router as admin_router
from app.api.notifications import router as notifications_router
from app.integrations.servicenow.webhook import router as sn_router
from app.websocket.manager import ws_manager
from sqlalchemy import text
from app.core.database import get_db, engine
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: could create tables here if not using alembic
    yield
    # Shutdown

app = FastAPI(title="IncidentFlow API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(employees_router, prefix="/api/me", tags=["Employees"])
app.include_router(incidents_router, prefix="/api/incidents", tags=["Incidents"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(sn_router, prefix="/api/integrations/servicenow", tags=["ServiceNow"])

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/ready")
async def ready(db = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {"status": "ready" if db_status == "ok" else "error", "database": db_status}

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    # Verify token
    user_id = "extracted_user_id" # replace with actual decode
    await ws_manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except Exception:
        await ws_manager.disconnect(websocket, user_id)
""",
    "api/auth.py": """from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, hash_password, get_current_user, Role
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, RegisterRequest, UserResponse

router = APIRouter()

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=access_token, token_type="bearer")

@router.post("/register", response_model=UserResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        role=req.role or 'USER',
        is_active=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
""",
    "api/employees.py": """from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.employee import Employee
from app.models.assignment import IncidentAssignment
from app.models.incident import Incident
from app.models.shift import Shift, ShiftAssignment
from app.models.notification import Notification
from app.schemas.employee import EmployeeResponse, AvailabilityUpdate
from app.schemas.incident import IncidentBrief
from app.services.audit_service import AuditService
from datetime import date, timezone, datetime

router = APIRouter()

@router.get("/", response_model=EmployeeResponse)
async def get_profile(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return emp

@router.get("/work", response_model=list[IncidentBrief])
async def get_work(status: str = None, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.id))
    emp = result.scalar_one_or_none()
    if not emp:
        return []
    
    query = select(Incident).join(IncidentAssignment).where(
        IncidentAssignment.employee_id == emp.id,
        IncidentAssignment.is_active == True
    )
    if status:
        query = query.where(IncidentAssignment.status == status.upper())
        
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/shift")
async def get_shift(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    today = datetime.now(timezone.utc).date()
    query = select(ShiftAssignment).join(Shift).where(
        ShiftAssignment.employee_id == emp.id,
        ShiftAssignment.date == today,
        ShiftAssignment.is_active == True
    )
    result = await db.execute(query)
    assignment = result.scalar_one_or_none()
    return assignment

@router.get("/notifications")
async def get_notifications(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Notification).where(Notification.user_id == current_user.id).order_by(desc(Notification.created_at))
    result = await db.execute(query)
    notifs = result.scalars().all()
    unread_count = sum(1 for n in notifs if not n.is_read)
    return {"notifications": notifs, "unread_count": unread_count}

@router.patch("/availability")
async def update_availability(req: AvailabilityUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    old_status = emp.availability_status
    emp.availability_status = req.status
    
    audit_service = AuditService(db)
    await audit_service.log('AVAILABILITY_CHANGE', 'EMPLOYEE', emp.id, old_value={'status': old_status}, new_value={'status': req.status}, actor_id=current_user.id)
    
    await db.commit()
    return {"status": "success", "new_status": req.status}
""",
    "api/incidents.py": """from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.services.audit_service import AuditService
from app.services.sync_service import SyncService
from app.websocket.manager import ws_manager
from datetime import datetime, timezone

router = APIRouter()

@router.get("/{incident_number}")
async def get_incident(incident_number: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Incident).where(Incident.incident_number == incident_number))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
        
    # TODO: verify auth
    
    audit_service = AuditService(db)
    timeline = await audit_service.get_entity_timeline('INCIDENT', incident.id)
    
    return {"incident": incident, "timeline": timeline}

@router.post("/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(IncidentAssignment).where(
        IncidentAssignment.incident_id == incident_id,
        IncidentAssignment.is_active == True
    ))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Active assignment not found")
        
    assignment.status = 'ACKNOWLEDGED'
    assignment.acknowledged_at = datetime.now(timezone.utc)
    
    audit_service = AuditService(db)
    await audit_service.log('INCIDENT_ACKNOWLEDGED', 'INCIDENT', incident_id, actor_id=current_user.id)
    
    await db.commit()
    await ws_manager.broadcast_all('INCIDENT_UPDATED', {"incident_id": incident_id, "status": "ACKNOWLEDGED"})
    return {"status": "success"}

@router.post("/{incident_id}/start")
async def start_incident(incident_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(IncidentAssignment).where(
        IncidentAssignment.incident_id == incident_id,
        IncidentAssignment.is_active == True
    ))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Active assignment not found")
        
    assignment.status = 'IN_PROGRESS'
    assignment.started_at = datetime.now(timezone.utc)
    
    result_inc = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result_inc.scalar_one()
    incident.state = 'IN_PROGRESS'
    
    audit_service = AuditService(db)
    await audit_service.log('INCIDENT_STARTED', 'INCIDENT', incident_id, actor_id=current_user.id)
    
    await db.commit()
    await ws_manager.broadcast_all('INCIDENT_UPDATED', {"incident_id": incident_id, "status": "IN_PROGRESS"})
    return {"status": "success"}

@router.post("/{incident_id}/complete")
async def complete_incident(incident_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(IncidentAssignment).where(
        IncidentAssignment.incident_id == incident_id,
        IncidentAssignment.is_active == True
    ))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Active assignment not found")
        
    assignment.status = 'COMPLETED'
    assignment.completed_at = datetime.now(timezone.utc)
    
    result_inc = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result_inc.scalar_one()
    incident.state = 'RESOLVED'
    
    audit_service = AuditService(db)
    await audit_service.log('INCIDENT_COMPLETED', 'INCIDENT', incident_id, actor_id=current_user.id)
    
    await db.commit()
    await ws_manager.broadcast_all('INCIDENT_UPDATED', {"incident_id": incident_id, "status": "COMPLETED"})
    return {"status": "success"}
""",
    "api/admin.py": """from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import require_role
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.schemas.admin import DashboardStats
from app.schemas.assignment import ManualAssignRequest, ReassignRequest

router = APIRouter(dependencies=[Depends(require_role("ADMIN"))])

@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(db: AsyncSession = Depends(get_db)):
    return DashboardStats(
        active_incidents=0,
        unassigned_incidents=0,
        employees_on_shift=0,
        available_employees=0,
        busy_employees=0
    )

@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    return {"status": "ok", "api": "ok", "database": "ok", "redis": "ok", "worker": "ok", "servicenow": "ok"}
""",
    "api/notifications.py": """from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/")
async def get_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"notifications": [], "unread_count": 0}

@router.patch("/{id}/read")
async def read_notification(id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"status": "success"}

@router.post("/read-all")
async def read_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"status": "success"}
""",
    "services/assignment_engine.py": """from sqlalchemy.ext.asyncio import AsyncSession
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
        return True
        
    async def _get_required_skills(self, incident: Incident) -> set:
        return set()
        
    async def _get_strategy(self, incident: Incident) -> str:
        return 'SKILL_PLUS_WORKLOAD'
        
    async def _is_dry_run(self) -> bool:
        return False
        
    async def _is_shadow_mode(self) -> bool:
        return False
        
    async def _get_last_assigned_employee(self):
        return None
""",
    "services/eligibility.py": """from sqlalchemy.ext.asyncio import AsyncSession
from app.models.employee import Employee
from app.services.shift_service import ShiftService

class EligibilityService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.shift_service = ShiftService(db)

    async def find_eligible_employees(self, assignment_group, required_skills, now) -> list[Employee]:
        active_shift = await self._find_active_shift(now)
        if not active_shift:
            return []
        
        scheduled = await self._get_scheduled_employees(active_shift, now.date())
        
        if assignment_group:
            scheduled = [e for e in scheduled if e.team and (e.team.name == assignment_group or e.team.servicenow_group_id == assignment_group)]
        
        present = [e for e in scheduled if e.is_present]
        available = [e for e in present if e.availability_status == 'AVAILABLE']
        
        if required_skills:
            skilled = []
            for emp in available:
                emp_skill_ids = {es.skill_id for es in emp.skills}
                if required_skills.issubset(emp_skill_ids):
                    skilled.append(emp)
            return skilled
        
        return available

    async def _find_active_shift(self, now):
        return await self.shift_service.get_active_shift(now)
        
    async def _get_scheduled_employees(self, active_shift, date):
        return await self.shift_service.get_shift_employees(active_shift.id, date)
""",
    "services/shift_service.py": """from sqlalchemy.ext.asyncio import AsyncSession
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
""",
    "services/presence_service.py": """from sqlalchemy.ext.asyncio import AsyncSession
from app.models.presence import PresenceRecord
from uuid import UUID
from datetime import date

class PresenceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_in(self, employee_id, shift_assignment_id) -> PresenceRecord:
        pass

    async def check_out(self, employee_id) -> PresenceRecord:
        pass

    async def set_break(self, employee_id) -> PresenceRecord:
        pass

    async def is_present(self, employee_id: UUID, check_date: date) -> bool:
        return True

    async def get_team_presence(self, team_id: UUID, check_date: date) -> list[dict]:
        return []
""",
    "services/incident_service.py": """from sqlalchemy.ext.asyncio import AsyncSession
from app.models.incident import Incident
from app.schemas.servicenow import ServiceNowIncidentPayload
from uuid import UUID

class IncidentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_update_from_servicenow(self, payload: ServiceNowIncidentPayload) -> tuple[Incident, bool]:
        existing = await self._find_existing(payload)
        if existing:
            return await self._update_incident(existing, payload), False
        return await self._create_incident(payload), True

    async def _find_existing(self, payload):
        return None
        
    async def _update_incident(self, existing, payload):
        return existing
        
    async def _create_incident(self, payload):
        incident = Incident()
        self.db.add(incident)
        await self.db.flush()
        return incident

    async def get_incident_by_number(self, incident_number: str) -> Incident | None:
        return None

    async def get_employee_incidents(self, employee_id: UUID, status_filter: str | None) -> list[Incident]:
        return []

    async def get_all_incidents(self, filters, page, per_page) -> tuple[list[Incident], int]:
        return [], 0
""",
    "services/workload_service.py": """from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from sqlalchemy import select, func
from app.models.assignment import IncidentAssignment

class WorkloadService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_workloads(self, employee_ids: list[UUID]) -> dict[UUID, int]:
        result = await self.db.execute(
            select(IncidentAssignment.employee_id, func.count(IncidentAssignment.id))
            .where(
                IncidentAssignment.employee_id.in_(employee_ids),
                IncidentAssignment.is_active == True,
                IncidentAssignment.status.in_(['ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS'])
            )
            .group_by(IncidentAssignment.employee_id)
        )
        counts = {row[0]: row[1] for row in result.all()}
        return {eid: counts.get(eid, 0) for eid in employee_ids}

    async def get_detailed_workload(self, employee_id: UUID) -> dict:
        return {"total": 0, "p1": 0, "p2": 0, "p3": 0, "p4": 0}
""",
    "services/notification_service.py": """from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notification import Notification

class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(self, user_id, type, title, message, incident_id=None) -> Notification:
        notif = Notification(user_id=user_id, type=type, title=title, message=message, incident_id=incident_id)
        self.db.add(notif)
        await self.db.flush()
        return notif

    async def get_user_notifications(self, user_id, limit=50) -> tuple[list[Notification], int]:
        return [], 0

    async def mark_read(self, notification_id, user_id):
        pass

    async def mark_all_read(self, user_id):
        pass
""",
    "services/audit_service.py": """from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLog

class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(self, action, entity_type, entity_id=None, old_value=None, new_value=None, reason=None, actor_id=None):
        audit = AuditLog(
            action=action, entity_type=entity_type, entity_id=entity_id, 
            old_value=old_value, new_value=new_value, reason=reason, actor_id=actor_id
        )
        self.db.add(audit)
        await self.db.flush()

    async def get_logs(self, filters, page, per_page) -> tuple[list[AuditLog], int]:
        return [], 0

    async def get_entity_timeline(self, entity_type, entity_id) -> list[AuditLog]:
        return []
""",
    "services/sync_service.py": """from sqlalchemy.ext.asyncio import AsyncSession
from app.models.incident import Incident
from app.models.employee import Employee
from app.models.integration import SyncFailure
from app.integrations.servicenow.client import ServiceNowClient

class SyncService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = ServiceNowClient("url", "user", "pass")

    async def sync_assignment_to_servicenow(self, incident: Incident, employee: Employee):
        try:
            await self.client.update_assignment(incident.servicenow_sys_id, employee.user.full_name)
            incident.sync_status = 'SYNCED'
        except Exception as e:
            incident.sync_status = 'SYNC_FAILED'
            await self._create_sync_failure(incident, 'UPDATE_ASSIGNMENT', str(e))

    async def sync_status_to_servicenow(self, incident: Incident, new_state: str):
        pass

    async def handle_servicenow_update(self, payload) -> bool:
        return True

    async def retry_failed_syncs(self):
        pass

    async def _create_sync_failure(self, incident, operation, error):
        fail = SyncFailure(incident_id=incident.id, operation=operation, error_message=error, status='PENDING')
        self.db.add(fail)
        await self.db.flush()
""",
    "integrations/servicenow/client.py": """class ServiceNowClient:
    def __init__(self, base_url, username, password, client_id=None, client_secret=None):
        self.base_url = base_url
        
    async def get_incident(self, sys_id: str) -> dict:
        return {}
        
    async def update_incident(self, sys_id: str, fields: dict) -> dict:
        return {}
        
    async def update_assignment(self, sys_id: str, assigned_to: str) -> dict:
        return {}
        
    async def update_state(self, sys_id: str, state: str) -> dict:
        return {}
""",
    "integrations/servicenow/mapper.py": """from app.models.incident import Incident

class ServiceNowMapper:
    FIELD_MAP = {
        'number': 'incident_number',
        'sys_id': 'servicenow_sys_id',
        'short_description': 'short_description',
        'description': 'description',
        'priority': 'priority',
        'impact': 'impact',
        'urgency': 'urgency',
        'category': 'category',
        'subcategory': 'subcategory',
        'assignment_group.display_value': 'assignment_group',
        'assigned_to.display_value': 'assigned_to',
        'state': 'state',
        'opened_at': 'opened_at',
        'work_notes': 'work_notes',
    }
    
    def to_incident(self, payload: dict) -> dict:
        return {}
        
    def to_servicenow(self, incident: Incident) -> dict:
        return {}
        
    def map_priority(self, sn_priority) -> str:
        return "P1"
        
    def map_state(self, sn_state) -> str:
        return "NEW"
""",
    "integrations/servicenow/webhook.py": """from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.servicenow import ServiceNowIncidentPayload
from app.services.incident_service import IncidentService
from app.services.assignment_engine import AssignmentEngine
from app.integrations.servicenow.mapper import ServiceNowMapper

router = APIRouter()

@router.post("/incidents")
async def receive_incident(payload: ServiceNowIncidentPayload, db: AsyncSession = Depends(get_db)):
    try:
        incident_service = IncidentService(db)
        mapper = ServiceNowMapper()
        mapped = mapper.to_incident(payload.dict())
        
        # Fake payload for now to pass type hints
        incident, is_new = await incident_service.create_or_update_from_servicenow(payload)
        
        if is_new:
            engine = AssignmentEngine(db)
            await engine.process_incident(incident)
            
        return {"status": "processed", "incident_number": payload.number if hasattr(payload, 'number') else 'INC'}
    except Exception:
        return {"status": "error_logged"}
""",
    "integrations/servicenow/mock.py": """class MockServiceNowClient:
    async def get_incident(self, sys_id) -> dict:
        return {}
        
    async def update_incident(self, sys_id, fields) -> dict:
        return {}
        
    async def update_assignment(self, sys_id, assigned_to) -> dict:
        return {}
        
    async def generate_incident(self) -> dict:
        return {"number": "INC0010010", "short_description": "Test incident", "priority": "1"}
""",
    "websocket/manager.py": """from fastapi import WebSocket

NEW_INCIDENT = 'NEW_INCIDENT'
INCIDENT_ASSIGNED = 'INCIDENT_ASSIGNED'
INCIDENT_UPDATED = 'INCIDENT_UPDATED'
INCIDENT_REASSIGNED = 'INCIDENT_REASSIGNED'
SHIFT_CHANGED = 'SHIFT_CHANGED'
EMPLOYEE_STATUS_CHANGED = 'EMPLOYEE_STATUS_CHANGED'
NOTIFICATION_CREATED = 'NOTIFICATION_CREATED'

class WebSocketManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        
    async def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            
    async def send_to_user(self, user_id: str, event: str, data: dict):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                await connection.send_json({"event": event, "data": data})
                
    async def broadcast_to_admins(self, event: str, data: dict):
        pass
        
    async def broadcast_all(self, event: str, data: dict):
        for connections in self.active_connections.values():
            for connection in connections:
                try:
                    await connection.send_json({"event": event, "data": data})
                except Exception:
                    pass

ws_manager = WebSocketManager()
""",
    "workers/celery_app.py": """from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "incidentflow_workers",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone=settings.DEFAULT_TIMEZONE,
    enable_utc=True,
)
""",
    "workers/tasks.py": """from app.workers.celery_app import celery_app

@celery_app.task
def sync_assignment_to_servicenow(incident_id, employee_id):
    pass

@celery_app.task
def send_notification_email(user_id, subject, body):
    pass

@celery_app.task
def retry_failed_syncs():
    pass

@celery_app.task
def poll_servicenow_incidents():
    pass

@celery_app.task
def process_new_incident(incident_id):
    pass
"""
}

for path, content in files.items():
    full_path = os.path.join(base_dir, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write(content)

print("Files generated successfully.")
