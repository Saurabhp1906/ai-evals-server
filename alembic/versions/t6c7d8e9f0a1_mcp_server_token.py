"""add token to mcp_servers

Revision ID: t6c7d8e9f0a1
Revises: s5b6c7d8e9f0
Create Date: 2026-03-20 00:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "t6c7d8e9f0a1"
down_revision: Union[str, None] = "s5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mcp_servers", sa.Column("token", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("mcp_servers", "token")
