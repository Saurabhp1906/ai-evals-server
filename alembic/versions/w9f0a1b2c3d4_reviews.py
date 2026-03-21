"""add reviews and review_rows tables

Revision ID: w9f0a1b2c3d4
Revises: v8e9f0a1b2c3
Create Date: 2026-03-21

"""
from alembic import op
import sqlalchemy as sa

revision = "w9f0a1b2c3d4"
down_revision = "v8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("playground_id", sa.String(), nullable=True),
        sa.Column("playground_name", sa.String(), nullable=True),
        sa.Column("run_label", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "review_rows",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("review_id", sa.String(), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False, default=""),
        sa.Column("score", sa.Text(), nullable=False, default=""),
        sa.Column("row_comment", sa.Text(), nullable=False, default=""),
        sa.Column("annotation", sa.Text(), nullable=True),
        sa.Column("rating", sa.String(), nullable=True),  # good | bad | neutral
        sa.Column("expected_behavior", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("review_rows")
    op.drop_table("reviews")
