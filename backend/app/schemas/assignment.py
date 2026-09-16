from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List

class AssignmentBrief(BaseModel):
    id: UUID
    employee_name: str
    assignment_type: str
    status: str
    assigned_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class AssignmentResponse(BaseModel):
    id: UUID
    incident_id: UUID
    incident_number: str
    short_description: str
    employee_id: UUID
    employee_name: str
    assignment_type: str
    status: str
    reason: Optional[str] = None
    assigned_at: datetime
    acknowledged_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class AssignmentListResponse(BaseModel):
    assignments: List[AssignmentResponse]
    total: int

class ManualAssignRequest(BaseModel):
    employee_id: UUID
    reason: Optional[str] = None

class ReassignRequest(BaseModel):
    new_employee_id: UUID
    reason: Optional[str] = None
