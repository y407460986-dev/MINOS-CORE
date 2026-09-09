"""Persistent undo and redo snapshots for desktop runs."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Literal

from .sqlite_store import _to_json, _utc_now

HistoryDirection = Literal["undo", "redo"]
MAX_HISTORY_ENTRIES = 20
MAX_HISTORY_BYTES = 50 * 1024 * 1024


class DesktopHistoryStore:
    """Operate on history using the caller's active SQLite transaction."""

    def __init__(
        self,
        *,
        max_entries: int = MAX_HISTORY_ENTRIES,
        max_bytes: int = MAX_HISTORY_BYTES,
    ) -> None:
        self.max_entries = max_entries
        self.max_bytes = max_bytes

    def push(
        self,
        connection: sqlite3.Connection,
        run_id: int,
        direction: HistoryDirection,
        snapshot: dict[str, Any],
    ) -> None:
        snapshot_json = _to_json(snapshot)
        connection.execute(
            """
            INSERT INTO run_history (
                run_id, direction, snapshot_json, size_bytes, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                direction,
                snapshot_json,
                len(snapshot_json.encode("utf-8")),
                _utc_now(),
            ),
        )

    def pop_latest(
        self,
        connection: sqlite3.Connection,
        run_id: int,
        direction: HistoryDirection,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT id, snapshot_json
            FROM run_history
            WHERE run_id = ? AND direction = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (run_id, direction),
        ).fetchone()
        if row is None:
            return None
        try:
            snapshot = json.loads(str(row["snapshot_json"]))
        except json.JSONDecodeError as exc:
            raise ValueError("history snapshot is not valid JSON") from exc
        if not isinstance(snapshot, dict):
            raise ValueError("history snapshot must be a JSON object")
        connection.execute("DELETE FROM run_history WHERE id = ?", (int(row["id"]),))
        return snapshot

    def clear(
        self,
        connection: sqlite3.Connection,
        run_id: int,
        direction: HistoryDirection,
    ) -> None:
        connection.execute(
            "DELETE FROM run_history WHERE run_id = ? AND direction = ?",
            (run_id, direction),
        )

    def trim(
        self,
        connection: sqlite3.Connection,
        run_id: int,
        direction: HistoryDirection,
    ) -> None:
        rows = connection.execute(
            """
            SELECT id, size_bytes
            FROM run_history
            WHERE run_id = ? AND direction = ?
            ORDER BY id DESC
            """,
            (run_id, direction),
        ).fetchall()
        retained_bytes = 0
        delete_ids: list[int] = []
        for index, row in enumerate(rows):
            size_bytes = int(row["size_bytes"])
            if index >= self.max_entries or retained_bytes + size_bytes > self.max_bytes:
                delete_ids.append(int(row["id"]))
            else:
                retained_bytes += size_bytes
        if delete_ids:
            connection.executemany(
                "DELETE FROM run_history WHERE id = ?",
                [(history_id,) for history_id in delete_ids],
            )
