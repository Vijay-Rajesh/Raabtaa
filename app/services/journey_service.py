import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.journey import Journey, JourneyStatus
from app.models.safe_place import SafePlace
from app.models.tracking_schedule import TrackingSchedule
from app.utils.time import utcnow

logger = get_logger(__name__)


async def start_scheduled_journey_if_due(
    db: AsyncSession, user_id: uuid.UUID, family_member_id: uuid.UUID, now: datetime | None = None
) -> Journey | None:
    """Start the matching timetable journey when the first location arrives near departure time."""
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(TrackingSchedule).where(
            TrackingSchedule.user_id == user_id,
            TrackingSchedule.family_member_id == family_member_id,
            TrackingSchedule.is_active == True,  # noqa: E712
        )
    )
    weekday = str(now.weekday())
    current_minutes = now.hour * 60 + now.minute
    schedule = next(
        (
            item for item in result.scalars().all()
            if weekday in item.days_of_week.split(",")
            and abs((item.departure_time.hour * 60 + item.departure_time.minute) - current_minutes) <= 15
        ),
        None,
    )
    if schedule is None:
        return None

    active = await db.execute(
        select(Journey).where(
            Journey.user_id == user_id,
            Journey.family_member_id == family_member_id,
            Journey.status == JourneyStatus.active.value,
        ).limit(1)
    )
    if (existing := active.scalar_one_or_none()) is not None:
        return existing

    journey = Journey(
        user_id=user_id,
        family_member_id=family_member_id,
        schedule_id=schedule.id,
        origin_place_id=schedule.origin_place_id,
        destination_place_id=schedule.destination_place_id,
        started_at=now,
        expected_arrival_at=now + timedelta(minutes=schedule.expected_duration_minutes),
        status=JourneyStatus.active.value,
    )
    db.add(journey)
    await db.flush()
    await db.refresh(journey)
    logger.info("Scheduled journey started: schedule=%s family_member=%s", schedule.id, family_member_id)
    return journey


async def get_active_journey(db: AsyncSession, user_id: uuid.UUID) -> Journey | None:
    result = await db.execute(
        select(Journey).where(Journey.user_id == user_id, Journey.status == JourneyStatus.active.value)
        .order_by(Journey.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def start_journey_on_exit(
    db: AsyncSession, user_id: uuid.UUID, origin_place: SafePlace
) -> Journey | None:
    """
    Called when the user EXITs a safe place (e.g. Home). For MVP, since
    destinations are explicitly configured rather than predicted, we only
    start a journey if there is exactly one other active safe place that
    looks like a plausible destination (simple heuristic, extensible later).
    """
    existing_active = await get_active_journey(db, user_id)
    if existing_active is not None:
        logger.info("Journey already active for user=%s, skipping new journey on exit", user_id)
        return existing_active

    result = await db.execute(
        select(SafePlace).where(
            SafePlace.user_id == user_id,
            SafePlace.is_active == True,  # noqa: E712
            SafePlace.id != origin_place.id,
        )
    )
    candidate_destinations = list(result.scalars().all())

    if len(candidate_destinations) != 1:
        logger.info(
            "Cannot auto-determine a single destination for user=%s (%d candidates); "
            "journey not created automatically.",
            user_id,
            len(candidate_destinations),
        )
        return None

    destination = candidate_destinations[0]
    journey = Journey(
        user_id=user_id,
        origin_place_id=origin_place.id,
        destination_place_id=destination.id,
        started_at=utcnow(),
        status=JourneyStatus.active.value,
    )
    db.add(journey)
    await db.flush()
    await db.refresh(journey)
    logger.info("Journey started: user=%s origin=%s destination=%s", user_id, origin_place.name, destination.name)
    return journey


async def complete_journey_on_arrival(
    db: AsyncSession, journey: Journey, arrived_at
) -> Journey:
    journey.status = JourneyStatus.arrived.value
    journey.actual_arrival_at = arrived_at
    await db.flush()
    await db.refresh(journey)
    logger.info("Journey completed (arrived): journey=%s", journey.id)
    return journey


async def get_journey_for_destination(
    db: AsyncSession, user_id: uuid.UUID, destination_place_id: uuid.UUID, family_member_id: uuid.UUID | None = None
) -> Journey | None:
    """Find the active journey targeting this destination, if any."""
    result = await db.execute(
        select(Journey).where(
            Journey.user_id == user_id,
            Journey.destination_place_id == destination_place_id,
            Journey.status == JourneyStatus.active.value,
            Journey.family_member_id == family_member_id,
        ).order_by(Journey.started_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()
