"""SQLite persistence boundary for desktop run records."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..app_state import DesktopRunRecord, DesktopRunState
from .project_store import _from_json_object
from .run_record_mapper import _run_from_row
from .sqlite_store import DEFAULT_DESKTOP_DB_PATH, DesktopSQLiteStore, _to_json, _utc_now


class RunRepository:
    """Own run SQL and expose reusable transaction boundaries."""

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DESKTOP_DB_PATH,
        *,
        store: DesktopSQLiteStore | None = None,
    ) -> None:
        self.store = store or DesktopSQLiteStore(db_path)

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.store.db_path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def insert_run(
        self,
        project_id: int | None,
        state: DesktopRunState,
        output_dir: str | Path,
        raw_result: dict[str, Any],
        failure_message: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> DesktopRunRecord:
        with self._connection(connection) as active:
            cursor = active.execute(
                """
                INSERT INTO runs (
                    project_id, status, blocked_stage, exports_json,
                    manifest_path, manifest_run_id, manual_review_required,
                    manual_review_count, manual_review_json, output_dir,
                    raw_result_json, failure_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    state.status,
                    state.blocked_stage,
                    _to_json({record.name: record.path for record in state.exports}),
                    state.manifest_path,
                    state.manifest_run_id,
                    1 if state.manual_review_required else 0,
                    state.manual_review_count,
                    _to_json(list(state.manual_review_items)),
                    str(output_dir),
                    _to_json(raw_result),
                    failure_message,
                    _utc_now(),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("run insert did not return an id")
            run_id = int(cursor.lastrowid)
        return self.get_run(run_id, connection=connection)

    def update_run(
        self,
        run_id: int,
        state: DesktopRunState,
        raw_result: dict[str, Any],
        *,
        failure_message: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> DesktopRunRecord:
        assignments = """
            status = ?, blocked_stage = ?, exports_json = ?, manifest_path = ?,
            manifest_run_id = ?, manual_review_required = ?, manual_review_count = ?,
            manual_review_json = ?, raw_result_json = ?
        """
        values: list[Any] = [
            state.status,
            state.blocked_stage,
            _to_json({record.name: record.path for record in state.exports}),
            state.manifest_path,
            state.manifest_run_id,
            1 if state.manual_review_required else 0,
            state.manual_review_count,
            _to_json(list(state.manual_review_items)),
            _to_json(raw_result),
        ]
        if failure_message is not None:
            assignments += ", failure_message = ?"
            values.append(failure_message)
        values.append(run_id)
        with self._connection(connection) as active:
            cursor = active.execute(
                f"UPDATE runs SET {assignments} WHERE id = ?",
                values,
            )
            if cursor.rowcount != 1:
                raise KeyError(f"desktop run not found: {run_id}")
        return self.get_run(run_id, connection=connection)

    def get_run(
        self,
        run_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> DesktopRunRecord:
        with self._connection(connection) as active:
            row = active.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"desktop run not found: {run_id}")
        return _run_from_row(row)

    def list_recent_runs(self, limit: int = 10) -> list[DesktopRunRecord]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [_run_from_row(row) for row in rows]

    def get_raw_payload(
        self,
        run_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        with self._connection(connection) as active:
            row = active.execute(
                "SELECT raw_result_json FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"desktop run not found: {run_id}")
        return _from_json_object(str(row["raw_result_json"]))

    def get_output_dir(
        self,
        run_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> str:
        with self._connection(connection) as active:
            row = active.execute("SELECT output_dir FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"desktop run not found: {run_id}")
        return str(row["output_dir"] or "")

    @contextmanager
    def _connection(
        self, connection: sqlite3.Connection | None
    ) -> Iterator[sqlite3.Connection]:
        if connection is not None:
            yield connection
            return
        with self.store.connect() as owned:
            yield owned
