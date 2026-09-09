import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from minos_core.adapters.fixture_json import load_fixture_payload
from minos_core.adapters.multimodal import (
    FakeMultimodalDrawingAnalyzer,
    MultimodalDrawingResult,
)
from minos_core.characteristic_registry import (
    attach_characteristics_to_three_tables,
    build_characteristic_registry,
)
from minos_core.drawing_analysis import (
    DrawingAnalysisError,
    analyze_drawing_pages,
    evaluate_drawing_recognition_gate,
)
from minos_core.drawing_input import (
    DrawingInputError,
    load_drawing_source,
    render_drawing_pages,
)
from minos_core.drawing_to_pfd import infer_process_flow_from_drawing
from minos_core.pipeline.drawing_analysis import _analyze_drawing_pages_for_mode
from minos_core.pipeline.hybrid_fusion import (
    _attach_ocr_reference_metadata,
    _lock_hybrid_identity_from_ocr,
)
from minos_core.pipeline.orchestration import _assemble_three_table_chain
from minos_core.quality_gates import evaluate_export_gate
from minos_core.schemas import validate_bundle_schema

from .conftest import SharedTestHelpers


class DrawingAnalysisTests(unittest.TestCase):
    """Tests for drawing input, analysis, and gate evaluation."""

    def test_png_drawing_becomes_page_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")

            source = load_drawing_source(image_path)
            pages = render_drawing_pages(source)

            self.assertEqual(source.file_type, "png")
            self.assertEqual(len(pages), 1)
            self.assertEqual(pages[0].evidence_id, "drawing_page_001")
            self.assertEqual(pages[0].width, 100)
            self.assertEqual(pages[0].height, 80)
            self.assertTrue(pages[0].sha256)

    def test_missing_or_broken_drawing_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                load_drawing_source(Path(tmpdir) / "missing.png")

            bad = Path(tmpdir) / "bad.png"
            bad.write_text("not an image", encoding="utf-8")
            source = load_drawing_source(bad)
            with self.assertRaisesRegex(DrawingInputError, "cannot be opened"):
                render_drawing_pages(source)

    def test_pdf_without_renderer_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf = Path(tmpdir) / "drawing.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%%EOF")
            source = load_drawing_source(pdf)
            try:
                import fitz  # type: ignore[import-not-found]  # noqa: F401
            except ImportError:
                with self.assertRaisesRegex(DrawingInputError, "PDF rendering requires PyMuPDF"):
                    render_drawing_pages(source, Path(tmpdir) / "pages")
            else:
                with self.assertRaisesRegex(DrawingInputError, "PDF rendering failed"):
                    render_drawing_pages(source, Path(tmpdir) / "pages")

    def test_fake_multimodal_adapter_returns_valid_drawing_analysis_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")))
            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(SharedTestHelpers.analysis_payload())),
                {"part_family": "hinge"},
            )

            self.assertTrue(validate_bundle_schema(bundle, "drawing_analysis_bundle"))
            self.assertEqual(bundle["drawing_identity"]["part_name"], "Hinge Bracket")
            gate = evaluate_drawing_recognition_gate(bundle)
            self.assertTrue(gate.can_continue)
            self.assertFalse(gate.allow_user_export)
            self.assertTrue(gate.needs_human_review)

    def test_visual_evidence_regions_are_registered_as_evidence_refs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(
                load_drawing_source(
                    SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")
                )
            )
            payload = SharedTestHelpers.analysis_payload()
            payload["technical_requirements"][0]["evidence_refs"] = [
                "drawing_page_001_technical_requirements"
            ]

            class _Analyzer:
                def analyze_drawing_pages(self, _pages, _context=None):
                    return MultimodalDrawingResult(
                        content=json.dumps(payload, ensure_ascii=False),
                        model="gpt-test",
                        metadata={
                            "visual_evidence_regions": [
                                {
                                    "region_id": "drawing_page_001_technical_requirements",
                                    "page_evidence_id": "drawing_page_001",
                                    "label": "technical_requirements",
                                    "bbox": [100, 200, 300, 400],
                                    "image_path": "visual_evidence/technical_requirements.png",
                                    "evidence_refs": ["drawing_page_001"],
                                }
                            ]
                        },
                    )

            bundle = analyze_drawing_pages(pages, _Analyzer(), {})

        evidence_ids = {item["evidence_id"] for item in bundle["evidence"]}
        self.assertIn("drawing_page_001_technical_requirements", evidence_ids)
        self.assertEqual(
            bundle["technical_requirements"][0]["evidence_refs"],
            ["drawing_page_001_technical_requirements"],
        )
        self.assertNotIn("evidence_ref_repairs", bundle["metadata"])

    def test_hybrid_fallback_keeps_focused_special_characteristic_locator_results(self):
        class _TaskAwareAnalyzer:
            def analyze_drawing_pages(self, _pages, _context=None):
                context = _context or {}
                if context.get("visual_task") == "special_characteristic_locator":
                    payload = {
                        "drawing_identity": {},
                        "materials": [],
                        "surface_treatments": [],
                        "dimensions": [],
                        "tolerances": [],
                        "special_characteristics": [],
                        "technical_requirements": [],
                        "inspection_requirements": [],
                        "manufacturing_clues": [],
                        "uncertainties": [],
                        "declared_special_characteristics": [],
                        "declared_totals": {"CC": 2, "SC": 1},
                        "located_occurrences": [
                            {
                                "candidate_id": "SC-REQ4-TORQUE",
                                "candidate_type": "SC",
                                "source": "gpt55_visual_locator",
                                "symbol_text_or_shape": "SC marker",
                                "linked_feature": "技术要求第4条第(2)项：转动力矩(0.5~2.5)Nm",
                                "symbol_bbox": [0.62, 0.52, 0.08, 0.03],
                                "evidence_refs": ["drawing_page_001_technical_requirements"],
                                "confidence": 0.96,
                            },
                            {
                                "candidate_id": "CC-REQ5-GB15086",
                                "candidate_type": "CC",
                                "source": "gpt55_visual_locator",
                                "symbol_text_or_shape": "CC marker",
                                "linked_feature": "技术要求第5条：GB 15086",
                                "symbol_bbox": [0.58, 0.56, 0.08, 0.03],
                                "evidence_refs": ["drawing_page_001_technical_requirements"],
                                "confidence": 0.9,
                            },
                            {
                                "candidate_id": "CC-REQ6-M0102",
                                "candidate_type": "CC",
                                "source": "gpt55_visual_locator",
                                "symbol_text_or_shape": "CC marker",
                                "linked_feature": "技术要求第6条：Q/BJORV M 0102",
                                "symbol_bbox": [0.58, 0.59, 0.08, 0.03],
                                "evidence_refs": ["drawing_page_001_technical_requirements"],
                                "confidence": 0.82,
                            },
                        ],
                        "special_characteristic_candidates": [],
                        "special_characteristic_locations": [
                            {
                                "location_id": "SC-REQ4-TORQUE",
                                "classification": "SC",
                                "symbol_text_or_shape": "SC marker",
                                "linked_feature": "技术要求第4条第(2)项：转动力矩(0.5~2.5)Nm",
                                "bbox": [0.62, 0.52, 0.08, 0.03],
                                "evidence_refs": ["drawing_page_001_technical_requirements"],
                                "confidence": 0.96,
                            },
                            {
                                "location_id": "CC-REQ5-GB15086",
                                "classification": "CC",
                                "symbol_text_or_shape": "CC marker",
                                "linked_feature": "技术要求第5条：GB 15086",
                                "bbox": [0.58, 0.56, 0.08, 0.03],
                                "evidence_refs": ["drawing_page_001_technical_requirements"],
                                "confidence": 0.9,
                            },
                            {
                                "location_id": "CC-REQ6-M0102",
                                "classification": "CC",
                                "symbol_text_or_shape": "CC marker",
                                "linked_feature": "技术要求第6条：Q/BJORV M 0102",
                                "bbox": [0.58, 0.59, 0.08, 0.03],
                                "evidence_refs": ["drawing_page_001_technical_requirements"],
                                "confidence": 0.82,
                            },
                        ],
                        "missing_counts": {},
                        "focused_review_requests": [],
                    }
                    return MultimodalDrawingResult(
                        content=json.dumps(payload, ensure_ascii=False),
                        model="gpt-5.5",
                        metadata={
                            "source": "gpt55_visual_locator",
                            "visual_evidence_regions": [
                                {
                                    "region_id": "drawing_page_001_technical_requirements",
                                    "page_evidence_id": "drawing_page_001",
                                    "label": "technical_requirements",
                                    "bbox": [100, 200, 300, 400],
                                    "image_path": "visual_evidence/technical_requirements.png",
                                    "evidence_refs": ["drawing_page_001"],
                                }
                            ],
                        },
                    )
                raise RuntimeError("full visual analysis timed out")

        with tempfile.TemporaryDirectory() as tmpdir:
            source = load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            pages = render_drawing_pages(source)
            ocr_analysis = SharedTestHelpers.analysis_payload()
            ocr_analysis["declared_totals"] = {"CC": 0, "SC": 0}
            ocr_analysis["special_characteristic_candidates"] = []
            ocr_analysis["special_characteristic_locations"] = []
            ocr_analysis["special_characteristics"] = []
            with patch(
                "minos_core.pipeline.drawing_analysis._run_ocr_drawing_analysis",
                return_value=ocr_analysis,
            ):
                bundle, warnings, source_label, errors = _analyze_drawing_pages_for_mode(
                    source,
                    pages,
                    Path(tmpdir) / "out",
                    {"analysis_mode": "hybrid", "ocr_engine": "rapidocr"},
                    analysis_mode="hybrid",
                    ocr_engine="rapidocr",
                    ocr_adapter=None,
                    analyzer=_TaskAwareAnalyzer(),
                    default_analyzer_factory=_TaskAwareAnalyzer,
                    analyze_drawing_pages=analyze_drawing_pages,
                )

        self.assertEqual(source_label, "hybrid_ocr_fallback")
        self.assertTrue(any("AI 视觉识别错误" in warning for warning in warnings))
        self.assertEqual(errors[-1]["stage"], "vision")
        self.assertEqual(bundle["declared_totals"], {"CC": 2, "SC": 1})
        self.assertEqual(len(bundle["special_characteristic_candidates"]), 3)
        self.assertEqual(
            {
                item["candidate_id"]: item["candidate_type"]
                for item in bundle["special_characteristic_candidates"]
            },
            {
                "SC-REQ4-TORQUE": "SC",
                "CC-REQ5-GB15086": "CC",
                "CC-REQ6-M0102": "CC",
            },
        )
        self.assertEqual(len(bundle["special_characteristic_locations"]), 3)
        self.assertEqual(
            bundle["special_characteristic_discovery"]["found_counts"],
            {"CC": 2, "SC": 1},
        )
        self.assertEqual(
            bundle["special_characteristic_discovery"]["extra_counts"],
            {"CC": 0, "SC": 0},
        )
        evidence_ids = {item["evidence_id"] for item in bundle["evidence"]}
        self.assertIn("drawing_page_001_technical_requirements", evidence_ids)
        gate = evaluate_drawing_recognition_gate(bundle)
        self.assertTrue(gate.can_continue)
        self.assertFalse(gate.allow_user_export)
        self.assertTrue(gate.needs_human_review)

    def test_focused_locator_retries_detailed_when_broad_pass_misses_declared_counts(self):
        class _Analyzer:
            def __init__(self):
                self.contexts = []

            def analyze_drawing_pages(self, _pages, _context=None):
                context = dict(_context or {})
                self.contexts.append(context)
                if context.get("special_characteristic_locator_detail") == "detailed":
                    payload = {
                        "declared_totals": {"CC": 2, "SC": 1},
                        "located_occurrences": [
                            {
                                "candidate_id": "CC-REQ5-GB15086",
                                "candidate_type": "CC",
                                "linked_feature": "技术要求第5条：GB 15086",
                            },
                            {
                                "candidate_id": "SC-REQ4-TORQUE",
                                "candidate_type": "SC",
                                "linked_feature": "技术要求第4条第(2)项：转动力矩",
                            },
                        ],
                        "special_characteristic_candidates": [
                            {
                                "candidate_id": "SC-REQ4-TORQUE",
                                "candidate_type": "SC",
                                "linked_feature": "技术要求第4条第(2)项：转动力矩",
                            }
                        ],
                        "special_characteristic_locations": [
                            {
                                "location_id": "SC-REQ4-TORQUE",
                                "classification": "SC",
                                "linked_feature": "技术要求第4条第(2)项：转动力矩",
                            }
                        ],
                        "missing_counts": {},
                    }
                else:
                    payload = {
                        "declared_totals": {"CC": 2, "SC": 1},
                        "located_occurrences": [],
                        "special_characteristic_candidates": [],
                        "special_characteristic_locations": [],
                        "missing_counts": {"CC": 2, "SC": 1},
                    }
                return MultimodalDrawingResult(
                    content=json.dumps(payload, ensure_ascii=False),
                    model="gpt-5.5",
                    metadata={"source": "gpt55_visual_locator"},
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            source = load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            pages = render_drawing_pages(source)
            analyzer = _Analyzer()

            from minos_core.pipeline.drawing_analysis import (
                _run_focused_special_characteristic_visual_locator,
            )

            result = _run_focused_special_characteristic_visual_locator(
                pages,
                {
                    "special_characteristic_discovery_request": {
                        "declared_totals": {"CC": 2, "SC": 1},
                    },
                },
                analyzer=analyzer,
                default_analyzer_factory=lambda: analyzer,
                analyze_drawing_pages=analyze_drawing_pages,
            )

        self.assertEqual(len(analyzer.contexts), 2)
        self.assertEqual(
            analyzer.contexts[0]["special_characteristic_locator_detail"], "broad"
        )
        self.assertEqual(
            analyzer.contexts[0]["visual_task"], "special_characteristic_locator"
        )
        self.assertIs(analyzer.contexts[0]["focused_special_characteristic_only"], True)
        self.assertEqual(
            analyzer.contexts[0]["special_characteristic_locator_scope"],
            "title_block,key_product_characteristic_table,technical_requirements",
        )
        self.assertEqual(
            analyzer.contexts[1]["special_characteristic_locator_detail"], "detailed"
        )
        self.assertEqual(
            analyzer.contexts[1]["visual_task"], "special_characteristic_locator"
        )
        self.assertIs(analyzer.contexts[1]["focused_special_characteristic_only"], True)
        self.assertEqual(len(result["located_occurrences"]), 2)
        self.assertEqual(
            {item["candidate_id"] for item in result["located_occurrences"]},
            {"CC-REQ5-GB15086", "SC-REQ4-TORQUE"},
        )
        self.assertEqual(
            result["special_characteristic_candidates"][0]["candidate_id"],
            "SC-REQ4-TORQUE",
        )
        self.assertEqual(
            result["special_characteristic_locations"][0]["location_id"],
            "SC-REQ4-TORQUE",
        )

    def test_focused_locator_retries_detailed_when_broad_pass_misses_declared_totals(self):
        class _Analyzer:
            def __init__(self):
                self.contexts = []

            def analyze_drawing_pages(self, _pages, _context=None):
                context = dict(_context or {})
                self.contexts.append(context)
                payload = {
                    "declared_totals": {"CC": 0, "SC": 0},
                    "located_occurrences": [],
                    "special_characteristic_candidates": [],
                    "special_characteristic_locations": [],
                    "missing_counts": {},
                }
                if context.get("special_characteristic_locator_detail") == "detailed":
                    payload["located_occurrences"] = [
                        {
                            "candidate_id": "SC-REQ4-TORQUE",
                            "candidate_type": "SC",
                            "linked_feature": "技术要求第4条第(2)项：转动力矩",
                        }
                    ]
                return MultimodalDrawingResult(
                    content=json.dumps(payload, ensure_ascii=False),
                    model="gpt-5.5",
                    metadata={"source": "gpt55_visual_locator"},
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            source = load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            pages = render_drawing_pages(source)
            analyzer = _Analyzer()

            from minos_core.pipeline.drawing_analysis import (
                _run_focused_special_characteristic_visual_locator,
            )

            result = _run_focused_special_characteristic_visual_locator(
                pages,
                {
                    "special_characteristic_discovery_request": {
                        "declared_totals": {"CC": 2, "SC": 1},
                    },
                },
                analyzer=analyzer,
                default_analyzer_factory=lambda: analyzer,
                analyze_drawing_pages=analyze_drawing_pages,
            )

        self.assertEqual(len(analyzer.contexts), 2)
        self.assertEqual(
            analyzer.contexts[1]["special_characteristic_locator_detail"], "detailed"
        )
        self.assertEqual(
            result["located_occurrences"][0]["candidate_id"],
            "SC-REQ4-TORQUE",
        )

    def test_focused_locator_does_not_retry_when_broad_pass_finds_all_declared_counts(self):
        class _Analyzer:
            def __init__(self):
                self.contexts = []

            def analyze_drawing_pages(self, _pages, _context=None):
                context = dict(_context or {})
                self.contexts.append(context)
                payload = {
                    "declared_totals": {"CC": 1, "SC": 0},
                    "located_occurrences": [
                        {
                            "candidate_id": "CC-REQ5-GB15086",
                            "candidate_type": "CC",
                            "linked_feature": "技术要求第5条：GB 15086",
                        }
                    ],
                    "special_characteristic_candidates": [],
                    "special_characteristic_locations": [],
                    "missing_counts": {},
                }
                return MultimodalDrawingResult(
                    content=json.dumps(payload, ensure_ascii=False),
                    model="gpt-5.5",
                    metadata={"source": "gpt55_visual_locator"},
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            source = load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            pages = render_drawing_pages(source)
            analyzer = _Analyzer()

            from minos_core.pipeline.drawing_analysis import (
                _run_focused_special_characteristic_visual_locator,
            )

            result = _run_focused_special_characteristic_visual_locator(
                pages,
                {
                    "special_characteristic_discovery_request": {
                        "declared_totals": {"CC": 1, "SC": 0},
                    },
                },
                analyzer=analyzer,
                default_analyzer_factory=lambda: analyzer,
                analyze_drawing_pages=analyze_drawing_pages,
            )

        self.assertEqual(len(analyzer.contexts), 1)
        self.assertEqual(
            analyzer.contexts[0]["special_characteristic_locator_detail"], "broad"
        )
        self.assertIs(analyzer.contexts[0]["focused_special_characteristic_only"], True)
        self.assertEqual(
            analyzer.contexts[0]["special_characteristic_locator_scope"],
            "title_block,key_product_characteristic_table,technical_requirements",
        )
        self.assertEqual(len(result["located_occurrences"]), 1)

    def test_focused_special_characteristic_locator_uses_medium_reasoning_by_default(self):
        class _Analyzer:
            def __init__(self):
                self.timeout = 0
                self.max_retries = 99
                self.reasoning_effort = "xhigh"

            def analyze_drawing_pages(self, _pages, _context=None):
                context = _context or {}
                self.seen_context = dict(context)
                self.seen_timeout = self.timeout
                self.seen_max_retries = self.max_retries
                self.seen_reasoning_effort = self.reasoning_effort
                payload = {
                    "declared_totals": {"CC": 2, "SC": 1},
                    "located_occurrences": [],
                    "special_characteristic_candidates": [],
                    "special_characteristic_locations": [],
                    "missing_counts": {"CC": 2, "SC": 1},
                    "focused_review_requests": [],
                }
                return MultimodalDrawingResult(
                    content=json.dumps(payload, ensure_ascii=False),
                    model="gpt-5.5",
                    metadata={"source": "gpt55_visual_locator"},
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            source = load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            pages = render_drawing_pages(source)
            analyzer = _Analyzer()

            from minos_core.pipeline.drawing_analysis import (
                _run_focused_special_characteristic_visual_locator,
            )

            _run_focused_special_characteristic_visual_locator(
                pages,
                {
                    "special_characteristic_discovery_request": {
                        "declared_totals": {"CC": 2, "SC": 1},
                    },
                },
                analyzer=analyzer,
                default_analyzer_factory=lambda: analyzer,
                analyze_drawing_pages=analyze_drawing_pages,
            )

        self.assertEqual(analyzer.seen_timeout, 300.0)
        self.assertEqual(analyzer.seen_max_retries, 0)
        self.assertEqual(analyzer.seen_reasoning_effort, "medium")
        self.assertEqual(analyzer.timeout, 0)
        self.assertEqual(analyzer.max_retries, 99)
        self.assertEqual(analyzer.reasoning_effort, "xhigh")
        self.assertEqual(analyzer.seen_context["visual_task"], "special_characteristic_locator")
        self.assertIs(analyzer.seen_context["focused_special_characteristic_only"], True)
        self.assertEqual(
            analyzer.seen_context["special_characteristic_locator_scope"],
            "title_block,key_product_characteristic_table,technical_requirements",
        )

    def test_focused_special_characteristic_locator_restores_runtime_limits(self):
        class _Analyzer:
            def __init__(self):
                self.timeout = 77
                self.max_retries = 4
                self.reasoning_effort = "xhigh"
                self.seen = {}

            def analyze_drawing_pages(self, _pages, _context=None):
                self.seen = {
                    "timeout": self.timeout,
                    "max_retries": self.max_retries,
                    "reasoning_effort": self.reasoning_effort,
                }
                payload = {
                    "declared_totals": {"CC": 1, "SC": 0},
                    "located_occurrences": [
                        {
                            "candidate_id": "CC-REQ5",
                            "candidate_type": "CC",
                            "linked_feature": "GB 15086",
                        }
                    ],
                    "missing_counts": {},
                }
                return MultimodalDrawingResult(
                    content=json.dumps(payload, ensure_ascii=False),
                    model="gpt-5.5",
                    metadata={"source": "gpt55_visual_locator"},
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            source = load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            pages = render_drawing_pages(source)
            analyzer = _Analyzer()

            from minos_core.pipeline.drawing_analysis import (
                _run_focused_special_characteristic_visual_locator,
            )

            _run_focused_special_characteristic_visual_locator(
                pages,
                {
                    "special_characteristic_discovery_request": {
                        "declared_totals": {"CC": 1, "SC": 0},
                    },
                },
                analyzer=analyzer,
                default_analyzer_factory=lambda: analyzer,
                analyze_drawing_pages=analyze_drawing_pages,
            )

        self.assertEqual(analyzer.seen["timeout"], 300.0)
        self.assertEqual(analyzer.seen["max_retries"], 0)
        self.assertEqual(analyzer.seen["reasoning_effort"], "medium")
        self.assertEqual(analyzer.timeout, 77)
        self.assertEqual(analyzer.max_retries, 4)
        self.assertEqual(analyzer.reasoning_effort, "xhigh")

    def test_hybrid_returns_focused_special_characteristics_when_ocr_and_full_vision_fail(self):
        class _TaskAwareAnalyzer:
            def analyze_drawing_pages(self, _pages, _context=None):
                context = _context or {}
                if context.get("visual_task") == "special_characteristic_locator":
                    payload = {
                        "drawing_identity": {},
                        "materials": [],
                        "surface_treatments": [],
                        "dimensions": [],
                        "tolerances": [],
                        "special_characteristics": [],
                        "technical_requirements": [],
                        "inspection_requirements": [],
                        "manufacturing_clues": [],
                        "uncertainties": [],
                        "declared_special_characteristics": [],
                        "declared_totals": {"CC": 2, "SC": 1},
                        "located_occurrences": [
                            {
                                "candidate_id": "SC-REQ4-TORQUE",
                                "candidate_type": "SC",
                                "source": "gpt55_visual_locator",
                                "symbol_text_or_shape": "SC marker",
                                "linked_feature": "技术要求第4条第(2)项：转动力矩(0.5~2.5)Nm",
                                "symbol_bbox": [0.62, 0.52, 0.08, 0.03],
                                "evidence_refs": ["drawing_page_001"],
                                "confidence": 0.96,
                            }
                        ],
                        "special_characteristic_candidates": [],
                        "special_characteristic_locations": [],
                        "missing_counts": {},
                        "focused_review_requests": [],
                    }
                    return MultimodalDrawingResult(
                        content=json.dumps(payload, ensure_ascii=False),
                        model="gpt-5.5",
                        metadata={"source": "gpt55_visual_locator"},
                    )
                raise RuntimeError("full visual analysis timed out")

        with tempfile.TemporaryDirectory() as tmpdir:
            source = load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            pages = render_drawing_pages(source)
            with patch(
                "minos_core.pipeline.drawing_analysis._run_ocr_drawing_analysis",
                side_effect=RuntimeError("ocr unavailable"),
            ):
                bundle, warnings, source_label, errors = _analyze_drawing_pages_for_mode(
                    source,
                    pages,
                    Path(tmpdir) / "out",
                    {"analysis_mode": "hybrid", "ocr_engine": "rapidocr"},
                    analysis_mode="hybrid",
                    ocr_engine="rapidocr",
                    ocr_adapter=None,
                    analyzer=_TaskAwareAnalyzer(),
                    default_analyzer_factory=_TaskAwareAnalyzer,
                    analyze_drawing_pages=analyze_drawing_pages,
                )

        self.assertEqual(source_label, "hybrid_focused_fallback")
        self.assertTrue(any("OCR 识别未完成" in warning for warning in warnings))
        self.assertEqual(
            [error["stage"] for error in errors],
            ["ocr", "vision"],
        )
        self.assertEqual(bundle["declared_totals"], {"CC": 2, "SC": 1})
        self.assertEqual(
            bundle["special_characteristic_candidates"][0]["candidate_id"],
            "SC-REQ4-TORQUE",
        )

    def test_drawing_analysis_preserves_special_characteristic_judgments_top_level(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(
                load_drawing_source(
                    SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")
                )
            )
            payload = SharedTestHelpers.analysis_payload()
            payload["special_characteristic_evidence_packet"] = {
                "packet_id": "SC-EVIDENCE-001",
                "symbol_occurrences": [{"candidate_id": "MSC-001"}],
                "page_evidence_refs": ["drawing_page_001"],
            }
            payload["special_characteristic_judgments"] = [
                {
                    "judgment_id": "SCJ-001",
                    "candidate_id": "MSC-001",
                    "classification": "CC",
                    "verdict": "confirmed",
                    "linked_feature": "安装孔位置度",
                    "confidence": 0.91,
                    "standard_evidence_refs": ["TXT-001"],
                    "symbol_evidence_refs": ["MSC-001"],
                    "page_evidence_refs": ["drawing_page_001"],
                    "reasoning_summary": "图例说明菱形为 CC。",
                }
            ]

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload, ensure_ascii=False)),
                {"part_family": "hinge"},
            )

        self.assertEqual(
            bundle["special_characteristic_judgments"][0]["judgment_id"],
            "SCJ-001",
        )
        self.assertEqual(
            bundle["special_characteristic_judgments"][0]["classification"],
            "CC",
        )
        self.assertEqual(
            bundle["special_characteristic_evidence_packet"]["packet_id"],
            "SC-EVIDENCE-001",
        )

    def test_drawing_analysis_preserves_declared_special_discovery_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(
                load_drawing_source(
                    SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")
                )
            )
            payload = SharedTestHelpers.analysis_payload()
            payload["declared_special_characteristics"] = [
                {
                    "declaration_id": "SCD-CC-001",
                    "classification": "CC",
                    "expected_count": 2,
                    "evidence_refs": ["drawing_page_001"],
                },
                {
                    "declaration_id": "SCD-SC-001",
                    "classification": "SC",
                    "expected_count": 0,
                    "evidence_refs": ["drawing_page_001"],
                },
            ]
            payload["declared_totals"] = {"CC": 2, "SC": 0}
            payload["special_characteristic_locations"] = [
                {
                    "location_id": "SCL-RAW-001",
                    "classification": "cc",
                    "linked_feature": "hole position",
                    "symbol_text_or_shape": "CC",
                    "bbox": [0.25, 0.5, 0.1, 0.05],
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.91,
                    "reasoning": "GPT5.5 visual locator found one CC marker.",
                }
            ]

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload, ensure_ascii=False)),
                {"part_family": "hinge"},
            )

        self.assertEqual(bundle["declared_totals"], {"CC": 2, "SC": 0})
        self.assertEqual(
            bundle["declared_special_characteristics"][0]["declaration_id"],
            "SCD-CC-001",
        )
        self.assertEqual(
            bundle["special_characteristic_locations"][0]["location_id"],
            "SCL-RAW-001",
        )
        self.assertEqual(
            bundle["special_characteristic_locations"][0]["classification"],
            "CC",
        )
        self.assertEqual(
            bundle["special_characteristic_discovery"]["missing_counts"],
            {"CC": 1, "SC": 0},
        )
        risk_ids = {
            item["risk_id"]
            for item in bundle["metadata"]["drawing_analysis_risks"]
        }
        self.assertIn("SC-DISCOVERY-MISSING-CC", risk_ids)
        self.assertNotIn("SC-DISCOVERY-MISSING-SC", risk_ids)

    def test_drawing_analysis_bridges_located_occurrences_to_candidates_and_locations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(
                load_drawing_source(
                    SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")
                )
            )
            payload = SharedTestHelpers.analysis_payload()
            payload["declared_totals"] = {"CC": 1, "SC": 1}
            payload["special_characteristic_candidates"] = []
            payload["special_characteristic_locations"] = []
            payload["located_occurrences"] = [
                {
                    "candidate_id": "SC-REQ4-TORQUE",
                    "candidate_type": "SC",
                    "source": "gpt55_visual_locator",
                    "symbol_text_or_shape": "水平圆角长框",
                    "linked_feature": "技术要求第4条第(2)项：转动力矩(0.5~2.5)Nm",
                    "symbol_bbox": [2050, 906, 2255, 929],
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.96,
                    "reasoning": "形状与右下 SC 图例一致。",
                },
                {
                    "candidate_id": "CC-REQ5-GB15086",
                    "candidate_type": "CC",
                    "source": "gpt55_visual_locator",
                    "symbol_text_or_shape": "圆内倒三角",
                    "linked_feature": "技术要求第5条：GB 15086",
                    "symbol_bbox": [1700, 932, 2370, 962],
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.90,
                    "reasoning": "第5条前标记与 CC 图例一致。",
                },
            ]

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload, ensure_ascii=False)),
                {"part_family": "hinge"},
            )

        self.assertEqual(
            [item["candidate_id"] for item in bundle["located_occurrences"]],
            ["SC-REQ4-TORQUE", "CC-REQ5-GB15086"],
        )
        self.assertEqual(
            [item["candidate_id"] for item in bundle["special_characteristic_candidates"]],
            ["SC-REQ4-TORQUE", "CC-REQ5-GB15086"],
        )
        self.assertEqual(
            bundle["special_characteristic_discovery"]["missing_counts"],
            {"CC": 0, "SC": 0},
        )

    def test_multimodal_json_can_be_wrapped_in_markdown_fence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")))
            content = "```json\n" + json.dumps(SharedTestHelpers.analysis_payload()) + "\n```"
            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(content),
                {"part_family": "hinge"},
            )

            self.assertTrue(validate_bundle_schema(bundle, "drawing_analysis_bundle"))
            self.assertEqual(bundle["drawing_identity"]["part_name"], "Hinge Bracket")

    def test_invalid_ai_json_and_non_page_unknown_evidence_refs_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")))

            with self.assertRaisesRegex(DrawingAnalysisError, "invalid JSON"):
                analyze_drawing_pages(pages, FakeMultimodalDrawingAnalyzer("{bad"))

            payload = SharedTestHelpers.analysis_payload()
            payload["materials"][0]["evidence_refs"] = ["missing"]
            pages.append(replace(pages[0], evidence_id="drawing_page_002", page_number=2))
            with self.assertRaisesRegex(DrawingAnalysisError, "unknown evidence"):
                analyze_drawing_pages(
                    pages,
                    FakeMultimodalDrawingAnalyzer(json.dumps(payload)),
                )

    def test_unknown_single_page_drawing_ref_is_repaired_for_manual_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")))
            payload = SharedTestHelpers.analysis_payload()
            payload["materials"][0]["evidence_refs"] = ["drawing_page_003"]

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload)),
            )
            material = bundle["materials"][0]
            gate = evaluate_drawing_recognition_gate(bundle)

            self.assertEqual(material["evidence_refs"], ["drawing_page_001"])
            self.assertEqual(material["original_evidence_refs"], ["drawing_page_003"])
            self.assertTrue(material["needs_confirmation"])
            self.assertIn("evidence_ref_repairs", material)
            self.assertIn("evidence_ref_repairs", bundle["metadata"])
            self.assertTrue(gate.can_continue)
            self.assertTrue(gate.needs_human_review)
            self.assertFalse(gate.missing_evidence_refs)
            self.assertTrue(
                any(
                    getattr(item, "category", "") == "drawing_evidence_ref_repaired"
                    for item in gate.manual_review_items
                )
            )

    def test_unknown_single_page_model_ref_is_repaired_for_manual_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")))
            payload = SharedTestHelpers.analysis_payload()
            payload["dimensions"][0]["evidence_refs"] = ["image_dimension_annotation"]

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload)),
            )
            dimension = bundle["dimensions"][0]
            gate = evaluate_drawing_recognition_gate(bundle)

            self.assertEqual(dimension["evidence_refs"], ["drawing_page_001"])
            self.assertEqual(dimension["original_evidence_refs"], ["image_dimension_annotation"])
            self.assertTrue(dimension["needs_confirmation"])
            self.assertIn("evidence_ref_repairs", dimension)
            self.assertIn("evidence_ref_repairs", bundle["metadata"])
            self.assertTrue(gate.can_continue)
            self.assertTrue(gate.needs_human_review)
            self.assertFalse(gate.missing_evidence_refs)

    def test_invalid_confidence_is_traceable_in_drawing_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")))
            payload = SharedTestHelpers.analysis_payload()
            payload["materials"][0]["confidence"] = "not-a-number"

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload)),
            )
            gate = evaluate_drawing_recognition_gate(bundle)

            self.assertTrue(bundle["materials"][0]["needs_confirmation"])
            self.assertIn("confidence_parse_errors", bundle["materials"][0])
            self.assertTrue(gate.evidence_coverage["confidence_parse_error_items"])
            self.assertTrue(
                any(
                    getattr(item, "category", "") == "drawing_confidence_parse_error"
                    for item in gate.manual_review_items
                )
            )

    def test_drawing_gate_projects_metadata_risks_as_manual_review_items(self):
        bundle = {
            "drawing_identity": {
                "part_name": "D00R HIMGE",
                "drawing_number": "JLV03000500",
                "revision": "A",
            },
            "materials": [{"name": "steel", "evidence_refs": ["drawing_page_001"]}],
            "manufacturing_clues": [{"clue": "stamping", "evidence_refs": ["drawing_page_001"]}],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
            "metadata": {
                "drawing_analysis_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
                        "category": "drawing_identity",
                        "severity": "blocker",
                        "target": "drawing_identity.part_name",
                        "message": "图纸身份 OCR 疑似错误，正式输出前必须人工复核。",
                    }
                ],
                "ocr_identity_risks": [
                    {
                        "risk_id": "TECHREQ-SALT-SPRAY-RED-RUST-MISSING",
                        "category": "technical_requirement",
                        "severity": "blocker",
                        "target": "technical_requirements.salt_spray.red_rust",
                        "message": "红锈 240h 盐雾要求未进入正式控制链。",
                    }
                ],
            },
        }

        gate = evaluate_drawing_recognition_gate(bundle)
        dump = gate.model_dump()

        self.assertFalse(gate.can_continue)
        self.assertTrue(
            any(
                item.get("item_id") == "DRAWING-IDENTITY-SUSPECT-OCR"
                for item in dump["manual_review_items"]
            )
        )
        self.assertTrue(
            any(
                item.get("item_id") == "TECHREQ-SALT-SPRAY-RED-RUST-MISSING"
                for item in dump["manual_review_items"]
            )
        )

    def test_drawing_gate_review_risk_needs_review_without_blocking_continue(self):
        bundle = {
            "drawing_identity": {
                "part_name": "DOOR HINGE",
                "drawing_number": "JLV03000500",
                "revision": "A",
            },
            "materials": [{"name": "steel", "evidence_refs": ["drawing_page_001"]}],
            "manufacturing_clues": [{"clue": "stamping", "evidence_refs": ["drawing_page_001"]}],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
            "metadata": {
                "drawing_analysis_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-REVIEW",
                        "category": "drawing_identity",
                        "severity": "review",
                        "target": "drawing_identity.part_name",
                        "message": "图纸身份需要人工复核，但不阻断继续生成。",
                    }
                ]
            },
        }

        gate = evaluate_drawing_recognition_gate(bundle)
        dump = gate.model_dump()

        self.assertTrue(gate.can_continue)
        self.assertTrue(
            any(
                item.get("item_id") == "DRAWING-IDENTITY-REVIEW"
                for item in dump["manual_review_items"]
            )
        )

    def test_drawing_gate_dedupes_same_risk_id_from_drawing_and_ocr_metadata(self):
        bundle = {
            "drawing_identity": {
                "part_name": "D00R HIMGE",
                "drawing_number": "JLV03000500",
                "revision": "A",
            },
            "materials": [{"name": "steel", "evidence_refs": ["drawing_page_001"]}],
            "manufacturing_clues": [{"clue": "stamping", "evidence_refs": ["drawing_page_001"]}],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
            "metadata": {
                "drawing_analysis_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
                        "category": "drawing_identity",
                        "severity": "blocker",
                        "message": "图纸身份 OCR 疑似错误。",
                    }
                ],
                "ocr_identity_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
                        "category": "drawing_identity",
                        "severity": "blocker",
                        "message": "图纸身份 OCR 疑似错误。",
                    }
                ],
            },
        }

        gate = evaluate_drawing_recognition_gate(bundle)
        item_ids = [
            item.item_id
            for item in gate.manual_review_items
            if getattr(item, "item_id", "") == "DRAWING-IDENTITY-SUSPECT-OCR"
        ]

        self.assertEqual(item_ids, ["DRAWING-IDENTITY-SUSPECT-OCR"])

    def test_drawing_gate_duplicate_risk_id_keeps_blocker_severity(self):
        bundle = {
            "drawing_identity": {
                "part_name": "D00R HIMGE",
                "drawing_number": "JLV03000500",
                "revision": "A",
            },
            "materials": [{"name": "steel", "evidence_refs": ["drawing_page_001"]}],
            "manufacturing_clues": [{"clue": "stamping", "evidence_refs": ["drawing_page_001"]}],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
            "metadata": {
                "drawing_analysis_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
                        "category": "drawing_identity",
                        "severity": "review",
                        "message": "图纸身份 OCR 需要复核。",
                    }
                ],
                "ocr_identity_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
                        "category": "drawing_identity",
                        "severity": "blocker",
                        "message": "图纸身份 OCR 疑似错误，阻断继续生成。",
                    }
                ],
            },
        }

        gate = evaluate_drawing_recognition_gate(bundle)
        matching = [
            item
            for item in gate.manual_review_items
            if getattr(item, "item_id", "") == "DRAWING-IDENTITY-SUSPECT-OCR"
        ]

        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].severity, "blocker")
        self.assertFalse(gate.can_continue)

    def test_low_confidence_hybrid_ocr_identity_adds_suspect_risk(self):
        vision_analysis = {"metadata": {}, "drawing_identity": {"part_name": "DOOR HINGE"}}
        ocr_analysis = {
            "drawing_identity": {
                "part_name": "D00R HIMGE",
                "drawing_number": "JLV03000500",
                "revision": "A",
                "confidence": 0.42,
            }
        }

        _attach_ocr_reference_metadata(vision_analysis, ocr_analysis)
        _lock_hybrid_identity_from_ocr(vision_analysis, ocr_analysis)

        risks = vision_analysis["metadata"]["ocr_identity_risks"]
        self.assertEqual(risks[0]["risk_id"], "DRAWING-IDENTITY-SUSPECT-OCR")
        self.assertFalse(
            vision_analysis.get("drawing_identity", {}).get("ocr_identity_locked", False)
        )

    def test_three_table_chain_carries_drawing_and_ocr_risks(self):
        drawing_analysis = {
            "evidence": [],
            "metadata": {
                "drawing_analysis_risks": [
                    {
                        "risk_id": "TECHREQ-SALT-SPRAY-RED-RUST-MISSING",
                        "severity": "blocker",
                        "message": "红锈 240h 盐雾要求未进入正式控制链。",
                    }
                ],
                "ocr_identity_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
                        "severity": "blocker",
                        "message": "图纸身份 OCR 疑似错误，正式输出前必须人工复核。",
                    }
                ],
            },
        }

        chain = _assemble_three_table_chain(
            drawing_analysis,
            {"steps": [], "drawings": [], "characteristics": []},
            {"rows": []},
            {"rows": []},
        )

        risk_ids = {
            item["risk_id"]
            for item in chain["metadata"]["drawing_analysis_risks"]
        }
        self.assertEqual(
            risk_ids,
            {"DRAWING-IDENTITY-SUSPECT-OCR", "TECHREQ-SALT-SPRAY-RED-RUST-MISSING"},
        )

    def test_three_table_chain_duplicate_risk_id_keeps_blocker_severity(self):
        drawing_analysis = {
            "evidence": [],
            "metadata": {
                "drawing_analysis_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
                        "severity": "review",
                        "message": "图纸身份 OCR 需要复核。",
                    }
                ],
                "ocr_identity_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
                        "severity": "blocker",
                        "message": "图纸身份 OCR 疑似错误，阻断正式输出。",
                    }
                ],
            },
        }

        chain = _assemble_three_table_chain(
            drawing_analysis,
            {"steps": [], "drawings": [], "characteristics": []},
            {"rows": []},
            {"rows": []},
        )
        matching = [
            item
            for item in chain["metadata"]["drawing_analysis_risks"]
            if item.get("risk_id") == "DRAWING-IDENTITY-SUSPECT-OCR"
        ]

        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["severity"], "blocker")

    def test_export_gate_blocks_drawing_analysis_blocker_and_preserves_risk_id(self):
        chain = {
            "document_type": "apqp_chain",
            "schema_version": "minos-core.test.v1",
            "product": {},
            "process_steps": [],
            "failure_modes": [],
            "controls": [],
            "evidence": [],
            "pending_fields": [],
            "ai_inferred_items": [],
            "metadata": {
                "drawing_analysis_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
                        "category": "drawing_identity",
                        "severity": "blocker",
                        "target": "drawing_identity.part_name",
                        "message": "图纸身份 OCR 疑似错误，正式输出前必须人工复核。",
                    }
                ]
            },
        }

        gate = evaluate_export_gate(chain)
        gate_dump = gate.model_dump()
        gate_text = json.dumps(gate_dump, ensure_ascii=False, default=str)

        self.assertFalse(gate.allow_user_export)
        self.assertIn("DRAWING-IDENTITY-SUSPECT-OCR", gate_text)
        self.assertTrue(
            any(
                item.get("item_id") == "DRAWING-IDENTITY-SUSPECT-OCR"
                for item in gate_dump["manual_review_items"]
            )
        )

    def test_export_gate_blocks_unconfirmed_review_drawing_risk(self):
        chain = copy.deepcopy(
            load_fixture_payload(Path(__file__).resolve().parents[1] / "fixtures" / "apqp_chain")
        )
        chain.setdefault("metadata", {})["drawing_analysis_risks"] = [
            {
                "risk_id": "DRAWING-IDENTITY-REVIEW",
                "category": "drawing_identity",
                "severity": "review",
                "target": "drawing_identity.part_name",
                "message": "图纸身份需要人工复核后才能正式放行。",
            }
        ]

        gate = evaluate_export_gate(chain)
        gate_text = json.dumps(gate.model_dump(), ensure_ascii=False, default=str)

        self.assertFalse(gate.allow_user_export)
        self.assertIn("DRAWING-IDENTITY-REVIEW", gate_text)

    def test_export_gate_dedupes_same_risk_id_from_drawing_and_ocr_metadata(self):
        chain = copy.deepcopy(
            load_fixture_payload(Path(__file__).resolve().parents[1] / "fixtures" / "apqp_chain")
        )
        duplicate_risk = {
            "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
            "category": "drawing_identity",
            "severity": "review",
            "target": "drawing_identity.part_name",
            "message": "图纸身份 OCR 疑似错误，正式输出前必须人工复核。",
        }
        chain.setdefault("metadata", {})["drawing_analysis_risks"] = [dict(duplicate_risk)]
        chain["metadata"]["ocr_identity_risks"] = [dict(duplicate_risk)]

        gate = evaluate_export_gate(chain)
        item_ids = [
            item.item_id
            for item in gate.manual_review_items
            if getattr(item, "item_id", "") == "DRAWING-IDENTITY-SUSPECT-OCR"
        ]

        self.assertEqual(item_ids, ["DRAWING-IDENTITY-SUSPECT-OCR"])

    def test_export_gate_duplicate_risk_id_keeps_blocker_severity(self):
        chain = copy.deepcopy(
            load_fixture_payload(Path(__file__).resolve().parents[1] / "fixtures" / "apqp_chain")
        )
        chain.setdefault("metadata", {})["drawing_analysis_risks"] = [
            {
                "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
                "category": "drawing_identity",
                "severity": "review",
                "target": "drawing_identity.part_name",
                "message": "图纸身份 OCR 需要复核。",
            }
        ]
        chain["metadata"]["ocr_identity_risks"] = [
            {
                "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
                "category": "drawing_identity",
                "severity": "blocker",
                "target": "drawing_identity.part_name",
                "message": "图纸身份 OCR 疑似错误，正式输出前必须人工复核。",
            }
        ]

        gate = evaluate_export_gate(chain)
        matching = [
            item
            for item in gate.manual_review_items
            if getattr(item, "item_id", "") == "DRAWING-IDENTITY-SUSPECT-OCR"
        ]

        self.assertFalse(gate.allow_user_export)
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].severity, "blocker")

    def test_drawing_to_pfd_accepts_nested_ai_fields_and_process_step_clues(self):
        bundle = {
            "drawing_identity": {
                "part_name": {"value": "DEMO BRACKET", "confidence": 0.99, "evidence_refs": ["drawing_page_001"]},
                "drawing_number": {
                    "value": "MINOS-DEMO-001",
                    "confidence": 0.99,
                    "evidence_refs": ["drawing_page_001"],
                },
                "revision": {"value": "A", "confidence": 0.99, "evidence_refs": ["drawing_page_001"]},
            },
            "special_characteristics": [
                {
                    "id": "SC-01",
                    "description": "hole position",
                    "classification": "special characteristic",
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "manufacturing_clues": [
                {
                    "process_step": "blanking",
                    "sequence": 1,
                    "confidence": 0.99,
                    "evidence_refs": ["drawing_page_001"],
                },
                {
                    "process_step": "piercing",
                    "sequence": 2,
                    "confidence": 0.99,
                    "special_characteristics": ["SC-01"],
                    "evidence_refs": ["drawing_page_001"],
                },
            ],
            "evidence": [
                {
                    "evidence_id": "drawing_page_001",
                    "source": "drawing_page",
                }
            ],
        }

        pfd = infer_process_flow_from_drawing(bundle)

        operations = [step["operation"] for step in pfd["steps"]]
        self.assertEqual(operations[:2], ["来料检验", "材料准备"])
        self.assertIn("落料", operations)
        self.assertIn("冲孔", operations)
        self.assertEqual(operations[-3:], ["过程检验", "最终检验", "包装"])
        library_steps = [step for step in pfd["steps"] if step["source"] == "process_library"]
        self.assertTrue(library_steps)
        self.assertTrue(all(step["ai_inferred"] for step in library_steps))
        self.assertTrue(all(step["needs_confirmation"] for step in library_steps))
        self.assertTrue(all(step["evidence_refs"] == ["drawing_page_001"] for step in library_steps))
        self.assertEqual(pfd["product"]["part_name"], "DEMO BRACKET")
        self.assertEqual(pfd["drawings"][0]["drawing_id"], "MINOS-DEMO-001")
        self.assertEqual(pfd["drawings"][0]["source_ref"], "drawing_page_001")
        self.assertEqual(pfd["characteristics"][0]["characteristic_id"], "SC-01")
        self.assertEqual(pfd["links"][0]["from"], "P10")
        self.assertEqual(pfd["links"][0]["to"], "P20")

    def test_drawing_analysis_gate_accepts_nested_evidence_and_sequence_clues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(
                load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            )
            payload = {
                "drawing_identity": {
                    "part_name": {"value": "DEMO BRACKET", "evidence_refs": ["drawing_page_001"]},
                    "drawing_number": {"value": "MINOS-DEMO-001", "evidence_refs": ["drawing_page_001"]},
                    "revision": {"value": "A", "evidence_refs": ["drawing_page_001"]},
                },
                "materials": [
                    {
                        "material_spec": {
                            "value": "SPCC-SD",
                            "confidence": 0.96,
                            "evidence_refs": ["drawing_page_001"],
                        },
                        "thickness": {
                            "value": 1.6,
                            "confidence": 0.96,
                            "evidence_refs": ["drawing_page_001"],
                        },
                    }
                ],
                "surface_treatments": [],
                "dimensions": [],
                "tolerances": [],
                "special_characteristics": [],
                "technical_requirements": [],
                "inspection_requirements": [],
                "manufacturing_clues": [
                    {
                        "process_sequence": ["blanking", "piercing", "deburr"],
                        "source_text": "blanking -> piercing -> deburr",
                        "confidence": 0.95,
                        "evidence_refs": ["drawing_page_001"],
                    }
                ],
                "uncertainties": [],
            }

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload)),
            )

        gate = evaluate_drawing_recognition_gate(bundle)
        pfd = infer_process_flow_from_drawing(bundle)
        operations = [step["operation"] for step in pfd["steps"]]
        self.assertTrue(gate.can_continue)
        self.assertFalse(gate.missing_evidence_refs)
        self.assertEqual(operations[:2], ["来料检验", "材料准备"])
        self.assertIn("落料", operations)
        self.assertIn("冲孔", operations)
        self.assertIn("去毛刺", operations)
        self.assertEqual(operations[-3:], ["过程检验", "最终检验", "包装"])

    def test_drawing_to_pfd_can_infer_steps_from_free_text_manufacturing_clue(self):
        bundle = {
            "drawing_identity": {
                "part_name": {"value": "DEMO PANEL", "evidence_refs": ["drawing_page_001"]},
                "drawing_number": {"value": "PANEL-001", "evidence_refs": ["drawing_page_001"]},
                "revision": {"value": "A", "evidence_refs": ["drawing_page_001"]},
            },
            "special_characteristics": [],
            "manufacturing_clues": [
                {
                    "clue": "Likely injection molded part due to uniform thin wall and ribbing",
                    "confidence": 0.9,
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
        }

        pfd = infer_process_flow_from_drawing(bundle)

        operations = [step["operation"] for step in pfd["steps"]]
        self.assertEqual(operations[:2], ["来料检验", "材料准备"])
        self.assertIn("注塑", operations)
        self.assertIn("修边", operations)
        self.assertEqual(operations[-3:], ["过程检验", "最终检验", "包装"])
        self.assertTrue(all(step["needs_confirmation"] for step in pfd["steps"]))

    def test_drawing_to_pfd_adds_common_sheet_metal_process_library_steps(self):
        bundle = {
            "drawing_identity": {
                "part_name": {"value": "DEMO STAMPING", "evidence_refs": ["drawing_page_001"]},
                "drawing_number": {"value": "STAMP-001", "evidence_refs": ["drawing_page_001"]},
                "revision": {"value": "A", "evidence_refs": ["drawing_page_001"]},
            },
            "materials": [{"name": "sheet metal SPCC", "evidence_refs": ["drawing_page_001"]}],
            "surface_treatments": [{"name": "zinc plating", "evidence_refs": ["drawing_page_001"]}],
            "technical_requirements": [
                {
                    "text": "No burrs, clean before plating",
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "special_characteristics": [],
            "manufacturing_clues": [
                {
                    "clue": "Likely stamping sheet metal part",
                    "confidence": 0.9,
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
        }

        pfd = infer_process_flow_from_drawing(bundle)
        operations = [step["operation"] for step in pfd["steps"]]

        self.assertEqual(operations[:2], ["来料检验", "材料准备"])
        for expected in ("落料", "成形", "去毛刺", "清洗", "表面处理"):
            self.assertIn(expected, operations)
        self.assertEqual(operations[-3:], ["过程检验", "最终检验", "包装"])
        for step in pfd["steps"]:
            if step["source"] == "process_library":
                self.assertTrue(step["ai_inferred"])
                self.assertTrue(step["needs_confirmation"])
                self.assertEqual(step["evidence_refs"], ["drawing_page_001"])

    def test_drawing_analysis_preserves_unconfirmed_sc_candidate_as_review_risk(self):
        bundle = {
            "drawing_identity": {
                "part_name": "DEMO BRACKET",
                "drawing_number": "D-001",
                "revision": "A",
            },
            "materials": [{"name": "SPCC", "evidence_refs": ["drawing_page_001"]}],
            "manufacturing_clues": [{"operation": "冲孔", "evidence_refs": ["drawing_page_001"]}],
            "special_characteristic_candidates": [
                {
                    "candidate_type": "unknown",
                    "source": "visual_symbol",
                    "symbol_text_or_shape": "customer_star",
                    "linked_feature": "孔径 10.0 mm",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.70,
                }
            ],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
        }

        gate = evaluate_drawing_recognition_gate(bundle)
        dump = gate.model_dump()

        self.assertTrue(gate.can_continue)
        self.assertTrue(
            any(
                item.get("item_id") == "SC-CANDIDATE-MSC-001"
                for item in dump["manual_review_items"]
            )
        )

    def test_unconfirmed_sc_candidate_does_not_propagate_to_three_tables(self):
        drawing_analysis = {
            "drawing_identity": {
                "part_name": "DEMO BRACKET",
                "drawing_number": "D-001",
                "revision": "A",
            },
            "materials": [{"name": "SPCC", "evidence_refs": ["drawing_page_001"]}],
            "manufacturing_clues": [
                {
                    "operation": "冲孔",
                    "special_characteristics": ["SC-001"],
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "special_characteristic_candidates": [
                {
                    "candidate_id": "MSC-001",
                    "candidate_type": "unknown",
                    "source": "visual_symbol",
                    "linked_feature": "孔径 10.0 mm",
                    "evidence_refs": ["drawing_page_001"],
                    "needs_confirmation": True,
                    "confirmation_status": "needs_human_review",
                }
            ],
            "special_characteristics": [],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
            "metadata": {
                "drawing_analysis_risks": [
                    {
                        "risk_id": "SC-CANDIDATE-MSC-001",
                        "severity": "review",
                        "target": "special_characteristic_candidates.MSC-001",
                        "message": "图纸存在未确认的特殊特性候选。",
                    }
                ]
            },
        }

        process_flow = infer_process_flow_from_drawing(drawing_analysis)
        registry = build_characteristic_registry(drawing_analysis)
        attached = attach_characteristics_to_three_tables(
            {"process_flow": process_flow},
            registry,
        )["process_flow"]

        from minos_core.special_characteristic_candidates import (
            strip_unconfirmed_special_characteristic_refs,
        )

        strip_unconfirmed_special_characteristic_refs(attached, registry)

        self.assertEqual(attached["steps"][0]["special_characteristics"], [])

    def test_final_export_gate_blocks_unconfirmed_sc_candidate_risk(self):
        chain = {
            "document_type": "apqp_chain",
            "schema_version": "minos-core.generated.v1",
            "product": {},
            "process_steps": [],
            "failure_modes": [],
            "controls": [],
            "evidence": [],
            "metadata": {
                "drawing_analysis_risks": [
                    {
                        "risk_id": "SC-CANDIDATE-MSC-001",
                        "category": "special_characteristic_candidate",
                        "severity": "review",
                        "target": "special_characteristic_candidates.MSC-001",
                        "message": "图纸存在未确认的特殊特性候选。",
                    }
                ]
            },
        }

        gate = evaluate_export_gate(chain)

        self.assertFalse(gate.allow_user_export)
        self.assertTrue(
            any(
                item.item_id == "SC-CANDIDATE-MSC-001"
                for item in gate.manual_review_items
            )
        )

    def test_fake_visual_sc_candidate_stays_candidate_without_judge(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(
                load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            )
            payload = {
                "drawing_identity": {
                    "part_name": "DEMO BRACKET",
                    "drawing_number": "D-001",
                    "revision": "A",
                },
                "materials": [{"name": "SPCC", "evidence_refs": ["drawing_page_001"], "confidence": 0.95}],
                "manufacturing_clues": [
                    {
                        "operation": "冲孔",
                        "process_function": "控制孔径 10.0 +0.05/0 mm",
                        "evidence_refs": ["drawing_page_001"],
                        "confidence": 0.91,
                    }
                ],
                "special_characteristic_candidates": [
                    {
                        "candidate_type": "SC",
                        "source": "gpt55_visual_locator",
                        "symbol_text_or_shape": "SC",
                        "linked_feature": "孔径 10.0 +0.05/0 mm",
                        "symbol_bbox": [0.1, 0.2, 0.05, 0.04],
                        "linked_feature_bbox": [0.2, 0.2, 0.2, 0.05],
                        "evidence_refs": ["drawing_page_001"],
                        "confidence": 0.93,
                    }
                ],
                "special_characteristics": [],
                "technical_requirements": [],
                "inspection_requirements": [],
                "uncertainties": [],
            }

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload, ensure_ascii=False)),
            )

        registry = build_characteristic_registry(bundle)
        pfd = infer_process_flow_from_drawing(bundle)
        attached = attach_characteristics_to_three_tables({"process_flow": pfd}, registry)["process_flow"]

        sc_items = [
            item for item in registry["items"]
            if item["classification"] == "special_characteristic"
        ]
        self.assertEqual(sc_items, [])
        self.assertEqual(bundle["special_characteristic_candidates"][0]["candidate_id"], "MSC-001")
        self.assertEqual(bundle["special_characteristics"], [])
        self.assertFalse(
            any(step.get("special_characteristics") for step in attached["steps"])
        )

    def test_gpt55_visual_locator_jlv_candidates_keep_req4_sc_and_req5_req6_cc_without_raw_bypass(self):
        class _GPT55VisualLocatorAnalyzer:
            def analyze_drawing_pages(self, _pages, _context=None):
                payload = {
                    "drawing_identity": {
                        "part_name": "RR DH ASSY",
                        "drawing_number": "JLV03000500",
                        "revision": "A",
                    },
                    "materials": [
                        {
                            "name": "SPCC",
                            "evidence_refs": ["drawing_page_001"],
                            "confidence": 0.95,
                        }
                    ],
                    "manufacturing_clues": [
                        {
                            "operation": "装配",
                            "evidence_refs": ["drawing_page_001"],
                            "confidence": 0.91,
                        }
                    ],
                    "special_characteristics": [
                        {
                            "name": "技术要求第6条：Q/BJORV M 0102",
                            "classification": "SC",
                            "evidence_refs": ["drawing_page_001"],
                            "confidence": 0.96,
                        }
                    ],
                    "special_characteristic_candidates": [
                        {
                            "candidate_id": "SC-REQ4-TORQUE",
                            "candidate_type": "SC",
                            "source": "gpt55_visual_locator",
                            "symbol_text_or_shape": "水平圆角长框",
                            "linked_feature": "技术要求第4条第(2)项：转动力矩(0.5~2.5)Nm",
                            "symbol_bbox": [0.62, 0.52, 0.08, 0.03],
                            "evidence_refs": ["drawing_page_001"],
                            "confidence": 0.96,
                            "reasoning": "形状与右下 SC 图例一致。",
                        },
                        {
                            "candidate_id": "CC-REQ5-GB15086",
                            "candidate_type": "CC",
                            "source": "gpt55_visual_locator",
                            "symbol_text_or_shape": "圆内倒三角",
                            "linked_feature": "技术要求第5条：GB 15086",
                            "symbol_bbox": [0.58, 0.56, 0.08, 0.03],
                            "evidence_refs": ["drawing_page_001"],
                            "confidence": 0.90,
                            "reasoning": "第5条前标记与 CC 图例一致。",
                        },
                        {
                            "candidate_id": "CC-REQ6-M0102",
                            "candidate_type": "CC",
                            "source": "gpt55_visual_locator",
                            "symbol_text_or_shape": "圆内倒三角",
                            "linked_feature": "技术要求第6条：Q/BJORV M 0102",
                            "symbol_bbox": [0.58, 0.59, 0.08, 0.03],
                            "evidence_refs": ["drawing_page_001"],
                            "confidence": 0.82,
                            "reasoning": "第6条前标记与 CC 图例一致。",
                        },
                    ],
                }
                return MultimodalDrawingResult(
                    content=json.dumps(payload, ensure_ascii=False),
                    model="gpt-5.5",
                    metadata={"source": "gpt55_visual_locator"},
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(
                load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            )
            bundle = analyze_drawing_pages(pages, _GPT55VisualLocatorAnalyzer())

        self.assertEqual(bundle["special_characteristics"], [])
        self.assertEqual(
            {
                item["candidate_id"]: item["candidate_type"]
                for item in bundle["special_characteristic_candidates"]
            },
            {
                "SC-REQ4-TORQUE": "SC",
                "CC-REQ5-GB15086": "CC",
                "CC-REQ6-M0102": "CC",
            },
        )
        registry = build_characteristic_registry(bundle)
        self.assertEqual(
            [
                item
                for item in registry["items"]
                if item["classification"] == "special_characteristic"
            ],
            [],
        )


if __name__ == "__main__":
    unittest.main()
