"""initial

Revision ID: 3b09f7761cb6
Revises: 
Create Date: 2026-03-17 11:14:50.686770

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum


# revision identifiers, used by Alembic.
revision: str = '3b09f7761cb6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE connection_type AS ENUM ('claude', 'openai', 'azure_openai');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.create_table(
        "connections",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "type",
            PgEnum("claude", "openai", "azure_openai", name="connection_type", create_type=False),
            nullable=False,
        ),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("azure_endpoint", sa.Text(), nullable=True),
        sa.Column("azure_deployment", sa.Text(), nullable=True),
        sa.Column("azure_api_version", sa.String(), nullable=False, server_default="2024-02-01"),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "prompts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("prompt_string", sa.Text(), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("model", sa.String(), nullable=False, server_default="claude-sonnet-4-6"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "datasets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "dataset_rows",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dataset_rows_dataset_id", "dataset_rows", ["dataset_id"])

    op.create_table(
        "scorers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("prompt_string", sa.Text(), nullable=False),
        sa.Column("model", sa.String(), nullable=False, server_default="claude-sonnet-4-6"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_rows_dataset_id", table_name="dataset_rows")
    op.drop_table("scorers")
    op.drop_table("dataset_rows")
    op.drop_table("datasets")
    op.drop_table("prompts")
    op.drop_table("connections")
    op.execute("DROP TYPE connection_type")
