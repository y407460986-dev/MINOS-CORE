import unittest

from minos_core.audit import audit_chain
from minos_core.domain import APQPChain
from minos_core.stage import run_stage
from minos_core.validation import validate_chain


EVIDENCE_INPUT = {
    "document_type": "evidence_bundle",
    "schema_version": "0.1",
    "evidence": [
        {
            "evidence_id": "EV-GEN-ROUTE-001",
            "source": "routing fixture",
            "content": (
                "Released process routing defines P10 incoming material verification, "
                "P20 rivet assembly, P30 final inspection and pack, including sequence "
                "P10 -> P20 -> P30."
            ),
            "confidence": 1.0,
        },
        {
            "evidence_id": "EV-GEN-REQ-001",
            "source": "drawing fixture",
            "content": (
                "Drawing DRW-777 Rev B and engineering requirements define material "
                "thickness 2.00 +/- 0.10 mm, rivet height 1.50 +0.50/-0.00 mm, "
                "and push-out force >= 10 kN."
            ),
            "confidence": 1.0,
            "needs_confirmation": True,
        },
        {
            "evidence_id": "EV-GEN-AI-001",
            "source": "llm",
            "content": "AI inferred possible rivet setup risk for engineer review only.",
            "confidence": 0.55,
            "ai_inferred": True,
            "needs_confirmation": True,
        },
    ],
}


def _call_assemble_generated_apqp_chain(*, pfd, brainstorm, pfmea, control_plan):
    from minos_core.pipeline import assemble_generated_apqp_chain

    return assemble_generated_apqp_chain(
        pfd=pfd,
        brainstorm=brainstorm,
        pfmea=pfmea,
        control_plan=control_plan,
    )


def _stage_statuses_are_ok(testcase, results):
    for expected_stage, result in results:
        with testcase.subTest(stage=expected_stage):
            testcase.assertEqual(result.stage, expected_stage)
            testcase.assertEqual(result.status, "ok")
            testcase.assertTrue(result.quality_gate.can_continue)


class GeneratedChainStageTests(unittest.TestCase):
    def test_generated_pipeline_contract_from_evidence_to_audit(self):
        ingest_result = run_stage(EVIDENCE_INPUT, stage="ingest")
        analyze_result = run_stage(ingest_result.output, stage="analyze")
        pfd_result = run_stage(analyze_result.output, stage="generate_pfd")
        brainstorm_result = run_stage(
            pfd_result.output, stage="brainstorm_failure_modes"
        )
        pfmea_result = run_stage(brainstorm_result.output, stage="generate_pfmea")
        control_plan_result = run_stage(
            pfmea_result.output, stage="generate_control_plan"
        )

        _stage_statuses_are_ok(
            self,
            (
                ("ingest", ingest_result),
                ("analyze", analyze_result),
                ("generate_pfd", pfd_result),
                ("brainstorm_failure_modes", brainstorm_result),
                ("generate_pfmea", pfmea_result),
                ("generate_control_plan", control_plan_result),
            ),
        )
        self.assertFalse(control_plan_result.quality_gate.allow_user_export)
        self.assertIn(
            "EV-GEN-REQ-001", control_plan_result.quality_gate.needs_confirmation_items
        )

        process_flow = pfd_result.output
        pfmea = pfmea_result.output
        control_plan = control_plan_result.output
        self.assertTrue(process_flow["steps"])
        self.assertTrue(pfmea["rows"])
        self.assertTrue(control_plan["rows"])

        pfd_step_ids = {step["process_step_id"] for step in process_flow["steps"]}
        pfmea_ids = {row["pfmea_id"] for row in pfmea["rows"]}
        for row in pfmea["rows"]:
            self.assertIn(row["process_step_id"], pfd_step_ids)
        for row in control_plan["rows"]:
            self.assertIn(row["pfmea_id"], pfmea_ids)

        draft = _call_assemble_generated_apqp_chain(
            pfd=process_flow,
            brainstorm=brainstorm_result.output,
            pfmea=pfmea,
            control_plan=control_plan,
        )

        self.assertEqual(draft["document_type"], "apqp_chain")
        for key in (
            "process_steps",
            "failure_modes",
            "controls",
            "evidence",
            "links",
        ):
            self.assertIn(key, draft)
            self.assertTrue(draft[key])
        self.assertEqual(
            draft["pending_fields"], control_plan_result.output["pending_fields"]
        )
        self.assertEqual(
            draft["ai_inferred_items"], control_plan_result.output["ai_inferred_items"]
        )

        chain = APQPChain(**draft)
        self.assertEqual(chain.document_type, "apqp_chain")

        validation_result = validate_chain(draft)
        self.assertTrue(validation_result.ok, validation_result.messages)

        validate_stage_result = run_stage(draft, stage="validate")
        self.assertEqual(validate_stage_result.stage, "validate")
        self.assertEqual(validate_stage_result.status, "ok")
        self.assertTrue(validate_stage_result.quality_gate.can_continue)
        self.assertFalse(validate_stage_result.quality_gate.allow_user_export)
        self.assertTrue(
            any(
                "EV-GEN-REQ-001" in item
                for item in validate_stage_result.quality_gate.needs_confirmation_items
            )
        )
        self.assertTrue(
            any(
                "EV-GEN-REQ-001" in getattr(item, "item_id", "")
                for item in validate_stage_result.quality_gate.manual_review_items
            )
        )

        audit_report = audit_chain(draft)
        self.assertTrue(audit_report.ok)
        self.assertEqual(audit_report.counts["process_steps"], len(draft["process_steps"]))
        self.assertEqual(audit_report.counts["failure_modes"], len(draft["failure_modes"]))
        self.assertEqual(audit_report.counts["controls"], len(draft["controls"]))


if __name__ == "__main__":
    unittest.main()
