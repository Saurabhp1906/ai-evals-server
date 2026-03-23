"""prompt response_format column

Revision ID: c5f6a7b8d9e0
Revises: b4e5f6a7c8d9
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

revision = 'c5f6a7b8d9e0'
down_revision = 'b4e5f6a7c8d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('prompts', sa.Column('response_format', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('prompts', 'response_format')
