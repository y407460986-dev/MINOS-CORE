"""Project management for desktop application."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..app_state import DesktopProjectRecord, DesktopProjectState
from .sqlite_store import DesktopSQLiteStore, DEFAULT_DESKTOP_DB_PATH, _utc_now, _to_json
from .settings_store import DesktopSettingsStore


class DesktopProjectStore:
    """Manages project records stored in SQLite database."""

    def __init__(self, db_path: str | Path = DEFAULT_DESKTOP_DB_PATH) -> None:
        self._store = DesktopSQLiteStore(db_path)

    def create_project(self, state: DesktopProjectState) -> DesktopProjectRecord:
        """Create a new project."""
        now = _utc_now()
        output_dir = state.output_dir or DesktopSettingsStore(
            self._store.db_path
        ).get_default_output_dir()
        with self._store.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects
                    (project_name, drawing_path, output_dir, context_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    state.project_name,
                    state.drawing_path,
                    output_dir,
                    _to_json(state.context),
                    now,
                    now,
                ),
            )
            project_id = int(cursor.lastrowid)
        return self.get_project(project_id)

    def get_project(self, project_id: int) -> DesktopProjectRecord:
        """Get a project by ID."""
        with self._store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"desktop project not found: {project_id}")
        return _project_from_row(row)

    def update_project(
        self,
        project_id: int,
        *,
        project_name: str | None = None,
        drawing_path: str | None = None,
        output_dir: str | Path | None = None,
        context: dict[str, Any] | None = None,
    ) -> DesktopProjectRecord:
        """Update an existing project."""
        current = self.get_project(project_id)
        with self._store.connect() as connection:
            connection.execute(
                """
                UPDATE projects
                SET project_name = ?,
                    drawing_path = ?,
                    output_dir = ?,
                    context_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    current.project_name if project_name is None else project_name,
                    current.drawing_path if drawing_path is None else drawing_path,
                    current.output_dir if output_dir is None else str(Path(output_dir)),
                    _to_json(current.context if context is None else context),
                    _utc_now(),
                    project_id,
                ),
            )
        return self.get_project(project_id)


def _project_from_row(row: sqlite3.Row) -> DesktopProjectRecord:
    """Convert a database row to a project record."""
    return DesktopProjectRecord(
        id=int(row["id"]),
        project_name=str(row["project_name"]),
        drawing_path=str(row["drawing_path"]),
        output_dir=str(row["output_dir"]),
        context=_from_json_object(str(row["context_json"])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _from_json_object(value: str) -> dict[str, Any]:
    """Parse JSON string to dictionary."""
    data = json.loads(value or "{}")
    return data if isinstance(data, dict) else {}
