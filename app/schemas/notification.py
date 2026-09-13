import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    family_member_id: uuid.UUID
    journey_id: Optional[uuid.UUID]
    notification_type: str
    channel: str
    message: str
    status: str
    sent_at: Optional[datetime]
    created_at: datetime


class WhatsAppMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notification_id: uuid.UUID
    recipient_phone: str
    template_name: Optional[str]
    whatsapp_message_id: Optional[str]
    status: str
    error_message: Optional[str]
    sent_at: Optional[datetime]
    delivered_at: Optional[datetime]
    read_at: Optional[datetime]
