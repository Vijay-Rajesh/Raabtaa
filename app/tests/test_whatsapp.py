from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import whatsapp_service


@pytest.mark.asyncio
async def test_mock_send_success(monkeypatch):
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_MOCK_MODE", True)
    result = await whatsapp_service.send_message("+923001234567", "✅ Ali has safely arrived at College at 8:20 AM.")
    assert result.success is True
    assert result.status == "sent"
    assert result.whatsapp_message_id.startswith("mock-")


@pytest.mark.asyncio
async def test_real_api_failure_is_handled_gracefully(monkeypatch):
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_MOCK_MODE", False)
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_ACCESS_TOKEN", "fake-token")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_PHONE_NUMBER_ID", "123456")

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": {"message": "Invalid recipient phone number"}}

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
        result = await whatsapp_service.send_message("+92-not-a-number", "Test message")

    assert result.success is False
    assert result.status == "failed"
    assert "Invalid recipient" in result.error_message


@pytest.mark.asyncio
async def test_network_error_does_not_crash(monkeypatch):
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_MOCK_MODE", False)
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_ACCESS_TOKEN", "fake-token")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_PHONE_NUMBER_ID", "123456")

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))):
        result = await whatsapp_service.send_message("+923001234567", "Test message")

    assert result.success is False
    assert result.status == "failed"
    assert result.error_message is not None


@pytest.mark.asyncio
async def test_missing_credentials_fails_cleanly(monkeypatch):
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_MOCK_MODE", False)
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_ACCESS_TOKEN", None)
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_PHONE_NUMBER_ID", None)

    result = await whatsapp_service.send_message("+923001234567", "Test message")
    assert result.success is False
    assert "not configured" in result.error_message


def test_webhook_status_update_parsing():
    entry = {
        "changes": [
            {
                "value": {
                    "statuses": [
                        {"id": "wamid.ABC123", "status": "delivered"}
                    ]
                }
            }
        ]
    }
    parsed = whatsapp_service.process_webhook_status_event(entry)
    assert parsed is not None
    assert parsed["whatsapp_message_id"] == "wamid.ABC123"
    assert parsed["status"] == "delivered"


def test_webhook_status_update_with_error():
    entry = {
        "changes": [
            {
                "value": {
                    "statuses": [
                        {
                            "id": "wamid.XYZ999",
                            "status": "failed",
                            "errors": [{"title": "Recipient not on WhatsApp"}],
                        }
                    ]
                }
            }
        ]
    }
    parsed = whatsapp_service.process_webhook_status_event(entry)
    assert parsed["status"] == "failed"
    assert parsed["error_message"] == "Recipient not on WhatsApp"


def test_webhook_entry_with_no_statuses_returns_none():
    entry = {"changes": [{"value": {"messages": []}}]}
    assert whatsapp_service.process_webhook_status_event(entry) is None
