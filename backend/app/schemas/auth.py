from pydantic import BaseModel, EmailStr, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List


class LoginRequest(BaseModel):
    email: Optional[EmailStr] = None
    employee_id: Optional[UUID] = None
    password: str
    team_id: Optional[UUID] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Optional[str] = None
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "EMPLOYEE"


class LoginGroupResponse(BaseModel):
    id: UUID
    name: str
    work_domain: Optional[str] = None
    description: Optional[str] = None
    member_count: int = 0


class LoginEmployeeResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    email: str
    employee_code: Optional[str] = None
