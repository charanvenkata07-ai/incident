import uuid
from typing import Optional, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.core.datetime_utils import UTCDateTime, OptionalUTCDateTime

class GroupActivityHeader(BaseModel):
    team_id: uuid.UUID
    name: str
    work_domain: Optional[str] = None
    description: Optional[str] = None
    servicenow_group_id: Optional[str] = None
    is_active: bool = True
    active_shift_name: Optional[str] = None
    shift_window: Optional[str] = None
    health_status: str = "HEALTHY"  # HEALTHY, DEGRADED, ATTENTION
    total_members: int = 0
    on_shift_count: int = 0
    present_count: int = 0
    available_count: int = 0
    busy_count: int = 0
    active_incidents_count: int = 0
    unassigned_incidents_count: int = 0

class AssignedIncidentBrief(BaseModel):
    id: uuid.UUID
    incident_number: str
    short_description: str
    priority: str
    state: str
    assigned_at: OptionalUTCDateTime = None

    model_config = ConfigDict(from_attributes=True, json_encoders={datetime: lambda v: v.isoformat()})

class EmployeeActivityCard(BaseModel):
    employee_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    role: str
    employee_code: Optional[str] = None
    is_present: bool = False
    availability_status: str = "OFFLINE"
    on_shift: bool = False
    current_shift_name: Optional[str] = None
    active_incident_count: int = 0
    active_incidents: list[AssignedIncidentBrief] = []
    last_active_at: OptionalUTCDateTime = None

    model_config = ConfigDict(from_attributes=True, json_encoders={datetime: lambda v: v.isoformat()})

class WorkBoardItem(BaseModel):
    id: uuid.UUID
    incident_number: str
    short_description: str
    priority: str
    state: str
    assigned_to: Optional[str] = None
    assigned_employee_id: Optional[uuid.UUID] = None
    assigned_at: OptionalUTCDateTime = None
    created_at: UTCDateTime
    elapsed_minutes: int = 0

    model_config = ConfigDict(from_attributes=True, json_encoders={datetime: lambda v: v.isoformat()})

class WorkBoardColumns(BaseModel):
    unassigned: list[WorkBoardItem] = []
    assigned: list[WorkBoardItem] = []
    in_progress: list[WorkBoardItem] = []
    blocked: list[WorkBoardItem] = []
    completed_today: list[WorkBoardItem] = []

class TimelineEventItem(BaseModel):
    id: uuid.UUID
    event_type: str  # INCIDENTS, PRESENCE, ASSIGNMENTS, NOTICES, SYSTEM
    title: str
    description: str
    actor_name: Optional[str] = None
    entity_id: Optional[uuid.UUID] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True, json_encoders={datetime: lambda v: v.isoformat()})

class GroupAnalyticsSummary(BaseModel):
    period: str
    total_incidents: int = 0
    resolved_count: int = 0
    unassigned_count: int = 0
    avg_assignment_minutes: float = 0.0
    avg_resolution_minutes: float = 0.0
    auto_assignment_rate_pct: float = 0.0
    workload_distribution: list[dict[str, Any]] = []

class GroupActivityOverview(BaseModel):
    header: GroupActivityHeader
    members: list[EmployeeActivityCard]
    work_board: WorkBoardColumns

class NoticeAssignmentResult(BaseModel):
    incident_id: Optional[uuid.UUID] = None
    incident_number: Optional[str] = None
    short_description: Optional[str] = None
    target_group: Optional[str] = None
    notice_sent_time: str
    assignment_status: str  # ASSIGNED | UNASSIGNED
    assigned_employee_name: Optional[str] = None
    employee_id: Optional[uuid.UUID] = None
    assignment_time: Optional[str] = None
    employee_presence: Optional[str] = None
    current_task: Optional[str] = None
    task_status: Optional[str] = None
    unassigned_reason: Optional[str] = None
    notice_success_count: int = 0
    notice_failed_count: int = 0

