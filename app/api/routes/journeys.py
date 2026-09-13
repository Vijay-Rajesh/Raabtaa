from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.journey import Journey
from app.models.user import User
from app.schemas.journey import JourneyRead

router = APIRouter(prefix="/api/v1/journeys", tags=["Journeys"])


@router.get("", response_model=list[JourneyRead])
async def list_journeys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Journey]:
    result = await db.execute(
        select(Journey).where(Journey.user_id == current_user.id).order_by(Journey.started_at.desc())
    )
    return list(result.scalars().all())
