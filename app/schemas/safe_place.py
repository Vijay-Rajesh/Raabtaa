import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PlaceTypeLiteral = Literal["home", "school", "college", "office", "university", "custom"]


class SafePlaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    place_type: PlaceTypeLiteral
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_meters: int = Field(200, ge=50, le=1000)


class SafePlaceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    place_type: Optional[PlaceTypeLiteral] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius_meters: Optional[int] = Field(None, ge=50, le=1000)
    is_active: Optional[bool] = None


class SafePlaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    place_type: str
    latitude: float
    longitude: float
    radius_meters: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
