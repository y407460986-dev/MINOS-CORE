import tempfile
import unittest
from pathlib import Path

from minos_core.adapters.ocr import FakeOCRAdapter
from minos_core.ingest import ingest_evidence_bundle
from minos_core.stage import run_stage


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "apqp_chain"


class IngestStageTests(unittest.TestCase):
    def test_evidence_bundle_json_can_be_ingested(self):
        result = run_stage(
            {
                "document_type": "evidence_bundle",
                "evidence": [
                    {
                        "evidence_id": "EV-001",
                        "source": "manual",
                        "content": "Manual evidence note.",
                    }
                ],
            },
            stage="ingest",
        )

        self.assertEqual(result.stage, "ingest")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "evidence_bundle")
        self.assertEqual(result.output["metadata"]["ingest_mode"], "evidence")
        self.assertEqual(result.evidence[0].evidence_id, "EV-001")
        self.assertTrue(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.allow_user_export)

    def test_manual_json_generates_evidence_id(self):
        result = run_stage(
            {
                "source": "manual",
                "content": "Operator confirmed drawing revision A.",
            },
            stage="ingest",
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(result.evidence[0].evidence_id, "EV-MANUAL-001")
        self.assertEqual(result.evidence[0].source, "manual")
        self.assertIn("drawing revision", result.evidence[0].content)

    def test_manual_json_text_field_becomes_evidence_content(self):
        result = run_stage(
            {
                "source": "manual",
                "text": "Dimension 10 +/- 0.1 confirmed from drawing.",
            },
            stage="ingest",
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.evidence[0].content, "Dimension 10 +/- 0.1 confirmed from drawing."
        )

    def test_ocr_text_generates_evidence(self):
        result = run_stage(
            {
                "source_ref": "drawing.pdf",
                "ocr_text": "OCR recognized drawing text.",
            },
            stage="ingest",
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.evidence[0].evidence_id, "EV-OCR-001")
        self.assertEqual(result.evidence[0].source, "ocr:drawing.pdf")
        self.assertEqual(result.evidence[0].confidence, 1.0)
        self.assertEqual(result.evidence[0].content, "OCR recognized drawing text.")

    def test_fake_ocr_adapter_can_seed_evidence_bundle(self):
        bundle = ingest_evidence_bundle(
            {"source_ref": "drawing.pdf", "content": b"fake-pdf"},
            ocr_adapter=FakeOCRAdapter("hello ocr"),
        )

        self.assertEqual(bundle["document_type"], "evidence_bundle")
        self.assertEqual(bundle["metadata"]["ingest_mode"], "ocr_adapter")
        self.assertEqual(bundle["evidence"][0]["source"], "ocr:drawing.pdf")
        self.assertEqual(bundle["evidence"][0]["content"], "hello ocr")

    def test_fixture_directory_evidence_can_be_ingested(self):
        result = run_stage(FIXTURE_DIR, stage="ingest")
        evidence_ids = {item.evidence_id for item in result.evidence}

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["metadata"]["ingest_mode"], "fixture")
        self.assertGreaterEqual(len(result.evidence), 6)
        self.assertIn("EV-PFD-ROUTE-001", evidence_ids)
        self.assertIn("EV-ENG-REQ-001", evidence_ids)
        self.assertTrue(result.quality_gate.can_continue)

    def test_evidence_only_directory_can_be_ingested(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "evidence.json"
            evidence_path.write_text(
                '{"evidence":[{"evidence_id":"EV-DIR-001","source":"manual","content":"directory evidence"}]}',
                encoding="utf-8",
            )

            result = run_stage(Path(tmp), stage="ingest")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.evidence[0].evidence_id, "EV-DIR-001")

    def test_invalid_evidence_array_blocks_ingest(self):
        with self.assertRaises(ValueError):
            run_stage(
                {
                    "document_type": "evidence_bundle",
                    "evidence": {"bad": "not-list"},
                },
                stage="ingest",
            )

    def test_ingest_blocks_empty_or_all_ai_evidence(self):
        empty = run_stage({"evidence": []}, stage="ingest")
        all_ai = run_stage(
            {
                "evidence": [
                    {
                        "evidence_id": "EV-AI-001",
                        "source": "llm",
                        "content": "AI-only hypothesis.",
                        "ai_inferred": True,
                    }
                ]
            },
            stage="ingest",
        )

        self.assertEqual(empty.status, "blocked")
        self.assertFalse(empty.quality_gate.can_continue)
        self.assertEqual(all_ai.status, "blocked")
        self.assertFalse(all_ai.quality_gate.can_continue)
        self.assertIn("EV-AI-001", all_ai.ai_inferred_items)

    def test_ingest_allows_mixed_ai_and_needs_confirmation_as_review(self):
        result = run_stage(
            {
                "evidence": [
                    {
                        "evidence_id": "EV-REAL-001",
                        "source": "drawing",
                        "content": "Released drawing requirement.",
                    },
                    {
                        "evidence_id": "EV-AI-001",
                        "source": "llm",
                        "content": "Possible process risk.",
                        "ai_inferred": True,
                    },
                    {
                        "evidence_id": "EV-PENDING-001",
                        "source": "ocr",
                        "content": "OCR text needs review.",
                        "needs_confirmation": True,
                    },
                ]
            },
            stage="ingest",
        )

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.allow_user_export)
        self.assertIn("EV-AI-001", result.ai_inferred_items)
        self.assertIn("EV-PENDING-001", result.quality_gate.needs_confirmation_items)


if __name__ == "__main__":
    unittest.main()
