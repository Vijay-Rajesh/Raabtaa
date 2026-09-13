"""
Function tools for the Safe Arrival Agent.

Every tool here wraps deterministic backend logic (DB reads, service calls).
The agent NEVER computes GPS distance, geofence membership, or timestamps
itself -- it only reads results that were already computed by
`app.services.geofence_service` / `app.utils.geo` and decides what to do
with them.

Each tool is implemented as a plain `_*_impl(ctx: ArrivalAgentContext, ...)`
coroutine (easy to unit test directly), then exposed to the Agents SDK via a
thin `@function_tool`-wrapped function that unwraps `RunContextWrapper`.
"""
import uuid
from typing import Optional

from agents import RunContextWrapper, function_tool
from sqlalchemy import select

from app.agents.context import ArrivalAgentContext
from app.core.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.geofence_event import GeofenceEvent
from app.models.journey import Journey, JourneyStatus
from app.models.location_event import LocationEvent
from app.models.safe_place import SafePlace
from app.services import notification_service
from app.services.whatsapp_service import send_message
from app.utils.time import format_time_for_message

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Plain implementations (unit-testable without the Agents SDK / OpenAI API)
# ---------------------------------------------------------------------------

async def _get_geofence_event_impl(ctx: ArrivalAgentContext) -> dict:
    result = await ctx.db.execute(
        select(GeofenceEvent).where(GeofenceEvent.id == ctx.geofence_event_id)
    )
    event = result.scalar_one_or_none()
    if event is None:
        return {"found": False}
    return {
        "found": True,
        "event_type": event.event_type,
        "distance_meters": event.distance_meters,
        "occurred_at": event.occurred_at.isoformat(),
        "processed": event.processed,
        "safe_place_id": str(event.safe_place_id),
    }


async def _get_destination_impl(ctx: ArrivalAgentContext) -> dict:
    result = await ctx.db.execute(select(SafePlace).where(SafePlace.id == ctx.safe_place_id))
    place = result.scalar_one_or_none()
    if place is None:
        return {"found": False}
    return {
        "found": True,
        "id": str(place.id),
        "name": place.name,
        "place_type": place.place_type,
        "radius_meters": place.radius_meters,
        "is_active": place.is_active,
        "belongs_to_user": str(place.user_id) == str(ctx.user_id),
    }


async def _get_active_journey_impl(ctx: ArrivalAgentContext) -> dict:
    result = await ctx.db.execute(
        select(Journey).where(
            Journey.user_id == ctx.user_id,
            Journey.destination_place_id == ctx.safe_place_id,
        ).order_by(Journey.started_at.desc()).limit(1)
    )
    journey = result.scalar_one_or_none()
    if journey is None:
        return {"found": False}
    return {
        "found": True,
        "id": str(journey.id),
        "status": journey.status,
        "is_active_or_arrived": journey.status in (JourneyStatus.active.value, JourneyStatus.arrived.value),
        "started_at": journey.started_at.isoformat(),
        "actual_arrival_at": journey.actual_arrival_at.isoformat() if journey.actual_arrival_at else None,
    }


async def _get_last_location_impl(ctx: ArrivalAgentContext) -> dict:
    result = await ctx.db.execute(
        select(LocationEvent)
        .where(LocationEvent.user_id == ctx.user_id)
        .order_by(LocationEvent.recorded_at.desc())
        .limit(1)
    )
    loc = result.scalar_one_or_none()
    if loc is None:
        return {"found": False}
    return {
        "found": True,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "accuracy_meters": loc.accuracy_meters,
        "recorded_at": loc.recorded_at.isoformat(),
    }


async def _get_recent_location_events_impl(ctx: ArrivalAgentContext, limit: int = 5) -> dict:
    result = await ctx.db.execute(
        select(LocationEvent)
        .where(LocationEvent.user_id == ctx.user_id)
        .order_by(LocationEvent.recorded_at.desc())
        .limit(max(1, min(limit, 20)))
    )
    events = result.scalars().all()
    return {
        "count": len(events),
        "events": [
            {"latitude": e.latitude, "longitude": e.longitude, "recorded_at": e.recorded_at.isoformat()}
            for e in events
        ],
    }


async def _check_arrival_notification_status_impl(ctx: ArrivalAgentContext) -> dict:
    result = await ctx.db.execute(
        select(Journey).where(
            Journey.user_id == ctx.user_id,
            Journey.destination_place_id == ctx.safe_place_id,
        ).order_by(Journey.started_at.desc()).limit(1)
    )
    journey = result.scalar_one_or_none()
    journey_id = journey.id if journey else None

    already_sent = await notification_service.has_existing_arrival_notification(
        ctx.db, ctx.user_id, journey_id
    )
    return {"already_sent": already_sent, "journey_id": str(journey_id) if journey_id else None}


async def _get_family_member_impl(
    ctx: ArrivalAgentContext, family_member_id: Optional[str] = None
) -> dict:
    member: Optional[FamilyMember] = None
    if family_member_id:
        try:
            fm_uuid = uuid.UUID(family_member_id)
        except ValueError:
            return {"found": False, "reason": "invalid_family_member_id"}
        member = await notification_service.get_eligible_family_member(ctx.db, ctx.user_id, fm_uuid)
    else:
        member = await notification_service.get_default_family_member(ctx.db, ctx.user_id)

    if member is None:
        return {"found": False}

    return {
        "found": True,
        "id": str(member.id),
        "name": member.name,
        "phone_number": member.phone_number,
        "relationship_type": member.relationship_type,
        "whatsapp_enabled": member.whatsapp_enabled,
        "is_active": member.is_active,
    }


async def _send_whatsapp_message_impl(
    ctx: ArrivalAgentContext, recipient_phone: str, message: str
) -> dict:
    result = await send_message(recipient_phone, message)
    return {
        "success": result.success,
        "status": result.status,
        "whatsapp_message_id": result.whatsapp_message_id,
        "error_message": result.error_message,
    }


async def _record_notification_impl(
    ctx: ArrivalAgentContext,
    family_member_id: str,
    journey_id: Optional[str],
    message: str,
    recipient_phone: str,
) -> dict:
    try:
        fm_uuid = uuid.UUID(family_member_id)
    except ValueError:
        return {"success": False, "reason": "invalid_family_member_id"}

    journey_uuid = None
    if journey_id:
        try:
            journey_uuid = uuid.UUID(journey_id)
        except ValueError:
            journey_uuid = None

    notification = await notification_service.create_notification_record(
        ctx.db,
        user_id=ctx.user_id,
        family_member_id=fm_uuid,
        journey_id=journey_uuid,
        message=message,
    )
    delivery = await notification_service.dispatch_notification(
        ctx.db, notification, recipient_phone
    )

    return {
        "success": delivery.status == "sent",
        "notification_id": str(notification.id),
        "notification_channel": delivery.channel,
        "notification_status": delivery.status,
        "provider_message_id": delivery.provider_message_id,
        "whatsapp_message_status": delivery.status if delivery.channel == "whatsapp" else "failed",
        "whatsapp_message_id": delivery.provider_message_id if delivery.channel == "whatsapp" else None,
        "error_message": delivery.error_message,
    }


def _format_arrival_time_impl(iso_timestamp: str) -> str:
    from datetime import datetime

    dt = datetime.fromisoformat(iso_timestamp)
    return format_time_for_message(dt)


# ---------------------------------------------------------------------------
# Agents SDK tool wrappers
# ---------------------------------------------------------------------------

@function_tool
async def get_geofence_event(wrapper: RunContextWrapper[ArrivalAgentContext]) -> dict:
    """Return the deterministic geofence event that triggered this agent run.

    Includes the pre-computed distance and event type (enter/exit). The
    agent must treat this data as ground truth and never recompute it.
    """
    return await _get_geofence_event_impl(wrapper.context)


@function_tool
async def get_destination(wrapper: RunContextWrapper[ArrivalAgentContext]) -> dict:
    """Return the safe place (destination) associated with this arrival event."""
    return await _get_destination_impl(wrapper.context)


@function_tool
async def get_active_journey(wrapper: RunContextWrapper[ArrivalAgentContext]) -> dict:
    """Return the user's active journey targeting this destination, if any."""
    return await _get_active_journey_impl(wrapper.context)


@function_tool
async def get_last_location(wrapper: RunContextWrapper[ArrivalAgentContext]) -> dict:
    """Return the user's most recently recorded raw GPS location (read-only, for context)."""
    return await _get_last_location_impl(wrapper.context)


@function_tool
async def get_recent_location_events(
    wrapper: RunContextWrapper[ArrivalAgentContext], limit: int = 5
) -> dict:
    """Return the user's most recent raw GPS location events (for sanity context only)."""
    return await _get_recent_location_events_impl(wrapper.context, limit)


@function_tool
async def check_arrival_notification_status(wrapper: RunContextWrapper[ArrivalAgentContext]) -> dict:
    """Check whether an arrival notification has already been sent for the active journey
    tied to this destination. Prevents duplicate notifications (Rule 1)."""
    return await _check_arrival_notification_status_impl(wrapper.context)


@function_tool
async def get_family_member(
    wrapper: RunContextWrapper[ArrivalAgentContext], family_member_id: Optional[str] = None
) -> dict:
    """Return an eligible active family member with a delivery channel.

    If family_member_id is not provided, the first eligible family member
    for the user is returned. This tool never returns disabled or inactive
    family members (Rule 2) -- if none are eligible, found=False.
    """
    return await _get_family_member_impl(wrapper.context, family_member_id)


@function_tool
async def send_whatsapp_message(
    wrapper: RunContextWrapper[ArrivalAgentContext],
    recipient_phone: str,
    message: str,
) -> dict:
    """Send a WhatsApp message via the WhatsApp Cloud API (or mock mode).

    This is a deterministic side-effecting tool: it performs the actual
    HTTP call. It does NOT decide whether to send -- that decision must
    already have been made by the agent using the other tools.
    """
    return await _send_whatsapp_message_impl(wrapper.context, recipient_phone, message)


@function_tool
async def record_notification(
    wrapper: RunContextWrapper[ArrivalAgentContext],
    family_member_id: str,
    journey_id: Optional[str],
    message: str,
    recipient_phone: str,
) -> dict:
    """Persist the notification and provider delivery result in PostgreSQL.

    This performs the DB writes for the notifications and whatsapp_messages
    tables and triggers WhatsApp-first delivery with Telegram fallback via the
    notification service (single source of truth for the send+record transaction).
    """
    return await _record_notification_impl(
        wrapper.context, family_member_id, journey_id, message, recipient_phone
    )


@function_tool
def format_arrival_time(iso_timestamp: str) -> str:
    """Format an ISO-8601 timestamp into a human-readable clock time, e.g. '8:20 AM'.
    This is deterministic formatting only -- no time-zone guessing or math is done by the agent."""
    return _format_arrival_time_impl(iso_timestamp)


ALL_TOOLS = [
    get_geofence_event,
    get_destination,
    get_active_journey,
    get_last_location,
    get_recent_location_events,
    check_arrival_notification_status,
    get_family_member,
    send_whatsapp_message,
    record_notification,
    format_arrival_time,
]
