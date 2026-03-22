"""add agents, agent_chats, agent_messages tables and review source

Revision ID: y1b2c3d4e5f6
Revises: x0a1b2c3d4e5
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa

revision = "y1b2c3d4e5f6"
down_revision = "x0a1b2c3d4e5"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False, default=""),
        sa.Column("connection_id", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("mcp_server_id", sa.String(), nullable=True),
        sa.Column("mcp_tool_filter", sa.JSON(), nullable=True),
        sa.Column("tools", sa.JSON(), nullable=False, default=[]),
        sa.Column("summarize_after", sa.Integer(), nullable=False, default=10),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_email", sa.String(), nullable=True),
    )
    op.create_table(
        "agent_chats",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("chat_id", sa.String(), sa.ForeignKey("agent_chats.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(), nullable=False),  # user | assistant | summary
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Add source + agent_chat_id to reviews
    op.add_column("reviews", sa.Column("source", sa.String(), nullable=False, server_default="playground"))
    op.add_column("reviews", sa.Column("agent_chat_id", sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column("reviews", "agent_chat_id")
    op.drop_column("reviews", "source")
    op.drop_table("agent_messages")
    op.drop_table("agent_chats")
    op.drop_table("agents")
