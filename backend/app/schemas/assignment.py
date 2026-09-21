from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import Optional, List
from app.core.datetime_utils import UTCDateTime, OptionalUTCDateTime


class AssignmentBrief(BaseModel):
    id: UUID
    employee_name: str
    assignment_type: str
    status: str
    assigned_at: UTCDateTime

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
    assigned_at: UTCDateTime
    acknowledged_at: OptionalUTCDateTime = None
    started_at: OptionalUTCDateTime = None
    completed_at: OptionalUTCDateTime = None

    model_config = ConfigDict(from_attributes=True)


class AssignmentListResponse(BaseModel):
    assignments: List[AssignmentResponse]
    total: int


class ManualAssignRequest(BaseModel):
    employee_id: UUID
    reason: Optional[str] = None


class ReassignRequest(BaseModel):
    new_employee_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    reason: Optional[str] = None

