from fastapi import APIRouter, Depends, HTTPException
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
