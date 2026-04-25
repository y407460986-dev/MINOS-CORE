import copy
import tempfile
import unittest
from pathlib import Path

from minos_core.stage import run_stage


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "apqp_chain"


def _valid_process_flow():
    return {
        "document_type": "process_flow",
        "evidence": [
            {
                "evidence_id": "EV-ROUTE-001",
                "source": "manual",
                "content": "Released route",
            },
            {
                "evidence_id": "EV-ROUTE-002",
                "source": "manual",
                "content": "Released sequence",
            },
        ],
        "steps": [
            {
                "process_step_id": "P10",
                "sequence": 10,
                "operation": "incoming material verification",
                "process_function": "verify incoming material",
                "special_characteristics": ["SC-THICKNESS"],
                "evidence_refs": ["EV-ROUTE-001"],
            },
            {
                "process_step_id": "P20",
                "sequence": 20,
                "operation": "rivet assembly",
                "process_function": "assemble riveted joint",
                "special_characteristics": ["SC-HEIGHT"],
                "evidence_refs": ["EV-ROUTE-002"],
            },
            {
                "process_step_id": "P30",
                "sequence": 30,
                "operation": "final inspection and pack",
                "process_function": "verify finished product",
                "special_characteristics": ["SC-PACK"],
                "evidence_refs": ["EV-ROUTE-002"],
            },
        ],
        "links": [
            {
                "from": "P10",
                "to": "P20",
                "link_type": "sequence",
                "evidence_refs": ["EV-ROUTE-001", "EV-ROUTE-002"],
            },
            {
                "from": "P20",
                "to": "P30",
                "link_type": "sequence",
                "evidence_refs": ["EV-ROUTE-002"],
            },
        ],
    }


def _candidates_by_step(result):
    by_step = {}
    for item in result.output.get("candidates", []):
        by_step.setdefault(item["process_step_id"], []).append(item)
    return by_step


class BrainstormFailureModesStageTests(unittest.TestCase):
    def test_brainstorm_generates_candidates_from_generated_pfd(self):
        pfd_result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        result = run_stage(pfd_result.output, stage="brainstorm_failure_modes")

        self.assertEqual(pfd_result.status, "ok")
        self.assertEqual(result.stage, "brainstorm_failure_modes")
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.quality_gate.can_continue)
        self.assertEqual(result.output["document_type"], "failure_mode_candidates")
        self.assertGreaterEqual(len(result.output["candidates"]), 3)

    def test_brainstorm_candidates_cover_generated_p10_p20_p30(self):
        pfd_result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        result = run_stage(pfd_result.output, stage="brainstorm_failure_modes")
        by_step = _candidates_by_step(result)

        self.assertEqual(result.status, "ok")
        self.assertTrue({"P10", "P20", "P30"}.issubset(set(by_step)))
        self.assertGreaterEqual(len(by_step["P10"]), 1)
        self.assertGreaterEqual(len(by_step["P20"]), 1)
        self.assertGreaterEqual(len(by_step["P30"]), 1)

    def test_brainstorm_candidate_schema_is_minimal_and_not_formal_pfmea(self):
        pfd_result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        result = run_stage(pfd_result.output, stage="brainstorm_failure_modes")
        required = {
            "candidate_id",
            "process_step_id",
            "sequence",
            "operation",
            "process_function",
            "failure_mode",
            "source_rule",
            "evidence_refs",
            "needs_confirmation",
        }

        self.assertEqual(result.status, "ok")
        self.assertNotIn("rows", result.output)
        self.assertNotEqual(result.output["document_type"], "pfmea")
        self.assertTrue(result.output["metadata"]["not_formal_pfmea"])
        for item in result.output["candidates"]:
            self.assertTrue(required.issubset(item.keys()))
            self.assertTrue(item["candidate_id"].startswith("FMC-"))
            self.assertTrue(item["failure_mode"])
            self.assertTrue(item["source_rule"])
            self.assertTrue(item["evidence_refs"])
            self.assertTrue(item["needs_confirmation"])
            self.assertNotIn("severity", item)
            self.assertNotIn("occurrence", item)
            self.assertNotIn("detection", item)
            self.assertNotIn("action_priority", item)
            self.assertNotIn("linked_control_plan_id", item)

    def test_brainstorm_records_operation_and_special_characteristic_source_rules(self):
        process_flow = _valid_process_flow()
        result = run_stage(process_flow, stage="brainstorm_failure_modes")
        source_rules = {item["source_rule"] for item in result.output["candidates"]}
        failure_modes = {item["failure_mode"] for item in result.output["candidates"]}

        self.assertEqual(result.status, "ok")
        self.assertIn("operation_keyword:incoming_verification", source_rules)
        self.assertIn("operation_keyword:rivet_assembly", source_rules)
        self.assertIn("operation_keyword:final_inspection_pack", source_rules)
        self.assertIn("special_characteristic:not_met", source_rules)
        self.assertIn("Special characteristic not met: SC-THICKNESS", failure_modes)
        self.assertIn("Special characteristic not met: SC-HEIGHT", failure_modes)
        self.assertIn("Special characteristic not met: SC-PACK", failure_modes)

    def test_brainstorm_preserves_candidate_evidence_refs(self):
        process_flow = _valid_process_flow()
        result = run_stage(process_flow, stage="brainstorm_failure_modes")
        p20_candidates = [
            item
            for item in result.output["candidates"]
            if item["process_step_id"] == "P20"
        ]

        self.assertEqual(result.status, "ok")
        self.assertTrue(p20_candidates)
        for item in p20_candidates:
            self.assertEqual(item["evidence_refs"], ["EV-ROUTE-002"])

    def test_brainstorm_blocks_when_pfd_gate_is_blocked(self):
        process_flow = _valid_process_flow()
        process_flow["links"] = []

        result = run_stage(process_flow, stage="brainstorm_failure_modes")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertEqual(result.output["document_type"], "process_flow")
        self.assertIn("links:min_count", result.quality_gate.uncovered_evidence_items)

    def test_brainstorm_blocks_when_candidate_evidence_ref_is_missing(self):
        process_flow = _valid_process_flow()
        process_flow["steps"][0]["evidence_refs"] = ["EV-NOT-FOUND"]

        result = run_stage(process_flow, stage="brainstorm_failure_modes")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertTrue(
            any(
                "EV-NOT-FOUND" in item
                for item in result.quality_gate.missing_evidence_refs
            )
        )

    def test_brainstorm_blocks_ai_only_candidate(self):
        process_flow = _valid_process_flow()
        process_flow["evidence"] = [
            {
                "evidence_id": "EV-AI-FM-001",
                "source": "llm",
                "content": "AI route",
                "ai_inferred": True,
            }
        ]
        for step in process_flow["steps"]:
            step["evidence_refs"] = ["EV-AI-FM-001"]
        for link in process_flow["links"]:
            link["evidence_refs"] = ["EV-AI-FM-001"]

        result = run_stage(process_flow, stage="brainstorm_failure_modes")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.evidence_sufficient)
        self.assertIn("EV-AI-FM-001", result.ai_inferred_items)
        self.assertTrue(result.quality_gate.uncovered_evidence_items)

    def test_brainstorm_keeps_needs_confirmation_as_review_without_blocking(self):
        process_flow = _valid_process_flow()
        process_flow["evidence"][0]["needs_confirmation"] = True

        result = run_stage(process_flow, stage="brainstorm_failure_modes")
        review_items = [
            item
            for item in result.quality_gate.manual_review_items
            if item.category == "failure_mode_candidate_needs_confirmation"
        ]

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.quality_gate.can_continue)
        self.assertIn("EV-ROUTE-001", result.quality_gate.needs_confirmation_items)
        self.assertTrue(review_items)
        self.assertTrue(all(item.severity == "review" for item in review_items))

    def test_brainstorm_blocks_when_a_process_step_has_no_candidate(self):
        process_flow = _valid_process_flow()
        process_flow["steps"][1]["operation"] = ""
        process_flow["steps"][1]["process_function"] = ""
        process_flow["steps"][1]["special_characteristics"] = []

        result = run_stage(process_flow, stage="brainstorm_failure_modes")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertIn(
            "process_step:P20.failure_mode_candidates:min_count",
            result.quality_gate.uncovered_evidence_items,
        )

    def test_brainstorm_does_not_break_validate(self):
        pfd_result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        brainstorm_result = run_stage(
            pfd_result.output, stage="brainstorm_failure_modes"
        )
        validate_result = run_stage(FIXTURE_DIR, stage="validate")

        self.assertEqual(pfd_result.status, "ok")
        self.assertEqual(brainstorm_result.status, "ok")
        self.assertEqual(validate_result.status, "ok")
        self.assertTrue(validate_result.quality_gate.can_continue)

    def test_brainstorm_does_not_break_export(self):
        pfd_result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        brainstorm_result = run_stage(
            pfd_result.output, stage="brainstorm_failure_modes"
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "brainstorm-apqp.xlsx"
            export_result = run_stage(
                FIXTURE_DIR, stage="export", output_path=output_path
            )

            self.assertEqual(pfd_result.status, "ok")
            self.assertEqual(brainstorm_result.status, "ok")
            self.assertEqual(export_result.status, "ok")
            self.assertTrue(output_path.exists())

    def test_brainstorm_stage_result_model_dump_contains_candidates_and_gate_fields(
        self,
    ):
        pfd_result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        result = run_stage(pfd_result.output, stage="brainstorm_failure_modes")
        dumped = result.model_dump()

        self.assertEqual(dumped["stage"], "brainstorm_failure_modes")
        self.assertEqual(dumped["status"], "ok")
        self.assertIn("candidates", dumped["output"])
        self.assertIn("quality_gate", dumped)
        self.assertIn("can_continue", dumped["quality_gate"])
        self.assertIn("allow_user_export", dumped["quality_gate"])
        self.assertIn("evidence_sufficient", dumped["quality_gate"])
        self.assertIn("evidence_coverage", dumped["quality_gate"])
        self.assertEqual(
            dumped["quality_gate"]["evidence_coverage"]["stage_mode"],
            "brainstorm_failure_modes",
        )
        self.assertEqual(
            dumped["quality_gate"]["evidence_coverage"]["next_stage"], "generate_pfmea"
        )


if __name__ == "__main__":
    unittest.main()
