import io
import builtins
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from minos_desktop.app_state import (
    DESKTOP_PAGES,
    DesktopProjectState,
    desktop_run_state_from_result,
    summarize_generation_result,
)
from minos_desktop.cli import main
from minos_desktop.qt_app import build_export_summary, build_settings_status
from minos_desktop.services import (
    DesktopKnowledgeStore,
    DesktopProjectStore,
    DesktopRunService,
    DesktopSettingsStore,
    format_desktop_failure,
)
from minos_desktop.table_editor import ROW_STATUS_COLUMN, three_table_to_table_model


class DesktopShellTests(unittest.TestCase):
    def test_desktop_pages_match_three_table_workflow(self):
        self.assertEqual(
            [page.key for page in DESKTOP_PAGES],
            [
                "project",
                "drawing_import",
                "drawing_analysis",
                "pfd",
                "pfmea",
                "control_plan",
                "actions",
                "change_impacts",
                "knowledge",
                "automation_review",
                "review",
                "export",
                "settings",
            ],
        )

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

    def test_desktop_run_service_records_formatted_failure(self):
        def failing_runner(*args, **kwargs):
            raise RuntimeError("OPENAI_API_KEY missing")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            project = DesktopProjectStore(db_path).create_project(
                DesktopProjectState(
                    project_name="失败项目",
                    drawing_path="drawing.pdf",
                    output_dir=tmpdir,
                )
            )
            run = DesktopRunService(db_path, runner=failing_runner).run_project(project)

        self.assertEqual(run.state.status, "failed")
        self.assertIn("原始错误：OPENAI_API_KEY missing", run.failure_message)
        self.assertIn("原因判断：AI 配置可能缺失或不可用。", run.failure_message)
        self.assertIn("放弃任务", run.failure_message)

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

    def test_automation_batch_confirm_service_marks_low_risk_rows(self):
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
                                "review_status": "AI建议确认",
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

            updated = run_service.batch_confirm_automation_review(run.id)
            model = three_table_to_table_model(updated.current_result, "process_flow")

        self.assertFalse(updated.current_result["process_flow"]["steps"][0]["needs_confirmation"])
        self.assertEqual(updated.current_result["process_flow"]["steps"][0]["review_status"], "已批量确认")
        self.assertEqual(model["rows"][0][ROW_STATUS_COLUMN], "已批量确认")
        self.assertEqual(updated.edit_patch["items"][0]["confirmation_mode"], "ai_recommended_batch")

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

    def test_desktop_ai_settings_status_uses_chinese_model_labels(self):
        with patch.dict(
            os.environ,
            {
                "MINOS_OPENAI_API_KEY": "secret-value",
                "MINOS_OPENAI_MODEL": "gpt-acceptance",
                "MINOS_DISABLE_CODEX_CONFIG": "1",
            },
            clear=True,
        ):
            status = build_settings_status()

        self.assertEqual(status["模型"], "gpt-acceptance")
        self.assertTrue(status["模型已配置"])
        self.assertEqual(status["模型来源"], "MINOS_OPENAI_MODEL")
        self.assertNotIn("secret-value", str(status))

    def test_export_summary_reports_final_export_blockers_and_allowed_state(self):
        blocked = build_export_summary(
            {
                "status": "needs_review",
                "manual_review": {"required": True, "items": [{"id": "MR-1"}]},
                "quality_gate": {
                    "final_export_allowed": False,
                    "needs_confirmation_items": ["pfmea:PFMEA-P10-001"],
                },
            }
        )
        allowed = build_export_summary(
            {
                "status": "draft_ready",
                "manual_review": {"required": False, "items": []},
                "quality_gate": {"final_export_allowed": True},
            }
        )

        self.assertFalse(blocked["正式导出允许"])
        self.assertEqual(blocked["质量门"]["待确认项"], ["pfmea:PFMEA-P10-001"])
        self.assertTrue(allowed["正式导出允许"])

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

    def test_desktop_cli_reports_missing_pyside6_without_breaking_core_tests(self):
        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "minos_desktop.qt_app" or (level == 1 and name == "qt_app"):
                raise ModuleNotFoundError("No module named 'PySide6'", name="PySide6")
            return real_import(name, globals, locals, fromlist, level)

        buffer = io.StringIO()
        with patch("builtins.__import__", side_effect=fake_import):
            with redirect_stdout(buffer):
                code = main([])

        self.assertEqual(code, 2)
        self.assertIn("PySide6 is not installed", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
