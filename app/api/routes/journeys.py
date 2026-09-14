import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.journey import Journey
from app.models.location_event import LocationEvent
from app.models.user import User
from app.schemas.journey import JourneyRead
from app.schemas.location import LocationEventRead
from app.schemas.safety import SmartStatusRead
from app.services.smart_status_service import evaluate_journey_status

router = APIRouter(prefix="/api/v1/journeys", tags=["Journeys"])


@router.get("", response_model=list[JourneyRead])
async def list_journeys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Journey]:
    result = await db.execute(
        select(Journey).where(Journey.user_id == current_user.id).order_by(Journey.started_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{journey_id}/replay", response_model=list[LocationEventRead])
async def replay_journey(
    journey_id: uuid.UUID,
    max_points: int = Query(500, ge=10, le=2000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LocationEvent]:
    journey_result = await db.execute(
        select(Journey).where(Journey.id == journey_id, Journey.user_id == current_user.id)
    )
    journey = journey_result.scalar_one_or_none()
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")

    location_query = select(LocationEvent).where(
        LocationEvent.user_id == current_user.id,
        LocationEvent.recorded_at >= journey.started_at,
    )
    if journey.family_member_id is None:
        location_query = location_query.where(LocationEvent.family_member_id.is_(None))
    else:
        location_query = location_query.where(LocationEvent.family_member_id == journey.family_member_id)
    if journey.actual_arrival_at is not None:
        location_query = location_query.where(LocationEvent.recorded_at <= journey.actual_arrival_at)

    result = await db.execute(
        location_query.order_by(LocationEvent.recorded_at.asc()).limit(max_points)
    )
    return list(result.scalars().all())


@router.get("/{journey_id}/status", response_model=SmartStatusRead)
async def journey_status(
    journey_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SmartStatusRead:
    journey = await db.scalar(select(Journey).where(Journey.id == journey_id, Journey.user_id == current_user.id))
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    return SmartStatusRead.model_validate(await evaluate_journey_status(db, journey))
