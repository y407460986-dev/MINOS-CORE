import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from minos_core.audit import audit_chain
from minos_core.domain import APQPChain
from minos_core.stage import run_stage
from minos_core.validation import validate_chain

ROOT = Path(__file__).resolve().parents[1]


def _extract_json_from_log(text: str) -> dict:
    """Extract JSON from structlog line: timestamp [level] event result='{...}'"""
    match = re.search(r"result='(\{.*\})'", text, re.DOTALL)
    if match:
        raw = match.group(1)
        # structlog ConsoleRenderer escapes \n → \\n; restore for valid JSON
        cleaned = raw.replace('\\n', '\n').replace('\\t', '\t')
        return json.loads(cleaned)
    raise ValueError(f"Cannot extract JSON from log output: {text[:200]}")


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

    def test_generate_draft_pipeline_api_returns_draft_envelope(self):
        from minos_core.pipeline import DRAFT_WARNING, generate_draft

        result = generate_draft(EVIDENCE_INPUT)

        self.assertEqual(result["document_type"], "apqp_chain_draft_result")
        self.assertEqual(result["status"], "draft_ready")
        self.assertFalse(result["draft_is_formal_export"])
        self.assertEqual(result["draft_notice"], DRAFT_WARNING)
        self.assertEqual(result["draft"]["document_type"], "apqp_chain")
        self.assertEqual(result["draft"]["metadata"]["generated"], True)
        self.assertEqual(result["quality_gate"]["stage"], "validate")
        self.assertTrue(result["quality_gate"]["can_continue"])
        self.assertFalse(result["quality_gate"]["allow_user_export"])
        self.assertTrue(result["quality_gate"]["draft_only"])
        self.assertTrue(result["manual_review"]["required"])
        self.assertTrue(result["manual_review"]["items"])
        self.assertTrue(
            any(
                item["stage"] == "assemble_generated_apqp_chain"
                for item in result["stage_results"]
            )
        )

    def test_generate_draft_pipeline_api_can_save_json(self):
        from minos_core.pipeline import generate_draft

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "draft-result.json"
            result = generate_draft(EVIDENCE_INPUT, output_path)
            saved = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(saved, result)
        self.assertEqual(saved["draft"]["document_type"], "apqp_chain")
        self.assertFalse(saved["draft_is_formal_export"])

    def test_run_stage_generate_draft_alias_returns_stage_result(self):
        result = run_stage(EVIDENCE_INPUT, stage="generate_draft")

        self.assertEqual(result.stage, "generate_draft")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["status"], "draft_ready")
        self.assertEqual(result.output["draft"]["document_type"], "apqp_chain")
        self.assertFalse(result.quality_gate.allow_user_export)
        self.assertTrue(result.quality_gate.needs_human_review)

    def test_cli_generate_draft_prints_and_saves_draft_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "evidence.json"
            output_path = Path(tmp) / "draft-result.json"
            input_path.write_text(
                json.dumps(EVIDENCE_INPUT, ensure_ascii=False), encoding="utf-8"
            )
            cli_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "minos_core.cli",
                    "generate-draft",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            saved_payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(cli_result.returncode, 0, cli_result.stderr)
        self.assertEqual(saved_payload["status"], "draft_ready")
        self.assertEqual(saved_payload["draft"]["document_type"], "apqp_chain")
        self.assertFalse(saved_payload["draft_is_formal_export"])
        self.assertFalse(saved_payload["quality_gate"]["allow_user_export"])
        self.assertTrue(saved_payload["manual_review"]["required"])

    def test_cli_run_pipeline_alias_remains_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "evidence.json"
            output_path = Path(tmp) / "draft-result.json"
            input_path.write_text(
                json.dumps(EVIDENCE_INPUT, ensure_ascii=False), encoding="utf-8"
            )
            cli_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "minos_core.cli",
                    "run-pipeline",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(cli_result.returncode, 0, cli_result.stderr)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "draft_ready")
            self.assertEqual(payload["draft"]["document_type"], "apqp_chain")


if __name__ == "__main__":
    unittest.main()
