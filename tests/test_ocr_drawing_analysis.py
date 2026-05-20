import sys
import types
import unittest
from unittest.mock import patch

from minos_core.adapters.ocr import (
    OCRBlock,
    OCRDependencyError,
    OCRPageText,
    OCRResult,
    PyMuPDFTextLayerOCRAdapter,
    RapidOCRPageAdapter,
)
from minos_core.drawing_input import DrawingPageEvidence
from minos_core.drawing_ocr_analysis import build_drawing_analysis_bundle_from_ocr
from minos_core.drawing_ocr_analysis import analyze_drawing_with_ocr
from minos_core.part_family_classifier import classify_part_family
from minos_core.schemas import validate_bundle_schema


class OCRDrawingAnalysisTests(unittest.TestCase):
    def test_analyze_drawing_with_ocr_uses_adapter_and_preserves_traceability(self):
        adapter = _CapturingOCRAdapter(
            OCRResult(
                source_ref="drawing.png",
                pages=[
                    OCRPageText(
                        page_number=1,
                        text="Drawing No: OCR-101\nPart Name: OCR Bracket\nMaterial: SPCC\nProcess: stamping",
                        confidence=0.88,
                        engine="unit_ocr",
                        source_ref="drawing.png",
                        blocks=[
                            OCRBlock(
                                block_number=1,
                                text="Drawing No: OCR-101\nPart Name: OCR Bracket",
                                confidence=0.9,
                                bbox=(1.0, 2.0, 30.0, 40.0),
                                engine="unit_ocr",
                                source_ref="drawing.png",
                            )
                        ],
                    )
                ],
            )
        )

        bundle = analyze_drawing_with_ocr(
            source={"path": __file__},
            pages=[_page_evidence()],
            output_dir="unused",
            context={"analysis_mode": "ocr_only"},
            ocr_engine="rapidocr",
            ocr_adapter=adapter,
        )

        self.assertTrue(validate_bundle_schema(bundle, "drawing_analysis_bundle"))
        self.assertEqual(adapter.source_ref, __file__)
        self.assertGreater(adapter.content_length, 0)
        self.assertEqual(bundle["drawing_identity"]["drawing_number"], "OCR-101")
        self.assertEqual(bundle["metadata"]["ocr"]["engine"], "unit_ocr")
        self.assertEqual(bundle["metadata"]["drawing_page_evidence_refs"], ["drawing_page_001"])
        self.assertTrue(bundle["materials"][0]["evidence_refs"])

    def test_ocr_only_bundle_has_stable_evidence_ids_and_valid_shape(self):
        ocr_result = OCRResult(
            source_ref="HB-001_Hinge_Bracket.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text=(
                        "Drawing No: HB-001 Rev: A\n"
                        "Part Name: Hinge Bracket\n"
                        "Material: SPCC t=1.2\n"
                        "Surface treatment: Zinc plated\n"
                        "Technical requirements: No burrs; clean before plating\n"
                        "Inspection: Check critical dimensions by gauge\n"
                        "ISO 2768-mK\n"
                        "Ø8.0 +/-0.1 CC\n"
                        "Process: stamping blanking piercing"
                    ),
                    confidence=0.91,
                    engine="fake_ocr",
                    source_ref="HB-001_Hinge_Bracket.pdf",
                    blocks=[
                        OCRBlock(
                            block_number=1,
                            text="Drawing No: HB-001 Rev: A\nPart Name: Hinge Bracket",
                            confidence=0.95,
                            bbox=(1.0, 2.0, 30.0, 40.0),
                            engine="fake_ocr",
                            source_ref="HB-001_Hinge_Bracket.pdf",
                        ),
                        OCRBlock(
                            block_number=2,
                            text=(
                                "Material: SPCC t=1.2\n"
                                "Surface treatment: Zinc plated\n"
                                "Technical requirements: No burrs; clean before plating\n"
                                "Inspection: Check critical dimensions by gauge\n"
                                "ISO 2768-mK\n"
                                "Ø8.0 +/-0.1 CC\n"
                                "Process: stamping blanking piercing"
                            ),
                            confidence=0.72,
                            bbox=(3.0, 4.0, 50.0, 80.0),
                            engine="fake_ocr",
                            source_ref="HB-001_Hinge_Bracket.pdf",
                        ),
                    ],
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr(
            [_page_evidence()],
            ocr_result,
        )

        self.assertTrue(validate_bundle_schema(bundle, "drawing_analysis_bundle"))
        self.assertEqual(
            [item["evidence_id"] for item in bundle["evidence"]],
            ["ocr_page_001", "ocr_page_001_block_0001", "ocr_page_001_block_0002"],
        )
        self.assertEqual(bundle["metadata"]["ocr"]["engine"], "fake_ocr")
        self.assertEqual(bundle["metadata"]["ocr"]["page_count"], 1)
        self.assertEqual(bundle["metadata"]["ocr"]["source_ref"], "HB-001_Hinge_Bracket.pdf")

        identity = bundle["drawing_identity"]
        self.assertEqual(identity["drawing_number"], "HB-001")
        self.assertEqual(identity["part_name"], "Hinge Bracket")
        self.assertEqual(identity["revision"], "A")
        self.assertTrue(identity["field_evidence_refs"]["drawing_number"])
        self.assertTrue(identity["field_evidence_refs"]["part_name"])
        self.assertTrue(identity["field_evidence_refs"]["revision"])

        self.assertTrue(bundle["materials"])
        self.assertTrue(bundle["surface_treatments"])
        self.assertTrue(bundle["technical_requirements"])
        self.assertTrue(bundle["inspection_requirements"])
        self.assertTrue(bundle["standard_references"])
        self.assertTrue(bundle["dimensions"])
        self.assertTrue(bundle["special_characteristics"])
        self.assertTrue(bundle["manufacturing_clues"])

        key_blocks = (
            "materials",
            "surface_treatments",
            "technical_requirements",
            "inspection_requirements",
            "standard_references",
            "dimensions",
            "special_characteristics",
            "manufacturing_clues",
        )
        for block_name in key_blocks:
            for item in bundle[block_name]:
                self.assertTrue(item["evidence_refs"], block_name)
                self.assertFalse(item["ai_inferred"], block_name)
                self.assertTrue(item["ocr_inferred"], block_name)
                self.assertTrue(item["needs_confirmation"], block_name)

    def test_unlabeled_title_block_extracts_part_name_for_family_classification(self):
        ocr_result = OCRResult(
            source_ref="drawing.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text=(
                        "JLV03000500BACKX D00R HIMGE 尾门较链\n"
                        "3.较链总成不可有衬套露出校链，制造件不可有毛刺"
                    ),
                    confidence=0.89,
                    engine="fake_ocr",
                    source_ref="drawing.pdf",
                    blocks=[
                        OCRBlock(
                            block_number=1,
                            text="JLV03000500BACKX D00R HIMGE 尾门较链",
                            confidence=0.93,
                            bbox=(70.0, 60.0, 98.0, 76.0),
                            engine="fake_ocr",
                            source_ref="drawing.pdf",
                        ),
                        OCRBlock(
                            block_number=2,
                            text="3.较链总成不可有衬套露出校链，制造件不可有毛刺",
                            confidence=0.84,
                            bbox=(5.0, 10.0, 80.0, 30.0),
                            engine="fake_ocr",
                            source_ref="drawing.pdf",
                        ),
                    ],
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)
        identity = bundle["drawing_identity"]

        self.assertIn("尾门铰链", identity["part_name"])
        self.assertEqual(
            identity["field_evidence_refs"]["part_name"],
            ["ocr_page_001_block_0001"],
        )

        classification = classify_part_family(bundle)
        self.assertEqual(classification["family_key"], "door_hinge")
        self.assertFalse(classification["needs_confirmation"])

    def test_conservative_manufacturing_clue_from_filename_avoids_empty_route(self):
        ocr_result = OCRResult(
            source_ref="PLASTIC-COVER-001.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text="Drawing No: PC-001\nPart Name: Cover\nMaterial: ABS",
                    confidence=0.88,
                    engine="fake_ocr",
                    source_ref="PLASTIC-COVER-001.pdf",
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)

        self.assertEqual(bundle["manufacturing_clues"][0]["operation"], "injection molding")
        self.assertTrue(bundle["manufacturing_clues"][0]["needs_confirmation"])

    def test_extract_drawing_number_from_ocr_text(self):
        ocr_result = OCRResult(
            source_ref="test.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text="Drawing No: ABC-12345-REV-A\nPart Name: Test Bracket",
                    confidence=0.92,
                    engine="test_ocr",
                    source_ref="test.pdf",
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)

        self.assertEqual(bundle["drawing_identity"]["drawing_number"], "ABC-12345-REV-A")
        self.assertTrue(bundle["drawing_identity"]["field_evidence_refs"]["drawing_number"])
        self.assertTrue(bundle["drawing_identity"]["ocr_inferred"])

    def test_extract_part_name_from_ocr_text(self):
        ocr_result = OCRResult(
            source_ref="test.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text="Drawing No: TEST-001\nPart Name: Door Hinge Assembly\nMaterial: SPCC",
                    confidence=0.89,
                    engine="test_ocr",
                    source_ref="test.pdf",
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)

        self.assertEqual(bundle["drawing_identity"]["part_name"], "Door Hinge Assembly")
        self.assertTrue(bundle["drawing_identity"]["field_evidence_refs"]["part_name"])
        self.assertTrue(bundle["drawing_identity"]["ocr_inferred"])

    def test_extract_material_from_ocr_text(self):
        ocr_result = OCRResult(
            source_ref="test.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text="Drawing No: MAT-001\nMaterial: SPCC t=1.5\nSurface: Zinc plated",
                    confidence=0.91,
                    engine="test_ocr",
                    source_ref="test.pdf",
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)

        self.assertTrue(bundle["materials"])
        self.assertIn("SPCC", bundle["materials"][0]["name"])
        self.assertTrue(bundle["materials"][0]["ocr_inferred"])
        self.assertTrue(bundle["materials"][0]["evidence_refs"])

    def test_extract_surface_treatment_from_ocr_text(self):
        ocr_result = OCRResult(
            source_ref="test.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text="Drawing No: SURF-001\nSurface treatment: Zinc plated\nMaterial: SPCC",
                    confidence=0.88,
                    engine="test_ocr",
                    source_ref="test.pdf",
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)

        self.assertTrue(bundle["surface_treatments"])
        self.assertIn("Zinc plated", bundle["surface_treatments"][0]["name"])
        self.assertTrue(bundle["surface_treatments"][0]["ocr_inferred"])
        self.assertTrue(bundle["surface_treatments"][0]["evidence_refs"])

    def test_confidence_calculation_for_high_quality_ocr(self):
        ocr_result = OCRResult(
            source_ref="high_quality.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text="Drawing No: HQ-001\nPart Name: High Quality Part\nMaterial: SPCC",
                    confidence=0.96,
                    engine="test_ocr",
                    source_ref="high_quality.pdf",
                    blocks=[
                        OCRBlock(
                            block_number=1,
                            text="Drawing No: HQ-001",
                            confidence=0.98,
                            bbox=(10.0, 20.0, 50.0, 30.0),
                            engine="test_ocr",
                            source_ref="high_quality.pdf",
                        )
                    ],
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)

        self.assertGreaterEqual(bundle["drawing_identity"]["confidence"], 0.9)
        self.assertEqual(bundle["evidence"][1]["confidence"], 0.98)

    def test_confidence_calculation_for_low_quality_ocr(self):
        ocr_result = OCRResult(
            source_ref="low_quality.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text="Drawing No: LQ-001\nPart Name: Low Quality Part",
                    confidence=0.62,
                    engine="test_ocr",
                    source_ref="low_quality.pdf",
                    blocks=[
                        OCRBlock(
                            block_number=1,
                            text="Drawing No: LQ-001",
                            confidence=0.65,
                            bbox=(10.0, 20.0, 50.0, 30.0),
                            engine="test_ocr",
                            source_ref="low_quality.pdf",
                        )
                    ],
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)

        self.assertLess(bundle["drawing_identity"]["confidence"], 0.75)
        self.assertTrue(bundle["drawing_identity"]["needs_confirmation"])

    def test_confidence_propagation_to_fields(self):
        ocr_result = OCRResult(
            source_ref="test.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text="Drawing No: CONF-001\nMaterial: SPCC\nSurface: Zinc plated",
                    confidence=0.85,
                    engine="test_ocr",
                    source_ref="test.pdf",
                    blocks=[
                        OCRBlock(
                            block_number=1,
                            text="Material: SPCC",
                            confidence=0.82,
                            bbox=(10.0, 20.0, 50.0, 30.0),
                            engine="test_ocr",
                            source_ref="test.pdf",
                        )
                    ],
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)

        self.assertTrue(bundle["materials"])
        self.assertIsNotNone(bundle["materials"][0]["confidence"])
        self.assertGreater(bundle["materials"][0]["confidence"], 0.0)
        self.assertLessEqual(bundle["materials"][0]["confidence"], 1.0)

    def test_handles_invalid_ocr_results(self):
        ocr_result = OCRResult(
            source_ref="invalid.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text="",
                    confidence=0.0,
                    engine="test_ocr",
                    source_ref="invalid.pdf",
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)

        self.assertTrue(validate_bundle_schema(bundle, "drawing_analysis_bundle"))
        self.assertTrue(bundle["uncertainties"])
        self.assertGreater(len(bundle["uncertainties"]), 0)

    def test_handles_missing_required_fields(self):
        ocr_result = OCRResult(
            source_ref="missing_fields.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text="Some random text without any structured fields",
                    confidence=0.88,
                    engine="test_ocr",
                    source_ref="missing_fields.pdf",
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)

        self.assertTrue(validate_bundle_schema(bundle, "drawing_analysis_bundle"))
        self.assertTrue(bundle["uncertainties"])
        uncertainty_texts = [u["text"] for u in bundle["uncertainties"]]
        self.assertTrue(any("OCR" in text for text in uncertainty_texts))
        self.assertGreater(len(bundle["uncertainties"]), 2)

    def test_fallback_to_filename_when_ocr_fails(self):
        ocr_result = OCRResult(
            source_ref="DWG-001 Door Bracket.pdf",
            pages=[
                OCRPageText(
                    page_number=1,
                    text="No structured data here",
                    confidence=0.75,
                    engine="test_ocr",
                    source_ref="DWG-001 Door Bracket.pdf",
                )
            ],
        )

        bundle = build_drawing_analysis_bundle_from_ocr([_page_evidence()], ocr_result)

        self.assertIn("DWG-001", bundle["drawing_identity"]["drawing_number"])
        self.assertIn("Door Bracket", bundle["drawing_identity"]["part_name"])
        self.assertTrue(bundle["drawing_identity"]["needs_confirmation"])

    def test_missing_rapidocr_dependency_error_is_clear(self):
        with patch.dict(sys.modules, {"rapidocr_onnxruntime": None}):
            with self.assertRaisesRegex(
                OCRDependencyError,
                r"rapidocr-onnxruntime; install minos-core\[ocr\]",
            ):
                RapidOCRPageAdapter().extract_text("drawing.png", b"not a real image")

    def test_pymupdf_text_layer_adapter_can_extract_with_fake_fitz(self):
        fake_fitz = types.SimpleNamespace(open=_fake_fitz_open)
        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            result = PyMuPDFTextLayerOCRAdapter().extract_text(
                "drawing.pdf",
                b"%PDF-1.4\nfake",
            )

        self.assertEqual(result.source_ref, "drawing.pdf")
        self.assertEqual(result.text, "Drawing No: PDF-001")
        self.assertEqual(result.pages[0].engine, "pymupdf_text_layer")
        self.assertEqual(result.pages[0].blocks[0].text, "Drawing No: PDF-001")
        self.assertEqual(result.pages[0].blocks[0].bbox, (10.0, 20.0, 30.0, 40.0))


def _page_evidence():
    return DrawingPageEvidence(
        evidence_id="drawing_page_001",
        source_id="drawing_test",
        page_number=1,
        image_path="drawing.png",
        width=100,
        height=80,
        sha256="abc123",
    )


class _CapturingOCRAdapter:
    def __init__(self, result: OCRResult) -> None:
        self.result = result
        self.source_ref = ""
        self.content_length = 0

    def extract_text(self, source_ref: str, content: bytes) -> OCRResult:
        self.source_ref = source_ref
        self.content_length = len(content)
        return self.result


def _fake_fitz_open(stream, filetype):
    return _FakeDocument()


class _FakeDocument:
    def __iter__(self):
        return iter([_FakePage()])

    def close(self):
        return None


class _FakePage:
    rect = (0.0, 0.0, 100.0, 200.0)

    def get_text(self, kind):
        if kind == "text":
            return "Drawing No: PDF-001"
        if kind == "blocks":
            return [(10.0, 20.0, 30.0, 40.0, "Drawing No: PDF-001", 0, 0)]
        return ""


if __name__ == "__main__":
    unittest.main()
