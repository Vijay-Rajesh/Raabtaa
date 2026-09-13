import uuid
from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import UUIDPKMixin, utcnow

if TYPE_CHECKING:
    from app.models.family_member import FamilyMember
    from app.models.safe_place import SafePlace
    from app.models.user import User


class TrackingSchedule(UUIDPKMixin, Base):
    __tablename__ = "tracking_schedules"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    family_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False)
    origin_place_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("safe_places.id", ondelete="CASCADE"), nullable=False)
    destination_place_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("safe_places.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    days_of_week: Mapped[str] = mapped_column(String(32), nullable=False, default="0,1,2,3,4")
    departure_time: Mapped[time] = mapped_column(Time(), nullable=False)
    expected_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship()
    family_member: Mapped["FamilyMember"] = relationship()
    origin_place: Mapped["SafePlace"] = relationship(foreign_keys=[origin_place_id])
    destination_place: Mapped["SafePlace"] = relationship(foreign_keys=[destination_place_id])