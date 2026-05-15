import os
import tempfile
import unittest
from unittest.mock import patch

from minos_desktop.app_state import (
    ChainStageStates,
    DesktopProjectState,
    DesktopRunState,
    StageConfirmState,
    desktop_run_state_from_result,
    summarize_generation_result,
)
from minos_desktop.api.schemas import settings_to_dict
from minos_desktop.services import (
    DesktopKnowledgeStore,
    DesktopProjectStore,
    DesktopRunService,
    DesktopSettingsStore,
    format_desktop_failure,
)
from minos_desktop.table_editor import (
    ROW_STATUS_COLUMN,
    build_edit_patch,
    three_table_to_table_model,
)


class DesktopShellTests(unittest.TestCase):
    def test_generation_result_summary_extracts_export_and_review_state(self):
        summary = summarize_generation_result(
            {
                "status": "needs_review",
                "blocked_stage": None,
                "exports": {
                    "unified_workbook": "out/三表总工作簿.xlsx",
                    "pfmea": "out/PFMEA.xlsx",
                },
                "manifest": {"path": "out/run_manifest.json"},
                "manual_review": {"required": True, "items": ["PFMEA-P10-001"]},
            }
        )

        self.assertEqual(summary.status, "needs_review")
        self.assertEqual(summary.status_display, "待人工复核")
        self.assertEqual(summary.exports["pfmea"], "out/PFMEA.xlsx")
        self.assertEqual(summary.manifest_path, "out/run_manifest.json")
        self.assertTrue(summary.manual_review_required)
        self.assertEqual(summary.manual_review_count, 1)
        self.assertEqual(summary.manual_review_raw_count, 1)

    def test_desktop_run_state_extracts_manifest_exports_and_manual_review(self):
        state = desktop_run_state_from_result(
            {
                "status": "blocked",
                "blocked_stage": "pfmea",
                "exports": {"pfmea": "out/PFMEA.xlsx"},
                "manifest": {"path": "out/run_manifest.json", "run_id": "run-001"},
                "manual_review": {"required": True, "items": [{"id": "MR-1"}]},
            }
        )

        self.assertEqual(state.status, "blocked")
        self.assertEqual(state.status_display, "已阻断")
        self.assertEqual(state.blocked_stage, "pfmea")
        self.assertEqual(state.exports[0].name, "pfmea")
        self.assertEqual(state.manifest_path, "out/run_manifest.json")
        self.assertEqual(state.manifest_run_id, "run-001")
        self.assertTrue(state.manual_review_required)
        self.assertEqual(state.manual_review_count, 1)

    def test_sqlite_settings_projects_and_runs_round_trip_without_qt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            settings = DesktopSettingsStore(db_path)
            project_store = DesktopProjectStore(db_path)
            run_service = DesktopRunService(db_path)

            self.assertEqual(settings.get_default_output_dir(), "out\\desktop")
            settings.set_default_output_dir(os.path.join(tmpdir, "out"))
            self.assertEqual(settings.get_default_output_dir(), os.path.join(tmpdir, "out"))

            project = project_store.create_project(
                DesktopProjectState(
                    project_name="测试项目",
                    drawing_path="drawing.pdf",
                    context={"part_no": "A-001"},
                )
            )
            self.assertEqual(project.output_dir, os.path.join(tmpdir, "out"))
            updated = project_store.update_project(
                project.id,
                drawing_path="updated.pdf",
                context={"part_no": "A-002"},
            )
            self.assertEqual(updated.drawing_path, "updated.pdf")
            self.assertEqual(updated.context["part_no"], "A-002")

            run = run_service.save_result(
                project.id,
                {
                    "status": "needs_review",
                    "blocked_stage": None,
                    "exports": {"unified_workbook": "out/book.xlsx"},
                    "manifest": {
                        "path": "out/run_manifest.json",
                        "run_id": "run-002",
                    },
                    "manual_review": {"required": True, "items": ["MR-1", "MR-2"]},
                },
                updated.output_dir,
            )

            loaded = run_service.get_run(run.id)
            self.assertEqual(loaded.project_id, project.id)
            self.assertEqual(loaded.state.status, "needs_review")
            self.assertEqual(loaded.state.status_display, "待人工复核")
            self.assertEqual(loaded.state.manifest_run_id, "run-002")
            self.assertEqual(loaded.state.manual_review_count, 2)
            self.assertEqual(loaded.raw_result["status"], "needs_review")
            self.assertTrue(os.path.exists(os.path.join(updated.output_dir, "three_table_generation_result.json")))

    def test_run_project_compat_entry_uses_chain_and_records_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            project = DesktopProjectStore(db_path).create_project(
                DesktopProjectState(
                    project_name="失败项目",
                    drawing_path="drawing.pdf",
                    output_dir=tmpdir,
                )
            )
            with patch(
                "minos_desktop.services.analyze_drawing_for_three_table_chain",
                side_effect=RuntimeError("OPENAI_API_KEY missing"),
            ):
                run = DesktopRunService(db_path).run_project(project)

        self.assertEqual(run.state.status, "failed")
        self.assertEqual(run.state.chain_stages.pipeline_mode, "chain")
        self.assertIn("原始错误：OPENAI_API_KEY missing", run.failure_message)
        self.assertIn("原因判断：AI 配置可能缺失或不可用。", run.failure_message)
        self.assertIn("放弃任务", run.failure_message)

    def test_chain_start_records_pfd_generation_failure_without_batch_fallback(self):
        analysis_result = {
            "drawing_analysis": {
                "document_type": "drawing_analysis_bundle",
                "drawing_identity": {"part_name": "尾门铰链"},
                "metadata": {},
            },
            "drawing_gate": type("Gate", (), {"can_continue": True, "model_dump": lambda self: {"ok": True}})(),
            "part_family_classification": {"family_key": "door_hinge"},
            "family_context": {"family_key": "door_hinge"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            project = DesktopProjectStore(db_path).create_project(
                DesktopProjectState(
                    project_name="链式项目",
                    drawing_path="drawing.pdf",
                    output_dir=tmpdir,
                    context={"analysis_mode": "ocr_only"},
                )
            )
            with patch(
                "minos_desktop.services.analyze_drawing_for_three_table_chain",
                return_value=analysis_result,
            ) as analyze_mock:
                with patch(
                    "minos_core.pipeline_chain.generate_pfd_from_drawing",
                    side_effect=RuntimeError("PFD LLM failed"),
                ):
                    run = DesktopRunService(db_path).start_chain_run(project)

        self.assertEqual(run.state.status, "failed")
        self.assertEqual(run.state.blocked_stage, "pfd")
        self.assertIn("PFD LLM failed", run.failure_message)
        self.assertIn("放弃任务", run.failure_message)
        self.assertEqual(run.current_result["process_flow"], {"steps": []})
        analyze_mock.assert_called_once()

    def test_pfd_confirm_returns_immediately_and_pfmea_generation_runs_separately(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="generated", row_count=1, pending_count=1),
                pipeline_mode="chain",
            )
            run = service.save_chain_run(
                None,
                DesktopRunState(
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
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "drawing_analysis": {"drawing_identity": {"part_name": "尾门铰链"}},
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                chain_stages,
            )

            with patch(
                "minos_core.pipeline_chain.generate_pfmea_from_confirmed_pfd",
                side_effect=AssertionError("PFMEA generation must not run inside confirm"),
            ):
                confirmed = service.confirm_pfd_stage(run.id, confirmed_by="qe")

            self.assertEqual(confirmed.state.chain_stages.pfd.status, "confirmed")
            self.assertEqual(confirmed.state.chain_stages.pfmea.status, "running")
            self.assertEqual(confirmed.current_result["pfmea"], {"rows": []})
            self.assertEqual(
                confirmed.current_result["process_flow"]["steps"][0]["review_status"],
                "已确认",
            )

            def fake_generate_pfmea(_drawing_analysis, confirmed_pfd):
                return {
                    "rows": [
                        {
                            "pfmea_id": "F1",
                            "process_step_id": "P10",
                            "operation_seen_by_pfmea": confirmed_pfd["steps"][0]["operation"],
                        }
                    ]
                }

            with patch(
                "minos_core.pipeline_chain.generate_pfmea_from_confirmed_pfd",
                fake_generate_pfmea,
            ):
                generated = service.generate_pfmea_for_confirmed_pfd(run.id)

            self.assertEqual(generated.state.chain_stages.pfmea.status, "generated")
            self.assertEqual(generated.current_result["pfmea"]["rows"][0]["pfmea_id"], "F1")

    def test_background_pfmea_generation_failure_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=1),
                pfmea=StageConfirmState(status="running"),
                pipeline_mode="chain",
            )
            run = service.save_chain_run(
                None,
                DesktopRunState(
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
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "drawing_analysis": {},
                    "process_flow": {"steps": [{"process_step_id": "P10"}]},
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                chain_stages,
            )

            with patch(
                "minos_core.pipeline_chain.generate_pfmea_from_confirmed_pfd",
                side_effect=RuntimeError("PFMEA background failed"),
            ):
                failed = service.generate_pfmea_for_confirmed_pfd(run.id)

        self.assertEqual(failed.state.status, "failed")
        self.assertEqual(failed.state.blocked_stage, "pfmea")
        self.assertEqual(failed.state.chain_stages.pfmea.status, "failed")
        self.assertIn("PFMEA background failed", failed.failure_message)

    def test_legacy_pfmea_sync_placeholders_are_hidden_when_generation_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=1),
                pfmea=StageConfirmState(status="generated", row_count=1, pending_count=1),
                pipeline_mode="chain",
            )
            raw_result = {
                "document_type": "three_table_generation_result",
                "status": "needs_review",
                "process_flow": {
                    "steps": [
                        {
                            "process_step_id": "P10",
                            "operation": "来料检验",
                            "needs_confirmation": False,
                        }
                    ]
                },
                "pfmea": {"rows": []},
                "control_plan": {"rows": []},
                "manual_review": {"required": False, "items": []},
            }
            current_result = {
                **raw_result,
                "pfmea": {
                    "rows": [
                        {
                            "pfmea_id": "PFMEA-SYNC-P10",
                            "process_step_id": "P10",
                            "failure_mode": "待工程人员填写失效模式",
                            "review_status": "联动新增",
                            "needs_confirmation": True,
                        }
                    ]
                },
            }
            legacy_envelope = {
                "_desktop_storage_version": 1,
                "raw_result": raw_result,
                "current_result": current_result,
                "edit_patch": {"edit_patch_version": "minos-core.edit_patch.v1", "items": []},
                "chain_stages": chain_stages.to_dict(),
            }
            run = service.save_run(
                None,
                DesktopRunState(
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
                ),
                tmpdir,
                legacy_envelope,
                "原始错误：LLM Responses HTTP 504 Gateway Time-out",
            )
            reloaded = service.get_run(run.id)

        self.assertEqual(reloaded.current_result["pfmea"]["rows"], [])
        self.assertEqual(reloaded.state.status, "failed")
        self.assertEqual(reloaded.state.blocked_stage, "pfmea")
        self.assertEqual(reloaded.state.chain_stages.pfmea.status, "failed")
        self.assertEqual(reloaded.state.chain_stages.pfmea.row_count, 0)
        self.assertEqual(reloaded.state.chain_stages.pfmea.pending_count, 0)
        self.assertEqual(reloaded.current_result["status"], "failed")
        self.assertEqual(reloaded.current_result["blocked_stage"], "pfmea")
        self.assertIn("504 Gateway Time-out", reloaded.failure_message)

    def test_background_cp_generation_failure_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=1),
                pfmea=StageConfirmState(status="confirmed", row_count=1),
                cp=StageConfirmState(status="running"),
                pipeline_mode="chain",
            )
            run = service.save_chain_run(
                None,
                DesktopRunState(
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
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "drawing_analysis": {},
                    "process_flow": {"steps": [{"process_step_id": "P10"}]},
                    "pfmea": {"rows": [{"pfmea_id": "F1", "process_step_id": "P10"}]},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                chain_stages,
            )

            with patch(
                "minos_core.pipeline_chain.generate_cp_from_confirmed_pfmea",
                side_effect=RuntimeError("CP background failed"),
            ):
                failed = service.generate_cp_for_confirmed_pfmea(run.id)

        self.assertEqual(failed.state.status, "failed")
        self.assertEqual(failed.state.blocked_stage, "cp")
        self.assertEqual(failed.state.chain_stages.cp.status, "failed")
        self.assertIn("CP background failed", failed.failure_message)

    def test_process_flow_edit_invalidates_downstream_chain_stages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=1),
                pfmea=StageConfirmState(status="confirmed", row_count=1),
                cp=StageConfirmState(status="generated", row_count=1),
                pipeline_mode="chain",
            )
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "status": "needs_review",
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "needs_confirmation": False,
                            }
                        ]
                    },
                    "pfmea": {"rows": [{"pfmea_id": "F1", "process_step_id": "P10"}]},
                    "control_plan": {"rows": [{"control_plan_id": "C1", "process_step_id": "P10"}]},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                chain_stages,
            )
            updated = run_service.apply_edit_patch_to_run(
                run.id,
                build_edit_patch(
                    [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target_id": "P10",
                            "changes": {"operation": "更新后的工序"},
                        }
                    ]
                ),
            )

        self.assertEqual(updated.current_result["pfmea"], {"rows": []})
        self.assertEqual(updated.current_result["control_plan"], {"rows": []})
        self.assertEqual(updated.state.chain_stages.pfd.status, "generated")
        self.assertEqual(updated.state.chain_stages.pfmea.status, "not_started")
        self.assertEqual(updated.state.chain_stages.cp.status, "not_started")
        self.assertIn(
            "pfmea",
            updated.current_result["metadata"]["chain_invalidated_stages"],
        )
        self.assertIn(
            "control_plan",
            updated.current_result["metadata"]["chain_invalidated_stages"],
        )

    def test_pfmea_edit_invalidates_control_plan_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=1),
                pfmea=StageConfirmState(status="confirmed", row_count=1),
                cp=StageConfirmState(status="confirmed", row_count=1),
                pipeline_mode="chain",
            )
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "status": "needs_review",
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "process_flow": {"steps": [{"process_step_id": "P10"}]},
                    "pfmea": {
                        "rows": [
                            {
                                "pfmea_id": "F1",
                                "process_step_id": "P10",
                                "failure_mode": "尺寸偏差",
                            }
                        ]
                    },
                    "control_plan": {"rows": [{"control_plan_id": "C1", "process_step_id": "P10"}]},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                chain_stages,
            )
            updated = run_service.apply_edit_patch_to_run(
                run.id,
                build_edit_patch(
                    [
                        {
                            "action": "update",
                            "table": "pfmea",
                            "target_id": "F1",
                            "changes": {"failure_mode": "孔位偏差"},
                        }
                    ]
                ),
            )

        self.assertEqual(updated.current_result["control_plan"], {"rows": []})
        self.assertEqual(updated.state.chain_stages.pfd.status, "confirmed")
        self.assertEqual(updated.state.chain_stages.pfmea.status, "generated")
        self.assertEqual(updated.state.chain_stages.cp.status, "not_started")
        self.assertEqual(
            updated.current_result["metadata"]["chain_invalidated_stages"],
            ["control_plan"],
        )

    def test_confirm_pfd_marks_rows_confirmed_and_generates_pfmea(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "status": "needs_review",
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "drawing_analysis": {},
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "needs_confirmation": True,
                                "ai_inferred": True,
                            }
                        ]
                    },
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                ChainStageStates(
                    pfd=StageConfirmState(status="generated", row_count=1, pending_count=1),
                    pipeline_mode="chain",
                ),
            )
            updated = run_service.confirm_pfd_stage(run.id, confirmed_by="qe")

        step = updated.current_result["process_flow"]["steps"][0]
        self.assertFalse(step["needs_confirmation"])
        self.assertFalse(step["ai_inferred"])
        self.assertEqual(step["review_status"], "已确认")
        self.assertEqual(step["confirmed_by"], "qe")
        self.assertEqual(updated.state.chain_stages.pfd.status, "confirmed")
        self.assertEqual(updated.state.chain_stages.pfmea.status, "running")
        self.assertEqual(updated.current_result["pfmea"], {"rows": []})

    def test_confirm_pfd_applies_edit_patch_before_generating_pfmea(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "status": "needs_review",
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "drawing_analysis": {},
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "原始工序",
                                "needs_confirmation": True,
                                "ai_inferred": True,
                            }
                        ]
                    },
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                ChainStageStates(
                    pfd=StageConfirmState(status="generated", row_count=1, pending_count=1),
                    pipeline_mode="chain",
                ),
            )
            updated = run_service.confirm_pfd_stage(
                run.id,
                confirmed_by="qe",
                edit_patch=build_edit_patch(
                    [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target_id": "P10",
                            "changes": {"operation": "修改后的工序"},
                        }
                    ]
                ),
            )

        step = updated.current_result["process_flow"]["steps"][0]
        self.assertEqual(step["operation"], "修改后的工序")
        self.assertEqual(step["review_status"], "已确认")
        self.assertEqual(step["confirmed_by"], "qe")
        self.assertEqual(updated.state.chain_stages.pfd.status, "confirmed")
        self.assertEqual(updated.state.chain_stages.pfmea.status, "running")
        self.assertEqual(updated.current_result["pfmea"], {"rows": []})

    def test_confirm_pfd_with_edit_patch_drops_stale_control_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "status": "needs_review",
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "drawing_analysis": {},
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "原始工序",
                                "needs_confirmation": True,
                                "ai_inferred": True,
                            }
                        ]
                    },
                    "pfmea": {
                        "rows": [
                            {
                                "pfmea_id": "OLD-F1",
                                "process_step_id": "P10",
                                "failure_mode": "旧失效模式",
                            }
                        ]
                    },
                    "control_plan": {
                        "rows": [
                            {
                                "control_plan_id": "OLD-C1",
                                "pfmea_id": "OLD-F1",
                                "control_method": "旧控制方法",
                            }
                        ]
                    },
                    "manual_review": {"required": False, "items": []},
                },
                "",
                ChainStageStates(
                    pfd=StageConfirmState(status="generated", row_count=1, pending_count=1),
                    pfmea=StageConfirmState(status="confirmed", row_count=1),
                    cp=StageConfirmState(status="confirmed", row_count=1),
                    pipeline_mode="chain",
                ),
            )
            updated = run_service.confirm_pfd_stage(
                run.id,
                confirmed_by="qe",
                edit_patch=build_edit_patch(
                    [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target_id": "P10",
                            "changes": {"operation": "修改后的工序"},
                        }
                    ]
                ),
            )

        self.assertEqual(updated.current_result["pfmea"], {"rows": []})
        self.assertEqual(updated.current_result["control_plan"], {"rows": []})
        self.assertEqual(updated.state.chain_stages.pfmea.status, "running")
        self.assertEqual(updated.state.chain_stages.cp.status, "not_started")

    def test_regenerate_pfmea_clears_previous_failed_run_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_chain_run(
                None,
                DesktopRunState(
                    status="failed",
                    status_display="失败",
                    blocked_stage="pfmea",
                    exports=(),
                    manifest_path="",
                    manifest_run_id="",
                    manual_review_required=False,
                    manual_review_count=0,
                    manual_review_raw_count=0,
                    chain_stages=ChainStageStates(
                        pfd=StageConfirmState(status="confirmed", row_count=1),
                        pfmea=StageConfirmState(status="failed"),
                        pipeline_mode="chain",
                    ),
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "failed",
                    "blocked_stage": "pfmea",
                    "drawing_analysis": {},
                    "process_flow": {"steps": [{"process_step_id": "P10"}]},
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                "原始错误：PFMEA failed",
                ChainStageStates(
                    pfd=StageConfirmState(status="confirmed", row_count=1),
                    pfmea=StageConfirmState(status="failed"),
                    pipeline_mode="chain",
                ),
            )
            with patch(
                "minos_core.pipeline_chain.generate_pfmea_from_confirmed_pfd",
                return_value={
                    "rows": [
                        {
                            "pfmea_id": "F1",
                            "process_step_id": "P10",
                            "needs_confirmation": False,
                        }
                    ]
                },
            ):
                updated = run_service.regenerate_pfmea_stage(run.id)

        self.assertEqual(updated.state.status, "needs_review")
        self.assertEqual(updated.failure_message, "")
        self.assertEqual(updated.state.chain_stages.pfmea.status, "generated")
        self.assertEqual(updated.current_result["blocked_stage"], None)

    def test_desktop_failure_explains_unknown_drawing_evidence_refs(self):
        report = format_desktop_failure(
            "materials[0].evidence_refs references unknown evidence: drawing_page_003"
        )

        self.assertIn("drawing_page_003", report)
        self.assertIn("AI 引用了不存在的图纸页面证据", report)
        self.assertIn("实际渲染页数不一致", report)
        self.assertIn("放弃任务", report)

    def test_apply_edit_patch_to_run_round_trips_current_result_and_patch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_result(
                None,
                {
                    "status": "needs_review",
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "Before",
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": True, "items": []},
                },
                tmpdir,
            )

            updated = run_service.apply_edit_patch_to_run(
                run.id,
                {
                    "items": [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target": "process_step:P10",
                            "row_id": "P10",
                            "changes": {"operation": "After"},
                        },
                        {
                            "action": "confirm",
                            "table": "process_flow",
                            "target": "process_step:P10",
                            "row_id": "P10",
                        },
                    ]
                },
            )
            reloaded = DesktopRunService(db_path).get_run(run.id)

        self.assertEqual(
            updated.raw_result["process_flow"]["steps"][0]["operation"],
            "After",
        )
        self.assertFalse(updated.raw_result["process_flow"]["steps"][0]["needs_confirmation"])
        self.assertEqual(
            reloaded.current_result["process_flow"]["steps"][0]["operation"],
            "After",
        )
        self.assertEqual(
            reloaded.original_result["process_flow"]["steps"][0]["operation"],
            "Before",
        )
        self.assertEqual(len(reloaded.edit_patch["items"]), 2)

    def test_automation_batch_confirm_waits_until_cp_confirmed_and_after_control_plan_review_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=1),
                pfmea=StageConfirmState(status="confirmed", row_count=1),
                cp=StageConfirmState(status="generated", row_count=1, pending_count=1),
                pipeline_mode="chain",
            )
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "document_type": "three_table_generation_result",
                        "status": "needs_review",
                        "process_flow": {"steps": []},
                        "pfmea": {"rows": []},
                        "control_plan": {"rows": []},
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "review_status": "AI建议确认",
                                "needs_confirmation": False,
                                "evidence_refs": ["EV-1"],
                                "confidence": 0.95,
                            }
                        ]
                    },
                    "pfmea": {
                        "rows": [
                            {
                                "pfmea_id": "PFMEA-P10-OK",
                                "process_step_id": "P10",
                                "failure_mode": "来料错误",
                                "failure_effect": "返工",
                                "severity": 3,
                                "occurrence": 2,
                                "detection": 2,
                                "rpn": 12,
                                "action_priority": "L",
                                "review_status": "AI建议确认",
                                "needs_confirmation": False,
                                "evidence_refs": ["EV-1"],
                                "confidence": 0.95,
                            }
                        ]
                    },
                    "control_plan": {
                        "rows": [
                            {
                                "control_plan_id": "CP-P10-OK",
                                "process_step_id": "P10",
                                "pfmea_id": "PFMEA-P10-OK",
                                "control_method": "来料检验",
                                "review_status": "AI建议确认",
                                "needs_confirmation": True,
                                "evidence_refs": ["EV-1"],
                                "confidence": 0.95,
                            }
                        ]
                    },
                    "drawing_analysis": {"evidence": [{"evidence_id": "EV-1"}]},
                    "manual_review": {"required": True, "items": []},
                },
                "",
                chain_stages,
            )

            blocked = run_service.batch_confirm_automation_review(run.id)

            confirmed = run_service.confirm_cp_stage(run.id, confirmed_by="qe")
            updated = run_service.batch_confirm_automation_review(run.id)
            model = three_table_to_table_model(updated.current_result, "pfmea")

        self.assertNotIn("automation_review", blocked.current_result)
        self.assertEqual(blocked.edit_patch["items"], [])
        self.assertEqual(
            blocked.current_result["pfmea"]["rows"][0]["review_status"],
            "AI建议确认",
        )
        self.assertEqual(
            confirmed.current_result["automation_review"]["review_stage"],
            "after_control_plan",
        )
        self.assertTrue(confirmed.current_result["automation_review"]["human_decision_priority"])
        self.assertFalse(updated.current_result["pfmea"]["rows"][0]["needs_confirmation"])
        self.assertEqual(updated.current_result["pfmea"]["rows"][0]["review_status"], "已批量确认")
        self.assertEqual(model["rows"][0][ROW_STATUS_COLUMN], "已批量确认")
        self.assertEqual(
            updated.edit_patch["items"][0]["metadata"]["confirmation_mode"],
            "ai_recommended_batch",
        )

    def test_pfd_soft_delete_reload_hides_pfmea_and_cp_rows_until_restored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_result(
                None,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "process_function": "确认来料状态",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "pfmea": {
                        "rows": [
                            {
                                "pfmea_id": "PFMEA-P10-001",
                                "process_step_id": "P10",
                                "failure_mode": "来料错误",
                                "failure_effect": "不合格流出",
                                "severity": 6,
                                "failure_cause": "标识未确认",
                                "occurrence": 3,
                                "prevention_control": "批次隔离",
                                "detection_control": "首件确认",
                                "detection": 4,
                                "action_priority": "L",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "control_plan": {
                        "rows": [
                            {
                                "control_plan_id": "CP-P10-001",
                                "process_step_id": "P10",
                                "pfmea_id": "PFMEA-P10-001",
                                "product_process_characteristic": "来料状态",
                                "specification": "按图纸",
                                "measurement_method": "目视",
                                "sample_frequency": "每批",
                                "control_method": "来料检验",
                                "reaction_plan": "隔离",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "drawing_analysis": {"evidence": [{"evidence_id": "EV-1", "content": "fixture"}]},
                    "manual_review": {"required": True, "items": []},
                },
                tmpdir,
            )

            run_service.apply_edit_patch_to_run(
                run.id,
                {
                    "items": [
                        {
                            "action": "soft_delete",
                            "table": "process_flow",
                            "target": "process_step:P10",
                            "row_id": "P10",
                        }
                    ]
                },
            )
            reloaded = DesktopRunService(db_path).get_run(run.id)

            pfmea_model = three_table_to_table_model(reloaded.current_result, "pfmea")
            cp_model = three_table_to_table_model(reloaded.current_result, "control_plan")

            self.assertEqual(pfmea_model["rows"], [])
            self.assertEqual(cp_model["rows"], [])

            run_service.apply_edit_patch_to_run(
                run.id,
                {
                    "items": [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target": "process_step:P10",
                            "row_id": "P10",
                            "changes": {"deleted": False, "soft_deleted": False},
                        }
                    ]
                },
            )
            restored = DesktopRunService(db_path).get_run(run.id)
            restored_pfmea_model = three_table_to_table_model(restored.current_result, "pfmea")
            restored_cp_model = three_table_to_table_model(restored.current_result, "control_plan")

            self.assertEqual(restored_pfmea_model["rows"][0]["pfmea_id"], "PFMEA-P10-001")
            self.assertEqual(restored_cp_model["rows"][0]["control_plan_id"], "CP-P10-001")
            self.assertTrue(
                all(
                    item.get("status") in {"无影响", "已处理", "已忽略"}
                    for item in restored.current_result["metadata"].get("change_impacts", [])
                )
            )

    def test_metadata_patch_actions_accumulate_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_result(
                None,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "process_function": "确认来料状态",
                                "equipment": "旧检验台",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "pfmea": {
                        "rows": [
                            {
                                "pfmea_id": "PFMEA-P10-001",
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "process_step": "来料检验",
                                "function_requirement": "确认来料状态",
                                "process_work_element": "旧检验台",
                                "failure_mode": "来料错误",
                                "failure_effect": "不合格流出",
                                "severity": 6,
                                "failure_cause": "标识未确认",
                                "occurrence": 3,
                                "prevention_control": "批次隔离",
                                "detection_control": "首件确认",
                                "detection": 4,
                                "action_priority": "L",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "control_plan": {"rows": []},
                    "drawing_analysis": {"evidence": [{"evidence_id": "EV-1", "content": "fixture"}]},
                    "manual_review": {"required": True, "items": []},
                },
                tmpdir,
            )

            run_service.apply_edit_patch_to_run(
                run.id,
                {
                    "items": [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target": "process_step:P10",
                            "row_id": "P10",
                            "changes": {
                                "operation": "来料检验-已修改",
                                "process_function": "确认材料和版本已更新",
                                "equipment": "更新后的检验台",
                            },
                        }
                    ]
                },
            )
            reloaded = DesktopRunService(db_path).get_run(run.id)

        pfmea_model = three_table_to_table_model(reloaded.current_result, "pfmea")

        self.assertEqual(pfmea_model["rows"][0]["operation"], "来料检验-已修改")
        self.assertEqual(pfmea_model["rows"][0]["process_step"], "来料检验-已修改")
        self.assertEqual(pfmea_model["rows"][0]["function_requirement"], "确认材料和版本已更新")
        self.assertEqual(pfmea_model["rows"][0]["process_work_element"], "更新后的检验台")

    def test_metadata_patch_actions_accumulate_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            result = {
                "status": "needs_review",
                "process_flow": {"steps": []},
                "pfmea": {"rows": []},
                "control_plan": {"rows": []},
                "metadata": {
                    "knowledge_recommendations": [
                        {"recommendation_id": "KR-1", "status": "待确认"}
                    ],
                    "change_impacts": [
                        {"item_id": "CI-1", "status": "待同步"}
                    ],
                },
                "manual_review": {"required": True, "items": []},
            }
            run = run_service.save_result(None, result, tmpdir)

            run_service.handle_recommendation(
                run.id,
                "KR-1",
                accept=False,
                reason="已有等效控制",
            )
            updated = run_service.resolve_change_impact(run.id, "CI-1")
            reloaded = DesktopRunService(db_path).get_run(run.id)

        metadata = updated.raw_result["metadata"]
        self.assertEqual(metadata["knowledge_recommendations"][0]["status"], "已忽略")
        self.assertEqual(metadata["change_impacts"][0]["status"], "已处理")
        self.assertEqual(len(reloaded.edit_patch["items"]), 2)

    def test_knowledge_store_seeds_adds_and_disables_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            store = DesktopKnowledgeStore(db_path)

            seeded = store.list_rules()
            added = store.add_rule(
                rule_id="LOCAL-1",
                category="失效模式库",
                title="压装不到位",
                payload={"rule_id": "LOCAL-1", "message": "考虑压装不到位"},
            )
            disabled = store.disable_rule("LOCAL-1")

        self.assertTrue(seeded)
        self.assertEqual(added["title"], "压装不到位")
        self.assertFalse(disabled["enabled"])

    def test_export_run_returns_flat_export_paths_and_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_result(
                None,
                {
                    "status": "needs_review",
                    "process_flow": {"steps": []},
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                tmpdir,
            )

            result = run_service.export_run(run.id, os.path.join(tmpdir, "export"), "draft")

        self.assertEqual(result["export_mode"], "draft")
        self.assertIn("unified_workbook", result["exports"])
        self.assertIn("quality_gate", result)

    def test_desktop_api_settings_dict_does_not_expose_plain_api_key(self):
        with patch.dict(
            os.environ,
            {
                "MINOS_OPENAI_API_KEY": "secret-value",
                "MINOS_OPENAI_MODEL": "gpt-acceptance",
                "MINOS_DISABLE_CODEX_CONFIG": "1",
            },
            clear=True,
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                store = DesktopSettingsStore(os.path.join(tmpdir, "desktop.sqlite3"))
                settings = settings_to_dict(
                    store.get_default_output_dir(),
                    store.get_ai_config_state(),
                )

        self.assertEqual(settings["ai_config"]["model"], "gpt-acceptance")
        self.assertTrue(settings["ai_config"]["model_configured"])
        self.assertEqual(settings["ai_config"]["model_source"], "MINOS_OPENAI_MODEL")
        self.assertNotIn("secret-value", str(settings))

    def test_recent_runs_list_and_restore_latest_current_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            first = run_service.save_result(
                None,
                {
                    "status": "needs_review",
                    "process_flow": {"steps": [{"process_step_id": "P10", "operation": "First"}]},
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": True, "items": []},
                },
                tmpdir,
            )
            second = run_service.save_result(
                None,
                {
                    "status": "draft_ready",
                    "process_flow": {"steps": [{"process_step_id": "P20", "operation": "Second"}]},
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                tmpdir,
            )

            recent = run_service.list_recent_runs(limit=1)
            restored = run_service.restore_run(first.id)

        self.assertEqual(recent[0].id, second.id)
        self.assertEqual(
            restored.raw_result["process_flow"]["steps"][0]["operation"],
            "First",
        )

    def test_ai_config_state_does_not_expose_plain_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "MINOS_OPENAI_API_KEY": "secret-value",
                    "MINOS_OPENAI_MODEL": "gpt-test",
                    "MINOS_OPENAI_BASE_URL": "https://proxy.example/v1",
                    "MINOS_DISABLE_CODEX_CONFIG": "1",
                },
                clear=True,
            ):
                state = DesktopSettingsStore(
                    os.path.join(tmpdir, "desktop.sqlite3")
                ).get_ai_config_state()

        self.assertTrue(state.api_key_configured)
        self.assertEqual(state.api_key_source, "environment")
        self.assertEqual(state.api_key_env_name, "MINOS_OPENAI_API_KEY")
        self.assertEqual(state.model, "gpt-test")
        self.assertEqual(state.model_source, "MINOS_OPENAI_MODEL")
        self.assertEqual(state.base_url, "https://proxy.example/v1")
        self.assertEqual(state.base_url_source, "MINOS_OPENAI_BASE_URL")
        self.assertEqual(state.responses_path, "responses")
        self.assertNotIn("secret-value", repr(state))

    def test_failure_formatter_includes_required_sections_and_abandon_option(self):
        message = format_desktop_failure(
            "Access is denied",
            actions=["换一个输出目录。"],
        )

        self.assertIn("原始错误：Access is denied", message)
        self.assertIn("原因判断：输出目录或输入文件可能没有访问权限。", message)
        self.assertIn("处理方案：", message)
        self.assertIn("放弃任务", message)

    def test_failure_formatter_identifies_gateway_timeout(self):
        message = format_desktop_failure("LLM Responses HTTP 504 Gateway Time-out")

        self.assertIn("原始错误：LLM Responses HTTP 504 Gateway Time-out", message)
        self.assertIn("原因判断：AI 上游模型或中转服务响应超时。", message)
        self.assertIn("稍后重试", message)

if __name__ == "__main__":
    unittest.main()
