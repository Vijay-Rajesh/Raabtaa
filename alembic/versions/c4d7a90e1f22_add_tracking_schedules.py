"""add recurring tracking schedules

Revision ID: c4d7a90e1f22
Revises: b91e4f7c3a21
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c4d7a90e1f22"
down_revision: Union[str, Sequence[str], None] = "b91e4f7c3a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tracking_schedules",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("family_member_id", sa.UUID(), nullable=False),
        sa.Column("origin_place_id", sa.UUID(), nullable=False),
        sa.Column("destination_place_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("days_of_week", sa.String(length=32), nullable=False),
        sa.Column("departure_time", sa.Time(), nullable=False),
        sa.Column("expected_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["family_member_id"], ["family_members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["origin_place_id"], ["safe_places.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["destination_place_id"], ["safe_places.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tracking_schedules_user_id", "tracking_schedules", ["user_id"], unique=False)
    op.add_column("journeys", sa.Column("family_member_id", sa.UUID(), nullable=True))
    op.add_column("journeys", sa.Column("schedule_id", sa.UUID(), nullable=True))
    op.create_index("ix_journeys_family_member_id", "journeys", ["family_member_id"], unique=False)
    op.create_foreign_key("fk_journeys_family_member_id", "journeys", "family_members", ["family_member_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_journeys_schedule_id", "journeys", "tracking_schedules", ["schedule_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_journeys_schedule_id", "journeys", type_="foreignkey")
    op.drop_constraint("fk_journeys_family_member_id", "journeys", type_="foreignkey")
    op.drop_index("ix_journeys_family_member_id", table_name="journeys")
    op.drop_column("journeys", "schedule_id")
    op.drop_column("journeys", "family_member_id")
    op.drop_index("ix_tracking_schedules_user_id", table_name="tracking_schedules")
    op.drop_table("tracking_schedules")