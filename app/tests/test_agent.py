import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.context import ArrivalAgentContext
from app.agents.guardrails import safe_output_guardrail, valid_event_guardrail
from app.agents.tools import (
    _check_arrival_notification_status_impl,
    _get_active_journey_impl,
    _get_destination_impl,
    _get_family_member_impl,
    _get_geofence_event_impl,
    _record_notification_impl,
)
from app.models.family_member import FamilyMember
from app.models.geofence_event import GeofenceEvent
from app.models.journey import Journey, JourneyStatus
from app.models.notification import Notification, NotificationType
from app.models.safe_place import SafePlace


class FakeWrapper:
    """Minimal stand-in for agents.RunContextWrapper for guardrail tests."""

    def __init__(self, context):
        self.context = context


async def _seed_valid_arrival(db_session):
    user_id = uuid.uuid4()
    place = SafePlace(
        id=uuid.uuid4(), user_id=user_id, name="College", place_type="college",
        latitude=24.9000, longitude=67.1000, radius_meters=200, is_active=True,
    )
    db_session.add(place)
    await db_session.flush()

    event = GeofenceEvent(
        id=uuid.uuid4(), user_id=user_id, safe_place_id=place.id,
        event_type="enter", latitude=24.9001, longitude=67.1002,
        distance_meters=35.0, occurred_at=datetime.now(timezone.utc), processed=False,
    )
    db_session.add(event)
    await db_session.flush()

    return user_id, place, event


@pytest.mark.asyncio
async def test_valid_arrival_passes_input_guardrail(db_session):
    user_id, place, event = await _seed_valid_arrival(db_session)
    ctx = ArrivalAgentContext(db=db_session, user_id=user_id, geofence_event_id=event.id, safe_place_id=place.id)

    result = await valid_event_guardrail.guardrail_function(FakeWrapper(ctx), agent=None, input_data="evaluate")
    assert result.tripwire_triggered is False


@pytest.mark.asyncio
async def test_invalid_arrival_trips_input_guardrail_when_event_missing(db_session):
    user_id, place, _ = await _seed_valid_arrival(db_session)
    fake_event_id = uuid.uuid4()
    ctx = ArrivalAgentContext(db=db_session, user_id=user_id, geofence_event_id=fake_event_id, safe_place_id=place.id)

    result = await valid_event_guardrail.guardrail_function(FakeWrapper(ctx), agent=None, input_data="evaluate")
    assert result.tripwire_triggered is True
    assert "geofence_event_not_found" in result.output_info["problems"]


@pytest.mark.asyncio
async def test_invalid_arrival_trips_guardrail_on_exit_event(db_session):
    user_id = uuid.uuid4()
    place = SafePlace(
        id=uuid.uuid4(), user_id=user_id, name="Home", place_type="home",
        latitude=24.8607, longitude=67.0011, radius_meters=150, is_active=True,
    )
    db_session.add(place)
    await db_session.flush()

    event = GeofenceEvent(
        id=uuid.uuid4(), user_id=user_id, safe_place_id=place.id,
        event_type="exit", latitude=24.87, longitude=67.02,
        distance_meters=800.0, occurred_at=datetime.now(timezone.utc), processed=False,
    )
    db_session.add(event)
    await db_session.flush()

    ctx = ArrivalAgentContext(db=db_session, user_id=user_id, geofence_event_id=event.id, safe_place_id=place.id)
    result = await valid_event_guardrail.guardrail_function(FakeWrapper(ctx), agent=None, input_data="evaluate")
    assert result.tripwire_triggered is True
    assert "geofence_event_not_enter" in result.output_info["problems"]


@pytest.mark.asyncio
async def test_duplicate_arrival_notification_detected(db_session):
    user_id, place, event = await _seed_valid_arrival(db_session)

    journey = Journey(
        id=uuid.uuid4(), user_id=user_id, origin_place_id=None, destination_place_id=place.id,
        status=JourneyStatus.arrived.value, started_at=datetime.now(timezone.utc),
    )
    db_session.add(journey)
    await db_session.flush()

    fm = FamilyMember(
        id=uuid.uuid4(), user_id=user_id, name="Father", phone_number="+923001112222",
        relationship_type="parent", whatsapp_enabled=True, is_active=True,
    )
    db_session.add(fm)
    await db_session.flush()

    existing_notification = Notification(
        id=uuid.uuid4(), user_id=user_id, family_member_id=fm.id, journey_id=journey.id,
        notification_type=NotificationType.arrival.value, message="already sent",
    )
    db_session.add(existing_notification)
    await db_session.flush()

    ctx = ArrivalAgentContext(db=db_session, user_id=user_id, geofence_event_id=event.id, safe_place_id=place.id)
    status_result = await _check_arrival_notification_status_impl(ctx)
    assert status_result["already_sent"] is True


@pytest.mark.asyncio
async def test_missing_family_member_returns_not_found(db_session):
    user_id, place, event = await _seed_valid_arrival(db_session)
    ctx = ArrivalAgentContext(db=db_session, user_id=user_id, geofence_event_id=event.id, safe_place_id=place.id)

    result = await _get_family_member_impl(ctx)
    assert result["found"] is False


@pytest.mark.asyncio
async def test_whatsapp_disabled_family_member_not_returned(db_session):
    user_id, place, event = await _seed_valid_arrival(db_session)

    fm = FamilyMember(
        id=uuid.uuid4(), user_id=user_id, name="Father", phone_number="+923001112222",
        relationship_type="parent", whatsapp_enabled=False, is_active=True,
    )
    db_session.add(fm)
    await db_session.flush()

    ctx = ArrivalAgentContext(db=db_session, user_id=user_id, geofence_event_id=event.id, safe_place_id=place.id)
    result = await _get_family_member_impl(ctx, family_member_id=str(fm.id))
    assert result["found"] is False


@pytest.mark.asyncio
async def test_output_guardrail_blocks_send_without_family_member_id():
    output = SimpleNamespace(decision="send_notification", family_member_id=None, message="Hi there!")
    result = await safe_output_guardrail.guardrail_function(FakeWrapper(None), agent=None, output=output)
    assert result.tripwire_triggered is True
    assert "missing_family_member_id" in result.output_info["problems"]


@pytest.mark.asyncio
async def test_output_guardrail_blocks_raw_phone_number_in_message():
    output = SimpleNamespace(
        decision="send_notification",
        family_member_id=str(uuid.uuid4()),
        message="Contact them at +923001234567 for details",
    )
    result = await safe_output_guardrail.guardrail_function(FakeWrapper(None), agent=None, output=output)
    assert result.tripwire_triggered is True
    assert "message_contains_raw_phone_number" in result.output_info["problems"]


@pytest.mark.asyncio
async def test_output_guardrail_allows_valid_skip_decision():
    output = SimpleNamespace(decision="skip", family_member_id=None, message=None)
    result = await safe_output_guardrail.guardrail_function(FakeWrapper(None), agent=None, output=output)
    assert result.tripwire_triggered is False


@pytest.mark.asyncio
async def test_record_notification_impl_sends_and_persists(db_session, monkeypatch):
    user_id, place, event = await _seed_valid_arrival(db_session)
    fm = FamilyMember(
        id=uuid.uuid4(), user_id=user_id, name="Father", phone_number="+923001112222",
        relationship_type="parent", whatsapp_enabled=True, is_active=True,
    )
    db_session.add(fm)
    await db_session.flush()

    ctx = ArrivalAgentContext(db=db_session, user_id=user_id, geofence_event_id=event.id, safe_place_id=place.id)

    result = await _record_notification_impl(
        ctx,
        family_member_id=str(fm.id),
        journey_id=None,
        message="✅ Ali has safely arrived at College at 8:20 AM.",
        recipient_phone=fm.phone_number,
    )
    assert result["success"] is True
    assert result["whatsapp_message_status"] == "sent"
