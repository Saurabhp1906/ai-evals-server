"""agent use_responses_api column

Revision ID: b4e5f6a7c8d9
Revises: a3d4e5f6b7c8
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa

revision = 'b4e5f6a7c8d9'
down_revision = 'a3d4e5f6b7c8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('agents', sa.Column('use_responses_api', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('agents', 'use_responses_api')
