"""remove openai_responses connection type

Revision ID: l8a9b0c1d2e3
Revises: k7f8a9b0c1d2
Create Date: 2026-03-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'l8a9b0c1d2e3'
down_revision: Union[str, Sequence[str], None] = 'k7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove any connections using the deprecated openai_responses type
    op.execute("DELETE FROM connections WHERE type::text = 'openai_responses'")


def downgrade() -> None:
    pass
