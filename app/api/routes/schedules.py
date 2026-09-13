import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.family_member import FamilyMember
from app.models.safe_place import SafePlace
from app.models.tracking_schedule import TrackingSchedule
from app.models.user import User
from app.schemas.tracking_schedule import TrackingScheduleCreate, TrackingScheduleRead, TrackingScheduleUpdate

router = APIRouter(prefix="/api/v1/schedules", tags=["Tracking Schedules"])


async def _owned_schedule(schedule_id: uuid.UUID, user: User, db: AsyncSession) -> TrackingSchedule:
    result = await db.execute(select(TrackingSchedule).where(TrackingSchedule.id == schedule_id, TrackingSchedule.user_id == user.id))
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise HTTPException(status_code=404, detail="Tracking schedule not found")
    return schedule


async def _validate_setup(payload: TrackingScheduleCreate, user: User, db: AsyncSession) -> None:
    member = await db.execute(select(FamilyMember).where(FamilyMember.id == payload.family_member_id, FamilyMember.user_id == user.id, FamilyMember.is_active == True))  # noqa: E712
    places = await db.execute(select(SafePlace).where(SafePlace.user_id == user.id, SafePlace.id.in_([payload.origin_place_id, payload.destination_place_id]), SafePlace.is_active == True))  # noqa: E712
    if member.scalar_one_or_none() is None or len(list(places.scalars().all())) != 2:
        raise HTTPException(status_code=400, detail="Family member and both active places must belong to you")
    if payload.origin_place_id == payload.destination_place_id:
        raise HTTPException(status_code=400, detail="Origin and destination must be different")


@router.post("", response_model=TrackingScheduleRead, status_code=status.HTTP_201_CREATED)
async def create_schedule(payload: TrackingScheduleCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> TrackingSchedule:
    await _validate_setup(payload, current_user, db)
    schedule = TrackingSchedule(user_id=current_user.id, **payload.model_dump())
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.get("", response_model=list[TrackingScheduleRead])
async def list_schedules(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[TrackingSchedule]:
    result = await db.execute(select(TrackingSchedule).where(TrackingSchedule.user_id == current_user.id).order_by(TrackingSchedule.departure_time.asc()))
    return list(result.scalars().all())


@router.put("/{schedule_id}", response_model=TrackingScheduleRead)
async def update_schedule(schedule_id: uuid.UUID, payload: TrackingScheduleUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> TrackingSchedule:
    schedule = await _owned_schedule(schedule_id, current_user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(schedule_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    schedule = await _owned_schedule(schedule_id, current_user, db)
    await db.delete(schedule)
    await db.commit()