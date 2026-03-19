"""scorer connection_id

Revision ID: i5d6e7f8a9b0
Revises: h4c5d6e7f8a9
Create Date: 2026-03-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i5d6e7f8a9b0'
down_revision: Union[str, Sequence[str], None] = 'h4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('scorers', sa.Column('connection_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_scorers_connection_id',
        'scorers', 'connections',
        ['connection_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_scorers_connection_id', 'scorers', type_='foreignkey')
    op.drop_column('scorers', 'connection_id')
