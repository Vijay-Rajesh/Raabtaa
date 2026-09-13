import uuid

import pytest


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
async def test_protected_endpoint_requires_auth(app_client):
    resp = await app_client.get("/api/v1/auth/me")
    assert resp.status_code == 401
