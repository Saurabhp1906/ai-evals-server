"""add created_by_email to prompts, scorers, playgrounds

Revision ID: n0c1d2e3f4a5
Revises: m9b0c1d2e3f4
Create Date: 2026-03-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'n0c1d2e3f4a5'
down_revision: Union[str, Sequence[str], None] = 'm9b0c1d2e3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('prompts', sa.Column('created_by_email', sa.String(), nullable=True))
    op.add_column('scorers', sa.Column('created_by_email', sa.String(), nullable=True))
    op.add_column('playgrounds', sa.Column('created_by_email', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('playgrounds', 'created_by_email')
    op.drop_column('scorers', 'created_by_email')
    op.drop_column('prompts', 'created_by_email')
