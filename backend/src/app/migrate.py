"""Apply Alembic migrations from any working directory."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def upgrade_database() -> None:
    """Run `alembic upgrade head` against DATABASE_URL."""

    root = project_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("prepend_sys_path", str(root / "src"))
    command.upgrade(config, "head")
