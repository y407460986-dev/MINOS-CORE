import tempfile
import unittest
from pathlib import Path

from minos_core.stage import run_stage


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "apqp_chain"


class AnalyzeStageTests(unittest.TestCase):
    def test_analyze_stage_returns_analysis_bundle(self):
        result = run_stage(FIXTURE_DIR, stage="analyze")

        self.assertEqual(result.stage, "analyze")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "analysis_bundle")
        self.assertEqual(result.output["metadata"]["analysis_mode"], "keyword_rules")
        self.assertFalse(result.output["metadata"]["llm_used"])
        self.assertIn("drawings", result.output)
        self.assertIn("characteristics", result.output)
        self.assertIn("process_clues", result.output)
        self.assertIn("pending_fields", result.output)
        self.assertIn("ai_inferred_items", result.output)
        self.assertTrue(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.allow_user_export)

    def test_analyze_extracts_fixture_drawing_characteristics_and_process_clues(self):
        result = run_stage(FIXTURE_DIR, stage="analyze")
        analysis = result.output

        self.assertGreaterEqual(len(analysis["drawings"]), 1)
        self.assertGreaterEqual(len(analysis["characteristics"]), 2)
        self.assertGreaterEqual(len(analysis["process_clues"]), 2)

        characteristic_by_name = {
            item["name"]: item for item in analysis["characteristics"]
        }
        self.assertEqual(
            characteristic_by_name["material thickness"]["specification"],
            "2.00 +/- 0.10 mm",
        )
        self.assertEqual(
            characteristic_by_name["rivet height"]["specification"],
            "1.50 +0.50/-0.00 mm",
        )
        self.assertEqual(
            characteristic_by_name["push-out force"]["specification"], ">= 10 kN"
        )

        operations_by_step = {
            item["process_step_id"]: item["operation"]
            for item in analysis["process_clues"]
            if item["process_step_id"]
        }
        self.assertEqual(operations_by_step["P10"], "incoming material verification")
        self.assertEqual(operations_by_step["P20"], "rivet assembly")
        self.assertEqual(operations_by_step["P30"], "final inspection and pack")

    def test_analyze_reports_drawing_pending_fields_without_guessing(self):
        result = run_stage(FIXTURE_DIR, stage="analyze")
        pending = result.output["pending_fields"]

        self.assertTrue(
            any(
                item["field"] == "drawing_id" and item["source_ref"] == "EV-ENG-REQ-001"
                for item in pending
            )
        )
        self.assertTrue(
            all(
                item["drawing_id"] == ""
                for item in result.output["drawings"]
                if item["source_ref"].startswith("EV-")
            )
        )

    def test_analyze_accepts_manual_json_and_extracts_analysis_bundle(self):
        result = run_stage(
            {
                "source": "manual",
                "content": (
                    "Drawing DRW-100 revision B defines material thickness 2.00 +/- 0.10 mm "
                    "and rivet height 1.50 +0.50/-0.00 mm. Process route includes "
                    "incoming inspection then rivet assembly."
                ),
            },
            stage="analyze",
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "analysis_bundle")
        self.assertGreaterEqual(len(result.output["drawings"]), 1)
        self.assertGreaterEqual(len(result.output["characteristics"]), 2)
        self.assertGreaterEqual(len(result.output["process_clues"]), 2)
        self.assertEqual(result.evidence[0].source, "manual")
        self.assertFalse(result.quality_gate.allow_user_export)

    def test_analyze_accepts_ocr_text_and_preserves_ocr_evidence(self):
        result = run_stage(
            {
                "source_ref": "drawing.pdf",
                "ocr_text": (
                    "Drawing DRW-200 Rev C. Characteristic thickness 2.00 +/- 0.10 mm. "
                    "Characteristic push-out force >= 10 kN. Process clues: incoming inspection, "
                    "rivet assembly, final inspection."
                ),
                "needs_confirmation": True,
            },
            stage="analyze",
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.evidence[0].evidence_id, "EV-OCR-001")
        self.assertEqual(result.evidence[0].source, "ocr:drawing.pdf")
        self.assertEqual(result.evidence[0].confidence, 1.0)
        self.assertTrue(result.evidence[0].needs_confirmation)
        self.assertGreaterEqual(len(result.output["drawings"]), 1)
        self.assertGreaterEqual(len(result.output["characteristics"]), 2)
        self.assertGreaterEqual(len(result.output["process_clues"]), 2)
        self.assertIn("EV-OCR-001", result.quality_gate.needs_confirmation_items)
        self.assertTrue(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.allow_user_export)

    def test_analyze_reports_ai_inferred_and_pending_fields(self):
        result = run_stage(
            {
                "evidence": [
                    {
                        "evidence_id": "EV-REAL-001",
                        "source": "drawing",
                        "content": (
                            "Drawing DRW-300 Rev A defines thickness 2.00 +/- 0.10 mm "
                            "and rivet height 1.50 +0.50/-0.00 mm. Process route: "
                            "incoming inspection, rivet assembly."
                        ),
                    },
                    {
                        "evidence_id": "EV-AI-001",
                        "source": "llm",
                        "content": "AI inferred possible failure mode: press stroke drift.",
                        "ai_inferred": True,
                    },
                    {
                        "evidence_id": "EV-PENDING-001",
                        "source": "ocr",
                        "content": "OCR extracted push-out force >= 10 kN, needs review.",
                        "needs_confirmation": True,
                    },
                ]
            },
            stage="analyze",
        )

        self.assertEqual(result.status, "ok")
        self.assertIn("EV-AI-001", result.ai_inferred_items)
        self.assertIn("EV-PENDING-001", result.quality_gate.needs_confirmation_items)
        self.assertIsInstance(result.pending_fields, list)
        self.assertIn("pending_fields", result.output)
        self.assertIn("ai_inferred_items", result.output)

    def test_analyze_blocks_when_no_drawings_characteristics_or_process_clues(self):
        result = run_stage(
            {
                "source": "manual",
                "content": "This note has no useful engineering content.",
            },
            stage="analyze",
        )

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertIn("drawings", result.quality_gate.uncovered_evidence_items)
        self.assertIn("characteristics", result.quality_gate.uncovered_evidence_items)
        self.assertIn("process_clues", result.quality_gate.uncovered_evidence_items)

    def test_analyze_output_can_be_validated_without_regression(self):
        analyze_result = run_stage(FIXTURE_DIR, stage="analyze")
        validate_result = run_stage(FIXTURE_DIR, stage="validate")

        self.assertEqual(analyze_result.status, "ok")
        self.assertEqual(validate_result.status, "ok")
        self.assertTrue(validate_result.quality_gate.can_continue)
        self.assertTrue(validate_result.quality_gate.evidence_sufficient)

    def test_analyze_does_not_break_export(self):
        analyze_result = run_stage(FIXTURE_DIR, stage="analyze")

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "analyzed-apqp.xlsx"
            export_result = run_stage(
                FIXTURE_DIR, stage="export", output_path=output_path
            )

            self.assertEqual(analyze_result.status, "ok")
            self.assertEqual(export_result.status, "ok")
            self.assertTrue(output_path.exists())

    def test_analyze_stage_result_model_dump_contains_analysis_bundle_and_gate_fields(
        self,
    ):
        result = run_stage(FIXTURE_DIR, stage="analyze")
        dumped = result.model_dump()

        self.assertEqual(dumped["stage"], "analyze")
        self.assertEqual(dumped["status"], "ok")
        self.assertIn("drawings", dumped["output"])
        self.assertIn("characteristics", dumped["output"])
        self.assertIn("process_clues", dumped["output"])
        self.assertIn("quality_gate", dumped)
        self.assertIn("can_continue", dumped["quality_gate"])
        self.assertIn("allow_user_export", dumped["quality_gate"])
        self.assertIn("evidence_sufficient", dumped["quality_gate"])
        self.assertIn("evidence_coverage", dumped["quality_gate"])


if __name__ == "__main__":
    unittest.main()
