import json
import tempfile
import unittest
from pathlib import Path

from minos_core.adapters.multimodal import FakeMultimodalDrawingAnalyzer
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

    def test_drawing_analysis_preserves_bom_sub_components(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")))
            payload = SharedTestHelpers.analysis_payload()
            payload["sub_components"] = [
                {
                    "item_no": "2",
                    "part_name": "车门铰链车身件",
                    "part_number": "JLV03000501",
                    "quantity": 1,
                    "evidence_refs": ["drawing_page_001"],
                },
                {
                    "item_no": "4",
                    "part_name": "衬套",
                    "part_number": "BZJ01011000",
                    "quantity": 1,
                    "evidence_refs": ["drawing_page_001"],
                },
                {
                    "item_no": "5",
                    "part_name": "销轴",
                    "part_number": "BZJ01011100",
                    "quantity": 1,
                    "evidence_refs": ["drawing_page_001"],
                },
            ]

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload)),
                {"part_family": "hinge"},
            )

            self.assertTrue(validate_bundle_schema(bundle, "drawing_analysis_bundle"))
            names = [item["part_name"] for item in bundle["sub_components"]]
            self.assertEqual(names, ["车门铰链车身件", "衬套", "销轴"])

    def test_invalid_ai_json_and_non_page_unknown_evidence_refs_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png")))

            with self.assertRaisesRegex(DrawingAnalysisError, "invalid JSON"):
                analyze_drawing_pages(pages, FakeMultimodalDrawingAnalyzer("{bad"))

            payload = SharedTestHelpers.analysis_payload()
            payload["materials"][0]["evidence_refs"] = ["missing"]
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

    def test_drawing_to_pfd_accepts_nested_ai_fields_and_process_step_clues(self):
        bundle = {
            "drawing_identity": {
                "part_name": {"value": "DEMO BRACKET", "confidence": 0.99, "evidence_refs": ["drawing_page_001"]},
                "drawing_number": {"value": "MINOS-DEMO-001", "confidence": 0.99, "evidence_refs": ["drawing_page_001"]},
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
            "technical_requirements": [{"text": "No burrs, clean before plating", "evidence_refs": ["drawing_page_001"]}],
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


if __name__ == "__main__":
    unittest.main()
