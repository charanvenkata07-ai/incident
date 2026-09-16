from pydantic import BaseModel, EmailStr, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

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
