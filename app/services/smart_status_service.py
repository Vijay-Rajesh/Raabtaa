import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journey import Journey, JourneyStatus
from app.models.location_event import LocationEvent
from app.models.notification import Notification
from app.models.safe_place import SafePlace
from app.utils.time import utcnow


class SmartStatus:
    ON_TRACK = "on_track"
    LATE = "late"
    DEVIATED = "deviated"
    NO_MOVEMENT = "no_movement"
    EMERGENCY = "emergency"


@dataclass(frozen=True)
class SmartStatusResult:
    status: str
    reason: str
    last_updated: datetime | None
    deviation_meters: float | None
    eta: datetime | None


def _distance_meters(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6_371_000
    d_lat = math.radians(b_lat - a_lat)
    d_lon = math.radians(b_lon - a_lon)
    x = d_lon * math.cos(math.radians((a_lat + b_lat) / 2))
    return radius * math.sqrt(d_lat * d_lat + x * x)


def _distance_to_expected_route(point: LocationEvent, origin: SafePlace | None, destination: SafePlace) -> float | None:
    if origin is None:
        return None
    # Equirectangular projection is accurate enough for the short journeys this
    # service monitors and avoids a GIS dependency.
    scale = 111_320
    lat_scale = math.cos(math.radians((origin.latitude + destination.latitude) / 2))
    ax, ay = origin.longitude * scale * lat_scale, origin.latitude * scale
    bx, by = destination.longitude * scale * lat_scale, destination.latitude * scale
    px, py = point.longitude * scale * lat_scale, point.latitude * scale
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    ratio = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq)) if length_sq else 0.0
    return math.hypot(px - (ax + ratio * dx), py - (ay + ratio * dy))


async def evaluate_journey_status(
    db: AsyncSession,
    journey: Journey,
    now: datetime | None = None,
    deviation_threshold_meters: float = 250,
    late_grace_minutes: int = 2,
    no_movement_minutes: int = 10,
) -> SmartStatusResult:
    now = now or utcnow()
    if journey.status == JourneyStatus.arrived.value:
        return SmartStatusResult(SmartStatus.ON_TRACK, "Arrival confirmed", None, None, journey.expected_arrival_at)

    emergency = await db.scalar(
        select(Notification).where(
            Notification.user_id == journey.user_id,
            Notification.journey_id == journey.id,
            Notification.notification_type == "emergency",
        ).order_by(Notification.created_at.desc()).limit(1)
    )
    if emergency is not None:
        return SmartStatusResult(SmartStatus.EMERGENCY, "SOS was raised for this journey", emergency.created_at, None, journey.expected_arrival_at)

    point_result = await db.execute(
        select(LocationEvent)
        .where(LocationEvent.user_id == journey.user_id)
        .where(LocationEvent.family_member_id == journey.family_member_id if journey.family_member_id else LocationEvent.family_member_id.is_(None))
        .where(LocationEvent.recorded_at >= journey.started_at)
        .order_by(LocationEvent.recorded_at.desc())
        .limit(5)
    )
    points = list(point_result.scalars().all())
    latest = points[0] if points else None
    if latest is None:
        return SmartStatusResult(SmartStatus.NO_MOVEMENT, "No location has been received", None, None, journey.expected_arrival_at)

    destination = await db.get(SafePlace, journey.destination_place_id)
    origin = await db.get(SafePlace, journey.origin_place_id) if journey.origin_place_id else None
    deviation = _distance_to_expected_route(latest, origin, destination) if destination else None
    if deviation is not None and deviation > deviation_threshold_meters:
        return SmartStatusResult(SmartStatus.DEVIATED, "Latest location is outside the expected route", latest.recorded_at, deviation, journey.expected_arrival_at)

    latest_time = latest.recorded_at
    if latest_time.tzinfo is None:
        latest_time = latest_time.replace(tzinfo=timezone.utc)
    if now - latest_time > timedelta(minutes=no_movement_minutes):
        return SmartStatusResult(SmartStatus.NO_MOVEMENT, "No recent location update", latest.recorded_at, deviation, journey.expected_arrival_at)

    if len(points) >= 3:
        movement = sum(
            _distance_meters(points[i].latitude, points[i].longitude, points[i + 1].latitude, points[i + 1].longitude)
            for i in range(len(points) - 1)
        )
        if movement < 30 and all((point.speed or 0) <= 1 for point in points):
            return SmartStatusResult(SmartStatus.NO_MOVEMENT, "Recent points show no meaningful movement", latest.recorded_at, deviation, journey.expected_arrival_at)

    if journey.expected_arrival_at and now > journey.expected_arrival_at + timedelta(minutes=late_grace_minutes):
        return SmartStatusResult(SmartStatus.LATE, "Expected arrival time has passed", latest.recorded_at, None, journey.expected_arrival_at)

    return SmartStatusResult(SmartStatus.ON_TRACK, "Location is recent and on the expected route", latest.recorded_at, deviation, journey.expected_arrival_at)


async def get_active_journey_status(db: AsyncSession, user_id: uuid.UUID) -> tuple[Journey, SmartStatusResult] | None:
    result = await db.execute(
        select(Journey)
        .where(Journey.user_id == user_id, Journey.status == JourneyStatus.active.value)
        .order_by(Journey.started_at.desc())
        .limit(1)
    )
    journey = result.scalar_one_or_none()
    if journey is None:
        return None
    return journey, await evaluate_journey_status(db, journey)
