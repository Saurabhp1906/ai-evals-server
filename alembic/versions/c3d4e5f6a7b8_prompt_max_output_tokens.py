"""prompt: add max_output_tokens column

Revision ID: c3d4e5f6a7b8
Revises: a1c2d3e4f5b6
Create Date: 2026-03-17 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'a1c2d3e4f5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prompts", "max_output_tokens")
