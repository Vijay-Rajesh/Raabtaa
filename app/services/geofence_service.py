"""
Deterministic geofence evaluation.

This service NEVER calls the LLM. It is purely Python/SQL logic responsible
for deciding whether a location update represents an ENTER, EXIT, or no
transition relative to the user's configured safe places, and for preventing
duplicate ENTER events while the user remains inside a geofence.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.geofence_event import GeofenceEvent, GeofenceEventType
from app.models.safe_place import SafePlace
from app.utils.geo import is_inside_geofence
from app.utils.time import utcnow

logger = get_logger(__name__)


@dataclass
class GeofenceTransition:
    safe_place: SafePlace
    event_type: str  # "enter" | "exit"
    distance_meters: float


async def _get_last_event_for_place(
    db: AsyncSession, user_id: uuid.UUID, safe_place_id: uuid.UUID, family_member_id: uuid.UUID | None = None
) -> GeofenceEvent | None:
    result = await db.execute(
        select(GeofenceEvent)
        .where(
            GeofenceEvent.user_id == user_id,
            GeofenceEvent.safe_place_id == safe_place_id,
            GeofenceEvent.family_member_id == family_member_id,
        )
        .order_by(GeofenceEvent.occurred_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def evaluate_location_against_places(
    db: AsyncSession,
    user_id: uuid.UUID,
    latitude: float,
    longitude: float,
    active_places: list[SafePlace],
    family_member_id: uuid.UUID | None = None,
) -> list[GeofenceTransition]:
    """
    Compare a single location update against every active safe place and
    return only the state TRANSITIONS (outside->inside or inside->outside).

    Prevents duplicate ENTER events: if the last known state for a place is
    already "inside", a further "inside" reading produces no transition.
    """
    transitions: list[GeofenceTransition] = []

    for place in active_places:
        inside, distance = is_inside_geofence(
            latitude, longitude, place.latitude, place.longitude, place.radius_meters
        )

        last_event = await _get_last_event_for_place(db, user_id, place.id, family_member_id)
        last_state_inside = last_event is not None and last_event.event_type == GeofenceEventType.enter.value

        if inside and not last_state_inside:
            transitions.append(
                GeofenceTransition(safe_place=place, event_type=GeofenceEventType.enter.value, distance_meters=distance)
            )
            logger.info("Geofence ENTER detected: place=%s distance=%.1fm", place.name, distance)
        elif not inside and last_state_inside:
            transitions.append(
                GeofenceTransition(safe_place=place, event_type=GeofenceEventType.exit.value, distance_meters=distance)
            )
            logger.info("Geofence EXIT detected: place=%s distance=%.1fm", place.name, distance)
        # else: no state change -> no event, prevents duplicate arrivals

    return transitions


async def persist_transitions(
    db: AsyncSession,
    user_id: uuid.UUID,
    transitions: list[GeofenceTransition],
    latitude: float,
    longitude: float,
    family_member_id: uuid.UUID | None = None,
) -> list[GeofenceEvent]:
    events: list[GeofenceEvent] = []
    for t in transitions:
        event = GeofenceEvent(
            user_id=user_id,
            family_member_id=family_member_id,
            safe_place_id=t.safe_place.id,
            event_type=t.event_type,
            latitude=latitude,
            longitude=longitude,
            distance_meters=t.distance_meters,
            occurred_at=utcnow(),
            processed=False,
        )
        db.add(event)
        events.append(event)

    if events:
        await db.flush()
        for e in events:
            await db.refresh(e)

    return events
