import uuid

import pytest

from app.core.config import settings


@pytest.mark.asyncio
async def test_admin_can_sign_in_and_manage_users(app_client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "mohsintaj")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "musabjaan")

    login = await app_client.post(
        "/api/v1/admin/auth/login",
        json={"username": "mohsintaj", "password": "musabjaan"},
    )
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}

    created = await app_client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "full_name": "Managed User",
            "email": f"managed_{uuid.uuid4().hex[:8]}@example.com",
            "username": f"managed_{uuid.uuid4().hex[:8]}",
            "phone_number": "+923001234567",
            "password": "SecurePass123",
        },
    )
    assert created.status_code == 201

    stats = await app_client.get("/api/v1/admin/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["users"] >= 2

    user_id = created.json()["id"]
    updated_email = f"updated_{uuid.uuid4().hex[:8]}@example.com"
    updated_username = f"updated_{uuid.uuid4().hex[:8]}"
    updated = await app_client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=headers,
        json={
            "full_name": "Updated Managed User",
            "email": updated_email,
            "username": updated_username,
            "phone_number": "+923009876543",
            "password": "UpdatedPass123",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Updated Managed User"
    assert "password_hash" not in updated.json()
    user_login = await app_client.post(
        "/api/v1/auth/login",
        json={"email": updated_email, "password": "UpdatedPass123"},
    )
    assert user_login.status_code == 200


@pytest.mark.asyncio
async def test_regular_user_cannot_access_admin_routes(app_client, registered_user):
    response = await app_client.get("/api/v1/admin/users", headers=registered_user["headers"])
    assert response.status_code == 403
