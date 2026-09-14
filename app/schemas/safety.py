import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SmartStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    reason: str
    last_updated: datetime | None
    deviation_meters: float | None
    eta: datetime | None


class SosCreate(BaseModel):
    journey_id: uuid.UUID | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    message: str = Field("SOS: I need help. Please check my live location.", max_length=500)


class SosLocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    latitude: float
    longitude: float
    recorded_at: datetime


class SosRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    journey_id: uuid.UUID | None
    status: str
    notified_members: int
    locations: list[SosLocationRead]
    live_location: SosLocationRead | None
