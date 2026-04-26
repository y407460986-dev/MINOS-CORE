"""Database configuration, connection, and SQLAlchemy async setup."""

from __future__ import annotations

from pathlib import Path

DEFAULT_DB_PATH = Path("out/platform/minos_platform.sqlite3")
DEFAULT_ARTIFACTS_DIR = Path("out/platform/artifacts")


def get_db_url(db_path: Path | None = None) -> str:
    """Return an aiosqlite connection URL for the given DB path."""
    path = (db_path or DEFAULT_DB_PATH).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{path}"


def get_artifacts_dir(artifacts_dir: Path | None = None) -> Path:
    """Return the artifacts directory, creating it if needed."""
    d = (artifacts_dir or DEFAULT_ARTIFACTS_DIR).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d
