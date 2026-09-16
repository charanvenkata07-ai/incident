from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import List, Optional
from .skill import SkillResponse

class EmployeeResponse(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: str
    team_id: Optional[UUID] = None
    team_name: Optional[str] = None
    employee_code: Optional[str] = None
    availability_status: str
    is_present: bool
    skills: List[SkillResponse] = []
    active_incident_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)

class EmployeeListResponse(BaseModel):
    employees: List[EmployeeResponse]
    total_count: int

class AvailabilityUpdate(BaseModel):
    availability_status: str
