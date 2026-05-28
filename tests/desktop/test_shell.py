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


class TestDesktopShell(unittest.TestCase):
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
                "minos_desktop.services.run_service.analyze_drawing_for_three_table_chain",
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
                "minos_desktop.services.run_service.analyze_drawing_for_three_table_chain",
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

    def test_desktop_failure_explains_unknown_drawing_evidence_refs(self):
        report = format_desktop_failure(
            "materials[0].evidence_refs references unknown evidence: drawing_page_003"
        )

        self.assertIn("drawing_page_003", report)
        self.assertIn("AI 引用了不存在的图纸页面证据", report)
        self.assertIn("实际渲染页数不一致", report)
        self.assertIn("放弃任务", report)

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
