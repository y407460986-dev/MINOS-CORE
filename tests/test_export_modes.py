import copy
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from minos_core.adapters.fixture_json import load_fixture_payload
from minos_core.pipeline import export_draft_fixture, export_fixture
from minos_core.quality_gates import ExportGateError
from minos_core.review_patch import REVIEW_PATCH_VERSION, apply_review_patch
from minos_core.exporters.apqp_workbook import export_apqp_workbook
from minos_core.exporters.three_table_workbooks import export_split_three_table_workbooks
from minos_core.exporters.xlsx import WorkbookWriter, sanitize_sheet_name


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "apqp_chain"
NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _fixture():
    return load_fixture_payload(FIXTURE_DIR)


def _unreviewed_draft_fixture():
    fixture = copy.deepcopy(_fixture())
    fixture["process_flow"]["steps"][0]["needs_confirmation"] = True
    fixture["pfmea"]["rows"][0]["needs_confirmation"] = True
    fixture["control_plan"]["rows"][0]["needs_confirmation"] = True
    return fixture


def _workbook_text(path: Path) -> str:
    values = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            xml = ElementTree.fromstring(archive.read(name))
            for text_node in xml.findall(".//main:t", NS):
                values.append(text_node.text or "")
    return "\n".join(values)


def _assert_xlsx_openable(testcase, path: Path) -> None:
    testcase.assertTrue(path.exists())
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    testcase.assertIn("[Content_Types].xml", names)
    testcase.assertIn("xl/workbook.xml", names)
    testcase.assertTrue(any(name.startswith("xl/worksheets/sheet") for name in names))


def _sheet_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        workbook_xml = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    return [node.attrib["name"] for node in workbook_xml.findall(".//main:sheet", NS)]


class ExportModeTests(unittest.TestCase):
    def test_unreviewed_draft_final_export_fails_without_writing(self):
        fixture = _unreviewed_draft_fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "final.xlsx"

            with self.assertRaises(ExportGateError):
                export_fixture(fixture, output_path)

            self.assertFalse(output_path.exists())

    def test_export_draft_succeeds_and_marks_workbook_as_draft_only(self):
        fixture = _unreviewed_draft_fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "draft.xlsx"

            result = export_draft_fixture(fixture, output_path)

            self.assertEqual(result, output_path)
            _assert_xlsx_openable(self, output_path)
            self.assertIn("DRAFT_ONLY", _sheet_names(output_path))
            workbook_text = _workbook_text(output_path)
            self.assertIn("draft_only", workbook_text)
            self.assertIn("requires_engineering_review", workbook_text)
            self.assertIn("not for customer submission", workbook_text)
            self.assertIn("quality_gate_allow_final_export", workbook_text)
            self.assertIn("manual_review_required", workbook_text)
            self.assertIn("仅限草案", workbook_text)
            self.assertIn("process_step:P10", workbook_text)
            self.assertIn("failure_mode:PFMEA-P10-001", workbook_text)
            self.assertIn("control_item:CP-P10-001", workbook_text)

    def test_reviewed_gate_passed_fixture_final_export_succeeds_without_draft_marks(self):
        fixture = _unreviewed_draft_fixture()
        reviewed = apply_review_patch(
            fixture,
            {
                "review_patch_version": REVIEW_PATCH_VERSION,
                "confirmed_by": "quality.engineer",
                "confirmed_at": "2026-04-25T10:00:00Z",
                "reason": "Engineering review confirmed draft rows for formal release",
                "manual_confirmation_event": "MRB-2026-04-25-001",
                "items": [
                    {"action": "confirm", "target": "process_step:P10"},
                    {"action": "confirm", "target": "failure_mode:PFMEA-P10-001"},
                    {"action": "confirm", "target": "control_item:CP-P10-001"},
                ],
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "final.xlsx"

            result = export_fixture(reviewed, output_path)

            self.assertEqual(result, output_path)
            self.assertTrue(output_path.exists())
            workbook_text = _workbook_text(output_path)
            self.assertNotIn("DRAFT_ONLY", _sheet_names(output_path))
            self.assertIn("正式导出审计", _sheet_names(output_path))
            self.assertIn("export_mode", workbook_text)
            self.assertIn("final", workbook_text)
            self.assertIn("allow_final_export", workbook_text)
            self.assertIn("review_confirmations", workbook_text)
            self.assertIn("edit_history", workbook_text)
            self.assertIn("soft_deleted_items", workbook_text)
            self.assertNotIn("not for customer submission", workbook_text)

    def test_cli_export_draft_uses_draft_mode_without_final_gate_bypass(self):
        fixture = _unreviewed_draft_fixture()

        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "fixture.json"
            draft_output = Path(tmp) / "draft.xlsx"
            final_output = Path(tmp) / "final.xlsx"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            final_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "minos_core.cli",
                    "export",
                    "--input",
                    str(fixture_path),
                    "--output",
                    str(final_output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            draft_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "minos_core.cli",
                    "export-draft",
                    "--input",
                    str(fixture_path),
                    "--output",
                    str(draft_output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(final_result.returncode, 0)
            self.assertFalse(final_output.exists())
            self.assertEqual(draft_result.returncode, 0, draft_result.stderr)
            self.assertTrue(draft_output.exists())
            self.assertIn("draft_only", _workbook_text(draft_output))

    def test_exporters_evaluate_gate_when_quality_gate_is_explicit_none(self):
        fixture = _unreviewed_draft_fixture()

        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "draft.xlsx"
            split_dir = Path(tmp) / "split"

            export_apqp_workbook(
                fixture,
                workbook,
                require_gate=False,
                export_mode="draft",
                quality_gate=None,
            )
            split = export_split_three_table_workbooks(
                fixture,
                split_dir,
                export_mode="draft",
                quality_gate=None,
            )

            _assert_xlsx_openable(self, workbook)
            self.assertIn("质量门状态", _sheet_names(workbook))
            self.assertEqual(set(split), {"process_flow", "pfmea", "control_plan"})
            for path in split.values():
                _assert_xlsx_openable(self, path)

    def test_draft_export_succeeds_even_with_sync_blockers(self):
        """草案导出即使存在三表同步阻断也仍然生成 workbook。"""
        fixture = _unreviewed_draft_fixture()
        # 新增孤儿 PFMEA 行制造三表同步阻断
        orphan_row = {
            "pfmea_id": "PFMEA-P99-ORPHAN",
            "process_step_id": "P99",
            "process_function": "Orphan step test",
            "failure_mode": "Test orphan row",
            "failure_effect": "This creates a linkage gap",
            "severity": 1,
            "occurrence": 1,
            "detection": 1,
            "action_priority": "L",
        }
        fixture["pfmea"]["rows"].append(orphan_row)

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "draft.xlsx"
            result = export_draft_fixture(fixture, output_path)

            self.assertEqual(result, output_path)
            _assert_xlsx_openable(self, output_path)
            workbook_text = _workbook_text(output_path)
            # 草案导出肯定成功，有草案标记
            self.assertIn("draft_only", workbook_text)
            self.assertIn("仅限草案", workbook_text)

    def test_final_export_blocked_by_sync_issues(self):
        """有 sync_issues 时 evaluate_export_gate.allow_user_export 为 False。"""
        fixture = _unreviewed_draft_fixture()
        # 新增孤儿 PFMEA 行制造三表同步阻断
        orphan_row = {
            "pfmea_id": "PFMEA-P99-ORPHAN",
            "process_step_id": "P99",
            "process_function": "Orphan step test",
            "failure_mode": "Test orphan row",
            "failure_effect": "This creates a linkage gap",
            "severity": 1,
            "occurrence": 1,
            "detection": 1,
            "action_priority": "L",
        }
        fixture["pfmea"]["rows"].append(orphan_row)

        from minos_core.quality_gates import evaluate_export_gate

        gate = evaluate_export_gate(fixture)
        # 有孤儿行导致 sync blocker，allow_user_export 应为 False
        self.assertFalse(
            gate.allow_user_export,
            "sync_blockers should prevent allow_user_export",
        )
        # sync_issues 不应为空
        self.assertTrue(
            any(
                isinstance(i, dict) and i.get("severity") == "blocker"
                for i in gate.sync_issues
            ),
            "sync_issues should contain blocker items",
        )

    def test_knowledge_action_sheet_present_in_workbook(self):
        """导出 workbook 包含'知识推荐与行动闭环' sheet。"""
        fixture = _fixture()
        if "metadata" not in fixture:
            fixture["metadata"] = {}
        fixture["metadata"]["knowledge_recommendations"] = [
            {"recommendation_id": "KR-001", "lifecycle_status": "已采纳"},
        ]
        fixture["metadata"]["action_items"] = [
            {"action_id": "ACT-001", "status": "进行中"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "draft.xlsx"
            result = export_draft_fixture(fixture, output_path)

            self.assertEqual(result, output_path)
            _assert_xlsx_openable(self, output_path)
            sheet_names = _sheet_names(output_path)
            self.assertIn("知识推荐与行动闭环", sheet_names)
            workbook_text = _workbook_text(output_path)
            self.assertIn("KR-001", workbook_text)
            self.assertIn("ACT-001", workbook_text)

    def test_draft_export_handles_unhandled_knowledge_items(self):
        """draft export 有未处理知识推荐/行动项时仍可导出不抛错。"""
        fixture = _unreviewed_draft_fixture()
        if "metadata" not in fixture:
            fixture["metadata"] = {}
        fixture["metadata"]["knowledge_recommendations"] = [
            {"recommendation_id": "KR-UNHANDLED", "lifecycle_status": "pending"},
        ]
        fixture["metadata"]["action_items"] = [
            {"action_id": "ACT-UNHANDLED", "status": "open"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "draft.xlsx"
            result = export_draft_fixture(fixture, output_path)

            self.assertEqual(result, output_path)
            _assert_xlsx_openable(self, output_path)
            self.assertIn("知识推荐与行动闭环", _sheet_names(output_path))

    def test_xlsx_writer_sanitizes_and_deduplicates_sheet_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            workbook = WorkbookWriter()
            long_bad_name = "Invalid:/Name?With*Chars" * 2
            workbook.add_sheet(long_bad_name, [["A"]])
            workbook.add_sheet(long_bad_name.lower(), [["B"]])
            path = workbook.save(Path(tmp) / "names.xlsx")

            names = _sheet_names(path)

            self.assertLessEqual(max(len(name) for name in names), 31)
            self.assertNotIn(":", "".join(names))
            self.assertEqual(len(names), len({name.lower() for name in names}))
            self.assertEqual(sanitize_sheet_name("[]:*?/\\'"), "Sheet")


if __name__ == "__main__":
    unittest.main()
