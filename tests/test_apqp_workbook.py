"""Tests for exporters/apqp_workbook.py -- APQP workbook generation."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from minos_core.adapters.fixture_json import load_fixture_payload
from minos_core.exporters.apqp_workbook import export_apqp_workbook
from minos_core.quality_gates import evaluate_stage_gate

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "apqp_chain"
NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _fixture():
    """Load the full apqp_chain fixture and add required top-level keys."""
    fixture = load_fixture_payload(FIXTURE_DIR)
    fixture["display_name"] = "Door Hinge APQP"
    fixture["id"] = "test-chain-001"
    fixture["process_stage"] = "Prototype"
    fixture["critical_characteristics"] = ["CC-001", "SC-001"]
    fixture["metadata"] = {}
    return fixture


def _assert_xlsx_openable(testcase: unittest.TestCase, path: Path) -> None:
    """Assert that *path* is a valid OpenXML xlsx archive."""
    testcase.assertTrue(path.exists(), f"{path} does not exist")
    testcase.assertGreater(path.stat().st_size, 100, f"{path} is too small")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    testcase.assertIn("[Content_Types].xml", names)
    testcase.assertIn("xl/workbook.xml", names)
    testcase.assertTrue(
        any(name.startswith("xl/worksheets/sheet") for name in names),
        "no sheet XML found",
    )


def _sheet_names(path: Path) -> list[str]:
    """Return the list of sheet names from the xlsx workbook."""
    with zipfile.ZipFile(path) as archive:
        workbook_xml = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    return [node.attrib["name"] for node in workbook_xml.findall(".//main:sheet", NS)]


def _worksheet_text(path: Path) -> str:
    """Extract all text content from the xlsx worksheets."""
    values: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            xml = ElementTree.fromstring(archive.read(name))
            for text_node in xml.findall(".//main:t", NS):
                values.append(text_node.text or "")
    return "\n".join(values)


class ApqpWorkbookGenerateTests(unittest.TestCase):
    """Cover APQP workbook generation with fixture data."""

    def test_generate_workbook_creates_xlsx(self):
        """Generate from full fixture, verify file exists and > 1000 bytes."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "apqp.xlsx"
            result = export_apqp_workbook(
                fixture,
                output_path,
                require_gate=False,
                export_mode="draft",
            )

            self.assertEqual(result, output_path)
            _assert_xlsx_openable(self, output_path)
            self.assertGreater(
                output_path.stat().st_size, 1000,
                f"Expected xlsx > 1000 bytes, got {output_path.stat().st_size}",
            )

    def test_generate_workbook_full_chain(self):
        """PFD + PFMEA + CP fixture, verify multiple expected sheets."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "full.xlsx"
            result = export_apqp_workbook(
                fixture,
                output_path,
                require_gate=False,
                export_mode="draft",
            )

            self.assertEqual(result, output_path)
            names = _sheet_names(output_path)
            expected_sheets = [
                "摘要",
                "质量门状态",
                "过程流程图",
                "PFMEA",
                "控制计划",
                "三表追溯矩阵",
                "人工复核清单",
                "知识推荐与行动闭环",
            ]
            for sheet in expected_sheets:
                with self.subTest(sheet=sheet):
                    self.assertIn(sheet, names, f"Expected sheet {sheet!r} not found")

    def test_export_raises_on_invalid_export_mode(self):
        """Invalid export_mode raises ValueError."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                export_apqp_workbook(
                    fixture,
                    Path(tmp) / "bad.xlsx",
                    require_gate=False,
                    export_mode="invalid",
                )
            self.assertIn("unsupported export_mode", str(ctx.exception))

    def test_generate_workbook_empty_steps(self):
        """Empty chain (no process steps) still produces valid workbook."""
        fixture = _fixture()
        fixture["process_flow"]["steps"] = []
        fixture["pfmea"]["rows"] = []
        fixture["control_plan"]["rows"] = []

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "empty.xlsx"
            result = export_apqp_workbook(
                fixture,
                output_path,
                require_gate=False,
                export_mode="draft",
            )

            self.assertEqual(result, output_path)
            _assert_xlsx_openable(self, output_path)
            # Should still contain all expected sheets
            names = _sheet_names(output_path)
            self.assertIn("过程流程图", names)
            self.assertIn("PFMEA", names)
            self.assertIn("控制计划", names)

    def test_generate_workbook_output_path_is_dir(self):
        """Passing a directory as output path raises an error."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises((PermissionError, IsADirectoryError, OSError)):
                export_apqp_workbook(
                    fixture,
                    Path(tmp),
                    require_gate=False,
                    export_mode="draft",
                )

    def test_draft_mode_contains_draft_notice(self):
        """Draft mode export includes DRAFT_ONLY sheet and draft markers."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "draft.xlsx"
            export_apqp_workbook(
                fixture,
                output_path,
                require_gate=False,
                export_mode="draft",
            )

            names = _sheet_names(output_path)
            self.assertIn("DRAFT_ONLY", names)
            workbook_text = _worksheet_text(output_path)
            self.assertIn("draft_only", workbook_text)
            self.assertIn("requires_engineering_review", workbook_text)
            self.assertIn("not for customer submission", workbook_text)
            self.assertIn("仅限草案", workbook_text)

    def test_final_mode_no_draft_sheet(self):
        """Final mode export should not include DRAFT_ONLY sheet."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "final.xlsx"
            result = export_apqp_workbook(
                fixture,
                output_path,
                require_gate=False,
                export_mode="final",
                quality_gate=None,
            )

            self.assertEqual(result, output_path)
            names = _sheet_names(output_path)
            self.assertNotIn("DRAFT_ONLY", names)
            self.assertIn("正式导出审计", names)

    def test_final_mode_accepts_serialized_quality_gate(self):
        """Pipeline results expose quality gates as JSON-compatible dictionaries."""
        fixture = _fixture()
        serialized_gate = evaluate_stage_gate(fixture, stage="export").model_dump()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "serialized-gate.xlsx"
            result = export_apqp_workbook(
                fixture,
                output_path,
                require_gate=False,
                export_mode="final",
                quality_gate=serialized_gate,
                manual_review_items=serialized_gate["manual_review_items"],
            )

            self.assertEqual(result, output_path)
            _assert_xlsx_openable(self, output_path)
            workbook_text = _worksheet_text(output_path)
            self.assertIn("正式导出审计", _sheet_names(output_path))
            self.assertIn("证据覆盖率", workbook_text)

    def test_sheet_contains_process_flow_headers(self):
        """The process flow sheet should contain column headers."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "data.xlsx"
            export_apqp_workbook(
                fixture,
                output_path,
                require_gate=False,
                export_mode="draft",
            )

            workbook_text = _worksheet_text(output_path)
            expected_headers = ["工序编号", "流程符号", "工序名称", "过程功能", "设备/工装"]
            for header in expected_headers:
                with self.subTest(header=header):
                    self.assertIn(header, workbook_text,
                                  f"Expected header {header!r} in workbook")

    def test_sheet_contains_pfmea_data(self):
        """PFMEA failure mode data appears in traceability sheet."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "pfmea.xlsx"
            export_apqp_workbook(
                fixture,
                output_path,
                require_gate=False,
                export_mode="draft",
            )

            workbook_text = _worksheet_text(output_path)
            for row in fixture["pfmea"]["rows"]:
                with self.subTest(failure_mode=row.get("failure_mode", "?")):
                    self.assertIn(
                        row.get("failure_mode", ""),
                        workbook_text,
                        f"Expected failure mode {row.get('failure_mode')!r} "
                        f"in workbook text",
                    )

    def test_sheet_contains_control_plan_headers(self):
        """The control plan sheet should contain column headers."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "cp.xlsx"
            export_apqp_workbook(
                fixture,
                output_path,
                require_gate=False,
                export_mode="draft",
            )

            workbook_text = _worksheet_text(output_path)
            expected_headers = ["控制计划编号", "工序名称", "PFMEA 来源", "产品特性",
                                "特殊特性分类", "规格和公差", "控制方法", "反应计划"]
            for header in expected_headers:
                with self.subTest(header=header):
                    self.assertIn(header, workbook_text,
                                  f"Expected header {header!r} in workbook")

    def test_traceability_sheet_present_with_linkages(self):
        """Traceability sheet should exist and contain PFMEA IDs."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "trace.xlsx"
            export_apqp_workbook(
                fixture,
                output_path,
                require_gate=False,
                export_mode="draft",
            )

            names = _sheet_names(output_path)
            self.assertIn("三表追溯矩阵", names)
            workbook_text = _worksheet_text(output_path)
            # Should reference at least one PFMEA ID from a CP row
            for row in fixture["control_plan"]["rows"]:
                pfmea_id = row.get("pfmea_id", "")
                if pfmea_id:
                    self.assertIn(
                        pfmea_id,
                        workbook_text,
                        f"Expected PFMEA ID {pfmea_id!r} in traceability sheet",
                    )
                    break


if __name__ == "__main__":
    unittest.main()
