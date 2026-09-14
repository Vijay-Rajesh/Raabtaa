import uuid
from unittest.mock import AsyncMock

import pytest

from app.api.routes import auth as auth_route
from app.api.routes import family as family_route
from app.services.whatsapp_service import WhatsAppSendResult


@pytest.mark.asyncio
async def test_register_login_me_flow(app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    register_payload = {
        "full_name": "Test User",
        "email": email,
        "phone_number": "+923001234567",
        "password": "SuperSecret123",
    }
    resp = await app_client.post("/api/v1/auth/register", json=register_payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == email
    assert "password" not in body
    assert "password_hash" not in body

    login_resp = await app_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"}
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    me_resp = await app_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    await app_client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Test User",
            "email": email,
            "phone_number": "+923001234567",
            "password": "SuperSecret123",
        },
    )
    resp = await app_client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pass"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_registration_rejected(app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "full_name": "Test User",
        "email": email,
        "phone_number": "+923001234567",
        "password": "SuperSecret123",
    }
    resp1 = await app_client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201
    resp2 = await app_client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_registration_sends_one_welcome_message(app_client, monkeypatch):
    welcome_sender = AsyncMock(
        return_value=WhatsAppSendResult(True, "mock-welcome", "sent", None)
    )
    monkeypatch.setattr(auth_route, "send_message", welcome_sender)
    email = f"welcome_{uuid.uuid4().hex[:8]}@example.com"

    response = await app_client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Welcome User",
            "email": email,
            "phone_number": "+923001234567",
            "password": "SuperSecret123",
        },
    )

    assert response.status_code == 201
    welcome_sender.assert_awaited_once()
    assert welcome_sender.await_args.args[0] == "+923001234567"
    assert "Welcome to SafeReach" in welcome_sender.await_args.args[1]


@pytest.mark.asyncio
async def test_registration_succeeds_when_welcome_delivery_fails(app_client, monkeypatch):
    monkeypatch.setattr(
        auth_route,
        "send_message",
        AsyncMock(return_value=WhatsAppSendResult(False, None, "failed", "Provider unavailable")),
    )
    response = await app_client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Offline Welcome User",
            "email": f"offline_{uuid.uuid4().hex[:8]}@example.com",
            "phone_number": "+923001234567",
            "password": "SuperSecret123",
        },
    )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_family_member_receives_one_welcome_message(app_client, monkeypatch):
    email = f"family_welcome_{uuid.uuid4().hex[:8]}@example.com"
    await app_client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Family Owner",
            "email": email,
            "phone_number": "+923001234567",
            "password": "SuperSecret123",
        },
    )
    login_response = await app_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SuperSecret123"},
    )
    token = login_response.json()["access_token"]
    welcome_sender = AsyncMock(
        return_value=WhatsAppSendResult(True, "mock-family-welcome", "sent", None)
    )
    monkeypatch.setattr(family_route, "send_message", welcome_sender)

    response = await app_client.post(
        "/api/v1/family",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Family Member",
            "phone_number": "+923009876543",
            "relationship_type": "parent",
            "whatsapp_enabled": True,
            "telegram_enabled": False,
        },
    )

    assert response.status_code == 201
    welcome_sender.assert_awaited_once()
    assert welcome_sender.await_args.args[0] == "+923009876543"


@pytest.mark.asyncio
async def test_protected_endpoint_requires_auth(app_client):
    resp = await app_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_user_can_update_profile(app_client, registered_user):
    response = await app_client.put(
        "/api/v1/users/me",
        headers=registered_user["headers"],
        json={"full_name": "Updated User", "phone_number": "+923009998887"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated User"
    assert response.json()["phone_number"] == "+923009998887"


@pytest.mark.asyncio
async def test_user_can_change_password(app_client, registered_user):
    response = await app_client.post(
        "/api/v1/users/me/password",
        headers=registered_user["headers"],
        json={"current_password": "SuperSecret123", "new_password": "NewSecret456"},
    )
    assert response.status_code == 204
    login = await app_client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": "NewSecret456"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_wrong_current_password_is_rejected(app_client, registered_user):
    response = await app_client.post(
        "/api/v1/users/me/password",
        headers=registered_user["headers"],
        json={"current_password": "WrongPassword123", "new_password": "NewSecret456"},
    )
    assert response.status_code == 400
