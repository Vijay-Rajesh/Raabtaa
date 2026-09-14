import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.database.session import get_db
from app.models.journey import Journey
from app.models.notification import Notification
from app.models.user import User
from app.schemas.admin import (
    AdminLoginRequest,
    AdminStats,
    AdminStatus,
    AdminUserCreate,
    AdminUserRead,
    AdminUserUpdate,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@router.post("/auth/login")
async def admin_login(payload: AdminLoginRequest, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    result = await db.execute(select(User).where(User.username == payload.username, User.is_admin == True))  # noqa: E712
    admin = result.scalar_one_or_none()
    if admin is None and settings.ADMIN_USERNAME and settings.ADMIN_PASSWORD:
        if payload.username == settings.ADMIN_USERNAME and payload.password == settings.ADMIN_PASSWORD:
            admin = User(
                username=settings.ADMIN_USERNAME,
                full_name="SafeReach Administrator",
                email=f"{settings.ADMIN_USERNAME}@admin.local",
                phone_number="+0000000000",
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                is_admin=True,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid administrator credentials")
    if not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator account is inactive")
    return {"access_token": create_access_token(str(admin.id), claims={"role": "admin"})}


@router.get("/me", response_model=AdminUserRead)
async def admin_me(current_admin: User = Depends(get_current_admin)) -> User:
    return current_admin


@router.get("/stats", response_model=AdminStats)
async def admin_stats(current_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> AdminStats:
    users = await db.scalar(select(func.count(User.id))) or 0
    active_users = await db.scalar(select(func.count(User.id)).where(User.is_active == True)) or 0  # noqa: E712
    journeys = await db.scalar(select(func.count(Journey.id))) or 0
    notifications = await db.scalar(select(func.count(Notification.id))) or 0
    sent = await db.scalar(select(func.count(Notification.id)).where(Notification.status == "sent")) or 0
    failed = await db.scalar(select(func.count(Notification.id)).where(Notification.status == "failed")) or 0
    return AdminStats(users=users, active_users=active_users, journeys=journeys, notifications=notifications, sent_notifications=sent, failed_notifications=failed)


@router.get("/status", response_model=AdminStatus)
async def admin_status(current_admin: User = Depends(get_current_admin)) -> AdminStatus:
    return AdminStatus(
        whatsapp="mock" if settings.WHATSAPP_MOCK_MODE else ("configured" if settings.WHATSAPP_ACCESS_TOKEN else "not_configured"),
        telegram="mock" if settings.TELEGRAM_MOCK_MODE else ("configured" if settings.TELEGRAM_BOT_TOKEN else "not_configured"),
        environment=settings.ENVIRONMENT,
        mock_mode=settings.WHATSAPP_MOCK_MODE,
    )


@router.get("/users", response_model=list[AdminUserRead])
async def list_users(current_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


@router.post("/users", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: AdminUserCreate, current_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> User:
    existing = await db.execute(select(User).where((User.email == payload.email) | (User.username == payload.username)))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email or username already exists")
    user = User(**payload.model_dump(exclude={"password"}), password_hash=hash_password(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=AdminUserRead)
async def update_user(user_id: uuid.UUID, payload: AdminUserUpdate, current_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_admin.id and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own account")
    values = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "email" in values:
        values["email"] = values["email"].strip().lower()
        existing = await db.scalar(select(User).where(User.email == values["email"], User.id != user.id))
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    if "username" in values:
        values["username"] = values["username"].strip()
        existing = await db.scalar(select(User).where(User.username == values["username"], User.id != user.id))
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    if "password" in values:
        user.password_hash = hash_password(values.pop("password"))
    for field, value in values.items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: uuid.UUID, current_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> None:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account")
    await db.delete(user)
    await db.commit()
