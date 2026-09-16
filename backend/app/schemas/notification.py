from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List

class NotificationResponse(BaseModel):
    id: UUID
    type: str
    title: str
    message: str
    incident_id: Optional[UUID] = None
    incident_number: Optional[str] = None
    is_read: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    unread_count: int
