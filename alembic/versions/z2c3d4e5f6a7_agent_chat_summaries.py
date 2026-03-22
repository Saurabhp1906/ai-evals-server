"""add agent_chat_summaries table

Revision ID: z2c3d4e5f6a7
Revises: y1b2c3d4e5f6
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa

revision = "z2c3d4e5f6a7"
down_revision = "y1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_chat_summaries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("from_message_id", sa.String(), nullable=True),
        sa.Column("to_message_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["agent_chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_chat_summaries_chat_id", "agent_chat_summaries", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_chat_summaries_chat_id", table_name="agent_chat_summaries")
    op.drop_table("agent_chat_summaries")
