import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.core.datetime_utils import UTCDateTime, OptionalUTCDateTime

class AttachmentResponse(BaseModel):
    id: uuid.UUID
    message_id: Optional[uuid.UUID] = None
    file_name: str
    mime_type: str
    file_size: int
    storage_key: str
    url: str
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[int] = None
    status: str = "READY"
    created_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True)

class ReactionCount(BaseModel):
    emoji: str
    count: int
    users: list[str] = []

class ReplyToPreview(BaseModel):
    id: uuid.UUID
    sender_name: str
    sender_id: Optional[uuid.UUID] = None
    content: str
    message_type: str
    is_deleted: bool = False

class ChatMessageCreate(BaseModel):
    content: str
    incident_id: Optional[uuid.UUID] = None
    message_type: Optional[str] = "TEXT"  # TEXT, IMAGE, AUDIO, USER, SYSTEM
    reply_to_message_id: Optional[uuid.UUID] = None
    attachment_id: Optional[uuid.UUID] = None
    client_message_id: Optional[str] = None
    metadata_json: Optional[str] = None

class ChatMessageUpdate(BaseModel):
    content: str

class ReactionRequest(BaseModel):
    emoji: str

class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: Optional[uuid.UUID] = None
    sender_name: str
    sender_role: str
    sender_email: Optional[str] = None
    sender_avatar_url: Optional[str] = None
    content: str
    message_type: str
    incident_id: Optional[uuid.UUID] = None
    incident_number: Optional[str] = None
    reply_to_message_id: Optional[uuid.UUID] = None
    reply_to: Optional[ReplyToPreview] = None
    attachment_id: Optional[uuid.UUID] = None
    attachment: Optional[AttachmentResponse] = None
    reactions: list[ReactionCount] = []
    user_reactions: list[str] = []
    client_message_id: Optional[str] = None
    is_edited: bool = False
    is_deleted: bool = False
    edited_at: OptionalUTCDateTime = None
    deleted_at: OptionalUTCDateTime = None
    deleted_by: Optional[uuid.UUID] = None
    delete_reason: Optional[str] = None
    created_at: UTCDateTime
    read_by_count: int = 0

    model_config = ConfigDict(from_attributes=True)

class ConversationMemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: str
    role: str
    avatar_url: Optional[str] = None
    joined_at: UTCDateTime
    last_read_at: OptionalUTCDateTime = None

    model_config = ConfigDict(from_attributes=True)

class ConversationResponse(BaseModel):
    id: uuid.UUID
    type: str  # TEAM, GROUP, DIRECT, INCIDENT
    team_id: Optional[uuid.UUID] = None
    team_name: Optional[str] = None
    incident_id: Optional[uuid.UUID] = None
    incident_number: Optional[str] = None
    title: Optional[str] = None
    members: list[ConversationMemberResponse] = []
    last_message: Optional[ChatMessageResponse] = None
    unread_count: int = 0
    created_at: UTCDateTime
    updated_at: OptionalUTCDateTime = None

    model_config = ConfigDict(from_attributes=True)

class TeamMemberChatBrief(BaseModel):
    user_id: uuid.UUID
    employee_id: uuid.UUID
    full_name: str
    email: str
    employee_code: Optional[str] = None
    role: str = "EMPLOYEE"
    is_group_leader: bool = False
    avatar_url: Optional[str] = None
    is_present: bool = False
    availability_status: str = "OFFLINE"
    on_shift: bool = False
    current_shift_name: Optional[str] = None

class ChatSearchResponse(BaseModel):
    messages: list[ChatMessageResponse]
    total: int

class TeamChatGroupBrief(BaseModel):
    id: uuid.UUID
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    conversation_id: uuid.UUID
    member_count: int = 0

    model_config = ConfigDict(from_attributes=True)

class ChatTypingRequest(BaseModel):
    is_typing: bool = True

class DirectChatRequest(BaseModel):
    other_user_id: uuid.UUID

class GroupChatRequest(BaseModel):
    title: str
    member_user_ids: list[uuid.UUID]

class MyTeamChatResponse(BaseModel):
    team_id: uuid.UUID
    team_name: str
    team_description: Optional[str] = None
    conversation_id: uuid.UUID
    member_count: int
    present_count: int
    active_shift_name: Optional[str] = None
    members: list[TeamMemberChatBrief] = []
    conversation: ConversationResponse
