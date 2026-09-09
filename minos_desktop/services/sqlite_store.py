"""SQLite database connection and migration management."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minos_core._paths import user_data_dir
from minos_core.knowledge_recommendation import DEFAULT_KNOWLEDGE_RULES

DEFAULT_DESKTOP_DB_PATH = user_data_dir() / "minos_desktop.sqlite3"
CURRENT_SCHEMA_VERSION = 2


class DesktopSQLiteStore:
    """Manages SQLite database connection and schema migrations."""

    def __init__(self, db_path: str | Path = DEFAULT_DESKTOP_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections with automatic commit/rollback."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _migrate(self) -> None:
        """Initialize database schema and seed default data."""
        with self.connect() as connection:
            self._ensure_schema_version_table(connection)
            current_version = self._current_schema_version(connection)
            if current_version > CURRENT_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Desktop database schema version {current_version} is newer than "
                    f"supported version {CURRENT_SCHEMA_VERSION}"
                )
            if current_version < 1:
                self._migrate_to_v1(connection)
            if current_version == 1:
                self._backup_schema_v1(connection)
            if current_version < 2:
                self._migrate_to_v2(connection)
            self._set_schema_version(connection, CURRENT_SCHEMA_VERSION)
            _seed_knowledge_rules(connection)

    def _ensure_schema_version_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    def _current_schema_version(self, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT version FROM schema_version WHERE id = 1"
        ).fetchone()
        return int(row["version"]) if row else 0

    def _set_schema_version(
        self,
        connection: sqlite3.Connection,
        version: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO schema_version (id, version, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                version = excluded.version,
                updated_at = excluded.updated_at
            """,
            (version, _utc_now()),
        )

    def _migrate_to_v1(self, connection: sqlite3.Connection) -> None:
        """Create the initial desktop schema."""
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                drawing_path TEXT NOT NULL,
                component_drawings_json TEXT NOT NULL DEFAULT '[]',
                output_dir TEXT NOT NULL,
                context_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                status TEXT NOT NULL,
                blocked_stage TEXT NOT NULL,
                exports_json TEXT NOT NULL,
                manifest_path TEXT NOT NULL,
                manifest_run_id TEXT NOT NULL,
                manual_review_required INTEGER NOT NULL,
                manual_review_count INTEGER NOT NULL,
                manual_review_json TEXT NOT NULL,
                output_dir TEXT NOT NULL,
                raw_result_json TEXT NOT NULL,
                failure_message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS knowledge_rules (
                rule_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    def _backup_schema_v1(self, connection: sqlite3.Connection) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        backup_path = self.db_path.with_name(f"{self.db_path.stem}.schema-v1-{stamp}.sqlite3")
        target = sqlite3.connect(backup_path)
        try:
            connection.backup(target)
        except Exception:
            target.close()
            backup_path.unlink(missing_ok=True)
            raise
        target.close()
        return backup_path

    def _migrate_to_v2(self, connection: sqlite3.Connection) -> None:
        """Add persistent, run-scoped undo and redo history."""
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS run_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                direction TEXT NOT NULL CHECK(direction IN ('undo', 'redo')),
                snapshot_json TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_run_history_lookup
                ON run_history(run_id, direction, id);
            """
        )


def _seed_knowledge_rules(connection: sqlite3.Connection) -> None:
    """Seed default knowledge rules if the table is empty."""
    existing = connection.execute("SELECT COUNT(*) AS count FROM knowledge_rules").fetchone()
    if existing and int(existing["count"]) > 0:
        return
    now = _utc_now()
    for rule in DEFAULT_KNOWLEDGE_RULES:
        rule_id = str(rule.get("rule_id", ""))
        if not rule_id:
            continue
        connection.execute(
            """
            INSERT INTO knowledge_rules
                (rule_id, category, title, payload_json, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                rule_id,
                str(rule.get("recommendation_type", "知识库推荐")),
                str(rule.get("message", rule_id)),
                _to_json(rule),
                now,
                now,
            ),
        )


def _utc_now() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _to_json(value: Any) -> str:
    """Serialize value to JSON string."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
