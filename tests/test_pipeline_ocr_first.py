from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from minos_core.adapters.ocr import OCRPageText, OCRResult
from minos_core.drawing_analysis import analyze_drawing_pages
from minos_core.pipeline import (
    HYBRID_OCR_FALLBACK_WARNING,
    HYBRID_VISION_MAX_RETRIES,
    HYBRID_VISION_TIMEOUT_SECONDS,
    _analyze_drawing_pages_for_mode,
    generate_three_tables_from_drawing,
)


class PipelineOCRFirstTests(unittest.TestCase):
    def test_hybrid_returns_ocr_draft_when_vision_fails(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_pipeline(
                tmpdir,
                analysis_mode="hybrid",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
            )

        self.assertEqual(result["status"], "needs_review")
        self.assertIn(HYBRID_OCR_FALLBACK_WARNING, result["warnings"])
        self.assertEqual(
            result["drawing_analysis"]["metadata"]["analysis_source"],
            "hybrid_ocr_fallback",
        )
        error_text = " ".join(
            item["message"]
            for item in result["drawing_analysis"]["metadata"]["analysis_errors"]
        )
        self.assertIn("AI 视觉识别中断，已保留 OCR 识别结果。", error_text)
        self.assertIn("stream_read_error", error_text)
        self.assertIn("ocr_analysis_summary", captured["vision_context"])
        self.assertEqual(captured["ocr_engine"], "rapidocr")
        self.assertIsInstance(captured["ocr_adapter"], _FakeOCRAdapter)
        self.assertEqual(result["process_flow"]["steps"][0]["operation"], "来料检验")

    def test_ocr_only_enters_three_table_chain_without_vision(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_pipeline(
                tmpdir,
                analysis_mode="ocr_only",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
            )

        self.assertEqual(result["status"], "needs_review")
        self.assertNotEqual(result["blocked_stage"], "drawing_recognition")
        self.assertEqual(
            result["drawing_analysis"]["metadata"]["analysis_source"],
            "ocr",
        )
        self.assertNotIn("vision_context", captured)
        self.assertEqual(result["drawing_analysis"]["drawing_identity"]["part_name"], "OCR 支架")

    def test_ocr_only_uses_real_ocr_entrypoint_and_blocks_final_export(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            drawing_path.write_bytes(b"fake drawing")
            result = _run_pipeline_without_fake_ocr_module(
                root,
                drawing_path,
                analysis_mode="ocr_only",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
                export_mode="final",
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked_stage"], "final_three_table")
        self.assertEqual(result["exports"], {})
        self.assertIn("最终三表质量门未通过，已阻止正式导出。", result["warnings"])
        self.assertEqual(result["drawing_analysis"]["metadata"]["analysis_source"], "ocr")
        self.assertEqual(result["drawing_analysis"]["metadata"]["ocr_engine"], "rapidocr")
        self.assertEqual(result["drawing_analysis"]["metadata"]["ocr"]["engine"], "unit_ocr")
        self.assertGreater(result["manual_review"]["raw_count"], 0)

    def test_hybrid_stream_error_keeps_ocr_draft_exports_and_review_warning(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            drawing_path.write_bytes(b"fake drawing")
            result = _run_pipeline_without_fake_ocr_module(
                root,
                drawing_path,
                analysis_mode="hybrid",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
            )

        self.assertEqual(result["status"], "needs_review")
        self.assertIn("unified_workbook", result["exports"])
        self.assertIn(HYBRID_OCR_FALLBACK_WARNING, result["warnings"])
        self.assertIn("AI 视觉识别错误", "\n".join(result["warnings"]))
        self.assertEqual(
            result["drawing_analysis"]["metadata"]["analysis_source"],
            "hybrid_ocr_fallback",
        )
        self.assertEqual(result["drawing_analysis"]["metadata"]["ocr_engine"], "rapidocr")
        error_text = str(result["drawing_analysis"]["metadata"]["analysis_errors"])
        self.assertIn("AI 视觉识别中断，已保留 OCR 识别结果。", error_text)
        self.assertIn("stream_read_error", error_text)

    def test_hybrid_default_analyzer_gets_bounded_runtime_before_vision(self) -> None:
        captured: dict[str, object] = {}

        class _ConfigurableAnalyzer(_FailingAnalyzer):
            timeout = 120
            max_retries = 2

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzer = _ConfigurableAnalyzer(captured)
            with patch.dict(
                sys.modules,
                {"minos_core.drawing_ocr_analysis": _fake_hinge_ocr_module(captured)},
            ):
                bundle, warnings, analysis_source, errors = _analyze_drawing_pages_for_mode(
                    {"path": str(root / "JLV03000500.pdf")},
                    [_page_evidence()],
                    root / "out",
                    {},
                    analysis_mode="hybrid",
                    ocr_engine="rapidocr",
                    ocr_adapter=_FakeOCRAdapter(),
                    analyzer=None,
                    default_analyzer_factory=lambda: analyzer,
                    analyze_drawing_pages=analyze_drawing_pages,
                )

        self.assertEqual(analysis_source, "hybrid_ocr_fallback")
        self.assertEqual(bundle["drawing_identity"]["drawing_number"], "JLV03000500")
        self.assertIn(HYBRID_OCR_FALLBACK_WARNING, warnings)
        self.assertEqual(analyzer.timeout, HYBRID_VISION_TIMEOUT_SECONDS)
        self.assertEqual(analyzer.max_retries, HYBRID_VISION_MAX_RETRIES)
        self.assertEqual(errors[-1]["stage"], "vision")

    def test_hybrid_context_can_override_vision_runtime_budget(self) -> None:
        captured: dict[str, object] = {}

        class _ConfigurableAnalyzer(_FailingAnalyzer):
            timeout = 120
            max_retries = 2

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzer = _ConfigurableAnalyzer(captured)
            with patch.dict(
                sys.modules,
                {"minos_core.drawing_ocr_analysis": _fake_hinge_ocr_module(captured)},
            ):
                _analyze_drawing_pages_for_mode(
                    {"path": str(root / "JLV03000500.pdf")},
                    [_page_evidence()],
                    root / "out",
                    {
                        "hybrid_vision_timeout_seconds": 12,
                        "hybrid_vision_max_retries": 1,
                    },
                    analysis_mode="hybrid",
                    ocr_engine="rapidocr",
                    ocr_adapter=_FakeOCRAdapter(),
                    analyzer=None,
                    default_analyzer_factory=lambda: analyzer,
                    analyze_drawing_pages=analyze_drawing_pages,
                )

        self.assertEqual(analyzer.timeout, 12)
        self.assertEqual(analyzer.max_retries, 1)

    def test_hybrid_vision_cannot_override_high_confidence_ocr_identity(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.dict(
                sys.modules,
                {"minos_core.drawing_ocr_analysis": _fake_hinge_ocr_module(captured)},
            ):
                bundle, warnings, analysis_source, errors = _analyze_drawing_pages_for_mode(
                    {"path": str(root / "JLV03000500.pdf")},
                    [_page_evidence()],
                    root / "out",
                    {},
                    analysis_mode="hybrid",
                    ocr_engine="rapidocr",
                    ocr_adapter=_FakeOCRAdapter(),
                    analyzer=_VisionBushingAnalyzer(captured),
                    default_analyzer_factory=lambda: _VisionBushingAnalyzer(captured),
                    analyze_drawing_pages=analyze_drawing_pages,
                )

        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])
        self.assertEqual(analysis_source, "hybrid_vision")
        self.assertEqual(bundle["drawing_identity"]["part_name"], "尾门较链")
        self.assertEqual(bundle["drawing_identity"]["drawing_number"], "JLV03000500")
        self.assertTrue(bundle["drawing_identity"]["ocr_identity_locked"])

        metadata = bundle["metadata"]
        lock = metadata["ocr_identity_lock"]
        self.assertEqual(lock["source"], "ocr_title_block")
        self.assertIn("drawing_identity.part_name", lock["locked_fields"])
        self.assertEqual(lock["original_vision_identity"]["part_name"], "衬套")
        self.assertEqual(
            lock["part_family_classification"]["family_key"],
            "door_hinge",
        )
        self.assertEqual(
            metadata["locked_part_family_classification"]["family_key"],
            "door_hinge",
        )
        evidence_ids = {item["evidence_id"] for item in bundle["evidence"]}
        self.assertIn("drawing_page_001", evidence_ids)
        self.assertIn("ocr_page_001", evidence_ids)
        self.assertEqual(
            captured["vision_context"]["ocr_analysis_summary"]["drawing_identity"]["part_name"],
            "尾门较链",
        )


class _FailingAnalyzer:
    def __init__(self, captured: dict[str, object]) -> None:
        self.captured = captured

    def analyze_drawing_pages(self, pages, context=None):
        self.captured["vision_context"] = dict(context or {})
        raise RuntimeError("stream_read_error: simulated vision failure")


class _VisionBushingAnalyzer:
    def __init__(self, captured: dict[str, object]) -> None:
        self.captured = captured

    def analyze_drawing_pages(self, pages, context=None):
        self.captured["vision_context"] = dict(context or {})
        return types.SimpleNamespace(
            content=json.dumps(
                {
                    "drawing_identity": {
                        "part_name": "衬套",
                        "drawing_number": "JLV03000500",
                        "revision": "A",
                        "confidence": 0.92,
                    },
                    "materials": [
                        {"name": "SPCC", "confidence": 0.9, "evidence_refs": ["drawing_page_001"]}
                    ],
                    "surface_treatments": [],
                    "dimensions": [],
                    "tolerances": [],
                    "special_characteristics": [],
                    "technical_requirements": [
                        {
                            "content": "衬套压入后不得松动。",
                            "confidence": 0.9,
                            "evidence_refs": ["drawing_page_001"],
                        }
                    ],
                    "inspection_requirements": [],
                    "manufacturing_clues": [
                        {
                            "operation": "衬套压入",
                            "confidence": 0.9,
                            "evidence_refs": ["drawing_page_001"],
                        }
                    ],
                    "uncertainties": [],
                },
                ensure_ascii=False,
            ),
            model="unit-vision",
            metadata={"source": "unit"},
        )


class _FakeOCRAdapter:
    def extract_text(self, source_ref: str, content: bytes) -> OCRResult:
        return _ocr_result(source_ref)


class _Gate:
    def __init__(
        self,
        *,
        can_continue: bool = True,
        allow_user_export: bool = False,
        needs_human_review: bool = True,
        manual_review_items: list[dict[str, object]] | None = None,
    ) -> None:
        self.can_continue = can_continue
        self.allow_user_export = allow_user_export
        self.needs_human_review = needs_human_review
        self.manual_review_items: list[dict[str, object]] = manual_review_items or []

    def model_dump(self) -> dict[str, object]:
        return {
            "can_continue": self.can_continue,
            "allow_user_export": self.allow_user_export,
            "needs_human_review": self.needs_human_review,
            "manual_review_items": list(self.manual_review_items),
            "needs_confirmation_items": [],
        }


def _run_pipeline(
    tmpdir: str,
    *,
    analysis_mode: str,
    analyzer: object,
    captured: dict[str, object],
) -> dict[str, object]:
    root = Path(tmpdir)
    drawing_path = root / "drawing.png"
    drawing_path.write_bytes(b"fake drawing")

    patches = [
        patch("minos_core.drawing_input.load_drawing_source", return_value={"path": str(drawing_path)}),
        patch("minos_core.drawing_input.render_drawing_pages", return_value=["page-1"]),
        patch("minos_core.drawing_analysis.evaluate_drawing_recognition_gate", return_value=_Gate()),
        patch("minos_core.part_family_classifier.classify_part_family", return_value={"family_key": "unknown"}),
        patch("minos_core.drawing_to_pfd.infer_process_flow_from_drawing", return_value=_process_flow()),
        patch("minos_core.characteristic_registry.build_characteristic_registry", return_value={}),
        patch("minos_core.quality_gates.evaluate_pfd_bundle_gate", return_value=_Gate()),
        patch("minos_core.quality_gates.evaluate_pfmea_bundle_gate", return_value=_Gate()),
        patch("minos_core.quality_gates.evaluate_control_plan_bundle_gate", return_value=_Gate()),
        patch("minos_core.pfd_to_pfmea_ai.infer_pfmea_from_process_flow", return_value=_pfmea()),
        patch("minos_core.generate_control_plan.generate_control_plan_from_pfmea", return_value=_control_plan()),
        patch("minos_core.pipeline.evaluate_export_gate", return_value=_Gate()),
        patch("minos_core.pipeline.export_three_table_workbook", side_effect=_write_export),
        patch("minos_core.pipeline.export_split_three_table_workbooks", side_effect=_write_split_exports),
        patch("minos_core.action_tracking.build_action_items", return_value=[]),
        patch("minos_core.action_tracking.action_items_summary", return_value={"total": 0}),
        patch("minos_core.three_table_linkage.build_three_table_linkage_map", return_value={"gaps": []}),
        patch("minos_core.three_table_linkage.evaluate_three_table_linkage", return_value={}),
        patch("minos_core.risk_structure.build_risk_structure", return_value={}),
        patch("minos_core.edit_patch.evaluate_edit_export_gate", return_value={}),
        patch("minos_core.edit_patch._build_review_dashboard", return_value={}),
        patch("minos_core.knowledge_recommendation.load_knowledge_rules", return_value=[]),
    ]
    with ExitStack() as stack:
        stack.enter_context(
            patch.dict(
                sys.modules,
                {"minos_core.drawing_ocr_analysis": _fake_ocr_module(captured)},
            )
        )
        for item in patches:
            stack.enter_context(item)
        return generate_three_tables_from_drawing(
            drawing_path,
            root / "out",
            context={"analysis_mode": analysis_mode},
            analysis_mode=analysis_mode,
            ocr_engine="rapidocr",
            ocr_adapter=_FakeOCRAdapter(),
            analyzer=analyzer,
        )


def _run_pipeline_without_fake_ocr_module(
    root: Path,
    drawing_path: Path,
    *,
    analysis_mode: str,
    analyzer: object,
    captured: dict[str, object],
    export_mode: str = "draft",
) -> dict[str, object]:
    patches = _pipeline_patches(captured, final_gate=_Gate(can_continue=True, allow_user_export=False))
    with ExitStack() as stack:
        stack.enter_context(patch("minos_core.drawing_input.load_drawing_source", return_value={"path": str(drawing_path)}))
        stack.enter_context(patch("minos_core.drawing_input.render_drawing_pages", return_value=[_page_evidence()]))
        for item in patches:
            stack.enter_context(item)
        return generate_three_tables_from_drawing(
            drawing_path,
            root / "out",
            context={"analysis_mode": analysis_mode},
            analysis_mode=analysis_mode,
            ocr_engine="rapidocr",
            ocr_adapter=_FakeOCRAdapter(),
            analyzer=analyzer,
            export_mode=export_mode,
        )


def _pipeline_patches(
    _captured: dict[str, object],
    *,
    final_gate: _Gate | None = None,
) -> list[object]:
    return [
        patch("minos_core.drawing_analysis.evaluate_drawing_recognition_gate", return_value=_Gate(manual_review_items=[{"item_id": "drawing:ocr", "category": "drawing_recognition_ocr", "message": "OCR 待人工复核"}])),
        patch("minos_core.part_family_classifier.classify_part_family", return_value={"family_key": "unknown"}),
        patch("minos_core.drawing_to_pfd.infer_process_flow_from_drawing", return_value=_process_flow()),
        patch("minos_core.characteristic_registry.build_characteristic_registry", return_value={}),
        patch("minos_core.quality_gates.evaluate_pfd_bundle_gate", return_value=_Gate()),
        patch("minos_core.quality_gates.evaluate_pfmea_bundle_gate", return_value=_Gate()),
        patch("minos_core.quality_gates.evaluate_control_plan_bundle_gate", return_value=_Gate()),
        patch("minos_core.pfd_to_pfmea_ai.infer_pfmea_from_process_flow", return_value=_pfmea()),
        patch("minos_core.generate_control_plan.generate_control_plan_from_pfmea", return_value=_control_plan()),
        patch("minos_core.pipeline.evaluate_export_gate", return_value=final_gate or _Gate()),
        patch("minos_core.pipeline.export_three_table_workbook", side_effect=_write_export),
        patch("minos_core.pipeline.export_split_three_table_workbooks", side_effect=_write_split_exports),
        patch("minos_core.action_tracking.build_action_items", return_value=[]),
        patch("minos_core.action_tracking.action_items_summary", return_value={"total": 0}),
        patch("minos_core.three_table_linkage.build_three_table_linkage_map", return_value={"gaps": []}),
        patch("minos_core.three_table_linkage.evaluate_three_table_linkage", return_value={}),
        patch("minos_core.risk_structure.build_risk_structure", return_value={}),
        patch("minos_core.edit_patch.evaluate_edit_export_gate", return_value={}),
        patch("minos_core.edit_patch._build_review_dashboard", return_value={}),
        patch("minos_core.knowledge_recommendation.load_knowledge_rules", return_value=[]),
    ]


def _fake_ocr_module(captured: dict[str, object]) -> types.ModuleType:
    module = types.ModuleType("minos_core.drawing_ocr_analysis")

    def analyze_drawing_with_ocr(**kwargs):
        captured["ocr_engine"] = kwargs["ocr_engine"]
        captured["ocr_adapter"] = kwargs["ocr_adapter"]
        captured["ocr_context"] = dict(kwargs["context"])
        return _drawing_analysis()

    module.analyze_drawing_with_ocr = analyze_drawing_with_ocr
    return module


def _fake_hinge_ocr_module(captured: dict[str, object]) -> types.ModuleType:
    module = types.ModuleType("minos_core.drawing_ocr_analysis")

    def analyze_drawing_with_ocr(**kwargs):
        captured["ocr_engine"] = kwargs["ocr_engine"]
        captured["ocr_adapter"] = kwargs["ocr_adapter"]
        captured["ocr_context"] = dict(kwargs["context"])
        return _hinge_ocr_drawing_analysis()

    module.analyze_drawing_with_ocr = analyze_drawing_with_ocr
    return module


def _drawing_analysis() -> dict[str, object]:
    return {
        "document_type": "drawing_analysis_bundle",
        "schema_version": "minos-core.drawing_analysis.v1",
        "drawing_identity": {"part_name": "OCR 支架", "drawing_number": "OCR-001"},
        "materials": [{"name": "SPCC", "confidence": 0.9, "evidence_refs": ["EV-1"]}],
        "surface_treatments": [],
        "dimensions": [],
        "tolerances": [],
        "special_characteristics": [],
        "technical_requirements": [],
        "inspection_requirements": [],
        "manufacturing_clues": [
            {"operation": "来料检验", "confidence": 0.9, "evidence_refs": ["EV-1"]}
        ],
        "uncertainties": [],
        "evidence": [{"evidence_id": "EV-1", "source": "ocr_text"}],
        "metadata": {
            "source_stage": "drawing_ocr_analysis",
            "ocr_summary": {"raw_text_preview": "OCR 支架 SPCC 来料检验"},
        },
    }


def _hinge_ocr_drawing_analysis() -> dict[str, object]:
    return {
        "document_type": "drawing_analysis_bundle",
        "schema_version": "minos-core.drawing_analysis.v1",
        "drawing_identity": {
            "part_name": "尾门较链",
            "drawing_number": "JLV03000500",
            "revision": "A",
            "evidence_refs": ["ocr_page_001"],
            "field_evidence_refs": {
                "part_name": ["ocr_page_001"],
                "drawing_number": ["ocr_page_001"],
                "revision": ["ocr_page_001"],
            },
            "confidence": 0.82,
            "ai_inferred": False,
            "ocr_inferred": True,
            "needs_confirmation": True,
        },
        "materials": [{"name": "SPCC", "confidence": 0.9, "evidence_refs": ["ocr_page_001"]}],
        "surface_treatments": [],
        "dimensions": [],
        "tolerances": [],
        "special_characteristics": [],
        "technical_requirements": [],
        "inspection_requirements": [],
        "manufacturing_clues": [
            {"operation": "铰链装配", "confidence": 0.82, "evidence_refs": ["ocr_page_001"]}
        ],
        "uncertainties": [],
        "evidence": [
            {
                "evidence_id": "ocr_page_001",
                "source": "ocr_page",
                "content": "JLV03000500 BACKX D00R HIMGE 尾门较链",
                "confidence": 0.82,
            }
        ],
        "metadata": {
            "source_stage": "drawing_ocr_analysis",
            "ocr_summary": {
                "drawing_identity": {
                    "part_name": "尾门较链",
                    "drawing_number": "JLV03000500",
                }
            },
        },
    }


def _ocr_result(source_ref: str) -> OCRResult:
    return OCRResult(
        source_ref=source_ref,
        pages=[
            OCRPageText(
                page_number=1,
                text="Drawing No: OCR-001\nPart Name: OCR 支架\nMaterial: SPCC\nProcess: incoming inspection",
                confidence=0.88,
                engine="unit_ocr",
                source_ref=source_ref,
            )
        ],
    )


def _page_evidence():
    class Page:
        evidence_id = "drawing_page_001"
        image_path = "drawing.png"
        source_ref = "drawing.png"

        def model_dump(self):
            return {
                "evidence_id": "drawing_page_001",
                "source": "drawing_page",
                "page_number": 1,
                "image_path": "drawing.png",
                "content": "drawing page",
            }

    return Page()


def _process_flow() -> dict[str, object]:
    return {
        "document_type": "process_flow",
        "product": {"part_name": "OCR 支架"},
        "drawings": [],
        "characteristics": [],
        "steps": [
            {
                "process_step_id": "P10",
                "operation": "来料检验",
                "process_function": "确认材料",
                "evidence_refs": ["EV-1"],
            }
        ],
        "links": [],
        "pending_fields": [],
        "ai_inferred_items": [],
    }


def _pfmea() -> dict[str, object]:
    return {
        "document_type": "pfmea",
        "rows": [{"pfmea_id": "PFMEA-P10-001", "process_step_id": "P10"}],
        "pending_fields": [],
        "ai_inferred_items": [],
    }


def _control_plan() -> dict[str, object]:
    return {
        "document_type": "control_plan",
        "rows": [{"control_plan_id": "CP-P10-001", "process_step_id": "P10"}],
        "pending_fields": [],
        "ai_inferred_items": [],
    }


def _write_export(chain, path, **kwargs):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"test workbook")
    return destination


def _write_split_exports(chain, output_dir, **kwargs):
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    result = {}
    for name in ("process_flow", "pfmea", "control_plan"):
        path = directory / f"{name}.xlsx"
        path.write_bytes(b"test workbook")
        result[name] = path
    return result


if __name__ == "__main__":
    unittest.main()
