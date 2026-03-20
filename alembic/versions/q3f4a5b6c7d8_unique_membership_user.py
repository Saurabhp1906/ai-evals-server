"""add unique constraint on memberships.user_id

Revision ID: q3f4a5b6c7d8
Revises: p2e3f4a5b6c7
Create Date: 2026-03-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q3f4a5b6c7d8"
down_revision: Union[str, None] = "p2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove duplicate memberships for the same user_id, keeping the earliest one
    op.execute("""
        DELETE FROM memberships
        WHERE id NOT IN (
            SELECT DISTINCT ON (user_id) id
            FROM memberships
            ORDER BY user_id, created_at ASC
        )
    """)
    op.create_unique_constraint("uq_membership_user", "memberships", ["user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_membership_user", "memberships", type_="unique")
