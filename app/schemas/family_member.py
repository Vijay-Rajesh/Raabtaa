import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RelationshipLiteral = Literal["parent", "guardian", "brother", "sister", "spouse", "other"]


class FamilyMemberCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    phone_number: str = Field(..., min_length=6, max_length=32)
    telegram_chat_id: Optional[str] = Field(None, max_length=255)
    relationship_type: RelationshipLiteral
    whatsapp_enabled: bool = True
    telegram_enabled: bool = True


class FamilyMemberUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone_number: Optional[str] = Field(None, min_length=6, max_length=32)
    telegram_chat_id: Optional[str] = Field(None, max_length=255)
    relationship_type: Optional[RelationshipLiteral] = None
    whatsapp_enabled: Optional[bool] = None
    telegram_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class FamilyMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    phone_number: str
    telegram_chat_id: Optional[str]
    relationship_type: str
    whatsapp_enabled: bool
    telegram_enabled: bool
    tracking_token: Optional[str] = None
    is_active: bool
    created_at: datetime
