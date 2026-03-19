"""prompt use_responses_api

Revision ID: h4c5d6e7f8a9
Revises: 854fe2fcd1db
Create Date: 2026-03-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h4c5d6e7f8a9'
down_revision: Union[str, Sequence[str], None] = '854fe2fcd1db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('prompts', sa.Column('use_responses_api', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('prompts', 'use_responses_api')
