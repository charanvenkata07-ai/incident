from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import Optional, List, Any
from app.core.datetime_utils import UTCDateTime


class AuditLogResponse(BaseModel):
    id: UUID
    actor_name: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[UUID] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    reason: Optional[str] = None
    created_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    logs: List[AuditLogResponse]
    total: int
    page: int
    per_page: int
