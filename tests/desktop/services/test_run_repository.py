from __future__ import annotations

import pytest

from minos_desktop.app_state import DesktopRunState
from minos_desktop.services.run_repository import RunRepository


def _state(status: str = "needs_review") -> DesktopRunState:
    return DesktopRunState(
        status=status,
        status_display="待人工确认",
        blocked_stage="",
        exports=(),
        manifest_path="",
        manifest_run_id="",
        manual_review_required=False,
        manual_review_count=0,
        manual_review_raw_count=0,
    )


def test_repository_round_trips_unicode_run_and_lists_recent(tmp_path) -> None:
    repository = RunRepository(tmp_path / "desktop.sqlite3")
    first = repository.insert_run(None, _state(), tmp_path / "one", {"name": "第一项"}, "")
    second = repository.insert_run(None, _state("failed"), tmp_path / "two", {"name": "第二项"}, "失败")

    assert repository.get_run(first.id).current_result["name"] == "第一项"
    assert [record.id for record in repository.list_recent_runs(1)] == [second.id]
    assert repository.get_raw_payload(second.id)["name"] == "第二项"
    assert repository.get_output_dir(first.id) == str(tmp_path / "one")


def test_repository_transaction_rolls_back_and_supports_begin_immediate(tmp_path) -> None:
    repository = RunRepository(tmp_path / "desktop.sqlite3")

    with pytest.raises(RuntimeError, match="rollback"):
        with repository.transaction(immediate=True) as connection:
            repository.insert_run(None, _state(), "", {"name": "temporary"}, "", connection=connection)
            raise RuntimeError("rollback")

    assert repository.list_recent_runs() == []


def test_repository_update_checks_missing_run(tmp_path) -> None:
    repository = RunRepository(tmp_path / "desktop.sqlite3")

    with pytest.raises(KeyError, match="desktop run not found"):
        repository.update_run(99, _state(), {"name": "missing"})
