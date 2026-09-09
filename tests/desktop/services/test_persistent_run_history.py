from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from minos_desktop.services import DesktopRunService


def _result(operation: str, *, note: str = "") -> dict:
    return {
        "status": "needs_review",
        "process_flow": {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": operation,
                    "note": note,
                    "needs_confirmation": True,
                }
            ]
        },
        "pfmea": {"rows": []},
        "control_plan": {"rows": []},
        "manual_review": {"required": True, "items": []},
    }


def _patch(field: str, value: str) -> dict:
    return {
        "items": [
            {
                "action": "update",
                "table": "process_flow",
                "target": "process_step:P10",
                "row_id": "P10",
                "changes": {field: value},
            }
        ]
    }


def _operation(record) -> str:
    return record.current_result["process_flow"]["steps"][0]["operation"]


def test_edit_patch_history_survives_service_restart(tmp_path):
    db_path = tmp_path / "desktop.sqlite3"
    service = DesktopRunService(db_path)
    run = service.save_result(None, _result("Before"), tmp_path)

    service.apply_edit_patch_to_run(run.id, _patch("operation", "After"))
    del service
    restarted = DesktopRunService(db_path)

    assert _operation(restarted.undo_run(run.id)) == "Before"
    assert _operation(restarted.redo_run(run.id)) == "After"


def test_same_run_id_in_different_databases_has_isolated_history(tmp_path):
    first = DesktopRunService(tmp_path / "first.sqlite3")
    second = DesktopRunService(tmp_path / "second.sqlite3")
    first_run = first.save_result(None, _result("First"), tmp_path)
    second_run = second.save_result(None, _result("Second"), tmp_path)
    assert first_run.id == second_run.id

    first.apply_edit_patch_to_run(first_run.id, _patch("operation", "First edited"))

    assert second.undo_run(second_run.id) is None
    assert _operation(first.undo_run(first_run.id)) == "First"


def test_failed_run_update_rolls_back_history(monkeypatch, tmp_path):
    service = DesktopRunService(tmp_path / "desktop.sqlite3")
    run = service.save_result(None, _result("Before"), tmp_path)
    original_update = service.repository.update_run

    def fail_update(*args, **kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(service.repository, "update_run", fail_update)
    with pytest.raises(RuntimeError, match="write failed"):
        service.apply_edit_patch_to_run(run.id, _patch("operation", "After"))
    monkeypatch.setattr(service.repository, "update_run", original_update)

    assert _operation(service.get_run(run.id)) == "Before"
    assert service.undo_run(run.id) is None


def test_failed_undo_update_restores_history_entry(monkeypatch, tmp_path):
    service = DesktopRunService(tmp_path / "desktop.sqlite3")
    run = service.save_result(None, _result("Before"), tmp_path)
    service.apply_edit_patch_to_run(run.id, _patch("operation", "After"))
    original_update = service.repository.update_run

    def fail_update(*args, **kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(service.repository, "update_run", fail_update)
    with pytest.raises(RuntimeError, match="write failed"):
        service.undo_run(run.id)
    monkeypatch.setattr(service.repository, "update_run", original_update)

    assert _operation(service.get_run(run.id)) == "After"
    assert _operation(service.undo_run(run.id)) == "Before"


def test_default_history_limit_keeps_latest_twenty_snapshots(tmp_path):
    service = DesktopRunService(tmp_path / "desktop.sqlite3")
    run = service.save_result(None, _result("0"), tmp_path)
    for value in range(1, 26):
        service.save_with_undo(run.id, _result(str(value)))

    with service.repository.store.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM run_history WHERE run_id = ? AND direction = 'undo'",
            (run.id,),
        ).fetchone()[0]

    assert count == 20
    for expected in range(24, 4, -1):
        assert _operation(service.undo_run(run.id)) == str(expected)
    assert service.undo_run(run.id) is None


def test_concurrent_edits_keep_both_fields(tmp_path):
    db_path = tmp_path / "desktop.sqlite3"
    service = DesktopRunService(db_path)
    run = service.save_result(None, _result("Before"), tmp_path)

    def edit(patch):
        return DesktopRunService(db_path).apply_edit_patch_to_run(run.id, patch)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(edit, [_patch("operation", "After"), _patch("note", "Kept")]))

    row = service.get_run(run.id).current_result["process_flow"]["steps"][0]
    assert row["operation"] == "After"
    assert row["note"] == "Kept"
