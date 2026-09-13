from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import notification_service
from app.services.telegram_service import TelegramSendResult
from app.services.whatsapp_service import WhatsAppSendResult


@pytest.mark.asyncio
async def test_telegram_is_used_when_whatsapp_fails():
    db = MagicMock()
    db.get = AsyncMock(return_value=SimpleNamespace(
        telegram_enabled=True,
        telegram_chat_id="123456789",
    ))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    notification = SimpleNamespace(
        id="notification-id",
        family_member_id="family-member-id",
        message="Ali has arrived safely.",
        status="pending",
        channel="whatsapp",
        sent_at=None,
    )

    whatsapp_result = WhatsAppSendResult(False, None, "failed", "WhatsApp unavailable")
    telegram_result = TelegramSendResult(True, "telegram-42", "sent", None)

    original_whatsapp = notification_service.send_message
    original_telegram = notification_service.send_telegram_message
    notification_service.send_message = AsyncMock(return_value=whatsapp_result)
    notification_service.send_telegram_message = AsyncMock(return_value=telegram_result)
    try:
        result = await notification_service.dispatch_notification(db, notification, "+923001234567")
    finally:
        notification_service.send_message = original_whatsapp
        notification_service.send_telegram_message = original_telegram

    assert result.channel == "telegram"
    assert result.status == "sent"
    assert result.provider_message_id == "telegram-42"
    assert notification.channel == "telegram"
    assert notification.status == "sent"
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_failed_whatsapp_stays_failed_without_telegram_chat_id():
    db = MagicMock()
    db.get = AsyncMock(return_value=SimpleNamespace(telegram_enabled=True, telegram_chat_id=None))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    notification = SimpleNamespace(
        id="notification-id",
        family_member_id="family-member-id",
        message="Ali has arrived safely.",
        status="pending",
        channel="whatsapp",
        sent_at=None,
    )

    original_whatsapp = notification_service.send_message
    notification_service.send_message = AsyncMock(
        return_value=WhatsAppSendResult(False, None, "failed", "WhatsApp unavailable")
    )
    try:
        result = await notification_service.dispatch_notification(db, notification, "+923001234567")
    finally:
        notification_service.send_message = original_whatsapp

    assert result.channel == "whatsapp"
    assert result.status == "failed"
    assert notification.status == "failed"
