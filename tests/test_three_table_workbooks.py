"""Tests for exporters/three_table_workbooks.py -- individual table exports."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from minos_core.adapters.fixture_json import load_fixture_payload
from minos_core.exporters.three_table_workbooks import (
    export_split_three_table_workbooks,
    export_three_table_workbook,
)

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
    """Extract all text content from all xlsx worksheets."""
    values: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            xml = ElementTree.fromstring(archive.read(name))
            for text_node in xml.findall(".//main:t", NS):
                values.append(text_node.text or "")
    return "\n".join(values)


class ThreeTableWorkbookTests(unittest.TestCase):
    """Cover unified three-table workbook export."""

    def test_export_three_table_workbook_creates_xlsx(self):
        """export_three_table_workbook creates a valid xlsx file."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "three_table.xlsx"
            result = export_three_table_workbook(
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

    def test_export_three_table_workbook_contains_sheets(self):
        """Unified export contains multiple expected sheets."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "three_table.xlsx"
            export_three_table_workbook(
                fixture,
                output_path,
                require_gate=False,
                export_mode="draft",
            )

            names = _sheet_names(output_path)
            self.assertIn("摘要", names)
            self.assertIn("过程流程图", names)
            self.assertIn("PFMEA", names)
            self.assertIn("控制计划", names)
            self.assertIn("DRAFT_ONLY", names)

    def test_export_three_table_workbook_invalid_mode(self):
        """Invalid export_mode raises ValueError."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                export_three_table_workbook(
                    fixture,
                    Path(tmp) / "bad.xlsx",
                    require_gate=False,
                    export_mode="invalid",
                )


class SplitThreeTableWorkbookTests(unittest.TestCase):
    """Cover split three-table workbook export."""

    def test_export_split_creates_three_files(self):
        """export_split_three_table_workbooks creates three valid xlsx files."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            result = export_split_three_table_workbooks(
                fixture,
                tmp,
                require_gate=False,
                export_mode="draft",
            )

            self.assertIsInstance(result, dict)
            self.assertEqual(set(result.keys()), {"process_flow", "pfmea", "control_plan"})

            for key, path in result.items():
                with self.subTest(key=key):
                    self.assertIsInstance(path, Path)
                    _assert_xlsx_openable(self, path)
                    # Split workbooks each get one sheet
                    names = _sheet_names(path)
                    self.assertEqual(len(names), 1, f"{key} should have exactly 1 sheet")
                    self.assertIn(names[0], ["过程流程图", "PFMEA", "控制计划"])

    def test_export_split_draft_mode(self):
        """Draft mode split export includes draft notice rows."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            result = export_split_three_table_workbooks(
                fixture,
                tmp,
                require_gate=False,
                export_mode="draft",
            )

            for key, path in result.items():
                with self.subTest(key=key):
                    text = _worksheet_text(path)
                    self.assertIn("draft_only", text,
                                  f"{key} should contain draft_notice")

    def test_export_split_final_mode(self):
        """Final mode split export omits draft notices and includes quality gate."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            result = export_split_three_table_workbooks(
                fixture,
                tmp,
                require_gate=False,
                export_mode="final",
                quality_gate=None,
            )

            for key, path in result.items():
                with self.subTest(key=key):
                    text = _worksheet_text(path)
                    self.assertIn("quality_gate_allow_final_export", text,
                                  f"{key} should contain quality gate info")
                    self.assertNotIn("draft_only", text,
                                     f"{key} should NOT contain draft notice")

    def test_export_split_invalid_export_mode(self):
        """Invalid export_mode raises ValueError."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                export_split_three_table_workbooks(
                    fixture,
                    tmp,
                    require_gate=False,
                    export_mode="invalid",
                )
            self.assertIn("unsupported export_mode", str(ctx.exception))

    def test_export_split_output_dir_created_automatically(self):
        """Output directory is created if it does not exist."""
        fixture = _fixture()

        with tempfile.TemporaryDirectory() as tmp:
            non_existent_dir = Path(tmp) / "new_split_output"
            self.assertFalse(non_existent_dir.exists())

            result = export_split_three_table_workbooks(
                fixture,
                non_existent_dir,
                require_gate=False,
                export_mode="draft",
            )

            self.assertTrue(non_existent_dir.exists())
            for path in result.values():
                self.assertTrue(path.exists())

    def test_export_split_contains_expected_headers(self):
        """Each split workbook contains the correct column headers."""
        fixture = _fixture()

        pfmea_headers = [
            "PFMEA 编号", "工序编号", "失效模式", "失效后果", "S",
            "失效原因", "O", "预防控制", "探测控制", "D", "AP",
        ]
        cp_headers = [
            "控制计划编号", "工序名称", "PFMEA 来源", "产品特性", "过程特性",
            "控制方法", "反应计划",
        ]
        pfd_headers = ["工序编号", "工序名称", "过程功能", "设备/工装"]

        with tempfile.TemporaryDirectory() as tmp:
            result = export_split_three_table_workbooks(
                fixture,
                tmp,
                require_gate=False,
                export_mode="draft",
            )

            # Check PFD headers
            pfd_text = _worksheet_text(result["process_flow"])
            for header in pfd_headers:
                self.assertIn(header, pfd_text, f"PFD missing header: {header}")

            # Check PFMEA headers
            pfmea_text = _worksheet_text(result["pfmea"])
            for header in pfmea_headers:
                self.assertIn(header, pfmea_text, f"PFMEA missing header: {header}")

            # Check CP headers
            cp_text = _worksheet_text(result["control_plan"])
            for header in cp_headers:
                self.assertIn(header, cp_text, f"CP missing header: {header}")

    def test_export_split_empty_chain(self):
        """Empty chain (no steps/rows) still produces three valid files."""
        fixture = _fixture()
        fixture["process_flow"]["steps"] = []
        fixture["pfmea"]["rows"] = []
        fixture["control_plan"]["rows"] = []

        with tempfile.TemporaryDirectory() as tmp:
            result = export_split_three_table_workbooks(
                fixture,
                tmp,
                require_gate=False,
                export_mode="draft",
            )

            for key, path in result.items():
                with self.subTest(key=key):
                    _assert_xlsx_openable(self, path)


if __name__ == "__main__":
    unittest.main()
