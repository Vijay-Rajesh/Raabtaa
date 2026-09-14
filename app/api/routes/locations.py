import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.safe_arrival_agent import run_safe_arrival_agent
from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.database.session import get_db
from app.models.geofence_event import GeofenceEventType
from app.models.family_member import FamilyMember
from app.models.location_event import LocationEvent
from app.models.safe_place import SafePlace
from app.models.user import User
from app.schemas.location import GeofenceEventRead, LocationCreate, LocationEventRead, LocationIngestResponse
from app.services import arrival_service, geofence_service, journey_service
from app.services.smart_status_service import SmartStatus, evaluate_journey_status
from app.services import notification_service
from app.models.notification import Notification

router = APIRouter(prefix="/api/v1/locations", tags=["Locations"])


@router.post("/shared/{tracking_token}", response_model=LocationIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_shared_location(
    tracking_token: str,
    payload: LocationCreate,
    db: AsyncSession = Depends(get_db),
) -> LocationIngestResponse:
    result = await db.execute(
        select(FamilyMember).where(FamilyMember.tracking_token == tracking_token, FamilyMember.is_active == True)  # noqa: E712
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Tracking link is invalid or inactive")
    owner = await db.get(User, member.user_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Tracking owner not found")
    scoped_payload = payload.model_copy(update={"family_member_id": member.id})
    return await ingest_location(scoped_payload, owner, db)
logger = get_logger(__name__)


@router.get("", response_model=list[LocationEventRead])
async def list_locations(
    limit: int = Query(100, ge=1, le=500),
    family_member_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LocationEvent]:
    result = await db.execute(
        select(LocationEvent)
        .where(LocationEvent.user_id == current_user.id)
        .where(LocationEvent.family_member_id == family_member_id if family_member_id else LocationEvent.family_member_id.is_(None))
        .order_by(LocationEvent.recorded_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("", response_model=LocationIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_location(
    payload: LocationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LocationIngestResponse:
    """
    Core pipeline entry point:
    save location -> evaluate geofences -> create geofence events ->
    trigger arrival processing -> (maybe) invoke Safe Arrival Agent.
    """
    if payload.family_member_id is not None:
        member_result = await db.execute(
            select(FamilyMember).where(
                FamilyMember.id == payload.family_member_id,
                FamilyMember.user_id == current_user.id,
                FamilyMember.is_active == True,  # noqa: E712
            )
        )
        if member_result.scalar_one_or_none() is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Family member not found")

    logger.info("Location received: user=%s family_member=%s lat=%s lon=%s", current_user.id, payload.family_member_id, payload.latitude, payload.longitude)

    if payload.family_member_id is not None:
        await journey_service.start_scheduled_journey_if_due(db, current_user.id, payload.family_member_id)

    location = LocationEvent(
        user_id=current_user.id,
        family_member_id=payload.family_member_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=payload.accuracy_meters,
        speed=payload.speed,
        recorded_at=payload.recorded_at,
    )
    db.add(location)
    await db.flush()
    await db.refresh(location)

    result = await db.execute(
        select(SafePlace).where(SafePlace.user_id == current_user.id, SafePlace.is_active == True)  # noqa: E712
    )
    active_places = list(result.scalars().all())
    places_by_id = {p.id: p for p in active_places}

    transitions = await geofence_service.evaluate_location_against_places(
        db, current_user.id, payload.latitude, payload.longitude, active_places, payload.family_member_id
    )
    logger.info("Geofence evaluated: user=%s transitions=%d", current_user.id, len(transitions))

    geofence_events = await geofence_service.persist_transitions(
        db, current_user.id, transitions, payload.latitude, payload.longitude
        , payload.family_member_id
    )
    await db.commit()
    for e in geofence_events:
        await db.refresh(e)

    arrival_triggered = False

    for event in geofence_events:
        safe_place = places_by_id[event.safe_place_id]
        should_invoke_agent = await arrival_service.process_geofence_event(
            db, current_user.id, event, safe_place
        )
        if event.event_type == GeofenceEventType.enter.value:
            logger.info("Arrival event created: user=%s place=%s", current_user.id, safe_place.name)

        if should_invoke_agent:
            arrival_triggered = True
            await run_safe_arrival_agent(
                db=db,
                user_id=current_user.id,
                geofence_event_id=event.id,
                safe_place_id=safe_place.id,
            )

    await db.refresh(location)

    # Evaluate safety after the point is durable. Alert contacts only when a
    # late/deviation alert has not already been sent during this journey window.
    active_journey = await journey_service.get_active_journey(db, current_user.id)
    safety_status = await evaluate_journey_status(db, active_journey) if active_journey else None
    if safety_status and safety_status.status in (SmartStatus.LATE, SmartStatus.DEVIATED):
        recent = await db.scalar(
            select(Notification).where(
                Notification.user_id == current_user.id,
                Notification.journey_id == active_journey.id,
                Notification.notification_type == ("delay" if safety_status.status == SmartStatus.LATE else "deviation"),
            ).order_by(Notification.created_at.desc()).limit(1)
        )
        if recent is None:
            members = list((await db.execute(select(FamilyMember).where(
                FamilyMember.user_id == current_user.id,
                FamilyMember.is_active == True,  # noqa: E712
            ))).scalars().all())
            message = (
                f"SafeReach alert: journey is {safety_status.status.replace('_', ' ')}. "
                f"{safety_status.reason}."
            )
            for member in members:
                alert = await notification_service.create_notification_record(
                    db, current_user.id, member.id, active_journey.id, message,
                    "delay" if safety_status.status == SmartStatus.LATE else "deviation",
                )
                await notification_service.dispatch_notification(db, alert, member.phone_number)

    return LocationIngestResponse(
        location=location,
        geofence_events=[GeofenceEventRead.model_validate(e) for e in geofence_events],
        arrival_triggered=arrival_triggered,
    )
