import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.family_member import FamilyMember
from app.models.journey import Journey, JourneyStatus
from app.models.location_event import LocationEvent
from app.models.notification import Notification
from app.models.user import User
from app.schemas.safety import SmartStatusRead, SosCreate, SosLocationRead, SosRead
from app.services import notification_service
from app.services.smart_status_service import SmartStatus, evaluate_journey_status, get_active_journey_status
from app.utils.time import utcnow

router = APIRouter(prefix="/api/v1", tags=["Safety"])


def _location(point: LocationEvent | None) -> SosLocationRead | None:
    return SosLocationRead(latitude=point.latitude, longitude=point.longitude, recorded_at=point.recorded_at) if point else None


@router.get("/safety/status", response_model=SmartStatusRead)
async def current_status(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> SmartStatusRead:
    active = await get_active_journey_status(db, current_user.id)
    if active is None:
        emergency = await db.scalar(
            select(Notification).where(
                Notification.user_id == current_user.id,
                Notification.notification_type == "emergency",
            ).order_by(Notification.created_at.desc()).limit(1)
        )
        if emergency is not None:
            return SmartStatusRead(
                status=SmartStatus.EMERGENCY,
                reason="SOS was sent to active family members",
                last_updated=emergency.created_at,
                deviation_meters=None,
                eta=None,
            )
        return SmartStatusRead(status=SmartStatus.ON_TRACK, reason="No active journey", last_updated=None, deviation_meters=None, eta=None)
    _, result = active
    return SmartStatusRead.model_validate(result, from_attributes=True)


@router.post("/sos", response_model=SosRead, status_code=status.HTTP_201_CREATED)
async def trigger_sos(
    payload: SosCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SosRead:
    journey = None
    if payload.journey_id:
        journey = await db.scalar(select(Journey).where(Journey.id == payload.journey_id, Journey.user_id == current_user.id))
        if journey is None:
            raise HTTPException(status_code=404, detail="Journey not found")
    if journey is None:
        journey_result = await db.execute(select(Journey).where(Journey.user_id == current_user.id, Journey.status == JourneyStatus.active.value).order_by(Journey.started_at.desc()).limit(1))
        journey = journey_result.scalar_one_or_none()

    location_query = select(LocationEvent).where(LocationEvent.user_id == current_user.id)
    if journey:
        location_query = location_query.where(LocationEvent.recorded_at >= journey.started_at)
    location_result = await db.execute(location_query.order_by(LocationEvent.recorded_at.desc()).limit(5))
    locations = list(location_result.scalars().all())
    live = SosLocationRead(latitude=payload.latitude, longitude=payload.longitude, recorded_at=utcnow()) if payload.latitude is not None and payload.longitude is not None else _location(locations[0] if locations else None)
    if live is None:
        raise HTTPException(status_code=400, detail="A live location or a previously ingested location is required")

    members = list((await db.execute(select(FamilyMember).where(FamilyMember.user_id == current_user.id, FamilyMember.is_active == True))).scalars().all())  # noqa: E712
    history = "\n".join(
        f"- {point.recorded_at.isoformat()}: https://maps.google.com/?q={point.latitude},{point.longitude}"
        for point in locations
    )
    message = f"{payload.message}\nLive location: https://maps.google.com/?q={live.latitude},{live.longitude}"
    if history:
        message += f"\nLast {len(locations)} locations:\n{history}"
    for member in members:
        notification = await notification_service.create_notification_record(db, current_user.id, member.id, journey.id if journey else None, message, "emergency")
        await notification_service.dispatch_notification(db, notification, member.phone_number)
    return SosRead(id=uuid.uuid4(), journey_id=journey.id if journey else None, status=SmartStatus.EMERGENCY, notified_members=len(members), locations=[_location(point) for point in locations if _location(point)], live_location=live)


@router.get("/share/{tracking_token}/status")
async def shared_status(tracking_token: str, db: AsyncSession = Depends(get_db)) -> dict:
    member = await db.scalar(select(FamilyMember).where(FamilyMember.tracking_token == tracking_token, FamilyMember.is_active == True))  # noqa: E712
    if member is None:
        raise HTTPException(status_code=404, detail="Tracking link is invalid or inactive")
    journey = await db.scalar(select(Journey).where(Journey.user_id == member.user_id, Journey.family_member_id == member.id, Journey.status == JourneyStatus.active.value).order_by(Journey.started_at.desc()))
    if journey is None:
        return {"journey": None, "status": None, "locations": []}
    result = await evaluate_journey_status(db, journey)
    points = list((await db.execute(select(LocationEvent).where(LocationEvent.user_id == member.user_id, LocationEvent.family_member_id == member.id, LocationEvent.recorded_at >= journey.started_at).order_by(LocationEvent.recorded_at.desc()).limit(100))).scalars().all())
    return {"journey": {"id": str(journey.id), "eta": journey.expected_arrival_at, "last_updated": result.last_updated}, "status": SmartStatusRead.model_validate(result).model_dump(mode="json"), "locations": [SosLocationRead.model_validate(point).model_dump(mode="json") for point in points]}
