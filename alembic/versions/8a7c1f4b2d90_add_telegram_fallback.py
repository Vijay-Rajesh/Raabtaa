"""add Telegram fallback fields and delivery table

Revision ID: 8a7c1f4b2d90
Revises: 2ff9d6e36314
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8a7c1f4b2d90"
down_revision: Union[str, Sequence[str], None] = "2ff9d6e36314"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("family_members", sa.Column("telegram_chat_id", sa.String(length=255), nullable=True))
    op.add_column(
        "family_members",
        sa.Column("telegram_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "telegram_messages",
        sa.Column("notification_id", sa.UUID(), nullable=False),
        sa.Column("recipient_chat_id", sa.String(length=255), nullable=False),
        sa.Column("telegram_message_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("telegram_messages")
    op.drop_column("family_members", "telegram_enabled")
    op.drop_column("family_members", "telegram_chat_id")