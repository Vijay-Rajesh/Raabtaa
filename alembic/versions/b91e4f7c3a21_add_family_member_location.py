"""associate location events with family members

Revision ID: b91e4f7c3a21
Revises: 8a7c1f4b2d90
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b91e4f7c3a21"
down_revision: Union[str, Sequence[str], None] = "8a7c1f4b2d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("location_events", sa.Column("family_member_id", sa.UUID(), nullable=True))
    op.create_index("ix_location_events_family_member_id", "location_events", ["family_member_id"], unique=False)
    op.create_foreign_key("fk_location_events_family_member_id", "location_events", "family_members", ["family_member_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_location_events_family_member_id", "location_events", type_="foreignkey")
    op.drop_index("ix_location_events_family_member_id", table_name="location_events")
    op.drop_column("location_events", "family_member_id")