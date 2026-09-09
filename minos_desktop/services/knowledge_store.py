"""Knowledge rules management for desktop application."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .sqlite_store import DEFAULT_DESKTOP_DB_PATH, DesktopSQLiteStore, _to_json, _utc_now


class DesktopKnowledgeStore:
    """Manages knowledge rules stored in SQLite database."""

    def __init__(self, db_path: str | Path = DEFAULT_DESKTOP_DB_PATH) -> None:
        self._store = DesktopSQLiteStore(db_path)

    def list_rules(self, *, include_disabled: bool = False) -> list[dict[str, Any]]:
        """List all knowledge rules, optionally including disabled ones."""
        query = "SELECT * FROM knowledge_rules"
        params: tuple[Any, ...] = ()
        if not include_disabled:
            query += " WHERE enabled = 1"
        query += " ORDER BY category, rule_id"
        with self._store.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_knowledge_rule_from_row(row) for row in rows]

    def add_rule(
        self,
        *,
        rule_id: str,
        category: str,
        title: str,
        payload: dict[str, Any],
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Add or update a knowledge rule."""
        now = _utc_now()
        payload = dict(payload)
        payload.setdefault("rule_id", rule_id)
        with self._store.connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_rules
                    (rule_id, category, title, payload_json, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    category = excluded.category,
                    title = excluded.title,
                    payload_json = excluded.payload_json,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (rule_id, category, title, _to_json(payload), 1 if enabled else 0, now, now),
            )
        return self.get_rule(rule_id)

    def add_rule_from_recommendation(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        """Create a knowledge rule from a recommendation."""
        recommendation_id = str(recommendation.get("recommendation_id", "")).strip()
        rule_id = f"LOCAL-{recommendation_id}" if recommendation_id else f"LOCAL-{_utc_now()}"
        payload = {
            "rule_id": rule_id,
            "recommendation_type": recommendation.get("recommendation_type", "历史项目经验"),
            "message": recommendation.get("reason", ""),
            "suggested_fields": recommendation.get("suggested_fields", {}),
            "confidence": recommendation.get("confidence", 0.8),
        }
        return self.add_rule(
            rule_id=rule_id,
            category=str(recommendation.get("recommendation_type", "历史项目经验")),
            title=str(recommendation.get("reason", rule_id))[:120],
            payload=payload,
        )

    def disable_rule(self, rule_id: str) -> dict[str, Any]:
        """Disable a knowledge rule."""
        with self._store.connect() as connection:
            connection.execute(
                "UPDATE knowledge_rules SET enabled = 0, updated_at = ? WHERE rule_id = ?",
                (_utc_now(), rule_id),
            )
        return self.get_rule(rule_id)

    def get_rule(self, rule_id: str) -> dict[str, Any]:
        """Get a single knowledge rule by ID."""
        with self._store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_rules WHERE rule_id = ?",
                (rule_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"knowledge rule not found: {rule_id}")
        return _knowledge_rule_from_row(row)


def _knowledge_rule_from_row(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a database row to a knowledge rule dictionary."""
    try:
        payload = json.loads(str(row["payload_json"] or "{}"))
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "rule_id": str(row["rule_id"]),
        "category": str(row["category"]),
        "title": str(row["title"]),
        "payload": payload,
        "enabled": bool(row["enabled"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }
