from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.family_member import FamilyMember
    from app.models.safe_place import SafePlace
    from app.models.journey import Journey
    from app.models.location_event import LocationEvent
    from app.models.geofence_event import GeofenceEvent
    from app.models.notification import Notification


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    family_members: Mapped[list["FamilyMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    safe_places: Mapped[list["SafePlace"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    journeys: Mapped[list["Journey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    location_events: Mapped[list["LocationEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    geofence_events: Mapped[list["GeofenceEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
