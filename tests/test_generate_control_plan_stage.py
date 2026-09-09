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

    def test_generate_control_plan_preserves_pfmea_source_fields(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "evidence": [
                {
                    "evidence_id": "EV-PFMEA-001",
                    "source": "fixture",
                    "content": "Confirmed PFMEA evidence",
                }
            ],
            "rows": [
                {
                    "pfmea_id": "PFMEA-P20-001",
                    "process_step_id": "P20",
                    "process_function": "join bracket",
                    "failure_mode": "Joint loose",
                    "failure_effect": "Noise complaint",
                    "severity": 9,
                    "failure_cause": "Press drift",
                    "occurrence": 3,
                    "prevention_control": "Setup check",
                    "detection_control": "Height gauge",
                    "detection": 4,
                    "action_priority": "H",
                    "classification": "SC-RIVET",
                    "characteristic_refs": ["SC-RIVET"],
                    "evidence_refs": ["EV-PFMEA-001"],
                }
            ],
        }

        result = run_stage(pfmea_bundle, stage="generate_control_plan")
        row = result.output["rows"][0]

        self.assertEqual(row["source_pfmea_id"], "PFMEA-P20-001")
        self.assertEqual(row["source_failure_cause"], "Press drift")
        self.assertEqual(row["source_prevention_control"], "Setup check")
        self.assertEqual(row["source_detection_control"], "Height gauge")
        self.assertEqual(row["source_special_characteristics"], ["SC-RIVET"])
        self.assertTrue(row["source_high_risk"])

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
        self.assertIn(pfmea_bundle["ai_inferred_items"][0], result.output["ai_inferred_items"])
        self.assertIn(result.output["rows"][0]["control_plan_id"], result.output["ai_inferred_items"])
        self.assertIn(
            "pfmea_row:PFMEA-P10-001.failure_cause",
            result.pending_fields,
        )
        self.assertIn("PFMEA-P10-001.occurrence", result.pending_fields)
        self.assertIn("EV-AI-UPSTREAM-001", result.ai_inferred_items)
        self.assertTrue(result.output["rows"][0]["needs_confirmation"])

    def test_generate_control_plan_fills_draft_controls_without_blanket_confirmation(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "evidence": [
                {
                    "evidence_id": "EV-PFMEA-001",
                    "source": "fixture",
                    "content": "Confirmed PFMEA evidence",
                }
            ],
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-001",
                    "process_step_id": "P10",
                    "process_function": "verify incoming material",
                    "failure_mode": "Wrong material accepted",
                    "failure_effect": "Shipment may not meet requirements",
                    "severity": 6,
                    "failure_cause": "Incoming verification missed",
                    "occurrence": 3,
                    "prevention_control": "Supplier release check",
                    "detection_control": "Incoming inspection",
                    "detection": 5,
                    "action_priority": "L",
                    "classification": "",
                    "confidence": 0.82,
                    "evidence_refs": ["EV-PFMEA-001"],
                    "ai_inferred": True,
                }
            ],
        }

        result = run_stage(pfmea_bundle, stage="generate_control_plan")
        row = result.output["rows"][0]

        self.assertEqual(result.status, "ok")
        self.assertTrue(row["specification"].startswith("草案控制意图"))
        self.assertTrue(row["measurement_method"])
        self.assertTrue(row["sample_size"])
        self.assertTrue(row["sample_frequency"])
        self.assertTrue(row["control_method"])
        self.assertTrue(row["reaction_plan"])
        self.assertTrue(row["ai_inferred"])
        self.assertIn("specification", row["inferred_fields"])
        self.assertIn("已补充草案控制计划字段", row["ai_reasoning"])
        self.assertFalse(row["needs_confirmation"])
        self.assertNotIn(row["control_plan_id"], result.quality_gate.needs_confirmation_items)
        self.assertIn(row["control_plan_id"], result.ai_inferred_items)

    def test_generate_control_plan_confirms_only_risky_or_uncertain_ai_rows(self):
        base = {
            "document_type": "pfmea",
            "evidence": [
                {
                    "evidence_id": "EV-PFMEA-001",
                    "source": "fixture",
                    "content": "Confirmed PFMEA evidence",
                }
            ],
            "rows": [
                {
                    "pfmea_id": "PFMEA-P20-001",
                    "process_step_id": "P20",
                    "process_function": "rivet joint",
                    "failure_mode": "Joint loose",
                    "failure_effect": "Noise complaint",
                    "severity": 9,
                    "failure_cause": "Press drift",
                    "occurrence": 3,
                    "prevention_control": "Setup check",
                    "detection_control": "Height gauge",
                    "detection": 4,
                    "action_priority": "H",
                    "classification": "",
                    "confidence": 0.9,
                    "evidence_refs": ["EV-PFMEA-001"],
                    "ai_inferred": True,
                },
                {
                    "pfmea_id": "PFMEA-P30-001",
                    "process_step_id": "P30",
                    "process_function": "final pack",
                    "failure_mode": "Wrong label",
                    "failure_effect": "Traceability issue",
                    "severity": 6,
                    "failure_cause": "Manual entry error",
                    "occurrence": 3,
                    "prevention_control": "Order lock",
                    "detection_control": "Barcode scan",
                    "detection": 3,
                    "action_priority": "L",
                    "classification": "SC-LABEL",
                    "confidence": 0.9,
                    "evidence_refs": ["EV-PFMEA-001"],
                    "ai_inferred": True,
                },
                {
                    "pfmea_id": "PFMEA-P40-001",
                    "process_step_id": "P40",
                    "process_function": "visual inspection",
                    "failure_mode": "Scratch missed",
                    "failure_effect": "Appearance issue",
                    "severity": 5,
                    "failure_cause": "Lighting variation",
                    "occurrence": 3,
                    "prevention_control": "Lighting standard",
                    "detection_control": "Visual check",
                    "detection": 3,
                    "action_priority": "L",
                    "classification": "",
                    "confidence": 0.6,
                    "evidence_refs": ["EV-PFMEA-001"],
                    "ai_inferred": True,
                },
            ],
        }

        result = run_stage(base, stage="generate_control_plan")
        rows_by_pfmea = {row["pfmea_id"]: row for row in result.output["rows"]}

        self.assertTrue(rows_by_pfmea["PFMEA-P20-001"]["needs_confirmation"])
        self.assertTrue(rows_by_pfmea["PFMEA-P30-001"]["needs_confirmation"])
        self.assertTrue(rows_by_pfmea["PFMEA-P40-001"]["needs_confirmation"])
        self.assertIn(
            rows_by_pfmea["PFMEA-P20-001"]["control_plan_id"],
            result.quality_gate.needs_confirmation_items,
        )

    def test_generate_control_plan_does_not_break_validate_and_export(self):
        control_plan_result = run_stage(FIXTURE_DIR, stage="generate_control_plan")
        validate_result = run_stage(FIXTURE_DIR, stage="validate")

        self.assertEqual(control_plan_result.status, "ok")
        self.assertEqual(validate_result.status, "ok")
        self.assertTrue(validate_result.quality_gate.can_continue)


if __name__ == "__main__":
    unittest.main()
