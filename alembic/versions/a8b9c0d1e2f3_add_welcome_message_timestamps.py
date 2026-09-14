"""track one-time welcome message delivery

Revision ID: a8b9c0d1e2f3
Revises: f7a1c2d3e4b5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "f7a1c2d3e4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("welcome_message_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "family_members",
        sa.Column("welcome_message_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("family_members", "welcome_message_sent_at")
    op.drop_column("users", "welcome_message_sent_at")
