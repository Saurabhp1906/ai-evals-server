import os
from pathlib import Path
from alembic.config import Config
from alembic import command


def run_migrations() -> None:
    print("Running database migrations...")
    # Try repo-relative path first (local dev), fall back to cwd (Railway: /app)
    local_alembic = Path(__file__).resolve().parents[3] / "alembic"
    cwd_alembic = Path(os.getcwd()) / "alembic"
    script_location = str(local_alembic if local_alembic.exists() else cwd_alembic)

    config = Config()
    config.set_main_option("script_location", script_location)
    config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(config, "head")
