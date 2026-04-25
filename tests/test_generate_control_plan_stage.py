import copy
import unittest
from pathlib import Path

from minos_core.stage import run_stage


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "apqp_chain"


class GenerateControlPlanStageTests(unittest.TestCase):
    def test_generate_control_plan_stage_returns_control_plan_bundle_from_fixture(self):
        result = run_stage(FIXTURE_DIR, stage="generate_control_plan")

        self.assertEqual(result.stage, "generate_control_plan")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "control_plan")
        self.assertEqual(result.output["schema_version"], "minos-core.generated.v1")
        self.assertIn("rows", result.output)
        self.assertGreaterEqual(len(result.output["rows"]), 3)
        self.assertTrue(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.allow_user_export)
        self.assertEqual(
            result.quality_gate.evidence_coverage["stage_mode"],
            "generate_control_plan",
        )
        self.assertEqual(
            result.quality_gate.evidence_coverage["next_stage"], "validate"
        )

    def test_generate_control_plan_converts_pfmea_rows_to_control_items(self):
        pfmea_result = run_stage(FIXTURE_DIR, stage="generate_pfmea")
        result = run_stage(pfmea_result.output, stage="generate_control_plan")
        pfmea_ids = {row["pfmea_id"] for row in pfmea_result.output["rows"]}

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "control_plan")
        self.assertEqual(
            {row["pfmea_id"] for row in result.output["rows"]}, pfmea_ids
        )
        for row in result.output["rows"]:
            self.assertTrue(row["control_plan_id"].startswith("CP-"))
            self.assertTrue(row["process_step_id"])
            self.assertTrue(row["pfmea_id"])
            self.assertTrue(row["product_process_characteristic"])
            self.assertTrue(row["specification"])
            self.assertTrue(row["measurement_method"])
            self.assertTrue(row["control_method"])
            self.assertTrue(row["reaction_plan"])
            self.assertTrue(row["evidence_refs"])

    def test_generate_control_plan_preserves_pfmea_evidence_refs(self):
        pfmea_result = run_stage(FIXTURE_DIR, stage="generate_pfmea")
        result = run_stage(pfmea_result.output, stage="generate_control_plan")
        refs_by_pfmea = {
            row["pfmea_id"]: row["evidence_refs"] for row in pfmea_result.output["rows"]
        }

        self.assertEqual(result.status, "ok")
        for row in result.output["rows"]:
            self.assertEqual(row["evidence_refs"], refs_by_pfmea[row["pfmea_id"]])

    def test_generate_control_plan_blocks_missing_evidence_ref(self):
        pfmea_result = run_stage(FIXTURE_DIR, stage="generate_pfmea")
        pfmea_bundle = copy.deepcopy(pfmea_result.output)
        pfmea_bundle["rows"][0]["evidence_refs"] = ["EV-NOT-FOUND"]

        result = run_stage(pfmea_bundle, stage="generate_control_plan")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertTrue(
            any(
                "EV-NOT-FOUND" in item
                for item in result.quality_gate.missing_evidence_refs
            )
        )

    def test_generate_control_plan_blocks_ai_only_evidence(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "evidence": [
                {
                    "evidence_id": "EV-AI-CP-001",
                    "source": "llm",
                    "content": "AI inferred control",
                    "ai_inferred": True,
                }
            ],
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-001",
                    "process_step_id": "P10",
                    "process_function": "verify incoming material",
                    "failure_mode": "Wrong material accepted",
                    "failure_effect": "Shipment may not meet requirements",
                    "severity": 8,
                    "failure_cause": "Incoming verification missed",
                    "occurrence": 3,
                    "prevention_control": "Supplier release check",
                    "detection_control": "Incoming inspection",
                    "detection": 5,
                    "action_priority": "M",
                    "classification": "",
                    "evidence_refs": ["EV-AI-CP-001"],
                }
            ],
        }

        result = run_stage(pfmea_bundle, stage="generate_control_plan")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.evidence_sufficient)
        self.assertIn("EV-AI-CP-001", result.ai_inferred_items)
        self.assertTrue(result.quality_gate.uncovered_evidence_items)

    def test_generate_control_plan_preserves_pfmea_pending_and_ai_items(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "evidence": [
                {
                    "evidence_id": "EV-PFMEA-001",
                    "source": "fixture",
                    "content": "Confirmed PFMEA evidence",
                },
                {
                    "evidence_id": "EV-AI-UPSTREAM-001",
                    "source": "llm",
                    "content": "AI inferred PFMEA evidence",
                    "ai_inferred": True,
                },
            ],
            "pending_fields": [
                "pfmea_row:PFMEA-P10-001.failure_cause",
                {
                    "source_ref": "PFMEA-P10-001",
                    "field": "occurrence",
                    "reason": "requires engineer confirmation",
                },
            ],
            "ai_inferred_items": [
                {
                    "evidence_id": "EV-AI-UPSTREAM-001",
                    "field": "failure_effect",
                    "ai_inferred": True,
                }
            ],
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-001",
                    "process_step_id": "P10",
                    "process_function": "verify incoming material",
                    "failure_mode": "Wrong material accepted",
                    "failure_effect": "Shipment may not meet requirements",
                    "severity": 8,
                    "failure_cause": "Incoming verification missed",
                    "occurrence": 3,
                    "prevention_control": "Supplier release check",
                    "detection_control": "Incoming inspection",
                    "detection": 5,
                    "action_priority": "M",
                    "classification": "",
                    "evidence_refs": ["EV-PFMEA-001"],
                    "needs_confirmation": True,
                }
            ],
        }

        result = run_stage(pfmea_bundle, stage="generate_control_plan")

        self.assertEqual(result.output["pending_fields"], pfmea_bundle["pending_fields"])
        self.assertEqual(result.output["ai_inferred_items"], pfmea_bundle["ai_inferred_items"])
        self.assertIn(
            "pfmea_row:PFMEA-P10-001.failure_cause",
            result.pending_fields,
        )
        self.assertIn("PFMEA-P10-001.occurrence", result.pending_fields)
        self.assertIn("EV-AI-UPSTREAM-001", result.ai_inferred_items)
        self.assertTrue(result.output["rows"][0]["needs_confirmation"])

    def test_generate_control_plan_does_not_break_validate_and_export(self):
        control_plan_result = run_stage(FIXTURE_DIR, stage="generate_control_plan")
        validate_result = run_stage(FIXTURE_DIR, stage="validate")

        self.assertEqual(control_plan_result.status, "ok")
        self.assertEqual(validate_result.status, "ok")
        self.assertTrue(validate_result.quality_gate.can_continue)


if __name__ == "__main__":
    unittest.main()
