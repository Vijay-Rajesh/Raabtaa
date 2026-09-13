import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.geofence_event import GeofenceEvent, GeofenceEventType
from app.models.safe_place import SafePlace
from app.services import journey_service
from app.utils.time import utcnow

logger = get_logger(__name__)


async def process_geofence_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    geofence_event: GeofenceEvent,
    safe_place: SafePlace,
) -> bool:
    """
    Handle the deterministic side-effects of a geofence transition:
    - EXIT from a place may start a journey.
    - ENTER at a place may complete a journey and should trigger the
      Safe Arrival Agent to decide on notification.

    Returns True if the Safe Arrival Agent should be invoked for this event.
    """
    if geofence_event.event_type == GeofenceEventType.exit.value:
        await journey_service.start_journey_on_exit(db, user_id, safe_place)
        await db.commit()
        return False

    if geofence_event.event_type == GeofenceEventType.enter.value:
        journey = await journey_service.get_journey_for_destination(db, user_id, safe_place.id, geofence_event.family_member_id)
        if journey is not None:
            await journey_service.complete_journey_on_arrival(db, journey, utcnow())

        geofence_event.processed = True
        await db.commit()
        logger.info(
            "Arrival event ready for Safe Arrival Agent: user=%s place=%s geofence_event=%s",
            user_id,
            safe_place.name,
            geofence_event.id,
        )
        return True

    return False
