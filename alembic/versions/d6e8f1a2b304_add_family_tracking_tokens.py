"""add family tracking consent tokens

Revision ID: d6e8f1a2b304
Revises: c4d7a90e1f22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d6e8f1a2b304"
down_revision: Union[str, Sequence[str], None] = "c4d7a90e1f22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("family_members", sa.Column("tracking_token", sa.String(length=64), nullable=True))
    op.create_index("ix_family_members_tracking_token", "family_members", ["tracking_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_family_members_tracking_token", table_name="family_members")
    op.drop_column("family_members", "tracking_token")