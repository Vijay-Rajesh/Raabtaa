import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    family_member_id: Optional[uuid.UUID] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy_meters: Optional[float] = Field(None, ge=0)
    speed: Optional[float] = Field(None, ge=0)
    recorded_at: datetime


class LocationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    family_member_id: Optional[uuid.UUID]
    latitude: float
    longitude: float
    accuracy_meters: Optional[float]
    speed: Optional[float]
    recorded_at: datetime
    received_at: datetime


class GeofenceEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    safe_place_id: uuid.UUID
    family_member_id: Optional[uuid.UUID]
    event_type: str
    distance_meters: float
    occurred_at: datetime
    processed: bool


class LocationIngestResponse(BaseModel):
    location: LocationEventRead
    geofence_events: list[GeofenceEventRead]
    arrival_triggered: bool
