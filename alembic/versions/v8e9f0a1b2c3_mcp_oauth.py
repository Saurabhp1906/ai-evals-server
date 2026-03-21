"""add oauth fields to mcp_servers

Revision ID: v8e9f0a1b2c3
Revises: u7d8e9f0a1b2
Create Date: 2026-03-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "v8e9f0a1b2c3"
down_revision: Union[str, None] = "u7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mcp_servers", sa.Column("oauth_client_id", sa.Text(), nullable=True))
    op.add_column("mcp_servers", sa.Column("oauth_client_secret", sa.Text(), nullable=True))
    op.add_column("mcp_servers", sa.Column("oauth_access_token", sa.Text(), nullable=True))
    op.add_column("mcp_servers", sa.Column("oauth_refresh_token", sa.Text(), nullable=True))
    op.add_column("mcp_servers", sa.Column("oauth_token_expiry", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("mcp_servers", "oauth_token_expiry")
    op.drop_column("mcp_servers", "oauth_refresh_token")
    op.drop_column("mcp_servers", "oauth_access_token")
    op.drop_column("mcp_servers", "oauth_client_secret")
    op.drop_column("mcp_servers", "oauth_client_id")
