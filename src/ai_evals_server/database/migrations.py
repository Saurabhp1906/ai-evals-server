from pathlib import Path
from alembic.config import Config
from alembic import command


def run_migrations() -> None:
    print("Running database migrations...")
    alembic_cfg = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
