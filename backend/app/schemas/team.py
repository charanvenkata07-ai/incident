from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import Optional

class TeamBase(BaseModel):
    name: str
    description: Optional[str] = None
    servicenow_group_id: Optional[str] = None

class TeamCreate(TeamBase):
    pass

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    servicenow_group_id: Optional[str] = None
    is_active: Optional[bool] = None

class TeamResponse(TeamBase):
    id: UUID
    is_active: bool
    employee_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)
