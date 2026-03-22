"""add plan limits: custom_limits on orgs + daily_usage table

Revision ID: aa1b2c3d4e5f
Revises: z2c3d4e5f6a7
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "aa1b2c3d4e5f"
down_revision = "z2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add custom_limits override column to organizations (enterprise per-org overrides)
    op.add_column("organizations", sa.Column("custom_limits", JSONB, nullable=True))

    # Daily usage tracking table for quota enforcement
    op.create_table(
        "daily_usage",
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("playground_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("agent_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scorer_evaluations", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org_id", "date"),
    )
    op.create_index("ix_daily_usage_org_id", "daily_usage", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_daily_usage_org_id", table_name="daily_usage")
    op.drop_table("daily_usage")
    op.drop_column("organizations", "custom_limits")
