import uuid
from datetime import datetime, timezone

import pytest

from app.models.geofence_event import GeofenceEvent
from app.models.journey import Journey, JourneyStatus
from app.models.safe_place import SafePlace
from app.services import arrival_service, journey_service


@pytest.mark.asyncio
async def test_journey_created_on_home_exit_with_single_candidate_destination(db_session):
    user_id = uuid.uuid4()
    home = SafePlace(
        id=uuid.uuid4(), user_id=user_id, name="Home", place_type="home",
        latitude=24.8607, longitude=67.0011, radius_meters=150, is_active=True,
    )
    college = SafePlace(
        id=uuid.uuid4(), user_id=user_id, name="College", place_type="college",
        latitude=24.9000, longitude=67.1000, radius_meters=200, is_active=True,
    )
    db_session.add_all([home, college])
    await db_session.flush()

    journey = await journey_service.start_journey_on_exit(db_session, user_id, home)
    await db_session.commit()

    assert journey is not None
    assert journey.destination_place_id == college.id
    assert journey.status == JourneyStatus.active.value


@pytest.mark.asyncio
async def test_journey_completed_on_arrival(db_session):
    user_id = uuid.uuid4()
    college = SafePlace(
        id=uuid.uuid4(), user_id=user_id, name="College", place_type="college",
        latitude=24.9000, longitude=67.1000, radius_meters=200, is_active=True,
    )
    db_session.add(college)
    await db_session.flush()

    journey = Journey(
        id=uuid.uuid4(), user_id=user_id, origin_place_id=None,
        destination_place_id=college.id, status=JourneyStatus.active.value,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(journey)
    await db_session.flush()

    updated = await journey_service.complete_journey_on_arrival(
        db_session, journey, datetime.now(timezone.utc)
    )
    await db_session.commit()

    assert updated.status == JourneyStatus.arrived.value
    assert updated.actual_arrival_at is not None


@pytest.mark.asyncio
async def test_arrival_service_signals_agent_invocation_on_enter(db_session):
    user_id = uuid.uuid4()
    college = SafePlace(
        id=uuid.uuid4(), user_id=user_id, name="College", place_type="college",
        latitude=24.9000, longitude=67.1000, radius_meters=200, is_active=True,
    )
    db_session.add(college)
    await db_session.flush()

    event = GeofenceEvent(
        id=uuid.uuid4(), user_id=user_id, safe_place_id=college.id,
        event_type="enter", latitude=24.9001, longitude=67.1002,
        distance_meters=35.0, occurred_at=datetime.now(timezone.utc), processed=False,
    )
    db_session.add(event)
    await db_session.flush()

    should_invoke = await arrival_service.process_geofence_event(db_session, user_id, event, college)
    assert should_invoke is True
    assert event.processed is True


@pytest.mark.asyncio
async def test_arrival_service_does_not_invoke_agent_on_exit(db_session):
    user_id = uuid.uuid4()
    home = SafePlace(
        id=uuid.uuid4(), user_id=user_id, name="Home", place_type="home",
        latitude=24.8607, longitude=67.0011, radius_meters=150, is_active=True,
    )
    db_session.add(home)
    await db_session.flush()

    event = GeofenceEvent(
        id=uuid.uuid4(), user_id=user_id, safe_place_id=home.id,
        event_type="exit", latitude=24.8700, longitude=67.0100,
        distance_meters=500.0, occurred_at=datetime.now(timezone.utc), processed=False,
    )
    db_session.add(event)
    await db_session.flush()

    should_invoke = await arrival_service.process_geofence_event(db_session, user_id, event, home)
    assert should_invoke is False
