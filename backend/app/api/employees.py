from fastapi import APIRouter, Depends, HTTPException
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
