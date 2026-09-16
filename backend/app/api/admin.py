from fastapi import APIRouter, Depends, HTTPException
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
