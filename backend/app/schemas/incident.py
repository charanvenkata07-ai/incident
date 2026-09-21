from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import Optional, List
from .assignment import AssignmentBrief
from app.core.datetime_utils import UTCDateTime, OptionalUTCDateTime


class IncidentBase(BaseModel):
    incident_number: str
    short_description: str
    priority: str = "P4"
    state: str = "NEW"


class IncidentBrief(IncidentBase):
    id: UUID
    assignment_group: Optional[str] = None
    work_instructions: Optional[str] = None
    assigned_employee_name: Optional[str] = None
    assignment_status: Optional[str] = None
    assigned_at: OptionalUTCDateTime = None

    model_config = ConfigDict(from_attributes=True)


class IncidentCreate(BaseModel):
    incident_number: Optional[str] = None
    servicenow_sys_id: Optional[str] = None
    short_description: str
    description: Optional[str] = None
    priority: str = "P4"
    impact: Optional[str] = None
    urgency: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    assignment_group: Optional[str] = None
    state: str = "NEW"
    opened_at: OptionalUTCDateTime = None
    work_notes: Optional[str] = None
    work_instructions: Optional[str] = None


class IncidentResponse(IncidentBase):
    id: UUID
    servicenow_sys_id: Optional[str] = None
    description: Optional[str] = None
    impact: Optional[str] = None
    urgency: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    assignment_group: Optional[str] = None
    assigned_to: Optional[str] = None
    caller: Optional[str] = None
    location: Optional[str] = None
    configuration_item: Optional[str] = None
    work_notes: Optional[str] = None
    additional_comments: Optional[str] = None
    work_instructions: Optional[str] = None
    opened_at: OptionalUTCDateTime = None
    resolved_at: OptionalUTCDateTime = None
    closed_at: OptionalUTCDateTime = None
    servicenow_updated_at: OptionalUTCDateTime = None
    sync_status: str
    created_at: UTCDateTime
    updated_at: OptionalUTCDateTime = None

    current_assignment: Optional[AssignmentBrief] = None
    activity_timeline: List[dict] = []

    model_config = ConfigDict(from_attributes=True)


class IncidentListResponse(BaseModel):
    incidents: List[IncidentResponse]
    total: int
    page: int
    per_page: int
