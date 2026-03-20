"""add prompt_id, dataset_id, scorer_id to playground_runs

Revision ID: p2e3f4a5b6c7
Revises: o1d2e3f4a5b6
Create Date: 2026-03-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'p2e3f4a5b6c7'
down_revision: Union[str, Sequence[str], None] = 'o1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('playground_runs', sa.Column('prompt_id', sa.String(), nullable=True))
    op.add_column('playground_runs', sa.Column('dataset_id', sa.String(), nullable=True))
    op.add_column('playground_runs', sa.Column('scorer_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('playground_runs', 'scorer_id')
    op.drop_column('playground_runs', 'dataset_id')
    op.drop_column('playground_runs', 'prompt_id')
