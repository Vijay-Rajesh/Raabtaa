import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class JourneyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    family_member_id: Optional[uuid.UUID]
    schedule_id: Optional[uuid.UUID]
    origin_place_id: Optional[uuid.UUID]
    destination_place_id: uuid.UUID
    started_at: datetime
    expected_arrival_at: Optional[datetime]
    actual_arrival_at: Optional[datetime]
    status: str
