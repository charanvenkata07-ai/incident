from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import List, Optional
from .skill import SkillResponse

class EmployeeResponse(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: str
    avatar_url: Optional[str] = None
    role: Optional[str] = "EMPLOYEE"
    team_id: Optional[UUID] = None
    team_name: Optional[str] = None
    employee_code: Optional[str] = None
    availability_status: str
    is_present: bool
    is_group_leader: bool = False
    phone: Optional[str] = None
    bio: Optional[str] = None
    timezone: Optional[str] = "Asia/Kolkata"
    skills: List[SkillResponse] = []
    active_incident_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)

class EmployeeListResponse(BaseModel):
    employees: List[EmployeeResponse]
    total_count: int

class AvailabilityUpdate(BaseModel):
    availability_status: Optional[str] = None
    status: Optional[str] = None
    is_present: Optional[bool] = None

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

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    timezone: Optional[str] = None
    notification_preferences: Optional[str] = None
    chat_preferences: Optional[str] = None
    availability_status: Optional[str] = None

class UserProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: str
    role: str
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    timezone: Optional[str] = "Asia/Kolkata"
    notification_preferences: Optional[str] = None
    chat_preferences: Optional[str] = None
    team_id: Optional[UUID] = None
    team_name: Optional[str] = None
    employee_code: Optional[str] = None
    is_group_leader: bool = False
    availability_status: str = "OFFLINE"
    is_present: bool = False
    skills: List[SkillResponse] = []
    active_incident_count: int = 0
    shift: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class TeamMemberDetail(BaseModel):
    id: UUID
    employee_id: Optional[UUID] = None
    user_id: UUID
    full_name: str
    email: str
    avatar_url: Optional[str] = None
    role: str = "EMPLOYEE"
    is_group_leader: bool = False
    employee_code: Optional[str] = None
    is_present: bool = False
    availability_status: str = "OFFLINE"
    current_shift_name: Optional[str] = None
    current_shift_hours: Optional[str] = None
    active_assignments: int = 0
    skills: List[str] = []

    model_config = ConfigDict(from_attributes=True)


class MyTeamDetailResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    work_domain: Optional[str] = None
    servicenow_group_id: Optional[str] = None
    group_leader: Optional[TeamMemberDetail] = None
    members: List[TeamMemberDetail]
    member_count: int
    online_count: int
    available_count: int

    model_config = ConfigDict(from_attributes=True)


