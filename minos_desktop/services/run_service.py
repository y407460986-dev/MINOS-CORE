"""Run service for managing desktop application runs and chain workflows."""

from __future__ import annotations

import copy
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from minos_core.pipeline import analyze_drawing_for_three_table_chain

from ..chain_state import (
    chain_stages_from_envelope,
    confirm_chain_table,
    dedupe_texts as _chain_dedupe_texts,
    failed_chain_stage,
    init_chain_stages,
    invalidate_chain_after_patch,
    table_row_count,
    pending_row_count,
    table_rows_for_chain,
)
from ..app_state import (
    ChainStageStates,
    DesktopExportRecord,
    DesktopProjectRecord,
    DesktopRunRecord,
    DesktopRunState,
    StageConfirmState,
    desktop_run_state_from_result,
)
from ..table_editor import (
    EDIT_PATCH_VERSION,
    automation_batch_confirm_patch,
    automation_fix_suggestion_patch,
    build_edit_patch,
    change_impact_patch_item,
    recommendation_action_patch_item,
)
from .sqlite_store import DesktopSQLiteStore, DEFAULT_DESKTOP_DB_PATH, _utc_now, _to_json
from .project_store import _from_json_object

class DesktopRunService:
    def __init__(
        self,
        db_path: str | Path = DEFAULT_DESKTOP_DB_PATH,
    ) -> None:
        self._store = DesktopSQLiteStore(db_path)
        self._undo_stack: list[dict[str, Any]] = []
        self._redo_stack: list[dict[str, Any]] = []

    def run_project(self, project: DesktopProjectRecord) -> DesktopRunRecord:
        """兼容旧桌面调用名，但行为已收口为链式流程。"""
        return self.start_chain_run(project)

    # ------------------------------------------------------------------
    # 链式确认流程 (Chain Pipeline)
    # ------------------------------------------------------------------

    def start_chain_run(self, project: DesktopProjectRecord) -> DesktopRunRecord:
        """链式流程入口：图纸分析 + LLM 生成 PFD（仅第一步）。

        只运行图纸识别阶段，然后用 LLM 生成 PFD；不会偷偷一次性生成三表。
        """
        from minos_core.pipeline_chain import generate_pfd_from_drawing

        analysis_mode = _project_context_value(project.context, "analysis_mode", "hybrid")
        ocr_engine = _project_context_value(project.context, "ocr_engine", "mineru")

        try:
            analysis_result = analyze_drawing_for_three_table_chain(
                project.drawing_path,
                project.output_dir,
                context=project.context,
                analysis_mode=analysis_mode,
                ocr_engine=ocr_engine,
            )
        except (OSError, ValueError, TypeError, RuntimeError, KeyError, AttributeError) as exc:
            failure = format_desktop_failure(exc)
            chain_stages = _init_chain_stages("failed")
            state = DesktopRunState(
                status="failed", status_display="失败", blocked_stage="pfd",
                exports=(), manifest_path="", manifest_run_id="",
                manual_review_required=False, manual_review_count=0,
                manual_review_raw_count=0, chain_stages=chain_stages,
            )
            return self.save_chain_run(project.id, state, project.output_dir, {}, failure, chain_stages)

        drawing_analysis = analysis_result.get("drawing_analysis") or {}
        if isinstance(drawing_analysis, dict):
            drawing_analysis.setdefault(
                "_part_family",
                analysis_result.get("part_family_classification") or {},
            )
            drawing_analysis.setdefault(
                "_family_context",
                analysis_result.get("family_context") or {},
            )
        drawing_gate = analysis_result.get("drawing_gate")
        if drawing_gate is not None and not drawing_gate.can_continue:
            failure = format_desktop_failure("图纸识别质量门未通过，不能生成 PFD。")
            chain_stages = _init_chain_stages("failed")
            state = DesktopRunState(
                status="failed", status_display="失败", blocked_stage="drawing_recognition",
                exports=(), manifest_path="", manifest_run_id="",
                manual_review_required=False, manual_review_count=0,
                manual_review_raw_count=0, chain_stages=chain_stages,
            )
            result = {
                "document_type": "three_table_generation_result",
                "schema_version": "minos-core.three_table_generation_result.v1",
                "status": "failed",
                "blocked_stage": "drawing_recognition",
                "drawing_analysis": drawing_analysis,
                "quality_gate": drawing_gate.model_dump(),
                "part_family_classification": analysis_result.get("part_family_classification") or {},
                "family_context": analysis_result.get("family_context") or {},
            }
            return self.save_chain_run(project.id, state, project.output_dir, result, failure, chain_stages)

        try:
            llm_pfd = generate_pfd_from_drawing(drawing_analysis)
        except (OSError, ValueError, TypeError, RuntimeError, KeyError, AttributeError) as exc:
            failure = format_desktop_failure(exc)
            chain_stages = _init_chain_stages("failed")
            state = DesktopRunState(
                status="failed", status_display="失败", blocked_stage="pfd",
                exports=(), manifest_path="", manifest_run_id="",
                manual_review_required=False, manual_review_count=0,
                manual_review_raw_count=0, chain_stages=chain_stages,
            )
            result = {
                "document_type": "three_table_generation_result",
                "schema_version": "minos-core.three_table_generation_result.v1",
                "status": "failed",
                "blocked_stage": "pfd",
                "drawing_analysis": drawing_analysis,
                "process_flow": {"steps": []},
                "pfmea": {"rows": []},
                "control_plan": {"rows": []},
                "part_family_classification": analysis_result.get("part_family_classification") or {},
                "family_context": analysis_result.get("family_context") or {},
            }
            return self.save_chain_run(project.id, state, project.output_dir, result, failure, chain_stages)

        # 构建链式结果（只含 drawing_analysis + PFD，不含 PFMEA 和 CP）
        result = {
            "document_type": "three_table_generation_result",
            "schema_version": "minos-core.three_table_generation_result.v1",
            "status": "needs_review",
            "drawing_analysis": drawing_analysis,
            "process_flow": llm_pfd,
            "pfmea": {"rows": []},
            "control_plan": {"rows": []},
            "part_family_classification": analysis_result.get("part_family_classification") or {},
            "family_context": analysis_result.get("family_context") or {},
        }

        # 标记 PFD 已生成
        pfd_steps = llm_pfd.get("steps") or []
        pfd_pending = sum(1 for s in pfd_steps if s.get("needs_confirmation"))
        chain_stages = _init_chain_stages(
            "generated", pfd_rows=len(pfd_steps), pfd_pending=pfd_pending
        )
        state = DesktopRunState(
            status="needs_review", status_display="待人工确认",
            blocked_stage="", exports=(), manifest_path="", manifest_run_id="",
            manual_review_required=False, manual_review_count=0,
            manual_review_raw_count=0, manual_review_items=(),
            chain_stages=chain_stages,
        )
        return self.save_chain_run(
            project.id, state, project.output_dir, result, "", chain_stages
        )

    def confirm_pfd_stage(
        self,
        run_id: int,
        confirmed_by: str = "",
        edit_patch: dict[str, Any] | None = None,
    ) -> DesktopRunRecord:
        """确认并锁定 PFD，将 PFMEA 标记为后台生成中。"""
        run = self.get_run(run_id)
        current = run.current_result
        chain_stages = _chain_stages_from_run(run)
        current, cumulative_patch, chain_stages = _apply_confirm_edit_patch(
            current, run.edit_patch, edit_patch, chain_stages
        )
        _confirm_chain_table(current, "process_flow", confirmed_by=confirmed_by)
        confirmed_pfd = current.get("process_flow") or {}
        drawing_analysis = current.get("drawing_analysis") or {}

        # 更新 PFD 阶段状态
        now = _utc_now()
        chain_stages = ChainStageStates(
            pfd=StageConfirmState(
                status="confirmed",
                generated_at=chain_stages.pfd.generated_at or now,
                confirmed_at=now,
                confirmed_by=confirmed_by,
                row_count=len(confirmed_pfd.get("steps", [])),
                pending_count=0,
            ),
            pfmea=StageConfirmState(status="running"),
            cp=chain_stages.cp,
            pipeline_mode="chain",
        )

        # 保存 PFD 确认状态
        envelope = _desktop_result_envelope(
            run.raw_result,
            current_result=current,
            edit_patch=cumulative_patch,
        )
        envelope["chain_stages"] = chain_stages.to_dict()
        self._persist_chain_update(run_id, envelope)
        return self.get_run(run_id)

    def generate_pfmea_for_confirmed_pfd(self, run_id: int) -> DesktopRunRecord:
        """Generate PFMEA for an already confirmed PFD."""
        from minos_core.pipeline_chain import generate_pfmea_from_confirmed_pfd
        from minos_desktop.api.sse import create_channel, remove_channel

        run = self.get_run(run_id)
        current = run.current_result
        chain_stages = _chain_stages_from_run(run)
        confirmed_pfd = current.get("process_flow") or {}
        drawing_analysis = current.get("drawing_analysis") or {}
        envelope = _desktop_result_envelope(
            run.raw_result, current_result=current, edit_patch=run.edit_patch
        )

        channel = create_channel(run_id, "pfmea")
        checkpoint_rows: list[dict[str, Any]] = []

        def _save_pfmea_checkpoint() -> None:
            if not checkpoint_rows:
                return
            partial_pfmea = copy.deepcopy(current.get("pfmea") or {})
            partial_pfmea["rows"] = copy.deepcopy(checkpoint_rows)
            metadata = partial_pfmea.setdefault("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
                partial_pfmea["metadata"] = metadata
            metadata["chain_stage_status"] = "partial"
            current["pfmea"] = partial_pfmea
            partial_stages = ChainStageStates(
                pfd=chain_stages.pfd,
                pfmea=StageConfirmState(
                    status="running",
                    generated_at=chain_stages.pfmea.generated_at,
                    row_count=len(checkpoint_rows),
                    pending_count=sum(1 for row in checkpoint_rows if row.get("needs_confirmation")),
                ),
                cp=chain_stages.cp,
                pipeline_mode="chain",
            )
            checkpoint_envelope = _desktop_result_envelope(
                run.raw_result, current_result=current, edit_patch=run.edit_patch
            )
            checkpoint_envelope["chain_stages"] = partial_stages.to_dict()
            self._persist_chain_update(run_id, checkpoint_envelope)

        def _on_progress(event):
            event["run_id"] = run_id
            channel.emit(event)
            if event.get("type") == "step_complete":
                new_rows = event.get("new_rows")
                if isinstance(new_rows, list):
                    checkpoint_rows.extend(row for row in new_rows if isinstance(row, dict))
                    _save_pfmea_checkpoint()

        # 生成 PFMEA
        try:
            pfmea_bundle = generate_pfmea_from_confirmed_pfd(
                drawing_analysis,
                confirmed_pfd,
                on_progress=_on_progress,
            )
        except Exception as exc:
            channel.emit({"type": "error", "stage": "pfmea", "run_id": run_id, "message": str(exc)})
            channel.close()
            remove_channel(run_id, "pfmea")
            failure = format_desktop_failure(exc)
            chain_stages = ChainStageStates(
                pfd=chain_stages.pfd,
                pfmea=StageConfirmState(status="failed"),
                cp=StageConfirmState(status="not_started"),
                pipeline_mode="chain",
            )
            failure_envelope = _desktop_result_envelope(
                run.raw_result, current_result=current, edit_patch=run.edit_patch
            )
            failure_envelope["chain_stages"] = chain_stages.to_dict()
            self._persist_chain_update(run_id, failure_envelope, failure_message=failure)
            return self.get_run(run_id)

        # 合并 PFMEA 到 current_result
        current["pfmea"] = pfmea_bundle
        pfmea_rows = pfmea_bundle.get("rows", [])
        pfmea_pending = sum(1 for r in pfmea_rows if r.get("needs_confirmation"))
        chain_stages = ChainStageStates(
            pfd=chain_stages.pfd,
            pfmea=StageConfirmState(
                status="generated",
                generated_at=_utc_now(),
                row_count=len(pfmea_rows),
                pending_count=pfmea_pending,
            ),
            cp=chain_stages.cp,
            pipeline_mode="chain",
        )
        envelope = _desktop_result_envelope(
            run.raw_result, current_result=current, edit_patch=run.edit_patch
        )
        envelope["chain_stages"] = chain_stages.to_dict()
        self._persist_chain_update(run_id, envelope)
        channel.emit({"type": "done", "stage": "pfmea", "run_id": run_id, "total_rows": len(pfmea_rows), "status": "generated"})
        channel.close()
        remove_channel(run_id, "pfmea")
        return self.get_run(run_id)

    def confirm_pfmea_stage(
        self,
        run_id: int,
        confirmed_by: str = "",
        edit_patch: dict[str, Any] | None = None,
    ) -> DesktopRunRecord:
        """确认并锁定 PFMEA，将 CP 标记为后台生成中。"""
        run = self.get_run(run_id)
        current = run.current_result
        chain_stages = _chain_stages_from_run(run)
        current, cumulative_patch, chain_stages = _apply_confirm_edit_patch(
            current, run.edit_patch, edit_patch, chain_stages
        )
        confirmed_pfd = current.get("process_flow") or {}
        _confirm_chain_table(current, "pfmea", confirmed_by=confirmed_by)
        confirmed_pfmea = current.get("pfmea") or {}
        drawing_analysis = current.get("drawing_analysis") or {}

        # 更新 PFMEA 阶段状态
        now = _utc_now()
        chain_stages = ChainStageStates(
            pfd=chain_stages.pfd,
            pfmea=StageConfirmState(
                status="confirmed",
                generated_at=chain_stages.pfmea.generated_at or now,
                confirmed_at=now,
                confirmed_by=confirmed_by,
                row_count=len(confirmed_pfmea.get("rows", [])),
                pending_count=0,
            ),
            cp=StageConfirmState(status="running"),
            pipeline_mode="chain",
        )

        envelope = _desktop_result_envelope(
            run.raw_result,
            current_result=current,
            edit_patch=cumulative_patch,
        )
        envelope["chain_stages"] = chain_stages.to_dict()
        self._persist_chain_update(run_id, envelope)
        return self.get_run(run_id)

    def generate_cp_for_confirmed_pfmea(self, run_id: int) -> DesktopRunRecord:
        """Generate CP for an already confirmed PFMEA."""
        from minos_core.pipeline_chain import generate_cp_from_confirmed_pfmea
        from minos_desktop.api.sse import create_channel, remove_channel

        run = self.get_run(run_id)
        current = run.current_result
        chain_stages = _chain_stages_from_run(run)
        confirmed_pfd = current.get("process_flow") or {}
        confirmed_pfmea = current.get("pfmea") or {}
        drawing_analysis = current.get("drawing_analysis") or {}
        envelope = _desktop_result_envelope(
            run.raw_result, current_result=current, edit_patch=run.edit_patch
        )

        channel = create_channel(run_id, "cp")

        def _on_progress(event):
            event["run_id"] = run_id
            channel.emit(event)

        # 生成 CP
        try:
            cp_bundle = generate_cp_from_confirmed_pfmea(
                drawing_analysis,
                confirmed_pfd,
                confirmed_pfmea,
                on_progress=_on_progress,
            )
        except Exception as exc:
            channel.emit({"type": "error", "stage": "cp", "run_id": run_id, "message": str(exc)})
            channel.close()
            remove_channel(run_id, "cp")
            failure = format_desktop_failure(exc)
            chain_stages = ChainStageStates(
                pfd=chain_stages.pfd,
                pfmea=chain_stages.pfmea,
                cp=StageConfirmState(status="failed"),
                pipeline_mode="chain",
            )
            envelope["chain_stages"] = chain_stages.to_dict()
            self._persist_chain_update(run_id, envelope, failure_message=failure)
            return self.get_run(run_id)

        # 合并 CP 到 current_result
        current["control_plan"] = cp_bundle
        cp_rows = cp_bundle.get("rows", [])
        cp_pending = sum(1 for r in cp_rows if r.get("needs_confirmation"))
        chain_stages = ChainStageStates(
            pfd=chain_stages.pfd,
            pfmea=chain_stages.pfmea,
            cp=StageConfirmState(
                status="generated",
                generated_at=_utc_now(),
                row_count=len(cp_rows),
                pending_count=cp_pending,
            ),
            pipeline_mode="chain",
        )
        envelope = _desktop_result_envelope(
            run.raw_result, current_result=current, edit_patch=run.edit_patch
        )
        envelope["chain_stages"] = chain_stages.to_dict()
        self._persist_chain_update(run_id, envelope)
        channel.emit({"type": "done", "stage": "cp", "run_id": run_id, "total_rows": len(cp_rows), "status": "generated"})
        channel.close()
        remove_channel(run_id, "cp")
        return self.get_run(run_id)

    def confirm_cp_stage(
        self,
        run_id: int,
        confirmed_by: str = "",
        edit_patch: dict[str, Any] | None = None,
    ) -> DesktopRunRecord:
        """确认并锁定 CP，标记整个链式流程完成。"""
        run = self.get_run(run_id)
        chain_stages = _chain_stages_from_run(run)
        now = _utc_now()
        current = run.current_result
        current, cumulative_patch, chain_stages = _apply_confirm_edit_patch(
            current, run.edit_patch, edit_patch, chain_stages
        )
        _confirm_chain_table(current, "control_plan", confirmed_by=confirmed_by)
        control_plan = current.get("control_plan") or {}
        chain_stages = ChainStageStates(
            pfd=chain_stages.pfd,
            pfmea=chain_stages.pfmea,
            cp=StageConfirmState(
                status="confirmed",
                generated_at=chain_stages.cp.generated_at or now,
                confirmed_at=now,
                confirmed_by=confirmed_by,
                row_count=len(control_plan.get("rows", [])),
                pending_count=0,
            ),
            pipeline_mode="chain",
        )
        current["status"] = "draft_ready"
        from minos_core.automation_review import build_automation_review

        current["automation_review"] = build_automation_review(current)
        envelope = _desktop_result_envelope(
            run.raw_result,
            current_result=current,
            edit_patch=cumulative_patch,
        )
        envelope["chain_stages"] = chain_stages.to_dict()
        self._persist_chain_update(run_id, envelope)
        return self.get_run(run_id)

    def regenerate_pfmea_stage(self, run_id: int) -> DesktopRunRecord:
        """重新生成 PFMEA（用户对当前结果不满意）。"""
        from minos_core.pipeline_chain import generate_pfmea_from_confirmed_pfd
        from minos_desktop.api.sse import create_channel, remove_channel

        run = self.get_run(run_id)
        current = run.current_result
        confirmed_pfd = current.get("process_flow") or {}
        drawing_analysis = current.get("drawing_analysis") or {}

        chain_stages = _chain_stages_from_run(run)
        chain_stages = ChainStageStates(
            pfd=chain_stages.pfd,
            pfmea=StageConfirmState(status="running"),
            cp=chain_stages.cp,
            pipeline_mode="chain",
        )

        channel = create_channel(run_id, "pfmea")
        checkpoint_rows: list[dict[str, Any]] = []

        def _save_pfmea_checkpoint() -> None:
            if not checkpoint_rows:
                return
            partial_pfmea = copy.deepcopy(current.get("pfmea") or {})
            partial_pfmea["rows"] = copy.deepcopy(checkpoint_rows)
            metadata = partial_pfmea.setdefault("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
                partial_pfmea["metadata"] = metadata
            metadata["chain_stage_status"] = "partial"
            current["pfmea"] = partial_pfmea
            partial_stages = ChainStageStates(
                pfd=chain_stages.pfd,
                pfmea=StageConfirmState(
                    status="running",
                    generated_at=chain_stages.pfmea.generated_at,
                    row_count=len(checkpoint_rows),
                    pending_count=sum(1 for row in checkpoint_rows if row.get("needs_confirmation")),
                ),
                cp=chain_stages.cp,
                pipeline_mode="chain",
            )
            checkpoint_envelope = _desktop_result_envelope(
                run.raw_result, current_result=current, edit_patch=run.edit_patch
            )
            checkpoint_envelope["chain_stages"] = partial_stages.to_dict()
            self._persist_chain_update(run_id, checkpoint_envelope)

        def _on_progress(event):
            event["run_id"] = run_id
            channel.emit(event)
            if event.get("type") == "step_complete":
                new_rows = event.get("new_rows")
                if isinstance(new_rows, list):
                    checkpoint_rows.extend(row for row in new_rows if isinstance(row, dict))
                    _save_pfmea_checkpoint()

        try:
            pfmea_bundle = generate_pfmea_from_confirmed_pfd(
                drawing_analysis, confirmed_pfd, on_progress=_on_progress,
            )
        except Exception as exc:
            channel.emit({"type": "error", "stage": "pfmea", "run_id": run_id, "message": str(exc)})
            channel.close()
            remove_channel(run_id, "pfmea")
            failure = format_desktop_failure(exc)
            chain_stages = ChainStageStates(
                pfd=chain_stages.pfd,
                pfmea=StageConfirmState(status="failed"),
                cp=StageConfirmState(status="not_started"),
                pipeline_mode="chain",
            )
            failure_envelope = _desktop_result_envelope(
                run.raw_result, current_result=current, edit_patch=run.edit_patch
            )
            failure_envelope["chain_stages"] = chain_stages.to_dict()
            self._persist_chain_update(run_id, failure_envelope, failure_message=failure)
            return self.get_run(run_id)
        current["pfmea"] = pfmea_bundle
        pfmea_rows = pfmea_bundle.get("rows", [])
        pfmea_pending = sum(1 for r in pfmea_rows if r.get("needs_confirmation"))
        chain_stages = ChainStageStates(
            pfd=chain_stages.pfd,
            pfmea=StageConfirmState(
                status="generated",
                generated_at=_utc_now(),
                row_count=len(pfmea_rows),
                pending_count=pfmea_pending,
            ),
            cp=chain_stages.cp,
            pipeline_mode="chain",
        )
        envelope = _desktop_result_envelope(
            run.raw_result, current_result=current, edit_patch=run.edit_patch
        )
        envelope["chain_stages"] = chain_stages.to_dict()
        self._persist_chain_update(run_id, envelope)
        channel.emit({"type": "done", "stage": "pfmea", "run_id": run_id, "total_rows": len(pfmea_rows), "status": "generated"})
        channel.close()
        remove_channel(run_id, "pfmea")
        return self.get_run(run_id)

    def regenerate_cp_stage(self, run_id: int) -> DesktopRunRecord:
        """重新生成 CP。"""
        from minos_core.pipeline_chain import generate_cp_from_confirmed_pfmea
        from minos_desktop.api.sse import create_channel, remove_channel

        run = self.get_run(run_id)
        current = run.current_result
        confirmed_pfd = current.get("process_flow") or {}
        confirmed_pfmea = current.get("pfmea") or {}
        drawing_analysis = current.get("drawing_analysis") or {}

        chain_stages = _chain_stages_from_run(run)
        chain_stages = ChainStageStates(
            pfd=chain_stages.pfd,
            pfmea=chain_stages.pfmea,
            cp=StageConfirmState(status="running"),
            pipeline_mode="chain",
        )

        channel = create_channel(run_id, "cp")

        def _on_progress(event):
            event["run_id"] = run_id
            channel.emit(event)

        try:
            cp_bundle = generate_cp_from_confirmed_pfmea(
                drawing_analysis, confirmed_pfd, confirmed_pfmea, on_progress=_on_progress,
            )
        except Exception as exc:
            channel.emit({"type": "error", "stage": "cp", "run_id": run_id, "message": str(exc)})
            channel.close()
            remove_channel(run_id, "cp")
            failure = format_desktop_failure(exc)
            chain_stages = ChainStageStates(
                pfd=chain_stages.pfd,
                pfmea=chain_stages.pfmea,
                cp=StageConfirmState(status="failed"),
                pipeline_mode="chain",
            )
            envelope = _desktop_result_envelope(
                run.raw_result, current_result=current, edit_patch=run.edit_patch
            )
            envelope["chain_stages"] = chain_stages.to_dict()
            self._persist_chain_update(run_id, envelope, failure_message=failure)
            return self.get_run(run_id)
        current["control_plan"] = cp_bundle
        cp_rows = cp_bundle.get("rows", [])
        cp_pending = sum(1 for r in cp_rows if r.get("needs_confirmation"))
        chain_stages = ChainStageStates(
            pfd=chain_stages.pfd,
            pfmea=chain_stages.pfmea,
            cp=StageConfirmState(
                status="generated",
                generated_at=_utc_now(),
                row_count=len(cp_rows),
                pending_count=cp_pending,
            ),
            pipeline_mode="chain",
        )
        envelope = _desktop_result_envelope(
            run.raw_result, current_result=current, edit_patch=run.edit_patch
        )
        envelope["chain_stages"] = chain_stages.to_dict()
        self._persist_chain_update(run_id, envelope)
        channel.emit({"type": "done", "stage": "cp", "run_id": run_id, "total_rows": len(cp_rows), "status": "generated"})
        channel.close()
        remove_channel(run_id, "cp")
        return self.get_run(run_id)

    def get_chain_state(self, run_id: int) -> dict[str, Any]:
        """返回当前链式流程状态。"""
        return _chain_stages_from_run(self.get_run(run_id)).to_dict()

    def save_chain_run(
        self,
        project_id: int | None,
        state: DesktopRunState,
        output_dir: str | Path,
        raw_result: dict[str, Any],
        failure_message: str,
        chain_stages: ChainStageStates,
    ) -> DesktopRunRecord:
        """保存链式 run（与 save_run 相同，但 envelope 中包含 chain_stages）。"""
        now = _utc_now()
        exports = {record.name: record.path for record in state.exports}
        envelope = _desktop_result_envelope(
            raw_result,
            current_result=raw_result if failure_message else None,
            edit_patch=None,
        )
        envelope["chain_stages"] = chain_stages.to_dict()
        with self._store.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO runs (
                    project_id, status, blocked_stage, exports_json,
                    manifest_path, manifest_run_id, manual_review_required,
                    manual_review_count, manual_review_json, output_dir,
                    raw_result_json, failure_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id, state.status, state.blocked_stage,
                    _to_json(exports), state.manifest_path, state.manifest_run_id,
                    1 if state.manual_review_required else 0,
                    state.manual_review_count,
                    _to_json(list(state.manual_review_items)),
                    str(output_dir), _to_json(envelope), failure_message, now,
                ),
            )
            run_id = int(cursor.lastrowid)
        if output_dir:
            _write_three_table_result(output_dir, _chain_file_result(envelope))
        return self.get_run(run_id)

    def _persist_chain_update(
        self,
        run_id: int,
        envelope: dict[str, Any],
        failure_message: str = "",
    ) -> None:
        """持久化链式流程更新（更新 runs 表 + 写磁盘）。"""
        current_result = envelope.get("current_result", {})
        chain_stages = _chain_stages_from_envelope(envelope)
        failed_stage = _failed_chain_stage(chain_stages)
        if not failure_message and not failed_stage and isinstance(current_result, dict):
            if str(current_result.get("status") or "") == "failed":
                current_result["status"] = "needs_review"
            if str(current_result.get("blocked_stage") or "") in {"pfd", "pfmea", "cp"}:
                current_result["blocked_stage"] = None
        state = desktop_run_state_from_result(
            current_result if isinstance(current_result, dict) else {}
        )
        if chain_stages is not None:
            state = DesktopRunState(
                status=state.status,
                status_display=state.status_display,
                blocked_stage=state.blocked_stage,
                exports=state.exports,
                manifest_path=state.manifest_path,
                manifest_run_id=state.manifest_run_id,
                manual_review_required=state.manual_review_required,
                manual_review_count=state.manual_review_count,
                manual_review_raw_count=state.manual_review_raw_count,
                manual_review_items=state.manual_review_items,
                chain_stages=chain_stages,
            )
        if failure_message:
            state = DesktopRunState(
                status="failed",
                status_display="失败",
                blocked_stage=failed_stage or state.blocked_stage,
                exports=state.exports,
                manifest_path=state.manifest_path,
                manifest_run_id=state.manifest_run_id,
                manual_review_required=state.manual_review_required,
                manual_review_count=state.manual_review_count,
                manual_review_raw_count=state.manual_review_raw_count,
                manual_review_items=state.manual_review_items,
                chain_stages=chain_stages,
            )
            if isinstance(current_result, dict):
                current_result["status"] = "failed"
                if failed_stage:
                    current_result["blocked_stage"] = failed_stage
        with self._store.connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET status = ?,
                    blocked_stage = ?,
                    exports_json = ?,
                    manifest_path = ?,
                    manifest_run_id = ?,
                    manual_review_required = ?,
                    manual_review_count = ?,
                    manual_review_json = ?,
                    raw_result_json = ?,
                    failure_message = ?
                WHERE id = ?
                """,
                (
                    state.status,
                    state.blocked_stage,
                    _to_json({record.name: record.path for record in state.exports}),
                    state.manifest_path,
                    state.manifest_run_id,
                    1 if state.manual_review_required else 0,
                    state.manual_review_count,
                    _to_json(list(state.manual_review_items)),
                    _to_json(envelope),
                    failure_message,
                    run_id,
                ),
            )
        output_dir = ""
        with self._store.connect() as connection:
            row = connection.execute(
                "SELECT output_dir FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row:
                output_dir = str(row["output_dir"] or "")
        if output_dir:
            _write_three_table_result(output_dir, _chain_file_result(envelope))

    def save_result(
        self,
        project_id: int | None,
        result: dict[str, Any],
        output_dir: str | Path = "",
    ) -> DesktopRunRecord:
        output_dir_text = str(output_dir)
        if output_dir_text:
            _write_three_table_result(output_dir_text, result)
        return self.save_run(
            project_id,
            desktop_run_state_from_result(result),
            output_dir_text,
            _desktop_result_envelope(result),
            "",
        )

    def save_run(
        self,
        project_id: int | None,
        state: DesktopRunState,
        output_dir: str | Path,
        raw_result: dict[str, Any],
        failure_message: str = "",
    ) -> DesktopRunRecord:
        now = _utc_now()
        exports = {record.name: record.path for record in state.exports}
        with self._store.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO runs (
                    project_id,
                    status,
                    blocked_stage,
                    exports_json,
                    manifest_path,
                    manifest_run_id,
                    manual_review_required,
                    manual_review_count,
                    manual_review_json,
                    output_dir,
                    raw_result_json,
                    failure_message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    state.status,
                    state.blocked_stage,
                    _to_json(exports),
                    state.manifest_path,
                    state.manifest_run_id,
                    1 if state.manual_review_required else 0,
                    state.manual_review_count,
                    _to_json(list(state.manual_review_items)),
                    str(output_dir),
                    _to_json(raw_result),
                    failure_message,
                    now,
                ),
            )
            run_id = int(cursor.lastrowid)
        return self.get_run(run_id)

    def get_run(self, run_id: int) -> DesktopRunRecord:
        with self._store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"desktop run not found: {run_id}")
        return _run_from_row(row)

    def list_recent_runs(self, limit: int = 10) -> list[DesktopRunRecord]:
        limit = max(1, int(limit))
        with self._store.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM runs
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_run_from_row(row) for row in rows]

    def restore_run(self, run_id: int) -> DesktopRunRecord:
        return self.get_run(run_id)

    def apply_edit_patch_to_run(
        self,
        run_id: int,
        patch: dict[str, Any],
    ) -> DesktopRunRecord:
        current = self.get_run(run_id)
        stored_payload = _stored_payload_for_run(self._store, run_id)
        stored = _stored_result_parts(stored_payload)
        edit_patch = _normalize_edit_patch(patch)
        updated_result = _apply_edit_patch(stored["current_result"], edit_patch)
        updated_result, chain_stages = _invalidate_chain_after_patch(
            updated_result,
            edit_patch,
            _chain_stages_from_envelope(stored_payload),
        )
        cumulative_patch = _merge_edit_patch(stored.get("edit_patch", {}), edit_patch)
        envelope = _desktop_result_envelope(
            stored["raw_result"],
            current_result=updated_result,
            edit_patch=cumulative_patch,
        )
        if chain_stages is not None:
            envelope["chain_stages"] = chain_stages.to_dict()
        state = desktop_run_state_from_result(updated_result)
        return self._persist_run_update(run_id, state, envelope, current.output_dir)

    def handle_recommendation(
        self,
        run_id: int,
        recommendation_id: str,
        *,
        accept: bool,
        reason: str = "",
    ) -> DesktopRunRecord:
        action = "accept_recommendation" if accept else "ignore_recommendation"
        item = recommendation_action_patch_item(recommendation_id, action, reason=reason)
        return self.apply_edit_patch_to_run(run_id, build_edit_patch([item]))

    def resolve_change_impact(
        self,
        run_id: int,
        item_id: str,
        *,
        status: str = "已处理",
        reason: str = "",
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

    def accept_automation_fix_suggestion(
        self,
        run_id: int,
        row: dict[str, Any],
    ) -> DesktopRunRecord:
        patch = automation_fix_suggestion_patch(row)
        if not patch.get("items"):
            return self.get_run(run_id)
        return self.apply_edit_patch_to_run(run_id, patch)

    def apply_recommendation_to_run(
        self,
        run_id: int,
        recommendation_id: str,
    ) -> DesktopRunRecord:
        """应用知识推荐到 run。"""
        return self.handle_recommendation(run_id, recommendation_id, accept=True)

    def ignore_recommendation_in_run(
        self,
        run_id: int,
        recommendation_id: str,
        reason: str,
    ) -> DesktopRunRecord:
        """忽略知识推荐。"""
        return self.handle_recommendation(run_id, recommendation_id, accept=False, reason=reason)

    def resolve_action_in_run(
        self,
        run_id: int,
        action_id: str,
        changes: dict[str, Any],
        reason: str = "",
    ) -> DesktopRunRecord | None:
        """关闭或忽略行动项。

        返回 None 表示 action_tracking 模块不可用（旧版本兼容）。
        """
        try:
            from minos_core.action_tracking import build_action_items  # noqa: F401
        except ImportError:
            return None
        item: dict[str, Any] = {
            "action": "resolve_action_item",
            "table": "metadata",
            "target_id": action_id,
            "changes": changes,
        }
        if reason:
            item["reason"] = reason
        return self.apply_edit_patch_to_run(run_id, build_edit_patch([item]))

    def review_dashboard(self, run_result: dict) -> dict:
        """返回 review_dashboard，兼容旧版本。

        V1.10 起运行结果可能包含 review_dashboard 字段，其中 status_display
        和 next_actions 可直接用于复核页展示。旧数据没有该字段时返回空 dict。
        """
        return run_result.get("review_dashboard", {}) if isinstance(run_result, dict) else {}

    # ------------------------------------------------------------------
    # V1.11 工作包 E+F：实时预览 / 联动保存 / 撤销重做
    # ------------------------------------------------------------------

    def _persist_run_update(
        self,
        run_id: int,
        state: DesktopRunState,
        envelope: dict[str, Any],
        output_dir: str,
    ) -> DesktopRunRecord:
        """Write updated state + envelope to the runs table (shared by all update paths)."""
        exports = {record.name: record.path for record in state.exports}
        with self._store.connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET status = ?,
                    blocked_stage = ?,
                    exports_json = ?,
                    manifest_path = ?,
                    manifest_run_id = ?,
                    manual_review_required = ?,
                    manual_review_count = ?,
                    manual_review_json = ?,
                    raw_result_json = ?
                WHERE id = ?
                """,
                (
                    state.status,
                    state.blocked_stage,
                    _to_json(exports),
                    state.manifest_path,
                    state.manifest_run_id,
                    1 if state.manual_review_required else 0,
                    state.manual_review_count,
                    _to_json(list(state.manual_review_items)),
                    _to_json(envelope),
                    run_id,
                ),
            )
        if output_dir:
            _write_three_table_result(output_dir, envelope.get("current_result", envelope))
        return self.get_run(run_id)

    def preview_edit_patch_for_run(self, run_id: int, patch: dict) -> dict:
        """预览编辑 patch 的联动影响。"""
        try:
            from minos_core.live_linkage import preview_live_linkage_impacts
        except ImportError:
            return {}
        record = self.get_run(run_id)
        before = record.raw_result
        return preview_live_linkage_impacts(before, patch)

    def apply_live_edit_to_run(
        self,
        run_id: int,
        edit_patch: dict,
        selected_impact_ids: list[str] | None = None,
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
                merged = _apply_edit_patch(before, edit_patch)
                merged = _apply_edit_patch(merged, sync_patch)
                stored_payload = _stored_payload_for_run(self._store, run_id)
                stored = _stored_result_parts(stored_payload)
                merged, chain_stages = _invalidate_chain_after_patch(
                    merged,
                    _merge_edit_patch(edit_patch, sync_patch),
                    _chain_stages_from_envelope(stored_payload),
                )
                envelope = _desktop_result_envelope(
                    stored["raw_result"], current_result=merged,
                    edit_patch=_merge_edit_patch(
                        _merge_edit_patch(stored.get("edit_patch", {}), edit_patch),
                        sync_patch,
                    ),
                )
                if chain_stages is not None:
                    envelope["chain_stages"] = chain_stages.to_dict()
                state = desktop_run_state_from_result(merged)
                return self._persist_run_update(run_id, state, envelope, record.output_dir)

        return self.apply_edit_patch_to_run(run_id, edit_patch)

    def save_with_undo(self, run_id: int, current_result: dict) -> DesktopRunRecord:
        """保存 run current_result 并在撤销栈中保留 DB 快照。

        ``current_result`` 是完整的 three-table result dict。
        每次保存前将当前 run 的存储快照推入 undo 栈，清空 redo 栈，限制栈深度 20。
        """
        current_envelope: dict[str, Any] = {}
        try:
            current_envelope = _stored_payload_for_run(self._store, run_id)
            self._undo_stack.append(copy.deepcopy(current_envelope))
            self._redo_stack.clear()
            if len(self._undo_stack) > 20:
                self._undo_stack.pop(0)
        except KeyError:
            pass  # run does not exist yet; nothing to snapshot

        stored = _stored_result_parts(current_envelope)
        raw_result = stored.get("raw_result", current_result)
        envelope = _desktop_result_envelope(
            raw_result, current_result=current_result,
            edit_patch=stored.get("edit_patch", {}),
        )
        state = desktop_run_state_from_result(current_result)
        record = self.get_run(run_id)
        return self._persist_run_update(run_id, state, envelope, record.output_dir)

    def undo_run(self, run_id: int) -> dict | None:
        """撤销到上一个 DB 快照，返回恢复后的 current_result。"""
        if not self._undo_stack:
            return None
        try:
            current_envelope = _stored_payload_for_run(self._store, run_id)
        except KeyError:
            current_envelope = {}
        self._redo_stack.append(copy.deepcopy(current_envelope))
        previous_envelope = self._undo_stack.pop()
        stored = _stored_result_parts(previous_envelope)
        state = desktop_run_state_from_result(stored["current_result"])
        self._persist_run_update(run_id, state, previous_envelope, "")
        return stored["current_result"]

    def redo_run(self, run_id: int) -> dict | None:
        """重做到下一个 DB 快照，返回恢复后的 current_result。"""
        if not self._redo_stack:
            return None
        try:
            current_envelope = _stored_payload_for_run(self._store, run_id)
        except KeyError:
            current_envelope = {}
        self._undo_stack.append(copy.deepcopy(current_envelope))
        next_envelope = self._redo_stack.pop()
        stored = _stored_result_parts(next_envelope)
        state = desktop_run_state_from_result(stored["current_result"])
        self._persist_run_update(run_id, state, next_envelope, "")
        return stored["current_result"]

    def export_run(
        self,
        run_id: int,
        output_dir: str | Path,
        export_mode: str = "draft",
    ) -> dict[str, Any]:
        if export_mode not in {"draft", "final"}:
            raise ValueError("export_mode must be 'draft' or 'final'")
        record = self.get_run(run_id)
        stored = _stored_result_parts(record.raw_result)
        result = stored["current_result"]
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        exported = _export_edited_three_tables(result, output_path, export_mode)
        return {
            "run_id": run_id,
            "export_mode": export_mode,
            "output_dir": str(output_path),
            "exports": exported.get("exports", exported)
            if isinstance(exported, dict)
            else {"export": str(exported)},
            "quality_gate": _evaluate_edit_export_gate(result),
            "export_result": exported,
        }


def format_desktop_failure(
    error: BaseException | str,
    *,
    reason: str | None = None,
    actions: list[str] | None = None,
) -> str:
    raw = str(error)
    reason_text = reason or _guess_failure_reason(raw)
    action_items = actions or _default_failure_actions(raw)
    if not any("放弃任务" in item for item in action_items):
        action_items.append("放弃任务。")
    return "\n".join(
        [
            f"原始错误：{raw}",
            f"原因判断：{reason_text}",
            "处理方案：",
            *[f"{index}. {item}" for index, item in enumerate(action_items, start=1)],
        ]
    )


def _project_context_value(
    context: dict[str, Any],
    key: str,
    default: str,
) -> str:
    value = str((context or {}).get(key) or default).strip()
    return value or default


def _project_from_row(row: sqlite3.Row) -> DesktopProjectRecord:
    return DesktopProjectRecord(
        id=int(row["id"]),
        project_name=str(row["project_name"]),
        drawing_path=str(row["drawing_path"]),
        output_dir=str(row["output_dir"]),
        context=_from_json_object(str(row["context_json"])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _run_from_row(row: sqlite3.Row) -> DesktopRunRecord:
    exports = _from_json_object(str(row["exports_json"]))
    manual_review_items = _from_json_list(str(row["manual_review_json"]))
    raw_result = _from_json_object(str(row["raw_result_json"]))
    stored = _stored_result_parts(raw_result)
    current_result = copy.deepcopy(stored["current_result"])
    chain_stages = _chain_stages_from_envelope(raw_result)
    failure_message = str(row["failure_message"])
    current_result, chain_stages = _sanitize_legacy_pfmea_placeholders(
        current_result,
        chain_stages,
        failure_message=failure_message,
    )
    if stored.get("edit_patch"):
        current_result["edit_patch"] = stored["edit_patch"]
    state_status = str(row["status"])
    state_blocked_stage = str(row["blocked_stage"])
    if (
        failure_message
        and str(current_result.get("status") or "") == "failed"
        and str(current_result.get("blocked_stage") or "") == "pfmea"
    ):
        state_status = "failed"
        state_blocked_stage = "pfmea"
    state = DesktopRunState(
        status=state_status,
        status_display=_status_display(state_status),
        blocked_stage=state_blocked_stage,
        exports=tuple(
            sorted(
                (
                    DesktopExportRecord(str(name), str(path))
                    for name, path in exports.items()
                ),
                key=lambda item: item.name,
            )
        ),
        manifest_path=str(row["manifest_path"]),
        manifest_run_id=str(row["manifest_run_id"]),
        manual_review_required=bool(row["manual_review_required"]),
        manual_review_count=int(row["manual_review_count"]),
        manual_review_raw_count=int(row["manual_review_count"]),
        manual_review_items=tuple(manual_review_items),
        chain_stages=chain_stages,
    )
    return DesktopRunRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]) if row["project_id"] is not None else None,
        state=state,
        output_dir=str(row["output_dir"]),
        raw_result=current_result,
        failure_message=failure_message,
        created_at=str(row["created_at"]),
        original_result=stored["raw_result"],
        current_result=current_result,
        edit_patch=stored["edit_patch"],
    )


def _stored_payload_for_run(store: DesktopSQLiteStore, run_id: int) -> dict[str, Any]:
    with store.connect() as connection:
        row = connection.execute(
            "SELECT raw_result_json FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"desktop run not found: {run_id}")
    return _from_json_object(str(row["raw_result_json"]))


def _sanitize_legacy_pfmea_placeholders(
    result: dict[str, Any],
    chain_stages: ChainStageStates | None,
    *,
    failure_message: str,
) -> tuple[dict[str, Any], ChainStageStates | None]:
    pfmea = result.get("pfmea") if isinstance(result, dict) else None
    rows = pfmea.get("rows") if isinstance(pfmea, dict) else None
    if not isinstance(rows, list):
        return result, chain_stages
    kept_rows = [row for row in rows if not _is_legacy_pfmea_placeholder(row)]
    removed_count = len(rows) - len(kept_rows)
    if removed_count <= 0:
        return result, chain_stages

    pfmea["rows"] = kept_rows
    if not kept_rows and failure_message:
        result["status"] = "failed"
        result["blocked_stage"] = "pfmea"
        chain_stages = _mark_pfmea_stage_failed(chain_stages)
    return result, chain_stages


def _is_legacy_pfmea_placeholder(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    pfmea_id = str(row.get("pfmea_id") or "").strip()
    failure_mode = str(row.get("failure_mode") or "").strip()
    review_status = str(row.get("review_status") or "").strip()
    return pfmea_id.startswith("PFMEA-SYNC-") or (
        failure_mode == "待工程人员填写失效模式"
        and review_status == "联动新增"
    )


def _mark_pfmea_stage_failed(
    chain_stages: ChainStageStates | None,
) -> ChainStageStates | None:
    if chain_stages is None:
        return None
    return ChainStageStates(
        pfd=chain_stages.pfd,
        pfmea=StageConfirmState(
            status="failed",
            generated_at=chain_stages.pfmea.generated_at,
            confirmed_at=chain_stages.pfmea.confirmed_at,
            confirmed_by=chain_stages.pfmea.confirmed_by,
            row_count=0,
            pending_count=0,
        ),
        cp=chain_stages.cp,
        pipeline_mode=chain_stages.pipeline_mode,
    )


def _seed_knowledge_rules(connection: sqlite3.Connection) -> None:
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


def _knowledge_rule_from_row(row: sqlite3.Row) -> dict[str, Any]:
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


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def _zip_directory(archive: zipfile.ZipFile, directory: Path, prefix: str) -> None:
    if not directory.exists():
        return
    for item in directory.rglob("*"):
        if not item.is_file():
            continue
        try:
            archive.write(item, str(Path(prefix) / item.relative_to(directory)))
        except OSError:
            continue


def _clear_directory_contents(path: Path, *, keep_names: set[str]) -> None:
    if not path.exists():
        return
    for item in path.iterdir():
        if item.name in keep_names:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _guess_failure_reason(message: str) -> str:
    lowered = message.lower()
    if "504" in lowered or "gateway time-out" in lowered or "gateway timeout" in lowered:
        return "AI 上游模型或中转服务响应超时。"
    if "timed out" in lowered or "timeout" in lowered:
        return "AI 模型响应超时或网络链路过慢。"
    if "references unknown evidence" in lowered or "unknown evidence" in lowered:
        return "AI 引用了不存在的图纸页面证据，通常是模型页码引用和实际渲染页数不一致。"
    if "api" in lowered or "key" in lowered:
        return "AI 配置可能缺失或不可用。"
    if "permission" in lowered or "access is denied" in lowered:
        return "输出目录或输入文件可能没有访问权限。"
    if "not found" in lowered or "no such file" in lowered:
        return "输入文件或运行依赖的路径可能不存在。"
    return "不确定。"


def _default_failure_actions(message: str) -> list[str]:
    lowered = message.lower()
    if "504" in lowered or "gateway time-out" in lowered or "gateway timeout" in lowered:
        return [
            "稍后重试失效模式分析生成；当前 PFD 已保留。",
            "如果连续失败，降低文本模型推理强度或切换更稳定的 AI 服务。",
            "放弃任务。",
        ]
    return [
        "检查图纸路径、输出目录权限和 AI 配置后重试。",
        "保留当前项目记录，修正输入后重新运行。",
        "放弃任务。",
    ]


def _status_display(status: str) -> str:
    return {
        "draft_ready": "草案已就绪",
        "needs_review": "待人工复核",
        "blocked": "已阻断",
        "failed": "失败",
    }.get(status, status)


def _first_env_name(names: tuple[str, ...]) -> str:
    import os

    for name in names:
        if os.getenv(name):
            return name
    return ""


def _normalize_ai_base_url(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme == "https":
        return normalized
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return normalized
    raise ValueError("AI 服务地址必须使用 HTTPS；本机 127.0.0.1/localhost 代理可使用 HTTP。")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _desktop_result_envelope(
    raw_result: dict[str, Any],
    *,
    current_result: dict[str, Any] | None = None,
    edit_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_raw = _normalize_three_table_result(raw_result)
    normalized_current = (
        _normalize_three_table_result(current_result)
        if current_result is not None
        else normalized_raw
    )
    return {
        "_desktop_storage_version": 1,
        "raw_result": normalized_raw,
        "current_result": normalized_current,
        "edit_patch": edit_patch
        if edit_patch is not None
        else {"edit_patch_version": EDIT_PATCH_VERSION, "items": []},
    }


def _merge_edit_patch(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = {"edit_patch_version": EDIT_PATCH_VERSION, "items": []}
    for source in (existing, patch):
        items = source.get("items", []) if isinstance(source, dict) else []
        if isinstance(items, list):
            merged["items"].extend(item for item in items if isinstance(item, dict))
    return merged


def _apply_confirm_edit_patch(
    current: dict[str, Any],
    existing_patch: dict[str, Any],
    patch: dict[str, Any] | None,
    chain_stages: ChainStageStates | None = None,
) -> tuple[dict[str, Any], dict[str, Any], ChainStageStates | None]:
    if not patch:
        return current, existing_patch, chain_stages
    edit_patch = _normalize_edit_patch(patch)
    updated = _apply_edit_patch(current, edit_patch)
    updated, updated_stages = _invalidate_chain_after_patch(
        updated, edit_patch, chain_stages
    )
    return updated, _merge_edit_patch(existing_patch, edit_patch), updated_stages


def _stored_result_parts(stored: dict[str, Any]) -> dict[str, Any]:
    if stored.get("_desktop_storage_version") == 1:
        raw_result = stored.get("raw_result", {})
        current_result = stored.get("current_result", raw_result)
        edit_patch = stored.get("edit_patch", {})
        return {
            "raw_result": raw_result if isinstance(raw_result, dict) else {},
            "current_result": current_result if isinstance(current_result, dict) else {},
            "edit_patch": edit_patch if isinstance(edit_patch, dict) else {},
        }
    return {
        "raw_result": stored,
        "current_result": _normalize_three_table_result(stored),
        "edit_patch": {"edit_patch_version": EDIT_PATCH_VERSION, "items": []},
    }


def _normalize_three_table_result(result: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(result or {})
    if any(key in normalized for key in ("process_flow", "pfmea", "control_plan")):
        normalized.setdefault("document_type", "three_table_generation_result")
        normalized.setdefault(
            "schema_version", "minos-core.three_table_generation_result.v1"
        )
        normalized.setdefault("status", "needs_review")
        normalized.setdefault("blocked_stage", None)
        normalized.setdefault("drawing_analysis", {"evidence": []})
        normalized.setdefault("process_flow", {"steps": []})
        normalized.setdefault("pfmea", {"rows": []})
        normalized.setdefault("control_plan", {"rows": []})
        normalized.setdefault("quality_gate", {})
        normalized.setdefault("quality_gates", {})
        normalized.setdefault("exports", {})
        normalized.setdefault("manifest", {})
        normalized.setdefault("manual_review", {"required": False, "items": []})
        normalized.setdefault("warnings", [])
    return normalized


def _normalize_edit_patch(patch: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(patch)
    normalized.setdefault("edit_patch_version", EDIT_PATCH_VERSION)
    items = normalized.get("items", [])
    if not isinstance(items, list):
        normalized["items"] = []
        return normalized
    normalized_items: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            normalized_items.append(item)
            continue
        normalized_item = dict(item)
        if not normalized_item.get("target_id"):
            normalized_item["target_id"] = str(
                normalized_item.get("row_id")
                or _target_id(str(normalized_item.get("target") or ""))
            ).strip()
        normalized_items.append(normalized_item)
    normalized["items"] = normalized_items
    return normalized


def _apply_edit_patch(result: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    try:
        from minos_core.edit_patch import apply_edit_patch
    except ModuleNotFoundError as exc:
        if exc.name not in {"minos_core.edit_patch", "edit_patch"}:
            raise
        return _apply_edit_patch_locally(result, patch)
    updated = apply_edit_patch(result, patch)
    return _apply_desktop_patch_marks(updated, patch)


def _evaluate_edit_export_gate(result: dict[str, Any]) -> dict[str, Any]:
    try:
        from minos_core.edit_patch import evaluate_edit_export_gate
    except ModuleNotFoundError as exc:
        if exc.name not in {"minos_core.edit_patch", "edit_patch"}:
            raise
        return _evaluate_edit_export_gate_locally(result)
    gate = evaluate_edit_export_gate(result)
    if isinstance(gate, dict):
        return gate
    if hasattr(gate, "model_dump"):
        return gate.model_dump()
    if hasattr(gate, "__dict__"):
        return dict(gate.__dict__)
    return {"allow_final_export": bool(gate)}


def _export_edited_three_tables(
    result: dict[str, Any],
    output_dir: Path,
    export_mode: str,
) -> dict[str, Any]:
    try:
        from minos_core.edit_patch import export_edited_three_tables
    except ModuleNotFoundError as exc:
        if exc.name not in {"minos_core.edit_patch", "edit_patch"}:
            raise
        destination = _write_three_table_result(output_dir, result)
        return {"three_table_generation_result": str(destination)}
    exported = export_edited_three_tables(result, output_dir, export_mode=export_mode)
    return exported if isinstance(exported, dict) else {"export": str(exported)}


def _apply_edit_patch_locally(
    result: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    updated = json.loads(json.dumps(result, ensure_ascii=False))
    for item in patch.get("items", []):
        if not isinstance(item, dict):
            continue
        table = str(item.get("table") or "")
        action = str(item.get("action") or "")
        if action in {"accept_recommendation", "ignore_recommendation"}:
            _apply_recommendation_action_locally(updated, item)
            continue
        if action == "resolve_change_impact":
            _apply_change_impact_action_locally(updated, item)
            continue
        if action == "resolve_review_issue":
            _apply_review_issue_action_locally(updated, item)
            continue
        rows = _editable_rows(updated, table)
        row_id_field = _row_id_field(table)
        row_id = str(
            item.get("row_id")
            or item.get("target_id")
            or _target_id(str(item.get("target") or ""))
        )
        if action == "add":
            row = item.get("row", {})
            if isinstance(row, dict):
                rows.append(dict(row))
        elif action == "update":
            row = _find_row(rows, row_id_field, row_id)
            if row is not None:
                changes = item.get("changes", {})
                if not isinstance(changes, dict):
                    changes = item.get("row", {})
                if isinstance(changes, dict):
                    row.update(changes)
        elif action == "soft_delete":
            row = _find_row(rows, row_id_field, row_id)
            if row is not None:
                row["deleted"] = True
                row["soft_deleted"] = True
        elif action == "confirm":
            row = _find_row(rows, row_id_field, row_id)
            if row is not None:
                row["needs_confirmation"] = False
                row["review_status"] = (
                    "已批量确认"
                    if _is_automation_batch_confirm(item)
                    else "已确认"
                )
                row["ai_inferred"] = False
    updated = _apply_desktop_patch_marks(updated, patch)
    updated["edit_patch"] = patch
    updated["quality_gate"] = _evaluate_edit_export_gate_locally(updated)
    return updated


def _apply_desktop_patch_marks(result: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    for item in patch.get("items", []) if isinstance(patch, dict) else []:
        if not isinstance(item, dict) or item.get("action") != "confirm":
            continue
        if not _is_automation_batch_confirm(item):
            continue
        table = str(item.get("table") or "")
        row_id = str(item.get("row_id") or item.get("target_id") or _target_id(str(item.get("target") or "")))
        row = _find_row(_editable_rows(result, table), _row_id_field(table), row_id)
        if row is not None:
            row["review_status"] = "已批量确认"
            row["needs_confirmation"] = False
            row["ai_inferred"] = False
    return result


def _is_automation_batch_confirm(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        return (
            str(metadata.get("confirmation_mode", "")) == "ai_recommended_batch"
            and str(metadata.get("source", "")) == "automation_review"
        )
    return (
        str(item.get("confirmation_mode", "")) == "ai_recommended_batch"
        and str(item.get("source", "")) == "automation_review"
    )


def _can_apply_after_control_plan_automation_review(run: DesktopRunRecord) -> bool:
    chain_stages = _chain_stages_from_run(run)
    if chain_stages.cp.status != "confirmed":
        return False
    review = run.current_result.get("automation_review")
    if not isinstance(review, dict):
        return False
    return (
        review.get("review_stage") == "after_control_plan"
        and review.get("human_decision_priority") is True
    )


def _apply_recommendation_action_locally(result: dict[str, Any], item: dict[str, Any]) -> None:
    metadata = result.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        return
    items = metadata.setdefault("knowledge_recommendations", [])
    if not isinstance(items, list):
        return
    target_id = str(item.get("target_id", ""))
    target = _find_metadata_item(items, "recommendation_id", target_id)
    if target is None:
        target = {"recommendation_id": target_id}
        items.append(target)
    if item.get("action") == "accept_recommendation":
        target["status"] = "已采纳"
    else:
        target["status"] = "已忽略"
        target["ignore_reason"] = str(item.get("reason", ""))


def _apply_change_impact_action_locally(result: dict[str, Any], item: dict[str, Any]) -> None:
    metadata = result.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        return
    items = metadata.setdefault("change_impacts", [])
    if not isinstance(items, list):
        return
    target_id = str(item.get("target_id", ""))
    target = _find_metadata_item(items, "item_id", target_id)
    if target is None:
        target = {"item_id": target_id}
        items.append(target)
    changes = item.get("changes", {})
    target["status"] = changes.get("status", "已处理") if isinstance(changes, dict) else "已处理"
    if str(target.get("status", "")) == "已忽略":
        target["ignore_reason"] = str(item.get("reason", ""))


def _apply_review_issue_action_locally(result: dict[str, Any], item: dict[str, Any]) -> None:
    metadata = result.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        return
    items = metadata.setdefault("review_issues", [])
    if not isinstance(items, list):
        return
    target_id = str(item.get("target_id", ""))
    target = _find_metadata_item(items, "issue_id", target_id)
    if target is None:
        target = {"issue_id": target_id}
        items.append(target)
    changes = item.get("changes", {})
    target["status"] = changes.get("status", "已处理") if isinstance(changes, dict) else "已处理"
    if str(target.get("status", "")) == "已忽略":
        target["ignore_reason"] = str(item.get("reason", ""))


def _evaluate_edit_export_gate_locally(result: dict[str, Any]) -> dict[str, Any]:
    pending: list[str] = []
    for table in ("process_flow", "pfmea", "control_plan"):
        for row in _editable_rows(result, table):
            if row.get("soft_deleted") or row.get("deleted"):
                continue
            if row.get("needs_confirmation"):
                pending.append(f"{_target_prefix(table)}:{row.get(_row_id_field(table), '')}")
    return {
        "allow_final_export": not pending,
        "final_export_allowed": not pending,
        "needs_confirmation_items": pending,
    }


def _editable_rows(result: dict[str, Any], table: str) -> list[dict[str, Any]]:
    document = result.setdefault(table, {})
    if not isinstance(document, dict):
        return []
    key = "steps" if table == "process_flow" else "rows"
    rows = document.setdefault(key, [])
    return rows if isinstance(rows, list) else []


def _row_id_field(table: str) -> str:
    return {
        "process_flow": "process_step_id",
        "pfmea": "pfmea_id",
        "control_plan": "control_plan_id",
    }.get(table, "id")


def _target_prefix(table: str) -> str:
    return {
        "process_flow": "process_step",
        "pfmea": "failure_mode",
        "control_plan": "control_item",
    }.get(table, table)


def _find_row(
    rows: list[dict[str, Any]],
    row_id_field: str,
    row_id: str,
) -> dict[str, Any] | None:
    for row in rows:
        if isinstance(row, dict) and str(row.get(row_id_field, "")) == row_id:
            return row
    return None


def _find_metadata_item(items: list[Any], key: str, value: str) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and str(item.get(key, "")).strip() == value:
            return item
    return None


def _target_id(target: str) -> str:
    return target.split(":", 1)[1] if ":" in target else target


def _write_three_table_result(output_dir: str | Path, result: dict[str, Any]) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / "three_table_generation_result.json"
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination


def _from_json_object(value: str) -> dict[str, Any]:
    data = json.loads(value or "{}")
    return data if isinstance(data, dict) else {}


def _from_json_list(value: str) -> list[Any]:
    data = json.loads(value or "[]")
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# 链式流程辅助函数
# ---------------------------------------------------------------------------

def _init_chain_stages(
    pfd_status: str = "not_started",
    *,
    pfd_rows: int = 0,
    pfd_pending: int = 0,
) -> ChainStageStates:
    """创建初始的链式阶段状态。"""
    return init_chain_stages(
        pfd_status,
        pfd_rows=pfd_rows,
        pfd_pending=pfd_pending,
        now=_utc_now(),
    )


def _chain_stages_from_run(run: DesktopRunRecord) -> ChainStageStates:
    """从 DesktopRunRecord 提取链式阶段状态。"""
    if run.state.chain_stages is not None:
        return run.state.chain_stages
    return ChainStageStates(pipeline_mode="batch")


def _chain_stages_from_envelope(envelope: dict[str, Any]) -> ChainStageStates | None:
    """从存储 envelope 中解析链式阶段状态。"""
    return chain_stages_from_envelope(envelope)


def _chain_file_result(envelope: dict[str, Any]) -> dict[str, Any]:
    result = envelope.get("current_result", envelope)
    if not isinstance(result, dict):
        result = {}
    result = copy.deepcopy(result)
    chain_stages = envelope.get("chain_stages")
    if isinstance(chain_stages, dict):
        result["chain_stages"] = copy.deepcopy(chain_stages)
        result["pipeline_mode"] = chain_stages.get("pipeline_mode", "chain")
    return result


def _confirm_chain_table(
    result: dict[str, Any],
    table: str,
    *,
    confirmed_by: str = "",
) -> None:
    confirm_chain_table(result, table, confirmed_by=confirmed_by)


def _failed_chain_stage(chain_stages: ChainStageStates | None) -> str:
    return failed_chain_stage(chain_stages)


def _invalidate_chain_after_patch(
    result: dict[str, Any],
    patch: dict[str, Any],
    chain_stages: ChainStageStates | None,
) -> tuple[dict[str, Any], ChainStageStates | None]:
    """Invalidate downstream staged outputs when an upstream table changes."""
    return invalidate_chain_after_patch(result, patch, chain_stages)


def _changed_chain_tables(patch: dict[str, Any]) -> set[str]:
    tables: set[str] = set()
    items = patch.get("items", [])
    if not isinstance(items, list):
        return tables
    for item in items:
        if not isinstance(item, dict):
            continue
        table = str(item.get("table") or "").strip()
        action = str(item.get("action") or "").strip()
        if table not in {"process_flow", "pfmea", "control_plan"}:
            continue
        if action in {"add", "update", "soft_delete"}:
            tables.add(table)
    return tables


def _table_row_count(result: dict[str, Any], table: str) -> int:
    return table_row_count(result, table)


def _pending_row_count(result: dict[str, Any], table: str) -> int:
    return pending_row_count(result, table)


def _table_rows_for_chain(result: dict[str, Any], table: str) -> list[Any]:
    return table_rows_for_chain(result, table)


def _dedupe_texts(values: list[Any]) -> list[str]:
    return _chain_dedupe_texts(values)
