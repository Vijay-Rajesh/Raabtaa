import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.safe_arrival_agent import run_safe_arrival_agent
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.logging import get_logger
from app.database.session import get_db
from app.models.location_event import LocationEvent
from app.models.safe_place import SafePlace
from app.models.user import User
from app.schemas.location import GeofenceEventRead
from app.services import arrival_service, geofence_service
from app.utils.time import utcnow

router = APIRouter(prefix="/api/v1/test", tags=["Testing (dev only)"])
logger = get_logger(__name__)


class SimulateArrivalRequest(BaseModel):
    safe_place_id: uuid.UUID
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


def _ensure_dev_environment() -> None:
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is disabled in production.",
        )


@router.post("/simulate-arrival", response_model=list[GeofenceEventRead])
async def simulate_arrival(
    payload: SimulateArrivalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GeofenceEventRead]:
    """
    Simulate a real mobile location event so the full arrival workflow can be
    tested end-to-end without a mobile app. Disabled when ENVIRONMENT=production.
    """
    _ensure_dev_environment()

    result = await db.execute(
        select(SafePlace).where(
            SafePlace.id == payload.safe_place_id, SafePlace.user_id == current_user.id
        )
    )
    safe_place = result.scalar_one_or_none()
    if safe_place is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Safe place not found")

    location = LocationEvent(
        user_id=current_user.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=10,
        speed=0,
        recorded_at=utcnow(),
    )
    db.add(location)
    await db.flush()

    transitions = await geofence_service.evaluate_location_against_places(
        db, current_user.id, payload.latitude, payload.longitude, [safe_place]
    )
    geofence_events = await geofence_service.persist_transitions(
        db, current_user.id, transitions, payload.latitude, payload.longitude
    )
    await db.commit()
    for e in geofence_events:
        await db.refresh(e)

    for event in geofence_events:
        should_invoke_agent = await arrival_service.process_geofence_event(
            db, current_user.id, event, safe_place
        )
        if should_invoke_agent:
            await run_safe_arrival_agent(
                db=db,
                user_id=current_user.id,
                geofence_event_id=event.id,
                safe_place_id=safe_place.id,
            )

    return [GeofenceEventRead.model_validate(e) for e in geofence_events]
