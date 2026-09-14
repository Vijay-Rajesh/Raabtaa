import uuid
from typing import Optional

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.whatsapp_message import WhatsAppMessage
from app.models.telegram_message import TelegramMessage
from app.services.telegram_service import TelegramSendResult, send_message as send_telegram_message
from app.services.whatsapp_service import WhatsAppSendResult, send_message
from app.utils.time import utcnow

logger = get_logger(__name__)
WELCOME_MESSAGE_TYPE = "welcome"


@dataclass
class NotificationDeliveryResult:
    channel: str
    status: str
    provider_message_id: Optional[str]
    error_message: Optional[str]


async def has_existing_arrival_notification(
    db: AsyncSession, user_id: uuid.UUID, journey_id: Optional[uuid.UUID]
) -> bool:
    """Rule 1: one arrival event should result in at most one arrival notification."""
    if journey_id is None:
        return False
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.journey_id == journey_id,
            Notification.notification_type == NotificationType.arrival.value,
        )
    )
    return result.scalar_one_or_none() is not None


async def get_eligible_family_member(
    db: AsyncSession, user_id: uuid.UUID, family_member_id: uuid.UUID
) -> Optional[FamilyMember]:
    """Return an active member with at least one configured delivery channel."""
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.id == family_member_id,
            FamilyMember.user_id == user_id,
            FamilyMember.is_active == True,  # noqa: E712
            or_(
                (FamilyMember.whatsapp_enabled == True),  # noqa: E712
                (FamilyMember.telegram_enabled == True) & FamilyMember.telegram_chat_id.is_not(None),
            ),
        )
    )
    return result.scalar_one_or_none()


async def get_default_family_member(db: AsyncSession, user_id: uuid.UUID) -> Optional[FamilyMember]:
    """Pick the first active family member with at least one delivery channel."""
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.user_id == user_id,
            FamilyMember.is_active == True,  # noqa: E712
            or_(
                (FamilyMember.whatsapp_enabled == True),  # noqa: E712
                (FamilyMember.telegram_enabled == True) & FamilyMember.telegram_chat_id.is_not(None),
            ),
        ).order_by(FamilyMember.created_at.asc())
    )
    return result.scalars().first()


async def create_notification_record(
    db: AsyncSession,
    user_id: uuid.UUID,
    family_member_id: uuid.UUID,
    journey_id: Optional[uuid.UUID],
    message: str,
    notification_type: str = NotificationType.arrival.value,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        family_member_id=family_member_id,
        journey_id=journey_id,
        notification_type=notification_type,
        message=message,
        status=NotificationStatus.pending.value,
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)
    return notification


async def ensure_welcome_message(
    db: AsyncSession,
    member: FamilyMember,
    owner_name: Optional[str] = None,
) -> WhatsAppSendResult:
    """Attempt the one-time WhatsApp welcome before other alerts are delivered."""
    if getattr(member, "welcome_message_sent_at", None) is not None:
        return WhatsAppSendResult(True, None, "sent", None)

    recipient_phone = getattr(member, "phone_number", None)
    if not recipient_phone:
        return WhatsAppSendResult(False, None, "failed", "Family member has no phone number.")

    member_name = getattr(member, "name", "there")
    workspace_owner = owner_name or "your family"
    welcome = await send_message(
        recipient_phone,
        (
            f"Welcome to SafeReach, {member_name}! "
            f"You are now connected to {workspace_owner}'s family safety workspace."
        ),
    )
    if welcome.success:
        member.welcome_message_sent_at = utcnow()
        await db.commit()
        logger.info(
            "Welcome WhatsApp sent before follow-up alerts for member=%s",
            getattr(member, "id", "unknown"),
        )
    else:
        logger.warning(
            "Welcome WhatsApp failed before follow-up alert for member=%s: %s",
            getattr(member, "id", "unknown"),
            welcome.error_message,
        )
    return welcome


async def dispatch_notification(
    db: AsyncSession,
    notification: Notification,
    recipient_phone: str,
) -> NotificationDeliveryResult:
    """Try WhatsApp first and fall back to Telegram when WhatsApp fails."""
    member = await db.get(FamilyMember, notification.family_member_id)
    if member is not None and getattr(notification, "notification_type", None) != WELCOME_MESSAGE_TYPE:
        await ensure_welcome_message(db, member)

    result: WhatsAppSendResult = await send_message(recipient_phone, notification.message)

    whatsapp_message = WhatsAppMessage(
        notification_id=notification.id,
        recipient_phone=recipient_phone,
        template_name=None,
        whatsapp_message_id=result.whatsapp_message_id,
        status=result.status,
        error_message=result.error_message,
        sent_at=utcnow() if result.success else None,
    )
    db.add(whatsapp_message)

    if result.success:
        notification.channel = "whatsapp"
        delivery = NotificationDeliveryResult(
            channel="whatsapp", status=result.status,
            provider_message_id=result.whatsapp_message_id, error_message=None,
        )
    else:
        telegram_result: Optional[TelegramSendResult] = None
        if member and member.telegram_enabled and member.telegram_chat_id:
            telegram_result = await send_telegram_message(member.telegram_chat_id, notification.message)
            telegram_message = TelegramMessage(
                notification_id=notification.id,
                recipient_chat_id=member.telegram_chat_id,
                telegram_message_id=telegram_result.telegram_message_id,
                status=telegram_result.status,
                error_message=telegram_result.error_message,
                sent_at=utcnow() if telegram_result.success else None,
            )
            db.add(telegram_message)

        if telegram_result and telegram_result.success:
            notification.channel = "telegram"
            delivery = NotificationDeliveryResult(
                channel="telegram", status=telegram_result.status,
                provider_message_id=telegram_result.telegram_message_id, error_message=None,
            )
        else:
            delivery = NotificationDeliveryResult(
                channel="whatsapp", status="failed",
                provider_message_id=None,
                error_message=(telegram_result.error_message if telegram_result else result.error_message),
            )

    notification.status = NotificationStatus.sent.value if delivery.status == "sent" else NotificationStatus.failed.value
    notification.sent_at = utcnow() if delivery.status == "sent" else None

    await db.commit()
    await db.refresh(whatsapp_message)
    await db.refresh(notification)

    logger.info(
        "%s notification %s: notification_id=%s recipient=%s",
        delivery.channel,
        "sent" if delivery.status == "sent" else "failed",
        notification.id,
        recipient_phone if delivery.channel == "whatsapp" else notification.family_member_id,
    )
    return delivery


async def dispatch_whatsapp_notification(
    db: AsyncSession,
    notification: Notification,
    recipient_phone: str,
) -> NotificationDeliveryResult:
    """Backward-compatible name for callers that dispatch arrival notifications."""
    return await dispatch_notification(db, notification, recipient_phone)
