"""
Meta WhatsApp Cloud API integration.

All Meta-specific HTTP/API code lives here. The rest of the application talks
to `send_message` / `send_template_message` and never touches Meta's API
shape directly, so this module can be swapped out without changing callers.
"""
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

GRAPH_BASE_URL = "https://graph.facebook.com"


@dataclass
class WhatsAppSendResult:
    success: bool
    whatsapp_message_id: Optional[str]
    status: str  # "sent" | "failed"
    error_message: Optional[str]
    raw_response: Optional[dict[str, Any]] = None


def _mock_send(recipient_phone: str, message: str, template_name: Optional[str] = None) -> WhatsAppSendResult:
    fake_id = f"mock-{uuid.uuid4()}"
    print(f"\nMOCK WHATSAPP SENT\nTo: {recipient_phone}\n\n{message}\n")
    logger.info("MOCK WhatsApp message sent to %s", recipient_phone)
    return WhatsAppSendResult(
        success=True,
        whatsapp_message_id=fake_id,
        status="sent",
        error_message=None,
        raw_response={"mock": True},
    )


async def send_message(recipient_phone: str, message: str) -> WhatsAppSendResult:
    """Send a free-form text WhatsApp message (session-based conversation)."""
    if settings.WHATSAPP_MOCK_MODE:
        return _mock_send(recipient_phone, message)

    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        logger.error("WhatsApp credentials are not configured but mock mode is disabled.")
        return WhatsAppSendResult(
            success=False,
            whatsapp_message_id=None,
            status="failed",
            error_message="WhatsApp credentials are not configured.",
        )

    url = f"{GRAPH_BASE_URL}/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_phone,
        "type": "text",
        "text": {"body": message},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        data = response.json()

        if response.status_code >= 400:
            error_message = data.get("error", {}).get("message", "Unknown WhatsApp API error")
            logger.error("WhatsApp API error (status=%s): %s", response.status_code, error_message)
            return WhatsAppSendResult(
                success=False, whatsapp_message_id=None, status="failed",
                error_message=error_message, raw_response=data,
            )

        message_id = data.get("messages", [{}])[0].get("id")
        return WhatsAppSendResult(
            success=True, whatsapp_message_id=message_id, status="sent",
            error_message=None, raw_response=data,
        )
    except httpx.HTTPError as exc:
        logger.error("WhatsApp API request failed: %s", exc)
        return WhatsAppSendResult(
            success=False, whatsapp_message_id=None, status="failed",
            error_message="WhatsApp API request failed (network/timeout error).",
        )


async def send_template_message(
    recipient_phone: str,
    template_name: str,
    language_code: str,
    parameters: list[str],
    rendered_message_for_mock: Optional[str] = None,
) -> WhatsAppSendResult:
    """Send an approved WhatsApp template message (required outside 24h session window)."""
    if settings.WHATSAPP_MOCK_MODE:
        return _mock_send(
            recipient_phone,
            rendered_message_for_mock or f"[template:{template_name}] params={parameters}",
            template_name=template_name,
        )

    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        logger.error("WhatsApp credentials are not configured but mock mode is disabled.")
        return WhatsAppSendResult(
            success=False, whatsapp_message_id=None, status="failed",
            error_message="WhatsApp credentials are not configured.",
        )

    url = f"{GRAPH_BASE_URL}/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in parameters],
                }
            ],
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        data = response.json()

        if response.status_code >= 400:
            error_message = data.get("error", {}).get("message", "Unknown WhatsApp API error")
            logger.error("WhatsApp template API error (status=%s): %s", response.status_code, error_message)
            return WhatsAppSendResult(
                success=False, whatsapp_message_id=None, status="failed",
                error_message=error_message, raw_response=data,
            )

        message_id = data.get("messages", [{}])[0].get("id")
        return WhatsAppSendResult(
            success=True, whatsapp_message_id=message_id, status="sent",
            error_message=None, raw_response=data,
        )
    except httpx.HTTPError as exc:
        logger.error("WhatsApp template API request failed: %s", exc)
        return WhatsAppSendResult(
            success=False, whatsapp_message_id=None, status="failed",
            error_message="WhatsApp API request failed (network/timeout error).",
        )


def process_webhook_status_event(entry: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Parse a single WhatsApp status webhook entry into a normalized dict:
    {"whatsapp_message_id": ..., "status": "sent"|"delivered"|"read"|"failed", "error_message": ...}
    Returns None if the entry doesn't represent a status update we care about.
    """
    try:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            statuses = value.get("statuses", [])
            for status_update in statuses:
                return {
                    "whatsapp_message_id": status_update.get("id"),
                    "status": status_update.get("status"),
                    "error_message": (
                        status_update.get("errors", [{}])[0].get("title")
                        if status_update.get("errors")
                        else None
                    ),
                }
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("Failed to parse WhatsApp webhook entry: %s", exc)
    return None
