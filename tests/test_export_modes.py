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


if __name__ == "__main__":
    unittest.main()
