from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_sos_includes_recent_location_and_notifies_active_family(app_client, registered_user):
    headers = registered_user["headers"]
    family = await app_client.post(
        "/api/v1/family",
        headers=headers,
        json={
            "name": "Emergency contact",
            "phone_number": "+923001234567",
            "relationship_type": "parent",
            "whatsapp_enabled": True,
            "telegram_enabled": False,
        },
    )
    assert family.status_code == 201, family.text

    await app_client.post(
        "/api/v1/locations",
        headers=headers,
        json={
            "latitude": 24.8607,
            "longitude": 67.0011,
            "speed": 0,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    sos = await app_client.post(
        "/api/v1/sos",
        headers=headers,
        json={"latitude": 24.861, "longitude": 67.002},
    )

    assert sos.status_code == 201, sos.text
    body = sos.json()
    assert body["status"] == "emergency"
    assert body["notified_members"] == 1
    assert len(body["locations"]) == 1
    assert body["live_location"]["latitude"] == 24.861

    notifications = await app_client.get("/api/v1/notifications", headers=headers)
    assert notifications.status_code == 200
    assert any(item["notification_type"] == "emergency" for item in notifications.json())


@pytest.mark.asyncio
async def test_safety_status_is_available_without_active_journey(app_client, registered_user):
    response = await app_client.get("/api/v1/safety/status", headers=registered_user["headers"])

    assert response.status_code == 200
    assert response.json()["status"] == "on_track"
