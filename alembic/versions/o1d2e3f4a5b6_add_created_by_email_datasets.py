"""add created_by_email to datasets

Revision ID: o1d2e3f4a5b6
Revises: n0c1d2e3f4a5
Create Date: 2026-03-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'o1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'n0c1d2e3f4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('datasets', sa.Column('created_by_email', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('datasets', 'created_by_email')
