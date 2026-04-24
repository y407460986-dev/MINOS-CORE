import copy
import tempfile
import unittest
from pathlib import Path

from minos_core.adapters.fixture_json import load_fixture_payload


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "apqp_chain"


def _load_fixture():
    return load_fixture_payload(FIXTURE_DIR)


class StageResultTests(unittest.TestCase):
    def test_build_stage_context_loads_fixture(self):
        from minos_core.stage import build_stage_context

        context = build_stage_context(FIXTURE_DIR, stage="validate")

        self.assertEqual(context.stage, "validate")
        self.assertIsNotNone(context.payload)
        self.assertIsNotNone(context.chain)

    def test_run_stage_ingest_returns_evidence_bundle(self):
        from minos_core.stage import run_stage

        result = run_stage(FIXTURE_DIR, stage="ingest")

        self.assertEqual(result.stage, "ingest")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "evidence_bundle")
        self.assertGreaterEqual(len(result.evidence), 6)
        self.assertTrue(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.allow_user_export)

    def test_stage_result_exposes_required_fields(self):
        from minos_core.stage import build_stage_context, build_stage_result

        context = build_stage_context(FIXTURE_DIR, stage="validate")
        result = build_stage_result(context)

        self.assertEqual(result.stage, "validate")
        self.assertIn(result.status, {"ok", "blocked", "failed"})
        self.assertTrue(hasattr(result, "output"))
        self.assertIsInstance(result.evidence, list)
        self.assertGreaterEqual(len(result.evidence), 6)
        self.assertIsInstance(result.pending_fields, list)
        self.assertIsInstance(result.ai_inferred_items, list)
        self.assertIsNotNone(result.quality_gate)

    def test_run_stage_validate_returns_stage_result(self):
        from minos_core.stage import StageResult, run_stage

        result = run_stage(FIXTURE_DIR, stage="validate")

        self.assertIsInstance(result, StageResult)
        self.assertEqual(result.stage, "validate")
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.output)
        self.assertTrue(result.quality_gate.evidence_sufficient)
        self.assertIsNotNone(result.quality_gate)

    def test_run_stage_export_returns_export_path(self):
        from minos_core.stage import run_stage

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "apqp.xlsx"
            result = run_stage(FIXTURE_DIR, stage="export", output_path=output_path)

            self.assertEqual(result.status, "ok")
            self.assertEqual(result.output, output_path)
            self.assertTrue(output_path.exists())

    def test_stage_result_blocks_pending_fields_and_reports_ai_evidence(self):
        from minos_core.stage import run_stage

        fixture = _load_fixture()
        fixture["control_plan"] = copy.deepcopy(fixture["control_plan"])
        fixture["control_plan"]["rows"][0]["specification"] = ""
        fixture["evidence"] = [
            {
                "evidence_id": "EV-AI-001",
                "source": "llm",
                "content": "inferred failure mode",
                "ai_inferred": True,
            }
        ]
        for step in fixture["process_flow"]["steps"]:
            step["evidence_refs"] = ["EV-AI-001"]
        for row in fixture["pfmea"]["rows"]:
            row["evidence_refs"] = ["EV-AI-001"]
        for row in fixture["control_plan"]["rows"]:
            row["evidence_refs"] = ["EV-AI-001"]

        result = run_stage(fixture, stage="export", output_path="blocked.xlsx")

        self.assertEqual(result.status, "blocked")
        self.assertIn("CP-P10-001.specification", result.pending_fields)
        self.assertIn("EV-AI-001", result.ai_inferred_items)
        self.assertFalse(result.quality_gate.allow_user_export)


if __name__ == "__main__":
    unittest.main()
