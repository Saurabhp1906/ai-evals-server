"""agent_message_tool_calls

Revision ID: a3d4e5f6b7c8
Revises: z2c3d4e5f6a7
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa

revision = 'a3d4e5f6b7c8'
down_revision = 'aa1b2c3d4e5f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('agent_messages', sa.Column('tool_calls', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('agent_messages', 'tool_calls')
