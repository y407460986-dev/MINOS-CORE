from __future__ import annotations

import sqlite3

import pytest

from minos_desktop.services.history_store import DesktopHistoryStore
from minos_desktop.services.run_repository import RunRepository


def _run_id(repository: RunRepository, tmp_path) -> int:
    from minos_desktop.app_state import desktop_run_state_from_result

    result = {"status": "draft_ready", "manual_review": {"required": False, "items": []}}
    return repository.insert_run(
        None, desktop_run_state_from_result(result), tmp_path, result, ""
    ).id


def test_history_store_is_lifo_and_uses_utf8_byte_size(tmp_path):
    repository = RunRepository(tmp_path / "desktop.sqlite3")
    run_id = _run_id(repository, tmp_path)
    store = DesktopHistoryStore()
    first = {"current_result": {"operation": "中文"}}
    second = {"current_result": {"operation": "second"}}

    with repository.transaction(immediate=True) as connection:
        store.push(connection, run_id, "undo", first)
        store.push(connection, run_id, "undo", second)
        row = connection.execute(
            "SELECT snapshot_json, size_bytes FROM run_history WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchone()
        assert row["size_bytes"] == len(row["snapshot_json"].encode("utf-8"))
        assert store.pop_latest(connection, run_id, "undo") == second
        assert store.pop_latest(connection, run_id, "undo") == first
        assert store.pop_latest(connection, run_id, "undo") is None


def test_history_store_trims_each_run_and_direction_independently(tmp_path):
    repository = RunRepository(tmp_path / "desktop.sqlite3")
    run_a = _run_id(repository, tmp_path)
    run_b = _run_id(repository, tmp_path)
    store = DesktopHistoryStore(max_entries=2, max_bytes=1024)

    with repository.transaction(immediate=True) as connection:
        for value in range(3):
            store.push(connection, run_a, "undo", {"value": value})
        store.push(connection, run_a, "redo", {"value": "redo"})
        store.push(connection, run_b, "undo", {"value": "other"})
        store.trim(connection, run_a, "undo")
        values = [
            row[0]
            for row in connection.execute(
                "SELECT id FROM run_history WHERE run_id = ? AND direction = 'undo' ORDER BY id",
                (run_a,),
            )
        ]
        assert len(values) == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM run_history WHERE run_id = ? AND direction = 'redo'",
            (run_a,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM run_history WHERE run_id = ? AND direction = 'undo'",
            (run_b,),
        ).fetchone()[0] == 1


def test_history_store_trims_to_byte_limit(tmp_path):
    repository = RunRepository(tmp_path / "desktop.sqlite3")
    run_id = _run_id(repository, tmp_path)
    store = DesktopHistoryStore(max_entries=20, max_bytes=70)

    with repository.transaction(immediate=True) as connection:
        store.push(connection, run_id, "undo", {"value": "a" * 30})
        store.push(connection, run_id, "undo", {"value": "b" * 30})
        store.trim(connection, run_id, "undo")
        count, size = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM run_history"
        ).fetchone()

    assert count == 1
    assert size <= 70


def test_invalid_snapshot_rolls_back_pop(tmp_path):
    repository = RunRepository(tmp_path / "desktop.sqlite3")
    run_id = _run_id(repository, tmp_path)
    store = DesktopHistoryStore()
    with repository.store.connect() as connection:
        connection.execute(
            "INSERT INTO run_history (run_id, direction, snapshot_json, size_bytes, created_at) "
            "VALUES (?, 'undo', '{bad', 4, 'now')",
            (run_id,),
        )

    with pytest.raises(ValueError):
        with repository.transaction(immediate=True) as connection:
            store.pop_latest(connection, run_id, "undo")

    with sqlite3.connect(repository.store.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM run_history").fetchone()[0] == 1
