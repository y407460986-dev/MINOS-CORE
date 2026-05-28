"""SQLite database connection and migration management."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from minos_core._paths import user_data_dir
from minos_core.knowledge_recommendation import DEFAULT_KNOWLEDGE_RULES

DEFAULT_DESKTOP_DB_PATH = user_data_dir() / "minos_desktop.sqlite3"


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
            _seed_knowledge_rules(connection)


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
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_json(value: Any) -> str:
    """Serialize value to JSON string."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
