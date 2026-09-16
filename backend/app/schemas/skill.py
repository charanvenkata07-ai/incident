from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import Optional

class SkillBase(BaseModel):
    name: str
    description: Optional[str] = None

class SkillCreate(SkillBase):
    pass

class SkillResponse(SkillBase):
    id: UUID
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)
