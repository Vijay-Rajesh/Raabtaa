from typing import Optional

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.core.config import settings
from app.core.logging import get_logger
from app.database.session import get_db
from app.models.whatsapp_message import WhatsAppMessage
from app.services.whatsapp_service import process_webhook_status_event
from app.utils.time import utcnow

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])
logger = get_logger(__name__)


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
) -> Response:
    """Meta webhook verification handshake."""
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified successfully.")
        return Response(content=hub_challenge or "", media_type="text/plain")

    logger.warning("WhatsApp webhook verification failed.")
    return Response(status_code=status.HTTP_403_FORBIDDEN)


@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    """Process WhatsApp delivery status events (sent/delivered/read/failed)."""
    body = await request.json()
    logger.info("WhatsApp webhook event received.")

    entries = body.get("entry", [])
    updates_applied = 0

    for entry in entries:
        parsed = process_webhook_status_event(entry)
        if parsed is None or not parsed.get("whatsapp_message_id"):
            continue

        result = await db.execute(
            select(WhatsAppMessage).where(
                WhatsAppMessage.whatsapp_message_id == parsed["whatsapp_message_id"]
            )
        )
        message = result.scalar_one_or_none()
        if message is None:
            continue

        message.status = parsed["status"] or message.status
        if parsed.get("error_message"):
            message.error_message = parsed["error_message"]

        now = utcnow()
        if parsed["status"] == "delivered":
            message.delivered_at = now
        elif parsed["status"] == "read":
            message.read_at = now

        updates_applied += 1

    if updates_applied:
        await db.commit()

    return {"status": "ok", "updates_applied": updates_applied}
