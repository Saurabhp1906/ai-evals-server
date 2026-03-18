"""add email to memberships

Revision ID: 854fe2fcd1db
Revises: g3b4c5d6e7f8
Create Date: 2026-03-18 15:06:49.456167

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '854fe2fcd1db'
down_revision: Union[str, Sequence[str], None] = 'g3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('memberships', sa.Column('email', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('memberships', 'email')
