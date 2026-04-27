import copy
import unittest
from pathlib import Path

from minos_core.stage import run_stage


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "apqp_chain"


def _pfmea_by_step(result):
    by_step = {}
    for item in result.output.get("rows", []):
        by_step.setdefault(item["process_step_id"], []).append(item)
    return by_step


class GeneratePfmeaStageTests(unittest.TestCase):
    def test_generate_pfmea_stage_returns_pfmea_bundle_from_fixture(self):
        result = run_stage(FIXTURE_DIR, stage="generate_pfmea")

        self.assertEqual(result.stage, "generate_pfmea")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "pfmea")
        self.assertEqual(result.output["schema_version"], "minos-core.generated.v1")
        self.assertIn("rows", result.output)
        self.assertGreaterEqual(len(result.output["rows"]), 3)
        self.assertTrue(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.allow_user_export)
        self.assertEqual(
            result.quality_gate.evidence_coverage["stage_mode"], "generate_pfmea"
        )
        self.assertEqual(
            result.quality_gate.evidence_coverage["next_stage"],
            "generate_control_plan",
        )

    def test_generate_pfmea_converts_candidates_to_formal_pfmea_rows(self):
        pfd_result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        brainstorm_result = run_stage(
            pfd_result.output, stage="brainstorm_failure_modes"
        )
        result = run_stage(brainstorm_result.output, stage="generate_pfmea")
        by_step = _pfmea_by_step(result)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "pfmea")
        self.assertTrue({"P10", "P20", "P30"}.issubset(set(by_step)))
        for row in result.output["rows"]:
            self.assertTrue(row["pfmea_id"].startswith("PFMEA-"))
            self.assertTrue(row["process_step_id"])
            self.assertTrue(row["failure_mode"])
            self.assertTrue(row["failure_effect"])
            self.assertTrue(row["failure_cause"])
            self.assertTrue(row["evidence_refs"])
            self.assertIn(row["action_priority"], {"H", "M", "L"})
            self.assertNotIn("candidate_id", row)

    def test_generate_pfmea_preserves_candidate_evidence_refs(self):
        pfd_result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        brainstorm_result = run_stage(
            pfd_result.output, stage="brainstorm_failure_modes"
        )
        result = run_stage(brainstorm_result.output, stage="generate_pfmea")

        self.assertEqual(result.status, "ok")
        candidate_refs = {
            item["candidate_id"]: item["evidence_refs"]
            for item in brainstorm_result.output["candidates"]
        }
        for row in result.output["rows"]:
            source_candidate_id = row["source_candidate_id"]
            self.assertEqual(row["evidence_refs"], candidate_refs[source_candidate_id])

    def test_generate_pfmea_inherits_pfd_steps_and_drops_orphan_candidates(self):
        candidates = {
            "document_type": "failure_mode_candidates",
            "evidence": [
                {"evidence_id": "EV-P10", "source": "route", "content": "P10"},
                {"evidence_id": "EV-P20", "source": "route", "content": "P20"},
            ],
            "process_steps": [
                {
                    "process_step_id": "P10",
                    "operation": "Blanking",
                    "process_function": "Cut blank",
                    "product_characteristics": ["SC-LENGTH"],
                    "process_characteristics": ["PRESS-TONNAGE"],
                    "special_characteristics": ["SC-LENGTH"],
                    "evidence_refs": ["EV-P10"],
                },
                {
                    "process_step_id": "P20",
                    "operation": "Inspection",
                    "process_function": "Verify blank",
                    "evidence_refs": ["EV-P20"],
                },
            ],
            "candidates": [
                {
                    "candidate_id": "FMC-P10-001",
                    "process_step_id": "P10",
                    "failure_mode": "Length out of tolerance",
                    "failure_effect": "Assembly fit issue",
                    "failure_cause": "Feed drift",
                    "evidence_refs": ["EV-P10"],
                },
                {
                    "candidate_id": "FMC-P99-001",
                    "process_step_id": "P99",
                    "failure_mode": "Orphan risk",
                    "evidence_refs": ["EV-P10"],
                },
                {
                    "candidate_id": "FMC-P20-001",
                    "process_step_id": "P20",
                    "failure_mode": "Inspection missed defect",
                    "failure_effect": "Defect escapes",
                    "failure_cause": "Gauge not used",
                    "evidence_refs": ["EV-P20"],
                },
            ],
        }

        result = run_stage(candidates, stage="generate_pfmea")
        row = result.output["rows"][0]

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.output["rows"]), 2)
        self.assertNotIn("P99", {item["process_step_id"] for item in result.output["rows"]})
        self.assertEqual(row["process_step_id"], "P10")
        self.assertEqual(row["process_step_name"], "Blanking")
        self.assertEqual(row["process_function"], "Cut blank")
        self.assertEqual(row["product_characteristics"], ["SC-LENGTH"])
        self.assertEqual(row["process_characteristics"], ["PRESS-TONNAGE"])
        self.assertEqual(row["characteristic_refs"], ["SC-LENGTH"])
        self.assertEqual(result.output["process_steps"], candidates["process_steps"])

    def test_generate_pfmea_blocks_missing_candidate_evidence_ref(self):
        pfd_result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        brainstorm_result = run_stage(
            pfd_result.output, stage="brainstorm_failure_modes"
        )
        candidates = copy.deepcopy(brainstorm_result.output)
        candidates["candidates"][0]["evidence_refs"] = ["EV-NOT-FOUND"]

        result = run_stage(candidates, stage="generate_pfmea")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertTrue(
            any(
                "EV-NOT-FOUND" in item
                for item in result.quality_gate.missing_evidence_refs
            )
        )

    def test_generate_pfmea_blocks_ai_only_evidence(self):
        candidates = {
            "document_type": "failure_mode_candidates",
            "evidence": [
                {
                    "evidence_id": "EV-AI-FMEA-001",
                    "source": "llm",
                    "content": "AI inferred failure mode",
                    "ai_inferred": True,
                }
            ],
            "process_steps": [
                {"process_step_id": "P10", "operation": "incoming inspection"}
            ],
            "candidates": [
                {
                    "candidate_id": "FMC-P10-001",
                    "process_step_id": "P10",
                    "operation": "incoming inspection",
                    "failure_mode": "Incorrect material accepted",
                    "source_rule": "test",
                    "evidence_refs": ["EV-AI-FMEA-001"],
                }
            ],
        }

        result = run_stage(candidates, stage="generate_pfmea")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.evidence_sufficient)
        self.assertIn("EV-AI-FMEA-001", result.ai_inferred_items)
        self.assertTrue(result.quality_gate.uncovered_evidence_items)

    def test_generate_pfmea_does_not_break_validate(self):
        pfmea_result = run_stage(FIXTURE_DIR, stage="generate_pfmea")
        validate_result = run_stage(FIXTURE_DIR, stage="validate")

        self.assertEqual(pfmea_result.status, "ok")
        self.assertEqual(validate_result.status, "ok")
        self.assertTrue(validate_result.quality_gate.can_continue)


if __name__ == "__main__":
    unittest.main()
