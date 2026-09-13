"""associate geofence events with family members

Revision ID: f7a1c2d3e4b5
Revises: d6e8f1a2b304
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7a1c2d3e4b5"
down_revision: Union[str, Sequence[str], None] = "d6e8f1a2b304"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("geofence_events", sa.Column("family_member_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_geofence_events_family_member_id",
        "geofence_events",
        ["family_member_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_geofence_events_family_member_id",
        "geofence_events",
        "family_members",
        ["family_member_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_geofence_events_family_member_id",
        "geofence_events",
        type_="foreignkey",
    )
    op.drop_index("ix_geofence_events_family_member_id", table_name="geofence_events")
    op.drop_column("geofence_events", "family_member_id")