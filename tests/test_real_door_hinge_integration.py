"""Real-data integration tests for door hinge APQP generation.

Two tiers:
  1. One-shot pipeline (generate_three_tables_from_drawing) — 1 API call, ~60s
  2. Chain pipeline  (per-step LLM calls) — PFD ~2min, full chain ~15min+
     Chain tests require a responsive LLM backend to complete in reasonable time.

Usage:
  python -m unittest tests.test_real_door_hinge_integration -v

  MINOS_RUN_REAL_INTEGRATION=1  # opt-in gate
  MINOS_REAL_KNOWLEDGE_DIR      # override default Desktop/知识库种子
  MINOS_REAL_INTEGRATION_OUTPUT # override output dir
  MINOS_TEXT_LLM_TIMEOUT_SECONDS=600  # increase for slow backends
"""

from __future__ import annotations

import copy
import os
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from minos_core.ai_config import load_openai_responses_config
from minos_core.drawing_input import load_drawing_source, render_drawing_pages
from minos_core.exporters.three_table_workbooks import (
    export_split_three_table_workbooks,
    export_three_table_workbook,
)
from minos_core.pipeline import (
    _analyze_drawing_pages_for_mode,
    _effective_analysis_mode,
    _effective_ocr_engine,
    _part_family_context_from_drawing,
    generate_three_tables_from_drawing,
)
from minos_core.pipeline_chain import (
    generate_cp_from_confirmed_pfmea,
    generate_pfd_from_drawing,
    generate_pfmea_from_confirmed_pfd,
)

RUN_REAL_ENV = "MINOS_RUN_REAL_INTEGRATION"
DRAWING_ENV = "MINOS_REAL_KNOWLEDGE_DIR"

_DEFAULT_KNOWLEDGE_DIR = (
    Path(os.getenv("USERPROFILE", ""))
    / "Desktop/知识库种子"
)


def _resolve_knowledge_dir() -> Path:
    path = Path(os.getenv(DRAWING_ENV, str(_DEFAULT_KNOWLEDGE_DIR)))
    if not path.exists():
        raise AssertionError(
            f"Knowledge base directory not found: {path}. "
            f"Set {DRAWING_ENV} or place files at {_DEFAULT_KNOWLEDGE_DIR}."
        )
    return path


def _confirm_table(table: dict, table_name: str) -> dict:
    """Simulate human confirming all rows in a table."""
    key = {"process_flow": "steps", "pfmea": "rows", "control_plan": "rows"}[table_name]
    rows = table.get(key, [])
    for row in rows:
        row["needs_confirmation"] = False
        row["ai_inferred"] = False
        row["review_status"] = "已确认"
        row["confirmed_by"] = "integration_test"
    return table


def _assert_xlsx_valid(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            required = {
                "[Content_Types].xml",
                "_rels/.rels",
                "xl/workbook.xml",
                "xl/_rels/workbook.xml.rels",
            }
            missing = required - names
            if missing:
                raise AssertionError(
                    f"xlsx at {path} missing OpenXML parts: {sorted(missing)}"
                )
            for xml_part in ("xl/workbook.xml", "[Content_Types].xml"):
                ElementTree.fromstring(archive.read(xml_part))
    except zipfile.BadZipFile:
        raise AssertionError(f"Not a valid zip/xlsx: {path}") from None


def _xlsx_sheet_names(path: Path) -> list[str]:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    return [el.attrib["name"] for el in workbook.findall(".//main:sheet", ns)]


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class _BaseRealIntegration(unittest.TestCase):
    def setUp(self) -> None:
        if os.getenv(RUN_REAL_ENV) != "1":
            self.skipTest(f"set {RUN_REAL_ENV}=1")

        config = load_openai_responses_config()
        if not config.api_key_configured:
            self.fail("Real integration tests require a configured API key.")

        knowledge_dir = _resolve_knowledge_dir()
        self._drawing_path = knowledge_dir / "JLV03000500_001_AC_RR DH ASSY.pdf"
        if not self._drawing_path.exists():
            self.fail(f"Drawing not found: {self._drawing_path}")

        self._output_dir = Path(
            os.getenv("MINOS_REAL_INTEGRATION_OUTPUT", "out/integration/real_door_hinge")
        )
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _run_drawing_analysis(self):
        from minos_core.adapters.multimodal import OpenAIResponsesMultimodalDrawingAnalyzer
        from minos_core.drawing_analysis import analyze_drawing_pages

        analysis_mode = "hybrid"
        ocr_engine = "auto"
        context = {"language": "zh-CN"}
        active_analysis_mode = _effective_analysis_mode(analysis_mode, context)
        active_ocr_engine = _effective_ocr_engine(ocr_engine, context)
        context["ocr_engine"] = active_ocr_engine
        context["analysis_mode"] = active_analysis_mode

        source = load_drawing_source(str(self._drawing_path))
        pages = render_drawing_pages(source, self._output_dir / "pages")
        drawing_analysis, warnings, analysis_source, analysis_errors = (
            _analyze_drawing_pages_for_mode(
                source, pages, self._output_dir, context,
                analysis_mode=active_analysis_mode, ocr_engine=active_ocr_engine,
                ocr_adapter=None, analyzer=None,
                default_analyzer_factory=OpenAIResponsesMultimodalDrawingAnalyzer,
                analyze_drawing_pages=analyze_drawing_pages,
            )
        )
        pfc, family_context = _part_family_context_from_drawing(drawing_analysis)
        return drawing_analysis, pfc, family_context


# ---------------------------------------------------------------------------
# Tier 1 — One-shot pipeline (fast, practical for regression)
# ---------------------------------------------------------------------------

class RealDoorHingeOneShotTests(_BaseRealIntegration):
    """One-shot pipeline: 1 API call covers drawing→PFD→PFMEA→CP→export."""

    def test_full_pipeline_to_export(self):
        """Drawing → three tables → 4 xlsx workbooks, ~60s."""
        result = generate_three_tables_from_drawing(
            str(self._drawing_path), self._output_dir,
            context={"language": "zh-CN"}, export_mode="draft",
        )

        self.assertEqual(result["document_type"], "three_table_generation_result")
        self.assertIn(result["status"], {"needs_review", "draft_ready"})

        # Drawing identity
        da = result.get("drawing_analysis") or {}
        di = da.get("drawing_identity") or {}
        self.assertIn("JLV03000500", di.get("drawing_number", ""))

        # Part family
        metadata = result.get("metadata") or {}
        pfc = metadata.get("part_family_classification") or {}
        self.assertEqual(pfc.get("family_key"), "door_hinge")
        self.assertGreaterEqual(float(pfc.get("confidence", 0)), 0.55)

        # Knowledge base loaded
        fc = metadata.get("family_context") or {}
        self.assertTrue(fc.get("knowledge_source_refs"))

        # Process flow
        pf = result.get("process_flow") or {}
        steps = pf.get("steps", [])
        self.assertGreaterEqual(len(steps), 5)
        for s in steps:
            self.assertTrue(s.get("operation"))

        # PFMEA
        pfmea = result.get("pfmea") or {}
        pfmea_rows = pfmea.get("rows", [])
        self.assertGreaterEqual(len(pfmea_rows), len(steps))
        for row in pfmea_rows:
            for field in ("S", "O", "D"):
                self.assertIn(field, row)

        # Control Plan
        cp = result.get("control_plan") or {}
        cp_rows = cp.get("rows", [])
        self.assertGreaterEqual(len(cp_rows), len(steps))

        # Manual review
        mr = result.get("manual_review") or {}
        self.assertTrue(mr.get("items"))

        # Exports
        exports = result.get("exports") or {}
        for name in ("unified_workbook", "process_flow", "pfmea", "control_plan"):
            self.assertIn(name, exports)
            p = Path(exports[name])
            self.assertTrue(p.exists(), f"Export missing: {p}")
            _assert_xlsx_valid(p)

        unified = Path(exports["unified_workbook"])
        sheet_names = _xlsx_sheet_names(unified)
        for expected in ("过程流程图", "PFMEA", "控制计划", "人工复核清单"):
            self.assertIn(expected, sheet_names)

    def test_classifier_detects_door_hinge_without_explicit_context(self):
        """Part family classifier must work from drawing content alone."""
        result = generate_three_tables_from_drawing(
            str(self._drawing_path),
            self._output_dir / "no_context",
            context=None, export_mode="draft",
        )
        metadata = result.get("metadata") or {}
        pfc = metadata.get("part_family_classification") or {}
        self.assertEqual(pfc.get("family_key"), "door_hinge")
        self.assertGreaterEqual(float(pfc.get("confidence", 0)), 0.55)


# ---------------------------------------------------------------------------
# Tier 2 — Chain pipeline (per-step LLM calls, needs responsive backend)
# ---------------------------------------------------------------------------

class RealDoorHingeChainPipelineTests(_BaseRealIntegration):
    """Chain pipeline: PFD confirm → PFMEA confirm → CP confirm → export.

    Each step is a separate LLM call. With a fast backend (~5s/call) the
    full chain takes ~3min.  With a slow backend (~30s/call) it may exceed
    15min and should be run with MINOS_TEXT_LLM_TIMEOUT_SECONDS=600.
    """

    # Number of sequential LLM calls per phase:
    #   PFD: 1, PFMEA: len(pfd_steps), CP: len(pfmea_rows_high_ap)
    # Total ~33 calls for a typical 11-step door hinge.

    def test_chain_pfd_generation(self):
        """Drawing analysis → PFD generation → confirmation. ~2 LLM calls."""
        drawing_analysis, pfc, _family_context = self._run_drawing_analysis()

        self.assertTrue(drawing_analysis)
        di = (drawing_analysis.get("drawing_identity") or {})
        self.assertIn("JLV03000500", di.get("drawing_number", ""))
        self.assertEqual(pfc.get("family_key"), "door_hinge")

        process_flow = generate_pfd_from_drawing(drawing_analysis)
        pfd_steps = process_flow.get("steps", [])
        self.assertGreaterEqual(len(pfd_steps), 5)
        for s in pfd_steps:
            self.assertTrue(s.get("operation"))

        confirmation_needed = [s for s in pfd_steps if s.get("needs_confirmation")]
        self.assertGreater(len(confirmation_needed), 0,
                           "At least some PFD steps should need human confirmation.")

        # Simulate human confirmation
        confirmed_pfd = _confirm_table(copy.deepcopy(process_flow), "process_flow")
        for s in confirmed_pfd.get("steps", []):
            self.assertFalse(s["needs_confirmation"])

    def test_chain_pfmea_generation_from_confirmed_pfd(self):
        """Confirmed PFD → PFMEA generation (11 LLM calls, may take 5-10min)."""
        drawing_analysis, *_ = self._run_drawing_analysis()
        pfd = generate_pfd_from_drawing(drawing_analysis)
        confirmed_pfd = _confirm_table(copy.deepcopy(pfd), "process_flow")

        pfmea = generate_pfmea_from_confirmed_pfd(drawing_analysis, confirmed_pfd)
        pfmea_rows = pfmea.get("rows", [])
        pfd_steps = confirmed_pfd.get("steps", [])

        self.assertGreaterEqual(len(pfmea_rows), len(pfd_steps),
                                f"PFMEA rows ({len(pfmea_rows)}) < PFD steps ({len(pfd_steps)})")

        for row in pfmea_rows:
            for field in ("S", "O", "D"):
                self.assertIn(field, row, f"PFMEA row {row.get('pfmea_id')} missing {field}")

        # Check Fix B: failed_step_ids metadata
        meta = pfmea.get("metadata") or {}
        failed = meta.get("failed_step_ids", [])
        if failed:
            self.assertLess(len(failed), len(pfd_steps),
                            "All steps failed — PFMEA generation is broken.")

    def test_chain_cp_generation_from_confirmed_pfmea(self):
        """Confirmed PFMEA → CP generation (up to 22 LLM calls, may take 10-15min)."""
        drawing_analysis, *_ = self._run_drawing_analysis()
        pfd = generate_pfd_from_drawing(drawing_analysis)
        confirmed_pfd = _confirm_table(copy.deepcopy(pfd), "process_flow")
        pfmea = generate_pfmea_from_confirmed_pfd(drawing_analysis, confirmed_pfd)
        confirmed_pfmea = _confirm_table(copy.deepcopy(pfmea), "pfmea")

        cp = generate_cp_from_confirmed_pfmea(drawing_analysis, confirmed_pfd, confirmed_pfmea)
        cp_rows = cp.get("rows", [])
        pfd_steps = confirmed_pfd.get("steps", [])

        self.assertGreaterEqual(len(cp_rows), len(pfd_steps),
                                f"CP rows ({len(cp_rows)}) < PFD steps ({len(pfd_steps)})")

        for row in cp_rows:
            self.assertTrue(row.get("control_plan_id"),
                            "CP row missing control_plan_id")

        meta = cp.get("metadata") or {}
        failed = meta.get("failed_row_ids", [])
        if failed:
            self.assertLess(len(failed), len(cp_rows),
                            "All CP rows failed — CP generation is broken.")

    @unittest.skip("Full chain: ~33 LLM calls, 15-20min. Run manually with a fast backend.")
    def test_full_chain_to_export(self):
        """Drawing → PFD → confirm → PFMEA → confirm → CP → confirm → export."""
        drawing_analysis, pfc, family_context = self._run_drawing_analysis()

        pfd = generate_pfd_from_drawing(drawing_analysis)
        confirmed_pfd = _confirm_table(copy.deepcopy(pfd), "process_flow")
        pfmea = generate_pfmea_from_confirmed_pfd(drawing_analysis, confirmed_pfd)
        confirmed_pfmea = _confirm_table(copy.deepcopy(pfmea), "pfmea")
        cp = generate_cp_from_confirmed_pfmea(drawing_analysis, confirmed_pfd, confirmed_pfmea)
        confirmed_cp = _confirm_table(copy.deepcopy(cp), "control_plan")

        chain = {
            "process_flow": confirmed_pfd,
            "pfmea": confirmed_pfmea,
            "control_plan": confirmed_cp,
            "metadata": {
                "drawing_analysis": drawing_analysis,
                "part_family_classification": pfc,
                "family_context": family_context,
            },
        }

        unified = export_three_table_workbook(
            chain, self._output_dir / "三表总工作簿.xlsx",
            export_mode="draft", require_gate=False,
            quality_gate={}, manual_review_items=[],
        )
        split = export_split_three_table_workbooks(
            chain, self._output_dir / "三表独立文件", export_mode="draft",
        )

        for label, path in [("unified", unified),
                            ("PFD", split["process_flow"]),
                            ("PFMEA", split["pfmea"]),
                            ("CP", split["control_plan"])]:
            self.assertTrue(Path(path).exists(), f"{label} export missing: {path}")
            _assert_xlsx_valid(Path(path))


if __name__ == "__main__":
    unittest.main()
