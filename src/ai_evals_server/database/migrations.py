import os
from pathlib import Path
from alembic.config import Config
from alembic import command

# Resolve repo root relative to this file: database/migrations.py → database → ai_evals_server → src → root
_ROOT_DIR = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = str(_ROOT_DIR / "alembic.ini")


def run_migrations() -> None:
    print("Running database migrations...")
    config = Config(_ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(config, "head")
