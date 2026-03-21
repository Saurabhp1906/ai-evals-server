"""add prompt_string to review_rows

Revision ID: x0a1b2c3d4e5
Revises: w9f0a1b2c3d4
Create Date: 2026-03-21

"""
from alembic import op
import sqlalchemy as sa

revision = "x0a1b2c3d4e5"
down_revision = "w9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("review_rows", sa.Column("prompt_string", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("review_rows", "prompt_string")
