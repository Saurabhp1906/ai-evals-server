"""prompt: replace model with connection_id

Revision ID: a1c2d3e4f5b6
Revises: 3b09f7761cb6
Create Date: 2026-03-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c2d3e4f5b6'
down_revision: Union[str, Sequence[str], None] = '3b09f7761cb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("prompts", "model")
    op.add_column(
        "prompts",
        sa.Column("connection_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_prompts_connection_id",
        "prompts", "connections",
        ["connection_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_prompts_connection_id", "prompts", type_="foreignkey")
    op.drop_column("prompts", "connection_id")
    op.add_column(
        "prompts",
        sa.Column("model", sa.String(), nullable=False, server_default="claude-sonnet-4-6"),
    )
