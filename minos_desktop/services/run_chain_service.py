"""Desktop run responsibility service."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from ..app_state import (
    ChainStageStates,
    DesktopProjectRecord,
    DesktopRunRecord,
    DesktopRunState,
    StageConfirmState,
    desktop_run_state_from_result,
)
from .history_store import DesktopHistoryStore
from .run_chain import _desktop_result_envelope, format_desktop_failure
from .run_edit_helpers import (
    _apply_confirm_edit_patch,
)
from .run_repository import RunRepository
from .run_shared import (
    _chain_file_result,
    _chain_stages_from_envelope,
    _chain_stages_from_run,
    _confirm_chain_table,
    _failed_chain_stage,
    _init_chain_stages,
    _project_context_value,
    _write_three_table_result,
)
from .sqlite_store import _utc_now


class ChainGenerationService:
    def __init__(self, repository: RunRepository, history: DesktopHistoryStore) -> None:
        self.repository = repository
        self.history = history
        self._store = repository.store

    def _get_configured_model(self) -> str | None:
        """Resolve the user-configured LLM model for chain generation."""
        try:
            from minos_core.ai_config import load_openai_responses_config

            config = load_openai_responses_config()
            return config.model
        except Exception:
            return None

    def start_chain_run(
        self,
        project: DesktopProjectRecord,
        *,
        analyzer: Any,
    ) -> DesktopRunRecord:
        """链式流程入口：图纸分析 + LLM 生成 PFD（仅第一步）。

        只运行图纸识别阶段，然后用 LLM 生成 PFD；不会偷偷一次性生成三表。
        """
        from minos_core.pipeline_chain import generate_pfd_from_drawing

        analysis_mode = _project_context_value(project.context, "analysis_mode", "hybrid")
        ocr_engine = _project_context_value(project.context, "ocr_engine", "mineru")
        analysis_context = dict(project.context)
        if analysis_mode == "hybrid":
            analysis_context.setdefault("special_characteristic_judge_enabled", True)
        try:
            analysis_result = analyzer(
                project.drawing_path,
                project.output_dir,
                context=analysis_context,
                analysis_mode=analysis_mode,
                ocr_engine=ocr_engine,
                component_drawings=list(project.component_drawings) if project.component_drawings else None,
            )
        except (OSError, ValueError, TypeError, RuntimeError, KeyError, AttributeError) as exc:
            failure = format_desktop_failure(exc)
            chain_stages = _init_chain_stages("failed")
            state = DesktopRunState(
                status="failed",
                status_display="失败",
                blocked_stage="pfd",
                exports=(),
                manifest_path="",
                manifest_run_id="",
                manual_review_required=False,
                manual_review_count=0,
                manual_review_raw_count=0,
                chain_stages=chain_stages,
            )
            return self.save_chain_run(project.id, state, project.output_dir, {}, failure, chain_stages)
        drawing_analysis = analysis_result.get("drawing_analysis") or {}
        if isinstance(drawing_analysis, dict):
            drawing_analysis.setdefault("_part_family", analysis_result.get("part_family_classification") or {})
            drawing_analysis.setdefault("_family_context", analysis_result.get("family_context") or {})
        drawing_gate = analysis_result.get("drawing_gate")
        if drawing_gate is not None and (not drawing_gate.can_continue):
            failure = format_desktop_failure("图纸识别质量门未通过，不能生成 PFD。")
            chain_stages = _init_chain_stages("failed")
            state = DesktopRunState(
                status="failed",
                status_display="失败",
                blocked_stage="drawing_recognition",
                exports=(),
                manifest_path="",
                manifest_run_id="",
                manual_review_required=False,
                manual_review_count=0,
                manual_review_raw_count=0,
                chain_stages=chain_stages,
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
            llm_pfd = generate_pfd_from_drawing(drawing_analysis, model=self._get_configured_model())
        except (OSError, ValueError, TypeError, RuntimeError, KeyError, AttributeError) as exc:
            failure = format_desktop_failure(exc)
            chain_stages = _init_chain_stages("failed")
            state = DesktopRunState(
                status="failed",
                status_display="失败",
                blocked_stage="pfd",
                exports=(),
                manifest_path="",
                manifest_run_id="",
                manual_review_required=False,
                manual_review_count=0,
                manual_review_raw_count=0,
                chain_stages=chain_stages,
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
        pfd_steps = llm_pfd.get("steps") or []
        pfd_pending = sum(1 for s in pfd_steps if s.get("needs_confirmation"))
        chain_stages = _init_chain_stages("generated", pfd_rows=len(pfd_steps), pfd_pending=pfd_pending)
        state = DesktopRunState(
            status="needs_review",
            status_display="待人工确认",
            blocked_stage="",
            exports=(),
            manifest_path="",
            manifest_run_id="",
            manual_review_required=False,
            manual_review_count=0,
            manual_review_raw_count=0,
            manual_review_items=(),
            chain_stages=chain_stages,
        )
        return self.save_chain_run(project.id, state, project.output_dir, result, "", chain_stages)

    def confirm_pfd_stage(
        self, run_id: int, confirmed_by: str = "", edit_patch: dict[str, Any] | None = None
    ) -> DesktopRunRecord:
        """确认并锁定 PFD，将 PFMEA 标记为后台生成中。"""
        run = self.get_run(run_id)
        current = run.current_result
        chain_stages = _chain_stages_from_run(run)
        current, cumulative_patch, updated_chain_stages = _apply_confirm_edit_patch(
            current, run.edit_patch, edit_patch, chain_stages
        )
        if updated_chain_stages is not None:
            chain_stages = updated_chain_stages
        _confirm_chain_table(current, "process_flow", confirmed_by=confirmed_by)
        confirmed_pfd = current.get("process_flow") or {}
        current.get("drawing_analysis") or {}
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
        envelope = _desktop_result_envelope(run.raw_result, current_result=current, edit_patch=cumulative_patch)
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
        envelope = _desktop_result_envelope(run.raw_result, current_result=current, edit_patch=run.edit_patch)
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

        def _on_progress(event: dict[str, Any]) -> None:
            event["run_id"] = run_id
            channel.emit(event)
            if event.get("type") == "step_complete":
                new_rows = event.get("new_rows")
                if isinstance(new_rows, list):
                    checkpoint_rows.extend(row for row in new_rows if isinstance(row, dict))
                    _save_pfmea_checkpoint()

        try:
            pfmea_bundle = generate_pfmea_from_confirmed_pfd(
                drawing_analysis, confirmed_pfd, on_progress=_on_progress, model=self._get_configured_model()
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
                status="generated", generated_at=_utc_now(), row_count=len(pfmea_rows), pending_count=pfmea_pending
            ),
            cp=chain_stages.cp,
            pipeline_mode="chain",
        )
        envelope = _desktop_result_envelope(run.raw_result, current_result=current, edit_patch=run.edit_patch)
        envelope["chain_stages"] = chain_stages.to_dict()
        self._persist_chain_update(run_id, envelope)
        channel.emit(
            {"type": "done", "stage": "pfmea", "run_id": run_id, "total_rows": len(pfmea_rows), "status": "generated"}
        )
        channel.close()
        remove_channel(run_id, "pfmea")
        return self.get_run(run_id)

    def confirm_pfmea_stage(
        self, run_id: int, confirmed_by: str = "", edit_patch: dict[str, Any] | None = None
    ) -> DesktopRunRecord:
        """确认并锁定 PFMEA，将 CP 标记为后台生成中。"""
        run = self.get_run(run_id)
        current = run.current_result
        chain_stages = _chain_stages_from_run(run)
        current, cumulative_patch, updated_chain_stages = _apply_confirm_edit_patch(
            current, run.edit_patch, edit_patch, chain_stages
        )
        if updated_chain_stages is not None:
            chain_stages = updated_chain_stages
        current.get("process_flow") or {}
        _confirm_chain_table(current, "pfmea", confirmed_by=confirmed_by)
        confirmed_pfmea = current.get("pfmea") or {}
        current.get("drawing_analysis") or {}
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
        envelope = _desktop_result_envelope(run.raw_result, current_result=current, edit_patch=cumulative_patch)
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
        envelope = _desktop_result_envelope(run.raw_result, current_result=current, edit_patch=run.edit_patch)
        channel = create_channel(run_id, "cp")

        def _on_progress(event: dict[str, Any]) -> None:
            event["run_id"] = run_id
            channel.emit(event)

        try:
            cp_bundle = generate_cp_from_confirmed_pfmea(
                drawing_analysis,
                confirmed_pfd,
                confirmed_pfmea,
                on_progress=_on_progress,
                model=self._get_configured_model(),
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
        current["control_plan"] = cp_bundle
        cp_rows = cp_bundle.get("rows", [])
        cp_pending = sum(1 for r in cp_rows if r.get("needs_confirmation"))
        chain_stages = ChainStageStates(
            pfd=chain_stages.pfd,
            pfmea=chain_stages.pfmea,
            cp=StageConfirmState(
                status="generated", generated_at=_utc_now(), row_count=len(cp_rows), pending_count=cp_pending
            ),
            pipeline_mode="chain",
        )
        envelope = _desktop_result_envelope(run.raw_result, current_result=current, edit_patch=run.edit_patch)
        envelope["chain_stages"] = chain_stages.to_dict()
        self._persist_chain_update(run_id, envelope)
        channel.emit(
            {"type": "done", "stage": "cp", "run_id": run_id, "total_rows": len(cp_rows), "status": "generated"}
        )
        channel.close()
        remove_channel(run_id, "cp")
        return self.get_run(run_id)

    def confirm_cp_stage(
        self, run_id: int, confirmed_by: str = "", edit_patch: dict[str, Any] | None = None
    ) -> DesktopRunRecord:
        """确认并锁定 CP，标记整个链式流程完成。"""
        run = self.get_run(run_id)
        chain_stages = _chain_stages_from_run(run)
        now = _utc_now()
        current = run.current_result
        current, cumulative_patch, updated_chain_stages = _apply_confirm_edit_patch(
            current, run.edit_patch, edit_patch, chain_stages
        )
        if updated_chain_stages is not None:
            chain_stages = updated_chain_stages
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
        from minos_core.edit_patch import _refresh_three_table_result

        current["automation_review"] = build_automation_review(current)
        current = _refresh_three_table_result(current)
        envelope = _desktop_result_envelope(run.raw_result, current_result=current, edit_patch=cumulative_patch)
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
            pfd=chain_stages.pfd, pfmea=StageConfirmState(status="running"), cp=chain_stages.cp, pipeline_mode="chain"
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

        def _on_progress(event: dict[str, Any]) -> None:
            event["run_id"] = run_id
            channel.emit(event)
            if event.get("type") == "step_complete":
                new_rows = event.get("new_rows")
                if isinstance(new_rows, list):
                    checkpoint_rows.extend(row for row in new_rows if isinstance(row, dict))
                    _save_pfmea_checkpoint()

        try:
            pfmea_bundle = generate_pfmea_from_confirmed_pfd(
                drawing_analysis, confirmed_pfd, on_progress=_on_progress, model=self._get_configured_model()
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
                status="generated", generated_at=_utc_now(), row_count=len(pfmea_rows), pending_count=pfmea_pending
            ),
            cp=chain_stages.cp,
            pipeline_mode="chain",
        )
        envelope = _desktop_result_envelope(run.raw_result, current_result=current, edit_patch=run.edit_patch)
        envelope["chain_stages"] = chain_stages.to_dict()
        self._persist_chain_update(run_id, envelope)
        channel.emit(
            {"type": "done", "stage": "pfmea", "run_id": run_id, "total_rows": len(pfmea_rows), "status": "generated"}
        )
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

        def _on_progress(event: dict[str, Any]) -> None:
            event["run_id"] = run_id
            channel.emit(event)

        try:
            cp_bundle = generate_cp_from_confirmed_pfmea(
                drawing_analysis,
                confirmed_pfd,
                confirmed_pfmea,
                on_progress=_on_progress,
                model=self._get_configured_model(),
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
            envelope = _desktop_result_envelope(run.raw_result, current_result=current, edit_patch=run.edit_patch)
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
                status="generated", generated_at=_utc_now(), row_count=len(cp_rows), pending_count=cp_pending
            ),
            pipeline_mode="chain",
        )
        envelope = _desktop_result_envelope(run.raw_result, current_result=current, edit_patch=run.edit_patch)
        envelope["chain_stages"] = chain_stages.to_dict()
        self._persist_chain_update(run_id, envelope)
        channel.emit(
            {"type": "done", "stage": "cp", "run_id": run_id, "total_rows": len(cp_rows), "status": "generated"}
        )
        channel.close()
        remove_channel(run_id, "cp")
        return self.get_run(run_id)

    def get_run(self, run_id: int) -> DesktopRunRecord:
        return self.repository.get_run(run_id)

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
        envelope = _desktop_result_envelope(
            raw_result, current_result=raw_result if failure_message else None, edit_patch=None
        )
        envelope["chain_stages"] = chain_stages.to_dict()
        record = self.repository.insert_run(project_id, state, output_dir, envelope, failure_message)
        if output_dir:
            _write_three_table_result(output_dir, _chain_file_result(envelope))
        return record

    def _persist_chain_update(self, run_id: int, envelope: dict[str, Any], failure_message: str = "") -> None:
        """持久化链式流程更新（更新 runs 表 + 写磁盘）。"""
        current_result = envelope.get("current_result", {})
        chain_stages = _chain_stages_from_envelope(envelope)
        failed_stage = _failed_chain_stage(chain_stages)
        if not failure_message and (not failed_stage) and isinstance(current_result, dict):
            if str(current_result.get("status") or "") == "failed":
                current_result["status"] = "needs_review"
            if str(current_result.get("blocked_stage") or "") in {"pfd", "pfmea", "cp"}:
                current_result["blocked_stage"] = None
        state = desktop_run_state_from_result(current_result if isinstance(current_result, dict) else {})
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
        self.repository.update_run(run_id, state, envelope, failure_message=failure_message)
        output_dir = self.repository.get_output_dir(run_id)
        if output_dir:
            _write_three_table_result(output_dir, _chain_file_result(envelope))
