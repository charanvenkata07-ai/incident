from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import time, date
from typing import Optional, List

class ShiftBase(BaseModel):
    name: str
    start_time: time
    end_time: time
    timezone: str = "Asia/Kolkata"
    is_overnight: bool = False

class ShiftCreate(ShiftBase):
    pass

class ShiftUpdate(BaseModel):
    name: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    timezone: Optional[str] = None
    is_overnight: Optional[bool] = None
    is_active: Optional[bool] = None

class ShiftResponse(ShiftBase):
    id: UUID
    is_active: bool
    employees: List[dict] = []
    
    model_config = ConfigDict(from_attributes=True)

class ShiftAssignmentCreate(BaseModel):
    shift_id: UUID
    employee_id: UUID
    date: date

class ShiftAssignmentResponse(BaseModel):
    id: UUID
    shift: ShiftResponse
    employee: dict
    date: date
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)
