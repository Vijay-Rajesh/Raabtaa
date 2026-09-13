import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.safe_place import SafePlace
from app.models.user import User
from app.schemas.safe_place import SafePlaceCreate, SafePlaceRead, SafePlaceUpdate

router = APIRouter(prefix="/api/v1/places", tags=["Safe Places"])


async def get_owned_place(place_id: uuid.UUID, user: User, db: AsyncSession) -> SafePlace:
    """Enforces Rule 3: a destination must belong to the authenticated user."""
    result = await db.execute(
        select(SafePlace).where(SafePlace.id == place_id, SafePlace.user_id == user.id)
    )
    place = result.scalar_one_or_none()
    if place is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Safe place not found")
    return place


@router.post("", response_model=SafePlaceRead, status_code=status.HTTP_201_CREATED)
async def create_place(
    payload: SafePlaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SafePlace:
    place = SafePlace(user_id=current_user.id, **payload.model_dump())
    db.add(place)
    await db.commit()
    await db.refresh(place)
    return place


@router.get("", response_model=list[SafePlaceRead])
async def list_places(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SafePlace]:
    result = await db.execute(select(SafePlace).where(SafePlace.user_id == current_user.id))
    return list(result.scalars().all())


@router.get("/{place_id}", response_model=SafePlaceRead)
async def get_place(
    place_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SafePlace:
    return await get_owned_place(place_id, current_user, db)


@router.put("/{place_id}", response_model=SafePlaceRead)
async def update_place(
    place_id: uuid.UUID,
    payload: SafePlaceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SafePlace:
    place = await get_owned_place(place_id, current_user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(place, field, value)
    await db.commit()
    await db.refresh(place)
    return place


@router.delete("/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_place(
    place_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    place = await get_owned_place(place_id, current_user, db)
    await db.delete(place)
    await db.commit()
