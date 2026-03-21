"""add mcp_server_id to prompts

Revision ID: s5b6c7d8e9f0
Revises: r4a5b6c7d8e9
Create Date: 2026-03-20 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "s5b6c7d8e9f0"
down_revision: Union[str, None] = "r4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column(
            "mcp_server_id",
            sa.String(),
            sa.ForeignKey("mcp_servers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("prompts", "mcp_server_id")
