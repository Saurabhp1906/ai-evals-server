"""add mcp_tool_filter to prompts and playgrounds

Revision ID: u7d8e9f0a1b2
Revises: t6c7d8e9f0a1
Create Date: 2026-03-20 00:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision: str = "u7d8e9f0a1b2"
down_revision: Union[str, None] = "t6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prompts", sa.Column("mcp_tool_filter", JSON(), nullable=True))
    op.add_column("playgrounds", sa.Column("mcp_tool_filter", JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("playgrounds", "mcp_tool_filter")
    op.drop_column("prompts", "mcp_tool_filter")
