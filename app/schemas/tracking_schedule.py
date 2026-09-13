import uuid
from datetime import time

from pydantic import BaseModel, ConfigDict, Field


class TrackingScheduleCreate(BaseModel):
    family_member_id: uuid.UUID
    origin_place_id: uuid.UUID
    destination_place_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    days_of_week: str = Field("0,1,2,3,4", pattern=r"^[0-6](,[0-6])*$")
    departure_time: time
    expected_duration_minutes: int = Field(45, ge=1, le=1440)
    is_active: bool = True


class TrackingScheduleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    days_of_week: str | None = Field(None, pattern=r"^[0-6](,[0-6])*$")
    departure_time: time | None = None
    expected_duration_minutes: int | None = Field(None, ge=1, le=1440)
    is_active: bool | None = None


class TrackingScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    family_member_id: uuid.UUID
    origin_place_id: uuid.UUID
    destination_place_id: uuid.UUID
    name: str
    days_of_week: str
    departure_time: time
    expected_duration_minutes: int
    is_active: bool