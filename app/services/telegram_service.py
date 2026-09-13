"""Telegram Bot API integration used when WhatsApp delivery fails."""
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TelegramSendResult:
    success: bool
    telegram_message_id: Optional[str]
    status: str
    error_message: Optional[str]
    raw_response: Optional[dict[str, Any]] = None


async def send_message(recipient_chat_id: str, message: str) -> TelegramSendResult:
    if settings.TELEGRAM_MOCK_MODE:
        message_id = f"mock-{uuid.uuid4()}"
        logger.info("MOCK Telegram message sent to %s", recipient_chat_id)
        return TelegramSendResult(True, message_id, "sent", None, {"mock": True})

    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("Telegram bot token is not configured but mock mode is disabled.")
        return TelegramSendResult(False, None, "failed", "Telegram bot token is not configured.")

    url = f"{settings.TELEGRAM_API_BASE_URL.rstrip('/')}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json={"chat_id": recipient_chat_id, "text": message})
        data = response.json()
        if response.status_code >= 400 or not data.get("ok", False):
            error_message = data.get("description", "Unknown Telegram API error")
            logger.error("Telegram API error (status=%s): %s", response.status_code, error_message)
            return TelegramSendResult(False, None, "failed", error_message, data)

        message_id = str(data.get("result", {}).get("message_id"))
        return TelegramSendResult(True, message_id, "sent", None, data)
    except httpx.HTTPError as exc:
        logger.error("Telegram API request failed: %s", exc)
        return TelegramSendResult(False, None, "failed", "Telegram API request failed (network/timeout error).")