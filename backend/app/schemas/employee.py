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

class EmployeeCreate(BaseModel):
    email: str
    full_name: str
    password: Optional[str] = "password123"
    team_name: Optional[str] = None
    employee_code: Optional[str] = None
    role: Optional[str] = "EMPLOYEE"
    skills: List[str] = []

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    team_name: Optional[str] = None
    availability_status: Optional[str] = None
    is_present: Optional[bool] = None
    role: Optional[str] = None
    skills: Optional[List[str]] = None

