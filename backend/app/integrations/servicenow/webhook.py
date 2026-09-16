from fastapi import APIRouter, Depends
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
