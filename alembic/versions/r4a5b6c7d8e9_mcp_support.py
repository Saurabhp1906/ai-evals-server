"""add mcp_servers table, mcp_server_id to playgrounds, tool_calls to playground_run_rows

Revision ID: r4a5b6c7d8e9
Revises: q3f4a5b6c7d8
Create Date: 2026-03-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision: str = "r4a5b6c7d8e9"
down_revision: Union[str, None] = "q3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("playgrounds", sa.Column("mcp_server_id", sa.String(), sa.ForeignKey("mcp_servers.id", ondelete="SET NULL"), nullable=True))
    op.add_column("playground_run_rows", sa.Column("tool_calls", JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("playground_run_rows", "tool_calls")
    op.drop_column("playgrounds", "mcp_server_id")
    op.drop_table("mcp_servers")
