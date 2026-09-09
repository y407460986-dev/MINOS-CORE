"""Desktop run responsibility service."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from ..app_state import (
    DesktopRunRecord,
    DesktopRunState,
    desktop_run_state_from_result,
)
from ..table_editor import (
    automation_batch_confirm_patch,
    automation_fix_suggestion_patch,
    build_edit_patch,
    change_impact_patch_item,
    recommendation_action_patch_item,
)
from .history_store import DesktopHistoryStore, HistoryDirection
from .run_chain import _desktop_result_envelope
from .run_edit_helpers import (
    _merge_edit_patch,
    _normalize_edit_patch,
)
from .run_record_mapper import _stored_result_parts
from .run_repository import RunRepository
from .run_shared import (
    _apply_edit_patch,
    _can_apply_after_control_plan_automation_review,
    _chain_stages_from_envelope,
    _invalidate_chain_after_patch,
    _write_three_table_result,
)


class RunEditService:
    def __init__(self, repository: RunRepository, history: DesktopHistoryStore) -> None:
        self.repository = repository
        self.history = history
        self._store = repository.store

    def save_result(
        self, project_id: int | None, result: dict[str, Any], output_dir: str | Path = ""
    ) -> DesktopRunRecord:
        output_dir_text = str(output_dir)
        if output_dir_text:
            _write_three_table_result(output_dir_text, result)
        return self.save_run(
            project_id, desktop_run_state_from_result(result), output_dir_text, _desktop_result_envelope(result), ""
        )

    def save_run(
        self,
        project_id: int | None,
        state: DesktopRunState,
        output_dir: str | Path,
        raw_result: dict[str, Any],
        failure_message: str = "",
    ) -> DesktopRunRecord:
        return self.repository.insert_run(project_id, state, output_dir, raw_result, failure_message)

    def get_run(self, run_id: int) -> DesktopRunRecord:
        return self.repository.get_run(run_id)

    def list_recent_runs(self, limit: int = 10) -> list[DesktopRunRecord]:
        return self.repository.list_recent_runs(limit)

    def restore_run(self, run_id: int) -> DesktopRunRecord:
        return self.get_run(run_id)

    def apply_edit_patch_to_run(self, run_id: int, patch: dict[str, Any]) -> DesktopRunRecord:
        edit_patch = _normalize_edit_patch(patch)
        with self.repository.transaction(immediate=True) as connection:
            current = self.repository.get_run(run_id, connection=connection)
            stored_payload = self.repository.get_raw_payload(run_id, connection=connection)
            stored = _stored_result_parts(stored_payload)
            updated_result = _apply_edit_patch(stored["current_result"], edit_patch)
            updated_result, chain_stages = _invalidate_chain_after_patch(
                updated_result, edit_patch, _chain_stages_from_envelope(stored_payload)
            )
            if chain_stages is not None and chain_stages.cp.status == "confirmed":
                from minos_core.automation_review import build_automation_review
                from minos_core.edit_patch import _refresh_three_table_result

                updated_result["automation_review"] = build_automation_review(updated_result)
                updated_result = _refresh_three_table_result(updated_result)
            cumulative_patch = _merge_edit_patch(stored.get("edit_patch", {}), edit_patch)
            envelope = _desktop_result_envelope(
                stored["raw_result"], current_result=updated_result, edit_patch=cumulative_patch
            )
            if chain_stages is not None:
                envelope["chain_stages"] = chain_stages.to_dict()
            self.history.push(connection, run_id, "undo", stored_payload)
            self.history.clear(connection, run_id, "redo")
            self.history.trim(connection, run_id, "undo")
            state = desktop_run_state_from_result(updated_result)
            record = self.repository.update_run(run_id, state, envelope, connection=connection)
        if current.output_dir:
            _write_three_table_result(current.output_dir, updated_result)
        return record

    def refresh_run_result(self, run_id: int) -> DesktopRunRecord:
        current = self.get_run(run_id)
        stored_payload = self.repository.get_raw_payload(run_id)
        stored = _stored_result_parts(stored_payload)
        updated_result = copy.deepcopy(stored["current_result"])
        from minos_core.automation_review import build_automation_review
        from minos_core.edit_patch import _refresh_three_table_result

        updated_result["automation_review"] = build_automation_review(updated_result)
        updated_result = _refresh_three_table_result(updated_result)
        envelope = _desktop_result_envelope(
            stored["raw_result"], current_result=updated_result, edit_patch=stored.get("edit_patch", {})
        )
        chain_stages = _chain_stages_from_envelope(stored_payload)
        if chain_stages is not None:
            envelope["chain_stages"] = chain_stages.to_dict()
        state = desktop_run_state_from_result(updated_result)
        return self._persist_run_update(run_id, state, envelope, current.output_dir)

    def handle_recommendation(
        self, run_id: int, recommendation_id: str, *, accept: bool, reason: str = ""
    ) -> DesktopRunRecord:
        action = "accept_recommendation" if accept else "ignore_recommendation"
        item = recommendation_action_patch_item(recommendation_id, action, reason=reason)
        return self.apply_edit_patch_to_run(run_id, build_edit_patch([item]))

    def resolve_change_impact(
        self, run_id: int, item_id: str, *, status: str = "已处理", reason: str = ""
    ) -> DesktopRunRecord:
        item = change_impact_patch_item(item_id, status=status, reason=reason)
        return self.apply_edit_patch_to_run(run_id, build_edit_patch([item]))

    def batch_confirm_automation_review(self, run_id: int) -> DesktopRunRecord:
        current = self.get_run(run_id)
        if not _can_apply_after_control_plan_automation_review(current):
            return current
        patch = automation_batch_confirm_patch(current.current_result)
        if not patch.get("items"):
            return current
        for item in patch["items"]:
            if isinstance(item, dict):
                metadata = item.setdefault("metadata", {})
                if isinstance(metadata, dict):
                    metadata.setdefault("confirmation_mode", "ai_recommended_batch")
                    metadata.setdefault("source", "automation_review")
        return self.apply_edit_patch_to_run(run_id, patch)

    def accept_automation_fix_suggestion(self, run_id: int, row: dict[str, Any]) -> DesktopRunRecord:
        patch = automation_fix_suggestion_patch(row)
        if not patch.get("items"):
            return self.get_run(run_id)
        return self.apply_edit_patch_to_run(run_id, patch)

    def apply_recommendation_to_run(self, run_id: int, recommendation_id: str) -> DesktopRunRecord:
        """应用知识推荐到 run。"""
        return self.handle_recommendation(run_id, recommendation_id, accept=True)

    def ignore_recommendation_in_run(self, run_id: int, recommendation_id: str, reason: str) -> DesktopRunRecord:
        """忽略知识推荐。"""
        return self.handle_recommendation(run_id, recommendation_id, accept=False, reason=reason)

    def resolve_action_in_run(
        self, run_id: int, action_id: str, changes: dict[str, Any], reason: str = ""
    ) -> DesktopRunRecord | None:
        """关闭或忽略行动项。

        返回 None 表示 action_tracking 模块不可用（旧版本兼容）。
        """
        try:
            from minos_core.action_tracking import build_action_items
        except ImportError:
            return None
        del build_action_items
        item: dict[str, Any] = {
            "action": "resolve_action_item",
            "table": "metadata",
            "target_id": action_id,
            "changes": changes,
        }
        if reason:
            item["reason"] = reason
        return self.apply_edit_patch_to_run(run_id, build_edit_patch([item]))

    def review_dashboard(self, run_result: dict[str, Any]) -> dict[str, Any]:
        """返回 review_dashboard，兼容旧版本。

        V1.10 起运行结果可能包含 review_dashboard 字段，其中 status_display
        和 next_actions 可直接用于复核页展示。旧数据没有该字段时返回空 dict。
        """
        dashboard = run_result.get("review_dashboard", {})
        return dict(dashboard) if isinstance(dashboard, dict) else {}

    def _persist_run_update(
        self, run_id: int, state: DesktopRunState, envelope: dict[str, Any], output_dir: str
    ) -> DesktopRunRecord:
        """Write updated state + envelope to the runs table (shared by all update paths)."""
        record = self.repository.update_run(run_id, state, envelope)
        if output_dir:
            _write_three_table_result(output_dir, envelope.get("current_result", envelope))
        return record

    def preview_edit_patch_for_run(self, run_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        """预览编辑 patch 的联动影响。"""
        try:
            from minos_core.live_linkage import preview_live_linkage_impacts
        except ImportError:
            return {}
        record = self.get_run(run_id)
        before = record.raw_result
        return preview_live_linkage_impacts(before, patch)

    def apply_live_edit_to_run(
        self, run_id: int, edit_patch: dict[str, Any], selected_impact_ids: list[str] | None = None
    ) -> DesktopRunRecord:
        """应用编辑 patch，可选合并联动同步 patch。"""
        try:
            from minos_core.live_linkage import build_live_sync_patch
        except ImportError:
            return self.apply_edit_patch_to_run(run_id, edit_patch)
        record = self.get_run(run_id)
        before = record.raw_result
        if selected_impact_ids:
            sync_patch = build_live_sync_patch(before, edit_patch, selected_impact_ids)
            if sync_patch.get("items"):
                return self.apply_edit_patch_to_run(run_id, _merge_edit_patch(edit_patch, sync_patch))
        return self.apply_edit_patch_to_run(run_id, edit_patch)

    def save_with_undo(self, run_id: int, current_result: dict[str, Any]) -> DesktopRunRecord:
        """保存 run current_result 并在撤销栈中保留 DB 快照。

        ``current_result`` 是完整的 three-table result dict。
        每次保存前将当前 run 的存储快照推入 undo 栈，清空 redo 栈，限制栈深度 20。
        """
        with self.repository.transaction(immediate=True) as connection:
            record = self.repository.get_run(run_id, connection=connection)
            current_envelope = self.repository.get_raw_payload(run_id, connection=connection)
            stored = _stored_result_parts(current_envelope)
            envelope = _desktop_result_envelope(
                stored.get("raw_result", current_result),
                current_result=current_result,
                edit_patch=stored.get("edit_patch", {}),
            )
            self.history.push(connection, run_id, "undo", current_envelope)
            self.history.clear(connection, run_id, "redo")
            self.history.trim(connection, run_id, "undo")
            state = desktop_run_state_from_result(current_result)
            updated = self.repository.update_run(run_id, state, envelope, connection=connection)
        if record.output_dir:
            _write_three_table_result(record.output_dir, current_result)
        return updated

    def undo_run(self, run_id: int) -> DesktopRunRecord | None:
        """撤销到上一个持久化快照。"""
        return self._move_history(run_id, source="undo", target="redo")

    def redo_run(self, run_id: int) -> DesktopRunRecord | None:
        """重做到下一个持久化快照。"""
        return self._move_history(run_id, source="redo", target="undo")

    def _move_history(
        self, run_id: int, *, source: HistoryDirection, target: HistoryDirection
    ) -> DesktopRunRecord | None:
        if source not in {"undo", "redo"} or target not in {"undo", "redo"}:
            raise ValueError("unsupported history direction")
        with self.repository.transaction(immediate=True) as connection:
            current = self.repository.get_run(run_id, connection=connection)
            current_envelope = self.repository.get_raw_payload(run_id, connection=connection)
            snapshot = self.history.pop_latest(connection, run_id, source)
            if snapshot is None:
                return None
            stored = _stored_result_parts(snapshot)
            restored_result = stored.get("current_result")
            if not isinstance(restored_result, dict):
                raise ValueError("history snapshot must contain current_result mapping")
            self.history.push(connection, run_id, target, current_envelope)
            self.history.trim(connection, run_id, target)
            state = desktop_run_state_from_result(restored_result)
            updated = self.repository.update_run(run_id, state, snapshot, connection=connection)
        if current.output_dir:
            _write_three_table_result(current.output_dir, restored_result)
        return updated
