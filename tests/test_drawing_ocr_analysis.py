"""Tests for drawing_ocr_analysis: field extraction, confidence, error handling."""

from __future__ import annotations

import unittest

from minos_core.adapters.ocr import OCRPageText, OCRResult
from minos_core.drawing_ocr_analysis import build_drawing_analysis_bundle_from_ocr


def _ocr_result(text: str, confidence: float | None = 0.95, source_ref: str = "test.png") -> OCRResult:
    return OCRResult(
        source_ref=source_ref,
        pages=[OCRPageText(page_number=1, text=text, confidence=confidence, engine="test")],
    )


def _bundle(text: str, confidence: float | None = 0.95, source_ref: str = "test.png", context=None):
    return build_drawing_analysis_bundle_from_ocr([], _ocr_result(text, confidence, source_ref), context)


class TestExtractDrawingNumberFromOcrText(unittest.TestCase):
    def test_extract_drawing_number_from_ocr_text(self):
        bundle = _bundle("Drawing No.: ABC-12345\nPart Name: Bracket")
        self.assertEqual(bundle["drawing_identity"]["drawing_number"], "ABC-12345")

    def test_extract_drawing_number_chinese_label(self):
        bundle = _bundle("图号: HJ-0029\n名称: 铰链支架")
        self.assertEqual(bundle["drawing_identity"]["drawing_number"], "HJ-0029")


class TestExtractPartNameFromOcrText(unittest.TestCase):
    def test_extract_part_name_from_ocr_text(self):
        bundle = _bundle("Drawing No.: XYZ-100\nPart Name: Hinge Bracket Assembly")
        self.assertEqual(bundle["drawing_identity"]["part_name"], "Hinge Bracket Assembly")

    def test_extract_part_name_chinese_label(self):
        bundle = _bundle("图号: P001\n名称: 限位器支架")
        self.assertEqual(bundle["drawing_identity"]["part_name"], "限位器支架")


class TestExtractMaterialFromOcrText(unittest.TestCase):
    def test_extract_material_from_ocr_text(self):
        bundle = _bundle("Material: SPCC-SD\nDrawing No.: M-001")
        materials = bundle["materials"]
        self.assertTrue(any("SPCC-SD" in m["name"] for m in materials))

    def test_extract_material_pattern_match(self):
        bundle = _bundle("图号: T-001\nSPCC t=1.2")
        materials = bundle["materials"]
        self.assertTrue(len(materials) > 0)


class TestExtractSurfaceTreatmentFromOcrText(unittest.TestCase):
    def test_extract_surface_treatment_from_ocr_text(self):
        bundle = _bundle("Surface Treatment: Zinc plating\nDrawing No.: S-001")
        treatments = bundle["surface_treatments"]
        self.assertTrue(any("Zinc plating" in t["name"] for t in treatments))

    def test_extract_surface_treatment_chinese(self):
        bundle = _bundle("图号: S-002\n表面处理: 镀锌")
        treatments = bundle["surface_treatments"]
        self.assertTrue(any("镀锌" in t["name"] for t in treatments))


class TestSpecialCharacteristicExtractionFromOcrText(unittest.TestCase):
    def test_ocr_bundle_attaches_declared_special_characteristic_counts(self):
        bundle = _bundle(
            "关键特性 CC (Critical Characteristic) 2\n"
            "重要特性 SC (Special Characteristic) 1"
        )

        self.assertEqual(bundle["declared_totals"], {"CC": 2, "SC": 1})
        self.assertEqual(
            bundle["declared_special_characteristics"][0]["classification"],
            "CC",
        )

    def test_numeric_requirement_is_not_special_characteristic_without_marker(self):
        bundle = _bundle(
            "按GB/T10125进行中性盐雾试验，红锈出现时间不低于120h。"
        )

        self.assertTrue(bundle["numeric_specifications"])
        self.assertEqual(bundle["special_characteristics"], [])

    def test_explicit_special_characteristic_marker_is_preserved(self):
        bundle = _bundle("SC 孔径 10.0 +/- 0.1 mm")

        self.assertEqual(bundle["special_characteristics"][0]["classification"], "SC")

    def test_ptc_marker_is_not_promoted_to_supported_special_characteristic(self):
        bundle = _bundle("PTC 菱形 图例定义项")

        self.assertEqual(bundle["special_characteristics"], [])


class TestConfidenceCalculationForHighQualityOcr(unittest.TestCase):
    def test_confidence_calculation_for_high_quality_ocr(self):
        bundle = _bundle("Drawing No.: HQ-001\nPart Name: Test Part", confidence=0.98)
        identity = bundle["drawing_identity"]
        self.assertGreaterEqual(identity["confidence"], 0.9)


class TestConfidenceCalculationForLowQualityOcr(unittest.TestCase):
    def test_confidence_calculation_for_low_quality_ocr(self):
        bundle = _bundle("Drawing No.: LQ-001\nPart Name: Blurry Part", confidence=0.4)
        identity = bundle["drawing_identity"]
        self.assertLessEqual(identity["confidence"], 0.5)


class TestConfidencePropagationToFields(unittest.TestCase):
    def test_confidence_propagation_to_fields(self):
        result = _ocr_result("Material: SECC\nSurface Treatment: Nickel plating", confidence=0.85)
        bundle = build_drawing_analysis_bundle_from_ocr([], result, None)
        for material in bundle["materials"]:
            self.assertIn("confidence", material)
            self.assertLessEqual(material["confidence"], 0.85)
        for treatment in bundle["surface_treatments"]:
            self.assertIn("confidence", treatment)
            self.assertLessEqual(treatment["confidence"], 0.85)


class TestHandlesInvalidOcrResults(unittest.TestCase):
    def test_handles_invalid_ocr_results(self):
        empty_result = OCRResult(source_ref="empty.png", pages=[])
        bundle = build_drawing_analysis_bundle_from_ocr([], empty_result, None)
        self.assertEqual(bundle["document_type"], "drawing_analysis_bundle")
        self.assertEqual(bundle["drawing_identity"]["drawing_number"], "")


class TestHandlesMissingRequiredFields(unittest.TestCase):
    def test_handles_missing_required_fields(self):
        # Use a numeric-only filename so _part_name_from_filename returns ""
        bundle = _bundle("some random text with no structured fields at all", source_ref="0.png")
        identity = bundle["drawing_identity"]
        self.assertEqual(identity["drawing_number"], "")
        self.assertEqual(identity["part_name"], "")
        self.assertTrue(identity["needs_confirmation"])


class TestFallbackToFilenameWhenOcrFails(unittest.TestCase):
    def test_fallback_to_filename_when_ocr_fails(self):
        bundle = _bundle("", confidence=None, source_ref="ABC-999_Bracket_RevA.pdf")
        identity = bundle["drawing_identity"]
        self.assertIn("ABC-999", identity["drawing_number"])


if __name__ == "__main__":
    unittest.main()
