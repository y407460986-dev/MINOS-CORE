"""Database configuration, connection, and SQLAlchemy async setup."""

from __future__ import annotations

import os
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


def platform_auth_required() -> bool:
    """Return whether platform API auth is mandatory.

    Authentication is required unless it is explicitly disabled with one of
    the supported false values. Treating missing, blank, and unknown values as
    required prevents an accidental configuration omission from exposing the
    platform API.
    """
    raw_value = os.getenv("MINOS_PLATFORM_AUTH_REQUIRED")
    if raw_value is None:
        return True

    value = raw_value.strip().lower()
    return value not in {"0", "false", "no", "off"}


def get_platform_api_token() -> str | None:
    """Return configured platform API token, treating blank values as missing."""
    token = os.getenv("MINOS_PLATFORM_API_TOKEN")
    if token is None:
        return None
    token = token.strip()
    return token or None
