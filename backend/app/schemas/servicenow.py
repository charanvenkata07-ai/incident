from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from datetime import datetime

class ServiceNowIncidentPayload(BaseModel):
    sys_id: str
    number: str
    short_description: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    impact: Optional[str] = None
    urgency: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    assignment_group: Optional[Any] = None
    assigned_to: Optional[Any] = None
    caller_id: Optional[Any] = None
    location: Optional[Any] = None
    cmdb_ci: Optional[Any] = None
    state: Optional[str] = None
    opened_at: Optional[datetime] = None
    u_work_notes: Optional[str] = None
    work_notes: Optional[str] = None
    comments: Optional[str] = None
    u_work_instructions: Optional[str] = None
    
    model_config = ConfigDict(extra='ignore')

class ServiceNowSyncPayload(BaseModel):
    incident_number: str
    assigned_to: Optional[str] = None
    state: Optional[str] = None
