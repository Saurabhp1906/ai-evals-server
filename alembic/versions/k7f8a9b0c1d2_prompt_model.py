"""prompt: add model column

Revision ID: k7f8a9b0c1d2
Revises: j6e7f8a9b0c1
Create Date: 2026-03-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'k7f8a9b0c1d2'
down_revision: Union[str, Sequence[str], None] = 'j6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column("model", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prompts", "model")
