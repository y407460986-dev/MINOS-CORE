from __future__ import annotations

import json
import re
import subprocess as _subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from minos_core.adapters.multimodal import FakeMultimodalDrawingAnalyzer
from minos_core.cli import main
from minos_core.demo_acceptance import (
    check_three_table_workbook_exports,
    check_xlsx_zip_openable,
    summarize_three_table_acceptance,
    write_safe_demo_drawing_png,
)
from minos_core.drawing_input import load_drawing_source, render_drawing_pages
from minos_core.pipeline import generate_three_tables_from_drawing


def _extract_json_from_log(text: str) -> dict:
    """Extract JSON from structlog line: timestamp [level] event result='{...}'"""
    match = re.search(r"result='(\{.*\})'", text, re.DOTALL)
    if match:
        raw = match.group(1)
        # structlog ConsoleRenderer converts newlines to \n. Restore them to
        # actual newlines only when outside of JSON string values.
        cleaned = _restore_structural_newlines(raw)
        return json.loads(cleaned)
    raise ValueError(f"Cannot extract JSON from log output: {text[:200]}")


def _restore_structural_newlines(text: str) -> str:
    """Replace \\n with newlines only outside of JSON quoted strings."""
    chars = []
    in_string = False
    escape = False
    i = 0
    while i < len(text):
        if escape:
            chars.append(text[i])
            escape = False
        elif text[i] == '\\' and in_string:
            escape = True
            chars.append(text[i])
        elif text[i] == '"' and not escape:
            in_string = not in_string
            chars.append(text[i])
        elif text[i] == '\\' and not in_string and i + 1 < len(text) and text[i + 1] == 'n':
            chars.append('\n')
            i += 1  # skip the 'n'
        elif text[i] == '\\' and not in_string and i + 1 < len(text) and text[i + 1] == 't':
            chars.append('\t')
            i += 1  # skip the 't'
        else:
            chars.append(text[i])
        i += 1
    return ''.join(chars)


class DemoAcceptanceTests(unittest.TestCase):
    def test_safe_demo_png_can_be_read_by_drawing_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            drawing_path = write_safe_demo_drawing_png(Path(tmpdir) / "safe_demo.png")

            source = load_drawing_source(drawing_path)
            pages = render_drawing_pages(source)

            self.assertEqual(source.file_type, "png")
            self.assertEqual(len(pages), 1)
            self.assertEqual(pages[0].width, 1400)
            self.assertEqual(pages[0].height, 900)
            self.assertTrue(pages[0].sha256)

    def test_acceptance_summary_accepts_complete_generate_three_tables_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = write_safe_demo_drawing_png(root / "safe_demo.png")

            result = generate_three_tables_from_drawing(
                drawing_path,
                root / "out",
                analysis_mode="vision_only",
                analyzer=FakeMultimodalDrawingAnalyzer(json.dumps(_analysis_payload())),
            )

            summary = summarize_three_table_acceptance(result)

            self.assertTrue(summary.ok, summary.errors)
            self.assertTrue(summary.warnings)
            self.assertEqual(
                set(summary.workbook_checks),
                {"unified_workbook", "process_flow", "pfmea", "control_plan"},
            )
            self.assertTrue(all(check.ok for check in summary.workbook_checks.values()))

            workbook_checks = check_three_table_workbook_exports(result)
            self.assertTrue(all(check.ok for check in workbook_checks.values()))
            self.assertTrue(check_xlsx_zip_openable(result["exports"]["unified_workbook"]).ok)
            for path in result["exports"].values():
                self.assertTrue(check_xlsx_zip_openable(path).ok)

    def test_acceptance_summary_fails_when_workbook_or_manifest_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = write_safe_demo_drawing_png(root / "safe_demo.png")
            result = generate_three_tables_from_drawing(
                drawing_path,
                root / "out",
                analysis_mode="vision_only",
                analyzer=FakeMultimodalDrawingAnalyzer(json.dumps(_analysis_payload())),
            )

            missing_workbook = dict(result)
            missing_workbook["exports"] = dict(result["exports"])
            missing_workbook["exports"]["unified_workbook"] = str(root / "missing.xlsx")
            workbook_summary = summarize_three_table_acceptance(missing_workbook)

            self.assertFalse(workbook_summary.ok)
            self.assertTrue(
                any("unified_workbook" in error and "missing" in error for error in workbook_summary.errors),
                workbook_summary.errors,
            )

            missing_manifest = dict(result)
            missing_manifest["manifest"] = {}
            manifest_summary = summarize_three_table_acceptance(missing_manifest)

            self.assertFalse(manifest_summary.ok)
            self.assertIn("manifest must be a non-empty object", manifest_summary.errors)

    def test_demo_drawing_and_acceptance_cli_commands(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "safe_demo.png"

            code = main(["write-demo-drawing", "--output", str(drawing_path)])

            self.assertEqual(code, 0)
            self.assertTrue(drawing_path.exists())

            result = generate_three_tables_from_drawing(
                drawing_path,
                root / "out",
                analysis_mode="vision_only",
                analyzer=FakeMultimodalDrawingAnalyzer(json.dumps(_analysis_payload())),
            )
            result_path = root / "out" / "three_table_generation_result.json"
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

            accept_result = _subprocess.run(
                [sys.executable, "-m", "minos_core.cli", "accept-three-tables", "--result", str(result_path)],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(accept_result.returncode, 0)
            # accept-three-tables logs the result via structlog; subprocess captures it in stderr
            self.assertIn("three_tables_acceptance_result", accept_result.stderr)
            self.assertIn("ok\": true", accept_result.stderr)

    def test_accept_three_tables_cli_rejects_missing_result_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            accept_result = _subprocess.run(
                [sys.executable, "-m", "minos_core.cli", "accept-three-tables", "--result",
                 str(Path(tmpdir) / "missing.json")],
                cwd=Path(tmpdir),
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(accept_result.returncode, 2)
        self.assertIn("three_tables_acceptance_failed", accept_result.stderr or accept_result.stdout)


def _analysis_payload() -> dict:
    refs = ["drawing_page_001"]
    return {
        "drawing_identity": {
            "part_name": "Demo Bracket",
            "drawing_number": "MINOS-DEMO-001",
            "revision": "A",
            "evidence_refs": refs,
        },
        "materials": [
            {"name": "SPCC-SD 1.6 mm", "confidence": 0.92, "evidence_refs": refs}
        ],
        "surface_treatments": [
            {"name": "Zinc plated", "confidence": 0.86, "evidence_refs": refs}
        ],
        "dimensions": [
            {
                "name": "overall hole span",
                "value": "370.0 +/-0.20",
                "confidence": 0.9,
                "evidence_refs": refs,
            },
            {
                "name": "mounting hole diameter",
                "value": "10.0 +/-0.05",
                "confidence": 0.88,
                "evidence_refs": refs,
            },
        ],
        "tolerances": [
            {"name": "general tolerance", "value": "+/-0.20 mm", "confidence": 0.84, "evidence_refs": refs}
        ],
        "special_characteristics": [
            {
                "id": "SC-01",
                "name": "hole position",
                "classification": "SC",
                "specification": "+/-0.10",
                "confidence": 0.8,
                "evidence_refs": refs,
            }
        ],
        "technical_requirements": [
            {"text": "No sharp burrs", "confidence": 0.89, "evidence_refs": refs}
        ],
        "inspection_requirements": [
            {"text": "Critical holes require go/no-go check", "confidence": 0.87, "evidence_refs": refs}
        ],
        "manufacturing_clues": [
            {
                "process_step_id": "P10",
                "operation": "Blanking",
                "process_function": "Create flat blank profile",
                "equipment": "Press",
                "confidence": 0.82,
                "evidence_refs": refs,
            },
            {
                "process_step_id": "P20",
                "operation": "Piercing",
                "process_function": "Create mounting holes",
                "equipment": "Piercing die",
                "special_characteristics": ["SC-01"],
                "confidence": 0.8,
                "evidence_refs": refs,
            },
            {
                "process_step_id": "P30",
                "operation": "Deburr and plating",
                "process_function": "Remove burrs and apply corrosion protection",
                "confidence": 0.76,
                "evidence_refs": refs,
            },
            {
                "process_step_id": "P40",
                "operation": "Final inspection",
                "process_function": "Verify special characteristic and drawing requirements",
                "confidence": 0.78,
                "evidence_refs": refs,
            },
        ],
        "uncertainties": [
            {
                "text": "Synthetic demo process sequence still requires engineer confirmation",
                "confidence": 0.62,
                "evidence_refs": refs,
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
