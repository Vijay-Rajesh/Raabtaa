import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str | None
    full_name: str
    email: str
    phone_number: str
    is_active: bool
    is_admin: bool
    created_at: datetime


class AdminStats(BaseModel):
    users: int
    active_users: int
    journeys: int
    notifications: int
    sent_notifications: int
    failed_notifications: int


class AdminStatus(BaseModel):
    whatsapp: str
    telegram: str
    environment: str
    mock_mode: bool


class AdminUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = None
    username: str | None = Field(default=None, min_length=3, max_length=64)
    phone_number: str | None = Field(default=None, min_length=6, max_length=32)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class AdminUserCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: str
    username: str = Field(..., min_length=3, max_length=64)
    phone_number: str = Field(..., min_length=6, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
