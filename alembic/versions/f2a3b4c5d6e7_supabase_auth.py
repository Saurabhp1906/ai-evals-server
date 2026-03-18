"""migrate to supabase auth: drop users table and fk constraints

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-03-18 00:00:00.000000

"""
from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop FK constraints that pointed to the local users table.
    # user_id columns stay in place (now plain strings = Supabase auth.users UUIDs).
    for table in ("connections", "prompts", "datasets", "scorers", "playgrounds"):
        op.drop_constraint(f"fk_{table}_user_id", table, type_="foreignkey")

    # Drop the local users table — auth is now managed by Supabase
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")


def downgrade() -> None:
    import sqlalchemy as sa

    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    for table in ("connections", "prompts", "datasets", "scorers", "playgrounds"):
        op.create_foreign_key(
            f"fk_{table}_user_id",
            table, "users",
            ["user_id"], ["id"],
            ondelete="CASCADE",
        )
