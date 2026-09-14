import uuid
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.database.session import get_db
from app.models.family_member import FamilyMember
from app.models.user import User
from app.schemas.family_member import FamilyMemberCreate, FamilyMemberRead, FamilyMemberUpdate
from app.services.whatsapp_service import send_message
from app.utils.time import utcnow

router = APIRouter(prefix="/api/v1/family", tags=["Family Members"])
logger = get_logger(__name__)


@router.post("/{family_member_id}/tracking-link")
async def create_tracking_link(
    family_member_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    member = await _get_owned_family_member(family_member_id, current_user, db)
    member.tracking_token = secrets.token_urlsafe(32)
    await db.commit()
    return {"tracking_token": member.tracking_token, "member_id": str(member.id)}


async def _get_owned_family_member(
    family_member_id: uuid.UUID, user: User, db: AsyncSession
) -> FamilyMember:
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.id == family_member_id, FamilyMember.user_id == user.id
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family member not found")
    return member


@router.post("", response_model=FamilyMemberRead, status_code=status.HTTP_201_CREATED)
async def create_family_member(
    payload: FamilyMemberCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FamilyMember:
    member = FamilyMember(
        user_id=current_user.id,
        name=payload.name,
        phone_number=payload.phone_number,
        telegram_chat_id=payload.telegram_chat_id,
        relationship_type=payload.relationship_type,
        whatsapp_enabled=payload.whatsapp_enabled,
        telegram_enabled=payload.telegram_enabled,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    if member.whatsapp_enabled and member.welcome_message_sent_at is None:
        welcome = await send_message(
            member.phone_number,
            f"Welcome to SafeReach, {member.name}! You are now connected to {current_user.full_name}'s family safety workspace.",
        )
        if welcome.success:
            member.welcome_message_sent_at = utcnow()
            await db.commit()
        else:
            logger.warning("Welcome WhatsApp failed for family member %s: %s", member.id, welcome.error_message)
    return member


@router.get("", response_model=list[FamilyMemberRead])
async def list_family_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FamilyMember]:
    result = await db.execute(select(FamilyMember).where(FamilyMember.user_id == current_user.id))
    return list(result.scalars().all())


@router.put("/{family_member_id}", response_model=FamilyMemberRead)
async def update_family_member(
    family_member_id: uuid.UUID,
    payload: FamilyMemberUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FamilyMember:
    member = await _get_owned_family_member(family_member_id, current_user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(member, field, value)
    await db.commit()
    await db.refresh(member)
    return member


@router.delete("/{family_member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_family_member(
    family_member_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    member = await _get_owned_family_member(family_member_id, current_user, db)
    await db.delete(member)
    await db.commit()
