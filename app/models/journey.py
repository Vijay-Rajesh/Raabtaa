import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import UUIDPKMixin, utcnow

if TYPE_CHECKING:
    from app.models.user import User


class JourneyStatus(str, enum.Enum):
    planned = "planned"
    active = "active"
    arrived = "arrived"
    cancelled = "cancelled"
    delayed = "delayed"


class Journey(UUIDPKMixin, Base):
    __tablename__ = "journeys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="SET NULL"), nullable=True, index=True
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracking_schedules.id", ondelete="SET NULL"), nullable=True
    )
    origin_place_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("safe_places.id", ondelete="SET NULL"), nullable=True
    )
    destination_place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("safe_places.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    expected_arrival_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_arrival_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=JourneyStatus.active.value)

    user: Mapped["User"] = relationship(back_populates="journeys")
