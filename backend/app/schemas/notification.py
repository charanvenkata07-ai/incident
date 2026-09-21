from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import Optional, List
from app.core.datetime_utils import UTCDateTime


class NotificationAction(BaseModel):
    label: str
    action: str  # REPLY, VIEW, OPEN_INCIDENT, VIEW_WORK, etc.
    url: str
    variant: Optional[str] = "default"  # default, outline, secondary


class NotificationResponse(BaseModel):
    id: UUID
    type: str
    title: str
    message: str
    incident_id: Optional[UUID] = None
    incident_number: Optional[str] = None
    conversation_id: Optional[UUID] = None
    message_id: Optional[UUID] = None
    assignment_id: Optional[UUID] = None
    team_id: Optional[UUID] = None
    sender_id: Optional[UUID] = None
    sender_name: Optional[str] = None
    action_url: Optional[str] = None
    action_type: Optional[str] = None
    actions: List[NotificationAction] = []
    extra_data: Optional[dict] = None
    is_read: bool
    read_at: Optional[UTCDateTime] = None
    created_at: UTCDateTime  # Always serializes with timezone offset (+00:00)
    priority: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    unread_count: int

