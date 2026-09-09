"""Public composed desktop run service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from minos_core.pipeline import analyze_drawing_for_three_table_chain

from ..app_state import (
    ChainStageStates,
    DesktopProjectRecord,
    DesktopRunRecord,
    DesktopRunState,
)
from .history_store import DesktopHistoryStore
from .run_chain import format_desktop_failure
from .run_chain_service import ChainGenerationService
from .run_edit_service import RunEditService
from .run_export_service import RunExportService
from .run_repository import RunRepository
from .sqlite_store import DEFAULT_DESKTOP_DB_PATH

__all__ = ["DesktopRunService", "format_desktop_failure"]


class DesktopRunService:
    def __init__(
        self,
        db_path: str | Path = DEFAULT_DESKTOP_DB_PATH,
        *,
        repository: RunRepository | None = None,
    ) -> None:
        self.repository = repository or RunRepository(db_path)
        self.history = DesktopHistoryStore()
        self._store = self.repository.store
        self._chain = ChainGenerationService(self.repository, self.history)
        self._edit = RunEditService(self.repository, self.history)
        self._export = RunExportService(self.repository, self.history)

    def run_project(self, project: DesktopProjectRecord) -> DesktopRunRecord:
        return self.start_chain_run(project)

    def start_chain_run(self, project: DesktopProjectRecord) -> DesktopRunRecord:
        return self._chain.start_chain_run(project, analyzer=analyze_drawing_for_three_table_chain)

    def confirm_pfd_stage(
        self, run_id: int, confirmed_by: str = "", edit_patch: dict[str, Any] | None = None
    ) -> DesktopRunRecord:
        return self._chain.confirm_pfd_stage(run_id, confirmed_by, edit_patch)

    def generate_pfmea_for_confirmed_pfd(self, run_id: int) -> DesktopRunRecord:
        return self._chain.generate_pfmea_for_confirmed_pfd(run_id)

    def confirm_pfmea_stage(
        self, run_id: int, confirmed_by: str = "", edit_patch: dict[str, Any] | None = None
    ) -> DesktopRunRecord:
        return self._chain.confirm_pfmea_stage(run_id, confirmed_by, edit_patch)

    def generate_cp_for_confirmed_pfmea(self, run_id: int) -> DesktopRunRecord:
        return self._chain.generate_cp_for_confirmed_pfmea(run_id)

    def confirm_cp_stage(
        self, run_id: int, confirmed_by: str = "", edit_patch: dict[str, Any] | None = None
    ) -> DesktopRunRecord:
        return self._chain.confirm_cp_stage(run_id, confirmed_by, edit_patch)

    def regenerate_pfmea_stage(self, run_id: int) -> DesktopRunRecord:
        return self._chain.regenerate_pfmea_stage(run_id)

    def regenerate_cp_stage(self, run_id: int) -> DesktopRunRecord:
        return self._chain.regenerate_cp_stage(run_id)

    def get_chain_state(self, run_id: int) -> dict[str, Any]:
        return self._chain.get_chain_state(run_id)

    def save_chain_run(
        self,
        project_id: int | None,
        state: DesktopRunState,
        output_dir: str | Path,
        raw_result: dict[str, Any],
        failure_message: str,
        chain_stages: ChainStageStates,
    ) -> DesktopRunRecord:
        return self._chain.save_chain_run(project_id, state, output_dir, raw_result, failure_message, chain_stages)

    def save_result(
        self, project_id: int | None, result: dict[str, Any], output_dir: str | Path = ""
    ) -> DesktopRunRecord:
        return self._edit.save_result(project_id, result, output_dir)

    def save_run(
        self,
        project_id: int | None,
        state: DesktopRunState,
        output_dir: str | Path,
        raw_result: dict[str, Any],
        failure_message: str = "",
    ) -> DesktopRunRecord:
        return self._edit.save_run(project_id, state, output_dir, raw_result, failure_message)

    def get_run(self, run_id: int) -> DesktopRunRecord:
        return self._edit.get_run(run_id)

    def list_recent_runs(self, limit: int = 10) -> list[DesktopRunRecord]:
        return self._edit.list_recent_runs(limit)

    def restore_run(self, run_id: int) -> DesktopRunRecord:
        return self._edit.restore_run(run_id)

    def apply_edit_patch_to_run(self, run_id: int, patch: dict[str, Any]) -> DesktopRunRecord:
        return self._edit.apply_edit_patch_to_run(run_id, patch)

    def refresh_run_result(self, run_id: int) -> DesktopRunRecord:
        return self._edit.refresh_run_result(run_id)

    def handle_recommendation(
        self, run_id: int, recommendation_id: str, *, accept: bool, reason: str = ""
    ) -> DesktopRunRecord:
        return self._edit.handle_recommendation(run_id, recommendation_id, accept=accept, reason=reason)

    def resolve_change_impact(
        self, run_id: int, item_id: str, *, status: str = "已处理", reason: str = ""
    ) -> DesktopRunRecord:
        return self._edit.resolve_change_impact(run_id, item_id, status=status, reason=reason)

    def batch_confirm_automation_review(self, run_id: int) -> DesktopRunRecord:
        return self._edit.batch_confirm_automation_review(run_id)

    def accept_automation_fix_suggestion(self, run_id: int, row: dict[str, Any]) -> DesktopRunRecord:
        return self._edit.accept_automation_fix_suggestion(run_id, row)

    def apply_recommendation_to_run(self, run_id: int, recommendation_id: str) -> DesktopRunRecord:
        return self._edit.apply_recommendation_to_run(run_id, recommendation_id)

    def ignore_recommendation_in_run(self, run_id: int, recommendation_id: str, reason: str) -> DesktopRunRecord:
        return self._edit.ignore_recommendation_in_run(run_id, recommendation_id, reason)

    def resolve_action_in_run(
        self, run_id: int, action_id: str, changes: dict[str, Any], reason: str = ""
    ) -> DesktopRunRecord | None:
        return self._edit.resolve_action_in_run(run_id, action_id, changes, reason)

    def review_dashboard(self, run_result: dict[str, Any]) -> dict[str, Any]:
        return self._edit.review_dashboard(run_result)

    def preview_edit_patch_for_run(self, run_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        return self._edit.preview_edit_patch_for_run(run_id, patch)

    def apply_live_edit_to_run(
        self, run_id: int, edit_patch: dict[str, Any], selected_impact_ids: list[str] | None = None
    ) -> DesktopRunRecord:
        return self._edit.apply_live_edit_to_run(run_id, edit_patch, selected_impact_ids)

    def save_with_undo(self, run_id: int, current_result: dict[str, Any]) -> DesktopRunRecord:
        return self._edit.save_with_undo(run_id, current_result)

    def undo_run(self, run_id: int) -> DesktopRunRecord | None:
        return self._edit.undo_run(run_id)

    def redo_run(self, run_id: int) -> DesktopRunRecord | None:
        return self._edit.redo_run(run_id)

    def export_run(self, run_id: int, output_dir: str | Path, export_mode: str = "draft") -> dict[str, Any]:
        return self._export.export_run(run_id, output_dir, export_mode)
