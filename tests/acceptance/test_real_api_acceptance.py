from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from minos_core.adapters.multimodal import OpenAIResponsesMultimodalDrawingAnalyzer
from minos_core.ai_config import load_openai_responses_config
from minos_core.automation_review import build_automation_review
from minos_core.drawing_input import load_drawing_source, render_drawing_pages
from minos_core.exporters.three_table_workbooks import export_three_table_workbook
from minos_core.pipeline import generate_three_tables_from_drawing


RUN_REAL_ENV = "MINOS_RUN_REAL_ACCEPTANCE"
REAL_DRAWING_ENV = "MINOS_REAL_DRAWING_PATH"
OUTPUT_DIR_ENV = "MINOS_REAL_ACCEPTANCE_OUTPUT_DIR"


class RealAPIThreeTableAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        if os.getenv(RUN_REAL_ENV) != "1":
            self.skipTest(f"set {RUN_REAL_ENV}=1 to run real API acceptance")

    def test_real_streaming_api_drawing_to_aiag_vda_workbook_acceptance(self):
        config = load_openai_responses_config()
        if not config.api_key_configured:
            self.fail(
                "real acceptance requires a configured API key via "
                "MINOS_OPENAI_API_KEY, OPENAI_API_KEY, ARK_API_KEY, or Codex auth"
            )
        if config.wire_api != "responses":
            self.fail(f"real acceptance requires Responses wire_api, got {config.wire_api!r}")

        drawing_path = _required_real_drawing_path()
        output_dir = _real_output_dir()
        context = {
            "acceptance_task": "MINOS v1.8.1 子任务 B",
            "part_family": os.getenv("MINOS_REAL_PART_FAMILY", "stamping"),
            "language": "zh-CN",
        }

        analyzer = OpenAIResponsesMultimodalDrawingAnalyzer()
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(
                load_drawing_source(drawing_path),
                Path(tmpdir) / "pages",
            )
            payload = analyzer._request_payload(pages, context)

        self.assertTrue(payload.get("stream"), "真实验收必须走 Responses 流式调用")
        self.assertTrue(analyzer._responses_url().endswith("responses"))

        result = generate_three_tables_from_drawing(
            drawing_path,
            output_dir,
            context=context,
            analyzer=analyzer,
        )

        self.assertEqual(result["document_type"], "three_table_generation_result")
        self.assertIn(result["status"], {"needs_review", "draft_ready"})
        self.assertTrue(result["drawing_analysis"]["metadata"]["adapter_metadata"])
        self.assertTrue(result["process_flow"]["steps"])
        self.assertTrue(result["pfmea"]["rows"])
        self.assertTrue(result["control_plan"]["rows"])
        self.assertTrue(result["manual_review"]["items"])

        for export_name in ("unified_workbook", "process_flow", "pfmea", "control_plan"):
            self.assertIn(export_name, result["exports"])
            _assert_xlsx_can_open(Path(result["exports"][export_name]))

        review = build_automation_review(result)
        self.assertEqual(review["automation_review_version"], "minos-core.automation_review.v1")
        self.assertTrue(review["automation_tasks"])
        self.assertIn("AI 预审完成", review["summary"]["message"])

        audit_workbook = export_three_table_workbook(
            result["chain"],
            output_dir / "AIAG-VDA_正式导出审计验收.xlsx",
            export_mode="final",
            require_gate=False,
            quality_gate=result["quality_gate"],
            manual_review_items=result["manual_review"]["items"],
        )
        _assert_xlsx_can_open(audit_workbook)
        sheet_names = _sheet_names(audit_workbook)
        self.assertIn("正式导出审计", sheet_names)
        workbook_text = _xlsx_text(audit_workbook)
        self.assertIn("PFMEA 编号", workbook_text)
        self.assertIn("AP", workbook_text)
        self.assertIn("措施后 S/O/D/AP/RPN", workbook_text)
        self.assertIn("allow_final_export", workbook_text)


def _required_real_drawing_path() -> Path:
    raw_path = os.getenv(REAL_DRAWING_ENV, "").strip()
    if not raw_path:
        raise AssertionError(f"real acceptance requires {REAL_DRAWING_ENV}")
    path = Path(raw_path)
    if not path.exists():
        raise AssertionError(f"{REAL_DRAWING_ENV} does not exist: {path}")
    if not path.is_file():
        raise AssertionError(f"{REAL_DRAWING_ENV} must point to a real drawing file: {path}")
    return path


def _real_output_dir() -> Path:
    base = Path(os.getenv(OUTPUT_DIR_ENV, "out/acceptance/real_api"))
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = base / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _assert_xlsx_can_open(path: Path) -> None:
    if not path.exists():
        raise AssertionError(f"xlsx does not exist: {path}")
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        required = {
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
        }
        missing = required - names
        if missing:
            raise AssertionError(f"xlsx missing OpenXML parts: {sorted(missing)}")
        ElementTree.fromstring(archive.read("xl/workbook.xml"))


def _sheet_names(path: Path) -> list[str]:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    return [node.attrib["name"] for node in workbook.findall(".//main:sheet", ns)]


def _xlsx_text(path: Path) -> str:
    with ZipFile(path) as archive:
        return "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xml")
        )


if __name__ == "__main__":
    unittest.main()
