from __future__ import annotations

import sqlite3

import pytest

from minos_desktop.services.sqlite_store import (
    CURRENT_SCHEMA_VERSION,
    DesktopSQLiteStore,
)


def _tables(db_path):
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {str(row[0]) for row in rows}


def _schema_version(db_path):
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT version FROM schema_version WHERE id = 1"
        ).fetchone()
    return int(row[0])


def test_empty_database_initializes_schema_version(tmp_path):
    db_path = tmp_path / "desktop.sqlite3"

    DesktopSQLiteStore(db_path)

    assert _schema_version(db_path) == CURRENT_SCHEMA_VERSION


def test_legacy_database_without_schema_version_is_marked_current(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )

    DesktopSQLiteStore(db_path)

    assert _schema_version(db_path) == CURRENT_SCHEMA_VERSION


def test_migration_is_idempotent_and_keeps_core_tables(tmp_path):
    db_path = tmp_path / "desktop.sqlite3"

    DesktopSQLiteStore(db_path)
    DesktopSQLiteStore(db_path)

    assert _schema_version(db_path) == CURRENT_SCHEMA_VERSION
    assert {
        "settings",
        "projects",
        "runs",
        "knowledge_rules",
        "schema_version",
        "run_history",
    }.issubset(_tables(db_path))


def test_v1_migration_creates_recoverable_backup(tmp_path):
    db_path = tmp_path / "desktop.sqlite3"
    store = DesktopSQLiteStore(db_path)
    with store.connect() as connection:
        connection.execute("DROP TABLE run_history")
        connection.execute("UPDATE schema_version SET version = 1 WHERE id = 1")

    DesktopSQLiteStore(db_path)

    backups = list(tmp_path.glob("desktop.schema-v1-*.sqlite3"))
    assert len(backups) == 1
    assert _schema_version(backups[0]) == 1
    assert "run_history" not in _tables(backups[0])
    assert _schema_version(db_path) == 2
    assert "run_history" in _tables(db_path)


def test_backup_failure_does_not_upgrade_schema(monkeypatch, tmp_path):
    db_path = tmp_path / "desktop.sqlite3"
    store = DesktopSQLiteStore(db_path)
    with store.connect() as connection:
        connection.execute("DROP TABLE run_history")
        connection.execute("UPDATE schema_version SET version = 1 WHERE id = 1")

    def fail_backup(*_args):
        raise OSError("backup unavailable")

    monkeypatch.setattr(DesktopSQLiteStore, "_backup_schema_v1", fail_backup)
    with pytest.raises(OSError, match="backup unavailable"):
        DesktopSQLiteStore(db_path)

    assert _schema_version(db_path) == 1
    assert "run_history" not in _tables(db_path)


def test_connections_enable_foreign_keys_and_busy_timeout(tmp_path):
    store = DesktopSQLiteStore(tmp_path / "desktop.sqlite3")
    with store.connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_run_delete_cascades_history(tmp_path):
    from minos_desktop.services import DesktopRunService

    db_path = tmp_path / "desktop.sqlite3"
    service = DesktopRunService(db_path)
    run = service.save_result(None, {"status": "draft_ready"}, tmp_path)
    service.save_with_undo(run.id, {"status": "needs_review"})

    with service.repository.store.connect() as connection:
        connection.execute("DELETE FROM runs WHERE id = ?", (run.id,))
        count = connection.execute("SELECT COUNT(*) FROM run_history").fetchone()[0]

    assert count == 0


def test_future_schema_version_is_rejected(tmp_path):
    db_path = tmp_path / "future.sqlite3"
    DesktopSQLiteStore(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE schema_version SET version = 999 WHERE id = 1")

    with pytest.raises(RuntimeError, match="newer than supported"):
        DesktopSQLiteStore(db_path)


def test_history_foreign_key_rejects_orphan_run(tmp_path):
    store = DesktopSQLiteStore(tmp_path / "desktop.sqlite3")
    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as connection:
            connection.execute(
                "INSERT INTO run_history "
                "(run_id, direction, snapshot_json, size_bytes, created_at) "
                "VALUES (999, 'undo', '{}', 2, 'now')"
            )
