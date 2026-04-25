import copy
import tempfile
import unittest
from pathlib import Path

from minos_core.adapters.fixture_json import load_fixture_payload
from minos_core.stage import run_stage


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "apqp_chain"


def _steps_by_id(process_flow):
    return {item["process_step_id"]: item for item in process_flow["steps"]}


def _link_pairs(process_flow):
    return {(item["from"], item["to"]) for item in process_flow.get("links", [])}


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
                "operation": "incoming inspection",
                "process_function": "verify incoming material",
                "special_characteristics": ["SC-THICKNESS"],
                "evidence_refs": ["EV-ROUTE-001"],
            },
            {
                "process_step_id": "P20",
                "sequence": 20,
                "operation": "assembly",
                "process_function": "assemble parts",
                "special_characteristics": ["SC-HEIGHT"],
                "evidence_refs": ["EV-ROUTE-002"],
            },
        ],
        "links": [
            {
                "from": "P10",
                "to": "P20",
                "link_type": "sequence",
                "evidence_refs": ["EV-ROUTE-001", "EV-ROUTE-002"],
            }
        ],
    }


class GeneratePfdStageTests(unittest.TestCase):
    def test_generate_pfd_stage_returns_process_flow_bundle(self):
        result = run_stage(FIXTURE_DIR, stage="generate_pfd")

        self.assertEqual(result.stage, "generate_pfd")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "process_flow")
        self.assertIn("steps", result.output)
        self.assertIn("links", result.output)
        self.assertGreaterEqual(len(result.output["steps"]), 3)
        self.assertTrue(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.allow_user_export)

    def test_generate_pfd_extracts_fixture_p10_p20_p30_steps(self):
        result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        steps = _steps_by_id(result.output)

        self.assertEqual(set(steps), {"P10", "P20", "P30"})
        self.assertEqual(steps["P10"]["operation"], "incoming material verification")
        self.assertEqual(steps["P20"]["operation"], "rivet assembly")
        self.assertEqual(steps["P30"]["operation"], "final inspection and pack")
        self.assertEqual(steps["P10"]["sequence"], 10)
        self.assertEqual(steps["P20"]["sequence"], 20)
        self.assertEqual(steps["P30"]["sequence"], 30)

    def test_generate_pfd_builds_sequence_links_between_extracted_steps(self):
        result = run_stage(FIXTURE_DIR, stage="generate_pfd")

        self.assertEqual(_link_pairs(result.output), {("P10", "P20"), ("P20", "P30")})
        for link in result.output["links"]:
            self.assertEqual(link["link_type"], "sequence")
            self.assertIn("evidence_refs", link)
            self.assertTrue(link["evidence_refs"])

    def test_generate_pfd_preserves_step_evidence_refs_from_analysis_clues(self):
        result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        steps = _steps_by_id(result.output)

        self.assertIn("EV-PFD-ROUTE-001", steps["P10"]["evidence_refs"])
        self.assertIn("EV-PFD-ROUTE-001", steps["P20"]["evidence_refs"])
        self.assertIn("EV-PFD-ROUTE-001", steps["P30"]["evidence_refs"])
        for step in steps.values():
            self.assertTrue(step["evidence_refs"])
            self.assertEqual(step["output_refs"], [])

    def test_generate_pfd_preserves_link_evidence_refs(self):
        result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        links_by_pair = {
            (item["from"], item["to"]): item for item in result.output["links"]
        }

        self.assertIn(
            "EV-PFD-ROUTE-001", links_by_pair[("P10", "P20")]["evidence_refs"]
        )
        self.assertIn(
            "EV-PFD-ROUTE-001", links_by_pair[("P20", "P30")]["evidence_refs"]
        )

    def test_generate_pfd_accepts_manual_json_input(self):
        result = run_stage(
            {
                "source": "manual",
                "content": (
                    "Released routing defines P10 incoming material verification, "
                    "P20 rivet assembly, P30 final inspection and pack. "
                    "Sequence P10 -> P20 -> P30."
                ),
            },
            stage="generate_pfd",
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "process_flow")
        self.assertEqual(set(_steps_by_id(result.output)), {"P10", "P20", "P30"})
        self.assertEqual(_link_pairs(result.output), {("P10", "P20"), ("P20", "P30")})
        self.assertEqual(result.evidence[0].source, "manual")

    def test_generate_pfd_accepts_ocr_text_and_preserves_confirmation_gate(self):
        result = run_stage(
            {
                "source_ref": "routing.pdf",
                "ocr_text": (
                    "Released process routing defines P10 incoming material verification, "
                    "P20 rivet assembly, P30 final inspection and pack. Sequence P10 -> P20 -> P30."
                ),
                "needs_confirmation": True,
            },
            stage="generate_pfd",
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "process_flow")
        self.assertEqual(result.evidence[0].evidence_id, "EV-OCR-001")
        self.assertEqual(result.evidence[0].source, "ocr:routing.pdf")
        self.assertIn("EV-OCR-001", result.quality_gate.needs_confirmation_items)
        self.assertFalse(result.quality_gate.allow_user_export)

    def test_generate_pfd_reports_pending_when_process_clues_have_no_step_id(self):
        result = run_stage(
            {
                "source": "manual",
                "content": (
                    "Process route includes incoming inspection, rivet assembly, "
                    "final inspection, press setup verification and barcode scan."
                ),
            },
            stage="generate_pfd",
        )

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertTrue(
            any("process_step_id" in item for item in result.pending_fields),
            result.pending_fields,
        )
        self.assertFalse(
            any(
                step["process_step_id"] == "" for step in result.output.get("steps", [])
            )
        )

    def test_generate_pfd_blocks_when_no_route_steps_can_be_generated(self):
        result = run_stage(
            {
                "source": "manual",
                "content": "This note has material information but no process route.",
            },
            stage="generate_pfd",
        )

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertIn(
            "process_steps:min_count", result.quality_gate.uncovered_evidence_items
        )
        self.assertFalse(result.quality_gate.allow_user_export)

    def test_generate_pfd_blocks_when_route_is_only_ai_inferred(self):
        result = run_stage(
            {
                "evidence": [
                    {
                        "evidence_id": "EV-AI-ROUTE-001",
                        "source": "llm",
                        "content": (
                            "AI inferred route: P10 incoming material verification, "
                            "P20 rivet assembly, P30 final inspection and pack."
                        ),
                        "ai_inferred": True,
                    }
                ]
            },
            stage="generate_pfd",
        )

        self.assertEqual(result.status, "blocked")
        self.assertIn("EV-AI-ROUTE-001", result.ai_inferred_items)
        self.assertFalse(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.evidence_sufficient)
        self.assertFalse(result.quality_gate.allow_user_export)

    def test_generate_pfd_blocks_when_step_evidence_ref_is_missing(self):
        process_flow = _valid_process_flow()
        process_flow["steps"][0]["evidence_refs"] = ["EV-NOT-FOUND"]

        result = run_stage(process_flow, stage="generate_pfd")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.evidence_sufficient)
        self.assertTrue(
            any(
                "EV-NOT-FOUND" in item
                for item in result.quality_gate.missing_evidence_refs
            )
        )

    def test_generate_pfd_blocks_when_link_evidence_refs_are_empty(self):
        process_flow = _valid_process_flow()
        process_flow["links"][0]["evidence_refs"] = []

        result = run_stage(process_flow, stage="generate_pfd")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.evidence_sufficient)
        self.assertIn("trace_link[0].evidence_refs", result.pending_fields)

    def test_generate_pfd_blocks_when_link_evidence_ref_is_missing(self):
        process_flow = _valid_process_flow()
        process_flow["links"][0]["evidence_refs"] = ["EV-LINK-NOT-FOUND"]

        result = run_stage(process_flow, stage="generate_pfd")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.evidence_sufficient)
        self.assertTrue(
            any(
                "EV-LINK-NOT-FOUND" in item
                for item in result.quality_gate.missing_evidence_refs
            )
        )

    def test_generate_pfd_preserves_string_pending_fields(self):
        process_flow = _valid_process_flow()
        process_flow["pending_fields"] = [
            "process_step:P10.operator_confirmation",
            {"source_ref": "EV-ROUTE-001", "field": "process_step_id"},
        ]

        result = run_stage(process_flow, stage="generate_pfd")

        self.assertEqual(result.status, "ok")
        self.assertIn("process_step:P10.operator_confirmation", result.pending_fields)
        self.assertIn("EV-ROUTE-001.process_step_id", result.pending_fields)

    def test_generate_pfd_accepts_single_string_pending_fields(self):
        process_flow = _valid_process_flow()
        process_flow["pending_fields"] = "process_step:P10.operator_confirmation"

        result = run_stage(process_flow, stage="generate_pfd")

        self.assertEqual(result.status, "ok")
        self.assertIn("process_step:P10.operator_confirmation", result.pending_fields)

    def test_generate_pfd_blocks_when_link_type_is_missing(self):
        process_flow = _valid_process_flow()
        del process_flow["links"][0]["link_type"]

        result = run_stage(process_flow, stage="generate_pfd")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertIn("trace_link[0].link_type", result.pending_fields)

    def test_generate_pfd_blocks_when_link_type_is_empty(self):
        process_flow = _valid_process_flow()
        process_flow["links"][0]["link_type"] = ""

        result = run_stage(process_flow, stage="generate_pfd")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertIn("trace_link[0].link_type", result.pending_fields)

    def test_generate_pfd_blocks_when_link_type_is_invalid(self):
        process_flow = _valid_process_flow()
        process_flow["links"][0]["link_type"] = "dependency"

        result = run_stage(process_flow, stage="generate_pfd")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertIn(
            "trace_link[0].link_type_invalid:dependency",
            result.quality_gate.uncovered_evidence_items,
        )

    def test_generate_pfd_blocks_when_all_referenced_evidence_is_ai_inferred(self):
        process_flow = _valid_process_flow()
        process_flow["evidence"] = [
            {
                "evidence_id": "EV-AI-ROUTE-001",
                "source": "llm",
                "content": "AI inferred route",
                "ai_inferred": True,
            }
        ]
        for step in process_flow["steps"]:
            step["evidence_refs"] = ["EV-AI-ROUTE-001"]
        process_flow["links"][0]["evidence_refs"] = ["EV-AI-ROUTE-001"]

        result = run_stage(process_flow, stage="generate_pfd")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.evidence_sufficient)
        self.assertIn(
            "all_referenced_evidence_ai_inferred",
            result.quality_gate.uncovered_evidence_items,
        )
        self.assertIn("EV-AI-ROUTE-001", result.ai_inferred_items)

    def test_generate_pfd_reviews_thin_fields_without_blocking(self):
        process_flow = _valid_process_flow()
        process_flow["steps"][0]["process_function"] = ""
        process_flow["steps"][1]["special_characteristics"] = []

        result = run_stage(process_flow, stage="generate_pfd")
        review_item_ids = [
            item.item_id
            for item in result.quality_gate.manual_review_items
            if item.category == "pfd_review_field"
        ]

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.quality_gate.can_continue)
        self.assertTrue(result.quality_gate.evidence_sufficient)
        self.assertNotIn("process_step:P10.process_function", result.pending_fields)
        self.assertIn("process_step:P10.process_function", review_item_ids)
        self.assertIn("process_step:P20.special_characteristics", review_item_ids)

    def test_generate_pfd_report_stage_mode_points_to_generate_pfd(self):
        result = run_stage(FIXTURE_DIR, stage="generate_pfd")

        self.assertEqual(
            result.quality_gate.evidence_coverage["stage_mode"], "generate_pfd"
        )
        self.assertEqual(
            result.quality_gate.evidence_coverage["next_stage"],
            "brainstorm_failure_modes",
        )

    def test_generate_pfd_keeps_needs_confirmation_as_review_without_blocking(self):
        process_flow = _valid_process_flow()
        process_flow["evidence"][0]["needs_confirmation"] = True

        result = run_stage(process_flow, stage="generate_pfd")
        review_items = [
            item
            for item in result.quality_gate.manual_review_items
            if item.category == "pfd_needs_confirmation"
        ]

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.quality_gate.can_continue)
        self.assertIn("EV-ROUTE-001", result.quality_gate.needs_confirmation_items)
        self.assertTrue(review_items)
        self.assertTrue(all(item.severity == "review" for item in review_items))

    def test_generate_pfd_does_not_break_validate(self):
        generate_result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        validate_result = run_stage(FIXTURE_DIR, stage="validate")

        self.assertEqual(generate_result.status, "ok")
        self.assertEqual(validate_result.status, "ok")
        self.assertTrue(validate_result.quality_gate.can_continue)
        self.assertTrue(validate_result.quality_gate.evidence_sufficient)

    def test_generate_pfd_does_not_break_export(self):
        generate_result = run_stage(FIXTURE_DIR, stage="generate_pfd")

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "generated-pfd-apqp.xlsx"
            export_result = run_stage(
                FIXTURE_DIR, stage="export", output_path=output_path
            )

            self.assertEqual(generate_result.status, "ok")
            self.assertEqual(export_result.status, "ok")
            self.assertTrue(output_path.exists())

    def test_brainstorm_preflight_accepts_generated_process_flow(self):
        pfd_result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        result = run_stage(pfd_result.output, stage="brainstorm_failure_modes")

        self.assertEqual(result.stage, "brainstorm_failure_modes")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "process_flow")
        self.assertTrue(result.quality_gate.can_continue)
        self.assertEqual(
            result.quality_gate.evidence_coverage["stage_mode"],
            "brainstorm_failure_modes_preflight",
        )
        self.assertEqual(
            result.quality_gate.evidence_coverage["next_stage"],
            "brainstorm_failure_modes",
        )

    def test_brainstorm_preflight_blocks_when_link_type_is_missing(self):
        process_flow = _valid_process_flow()
        del process_flow["links"][0]["link_type"]

        result = run_stage(process_flow, stage="brainstorm_failure_modes")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertIn("trace_link[0].link_type", result.pending_fields)

    def test_brainstorm_preflight_keeps_needs_confirmation_as_review_without_blocking(
        self,
    ):
        process_flow = _valid_process_flow()
        process_flow["evidence"][0]["needs_confirmation"] = True

        result = run_stage(process_flow, stage="brainstorm_failure_modes")

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.quality_gate.can_continue)
        self.assertIn("EV-ROUTE-001", result.quality_gate.needs_confirmation_items)

    def test_brainstorm_preflight_blocks_invalid_process_flow_without_apqp_validation(
        self,
    ):
        process_flow = _valid_process_flow()
        process_flow["links"] = []

        result = run_stage(process_flow, stage="brainstorm_failure_modes")

        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.quality_gate.can_continue)
        self.assertIn("links:min_count", result.quality_gate.uncovered_evidence_items)

    def test_brainstorm_preflight_requires_process_flow_payload(self):
        with self.assertRaises(ValueError):
            run_stage(
                {"document_type": "analysis_bundle", "process_clues": []},
                stage="brainstorm_failure_modes",
            )

    def test_generate_pfd_stage_result_model_dump_contains_process_flow_and_gate_fields(
        self,
    ):
        result = run_stage(FIXTURE_DIR, stage="generate_pfd")
        dumped = result.model_dump()

        self.assertEqual(dumped["stage"], "generate_pfd")
        self.assertEqual(dumped["status"], "ok")
        self.assertEqual(dumped["output"]["document_type"], "process_flow")
        self.assertIn("steps", dumped["output"])
        self.assertIn("links", dumped["output"])
        self.assertIn("quality_gate", dumped)
        self.assertIn("can_continue", dumped["quality_gate"])
        self.assertIn("allow_user_export", dumped["quality_gate"])
        self.assertIn("evidence_sufficient", dumped["quality_gate"])
        self.assertIn("evidence_coverage", dumped["quality_gate"])

    def test_generate_pfd_output_contains_only_process_flow_not_downstream_documents(
        self,
    ):
        result = run_stage(FIXTURE_DIR, stage="generate_pfd")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "process_flow")
        self.assertNotIn("pfmea", result.output)
        self.assertNotIn("control_plan", result.output)
        self.assertNotIn("rows", result.output)

    def test_generate_pfd_uses_evidence_route_not_existing_process_flow_shortcut(self):
        fixture = copy.deepcopy(load_fixture_payload(FIXTURE_DIR))
        fixture["process_flow"]["steps"] = []
        fixture["process_flow"]["links"] = []

        result = run_stage(fixture, stage="generate_pfd")

        self.assertEqual(result.status, "ok")
        self.assertEqual(set(_steps_by_id(result.output)), {"P10", "P20", "P30"})
        self.assertEqual(_link_pairs(result.output), {("P10", "P20"), ("P20", "P30")})


if __name__ == "__main__":
    unittest.main()
