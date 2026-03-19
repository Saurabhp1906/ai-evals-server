"""prompt_versions scorer_threshold playground_run_version

Revision ID: j6e7f8a9b0c1
Revises: i5d6e7f8a9b0
Create Date: 2026-03-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j6e7f8a9b0c1'
down_revision: Union[str, Sequence[str], None] = 'i5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add pass_threshold to scorers
    op.add_column('scorers', sa.Column('pass_threshold', sa.Integer(), nullable=False, server_default='7'))

    # Add prompt_version fields to playground_runs
    op.add_column('playground_runs', sa.Column('prompt_version_id', sa.String(), nullable=True))
    op.add_column('playground_runs', sa.Column('prompt_version_number', sa.Integer(), nullable=True))

    # Create prompt_versions table
    op.create_table(
        'prompt_versions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('prompt_id', sa.String(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('prompt_string', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['prompt_id'], ['prompts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_prompt_versions_prompt_id', 'prompt_versions', ['prompt_id'])


def downgrade() -> None:
    op.drop_index('ix_prompt_versions_prompt_id', table_name='prompt_versions')
    op.drop_table('prompt_versions')
    op.drop_column('playground_runs', 'prompt_version_number')
    op.drop_column('playground_runs', 'prompt_version_id')
    op.drop_column('scorers', 'pass_threshold')
