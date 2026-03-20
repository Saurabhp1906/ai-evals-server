"""prompts: drop prompt_string column (now lives in prompt_versions only)

Revision ID: m9b0c1d2e3f4
Revises: l8a9b0c1d2e3
Create Date: 2026-03-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'm9b0c1d2e3f4'
down_revision: Union[str, Sequence[str], None] = 'l8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("prompts", "prompt_string")


def downgrade() -> None:
    op.add_column("prompts", sa.Column("prompt_string", sa.Text(), nullable=False, server_default=""))
