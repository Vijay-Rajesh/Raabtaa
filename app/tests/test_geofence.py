import uuid
from datetime import datetime, timezone

import pytest

from app.models.safe_place import SafePlace
from app.services import geofence_service
from app.utils.geo import haversine_distance_meters, is_inside_geofence, is_valid_latitude, is_valid_longitude


def test_inside_radius():
    inside, distance = is_inside_geofence(24.9001, 67.1002, 24.9000, 67.1000, 200)
    assert inside is True
    assert distance < 200


def test_outside_radius():
    # Roughly 1.1km away -> well outside a 200m radius
    inside, distance = is_inside_geofence(24.9100, 67.1000, 24.9000, 67.1000, 200)
    assert inside is False
    assert distance > 200


def test_boundary_condition_exactly_on_radius():
    # Construct a point exactly (approximately) at the radius boundary.
    # 1 degree latitude ~= 111,320 meters, so a small delta approximates a known distance.
    delta_deg = 200 / 111320.0
    inside, distance = is_inside_geofence(24.9000 + delta_deg, 67.1000, 24.9000, 67.1000, 200)
    # distance should be very close to 200; allow the deterministic <=  comparison to decide
    assert abs(distance - 200) < 5


def test_invalid_coordinates_are_flagged():
    assert is_valid_latitude(95) is False
    assert is_valid_latitude(45) is True
    assert is_valid_longitude(-200) is False
    assert is_valid_longitude(-90) is True


@pytest.mark.asyncio
async def test_duplicate_enter_event_not_generated_twice(db_session):
    user_id = uuid.uuid4()
    place = SafePlace(
        id=uuid.uuid4(),
        user_id=user_id,
        name="College",
        place_type="college",
        latitude=24.9000,
        longitude=67.1000,
        radius_meters=200,
        is_active=True,
    )
    db_session.add(place)
    await db_session.flush()

    # First reading: inside geofence -> should produce ENTER transition
    transitions_1 = await geofence_service.evaluate_location_against_places(
        db_session, user_id, 24.9001, 67.1002, [place]
    )
    assert len(transitions_1) == 1
    assert transitions_1[0].event_type == "enter"

    await geofence_service.persist_transitions(db_session, user_id, transitions_1, 24.9001, 67.1002)
    await db_session.commit()

    # Second reading: still inside geofence -> should produce NO transition (no duplicate)
    transitions_2 = await geofence_service.evaluate_location_against_places(
        db_session, user_id, 24.9001, 67.1003, [place]
    )
    assert len(transitions_2) == 0
