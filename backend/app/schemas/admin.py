from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class DashboardStats(BaseModel):
    active_incidents: int
    unassigned_incidents: int
    employees_on_shift: int
    available_employees: int
    busy_employees: int

class LiveAssignment(BaseModel):
    incident_number: str
    short_description: str
    employee_name: str
    assignment_type: str
    assigned_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class SystemHealthResponse(BaseModel):
    api: str
    database: str
    redis: str
    worker: str
    servicenow: str
    servicenow_last_sync: Optional[datetime] = None

class SettingsResponse(BaseModel):
    auto_assignment_enabled: bool
    assignment_strategy: str
    dry_run_mode: bool
    shadow_mode: bool
    servicenow_connected: bool

class SettingsUpdate(BaseModel):
    auto_assignment_enabled: Optional[bool] = None
    assignment_strategy: Optional[str] = None
    dry_run_mode: Optional[bool] = None
    shadow_mode: Optional[bool] = None
