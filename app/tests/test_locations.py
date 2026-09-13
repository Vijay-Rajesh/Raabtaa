from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest


async def _create_place(app_client, headers, name, place_type, lat, lon, radius=200):
    resp = await app_client.post(
        "/api/v1/places",
        headers=headers,
        json={
            "name": name,
            "place_type": place_type,
            "latitude": lat,
            "longitude": lon,
            "radius_meters": radius,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_location_ingestion_outside_geofence_no_arrival(app_client, registered_user):
    headers = registered_user["headers"]
    await _create_place(app_client, headers, "College", "college", 24.9000, 67.1000, 200)

    resp = await app_client.post(
        "/api/v1/locations",
        headers=headers,
        json={
            "latitude": 24.9500,
            "longitude": 67.1500,
            "accuracy_meters": 10,
            "speed": 5,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["arrival_triggered"] is False
    assert body["geofence_events"] == []


@pytest.mark.asyncio
async def test_location_ingestion_inside_geofence_triggers_arrival(app_client, registered_user):
    headers = registered_user["headers"]
    await _create_place(app_client, headers, "College", "college", 24.9000, 67.1000, 200)

    with patch(
        "app.api.routes.locations.run_safe_arrival_agent", new_callable=AsyncMock
    ) as mock_agent:
        mock_agent.return_value = None
        resp = await app_client.post(
            "/api/v1/locations",
            headers=headers,
            json={
                "latitude": 24.9001,
                "longitude": 67.1002,
                "accuracy_meters": 10,
                "speed": 1,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["arrival_triggered"] is True
        assert len(body["geofence_events"]) == 1
        assert body["geofence_events"][0]["event_type"] == "enter"
        mock_agent.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_inside_updates_do_not_retrigger_arrival(app_client, registered_user):
    headers = registered_user["headers"]
    await _create_place(app_client, headers, "College", "college", 24.9000, 67.1000, 200)

    with patch(
        "app.api.routes.locations.run_safe_arrival_agent", new_callable=AsyncMock
    ) as mock_agent:
        mock_agent.return_value = None

        for _ in range(5):
            resp = await app_client.post(
                "/api/v1/locations",
                headers=headers,
                json={
                    "latitude": 24.9001,
                    "longitude": 67.1002,
                    "accuracy_meters": 10,
                    "speed": 0,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            assert resp.status_code == 201

        # Only the FIRST update should have triggered the agent.
        assert mock_agent.await_count == 1


@pytest.mark.asyncio
async def test_invalid_coordinates_rejected(app_client, registered_user):
    headers = registered_user["headers"]
    resp = await app_client.post(
        "/api/v1/locations",
        headers=headers,
        json={
            "latitude": 999,
            "longitude": 67.1000,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == 422
