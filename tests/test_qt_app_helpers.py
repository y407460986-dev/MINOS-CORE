import unittest
from unittest.mock import patch

from minos_desktop.qt_app import (
    build_export_action_summary,
    build_export_summary,
    build_failure_report,
    build_settings_status,
    _recent_run_label,
    _display_manual_review,
)
from minos_desktop.app_state import DesktopRunRecord, DesktopRunState


class QtAppHelperTests(unittest.TestCase):
    def test_failure_report_keeps_raw_error_and_required_options(self):
        report = build_failure_report("FileNotFoundError: no such file: drawing.pdf")

        self.assertIn("FileNotFoundError: no such file: drawing.pdf", report)
        self.assertIn("原因判断", report)
        self.assertIn("放弃任务", report)

    def test_failure_report_explains_unknown_drawing_evidence_refs(self):
        report = build_failure_report(
            "materials[0].evidence_refs references unknown evidence: drawing_page_003"
        )

        self.assertIn("drawing_page_003", report)
        self.assertIn("AI 引用了不存在的图纸页面证据", report)
        self.assertIn("实际渲染页数不一致", report)

    def test_settings_status_masks_plaintext_key(self):
        with patch.dict(
            "os.environ",
            {
                "MINOS_OPENAI_MODEL": "gpt-test",
                "MINOS_OPENAI_BASE_URL": "https://example.test/v1",
                "MINOS_OPENAI_API_KEY": "sk-secret",
                "MINOS_DISABLE_CODEX_CONFIG": "1",
            },
            clear=True,
        ):
            status = build_settings_status()

        self.assertEqual(status["模型"], "gpt-test")
        self.assertEqual(status["接口地址"], "https://example.test/v1")
        self.assertTrue(status["API Key 已配置"])
        self.assertEqual(status["API Key 来源"], "environment")
        self.assertEqual(status["API Key 环境变量"], "MINOS_OPENAI_API_KEY")
        self.assertNotIn("sk-secret", repr(status))

    def test_export_summary_exposes_workbooks_manifest_and_hashes(self):
        summary = build_export_summary(
            {
                "status": "needs_review",
                "blocked_stage": None,
                "exports": {
                    "unified_workbook": "out/三表总工作簿.xlsx",
                    "process_flow": "out/三表独立文件/PFD.xlsx",
                    "pfmea": "out/三表独立文件/PFMEA.xlsx",
                    "control_plan": "out/三表独立文件/CP.xlsx",
                },
                "manifest": {
                    "path": "out/run_manifest.json",
                    "artifact_hashes": {"pfmea": "abc123"},
                },
                "quality_gate": {
                    "allow_final_export": False,
                    "needs_confirmation_items": ["failure_mode:PFMEA-P10-001"],
                },
                "manual_review": {"required": True, "items": ["check"]},
            }
        )

        self.assertEqual(summary["三表总工作簿"], "out/三表总工作簿.xlsx")
        self.assertEqual(summary["状态"], "待人工复核")
        self.assertEqual(summary["三表独立文件"]["PFMEA"], "out/三表独立文件/PFMEA.xlsx")
        self.assertEqual(summary["运行清单路径"], "out/run_manifest.json")
        self.assertEqual(summary["文件哈希"]["pfmea"], "abc123")
        self.assertEqual(summary["人工复核摘要项数"], 1)
        self.assertEqual(summary["内部明细复核项数"], 1)
        self.assertFalse(summary["正式导出允许"])
        self.assertEqual(
            summary["质量门"]["待确认项"],
            ["failure_mode:PFMEA-P10-001"],
        )

    def test_manual_review_display_uses_chinese_keys(self):
        display = _display_manual_review(
            {
                "manual_review": {"required": True, "items": ["check"], "raw_count": 3},
                "quality_gate": {"needs_confirmation_items": ["process_step:P10"]},
            }
        )

        self.assertTrue(display["需要人工复核"])
        self.assertEqual(display["问题列表"][0]["详情"], "check")
        self.assertEqual(display["问题列表"][1]["对象"], "process_step:P10")
        self.assertEqual(display["原始明细数量"], 3)

    def test_export_action_summary_uses_chinese_keys(self):
        summary = build_export_action_summary(
            {
                "run_id": 7,
                "export_mode": "final",
                "output_dir": "out/final",
                "exports": {"unified_workbook": "out/final/三表总工作簿.xlsx"},
                "quality_gate": {"allow_final_export": True},
            }
        )

        self.assertEqual(summary["运行记录编号"], 7)
        self.assertEqual(summary["导出模式"], "正式")
        self.assertEqual(summary["输出目录"], "out/final")
        self.assertEqual(summary["质量门"]["允许正式导出"], True)

    def test_recent_run_label_is_readable_for_restore_list(self):
        record = DesktopRunRecord(
            id=12,
            project_id=None,
            state=DesktopRunState(
                status="needs_review",
                status_display="待人工复核",
                blocked_stage="",
                exports=(),
                manifest_path="",
                manifest_run_id="",
                manual_review_required=True,
                manual_review_count=1,
                manual_review_raw_count=1,
            ),
            output_dir="out/desktop",
            raw_result={},
            failure_message="",
            created_at="2026-04-27T12:00:00+00:00",
        )

        label = _recent_run_label(record)

        self.assertIn("#12", label)
        self.assertIn("待人工复核", label)
        self.assertIn("out/desktop", label)


if __name__ == "__main__":
    unittest.main()
