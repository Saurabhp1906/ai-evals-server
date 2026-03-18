"""playgrounds: saved configs and run history

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-03-17 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playgrounds",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("prompt_id", sa.String(), sa.ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scorer_id", sa.String(), sa.ForeignKey("scorers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prompt_connection_id", sa.String(), nullable=True),
        sa.Column("scorer_connection_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "playground_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("playground_id", sa.String(), sa.ForeignKey("playgrounds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "playground_run_rows",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("playground_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_id", sa.String(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("output", sa.Text(), nullable=False, server_default=""),
        sa.Column("score", sa.Text(), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("playground_run_rows")
    op.drop_table("playground_runs")
    op.drop_table("playgrounds")
