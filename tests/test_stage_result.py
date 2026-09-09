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

    def test_run_stage_analyze_returns_analysis_bundle(self):
        from minos_core.stage import run_stage

        result = run_stage(FIXTURE_DIR, stage="analyze")

        self.assertEqual(result.stage, "analyze")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "analysis_bundle")
        self.assertIn("drawings", result.output)
        self.assertIn("characteristics", result.output)
        self.assertIn("process_clues", result.output)
        self.assertTrue(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.allow_user_export)

    def test_run_stage_generate_pfd_returns_process_flow(self):
        from minos_core.stage import run_stage

        result = run_stage(FIXTURE_DIR, stage="generate_pfd")

        self.assertEqual(result.stage, "generate_pfd")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["document_type"], "process_flow")
        self.assertIn("steps", result.output)
        self.assertIn("links", result.output)
        self.assertTrue(result.quality_gate.can_continue)
        self.assertFalse(result.quality_gate.allow_user_export)

    def test_run_stage_generate_pfmea_forwards_blocked_pfd_result(self):
        from minos_core.stage import run_stage

        process_flow = {
            "document_type": "process_flow",
            "steps": [],
            "evidence": [],
        }

        pfd_result = run_stage(process_flow, stage="generate_pfd")
        result = run_stage(process_flow, stage="generate_pfmea")

        self.assertEqual(pfd_result.status, "blocked")
        self.assertEqual(result.stage, "generate_pfmea")
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.output, pfd_result.output)
        self.assertEqual(result.pending_fields, pfd_result.pending_fields)
        self.assertEqual(result.ai_inferred_items, pfd_result.ai_inferred_items)
        self.assertEqual(
            result.quality_gate.model_dump(),
            pfd_result.quality_gate.model_dump(),
        )

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

    def test_pipeline_export_blocks_quality_gate_bypass(self):
        from minos_core.pipeline import export_fixture
        from minos_core.quality_gates import ExportGateError

        fixture = _load_fixture()
        fixture["evidence"][0]["needs_confirmation"] = True

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "blocked.xlsx"

            with self.assertRaises(ExportGateError):
                export_fixture(fixture, output_path)

            self.assertFalse(output_path.exists())

    def test_raw_workbook_export_also_uses_export_gate(self):
        from minos_core.exporters.apqp_workbook import export_apqp_workbook
        from minos_core.quality_gates import ExportGateError

        fixture = _load_fixture()
        fixture["evidence"][0]["needs_confirmation"] = True

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "blocked.xlsx"

            with self.assertRaises(ExportGateError):
                export_apqp_workbook(fixture, output_path)

            self.assertFalse(output_path.exists())

    def test_run_stage_export_blocks_needs_confirmation_without_writing(self):
        from minos_core.stage import run_stage

        fixture = _load_fixture()
        fixture["process_flow"]["steps"][0]["needs_confirmation"] = True

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "blocked.xlsx"
            result = run_stage(fixture, stage="export", output_path=output_path)

            self.assertEqual(result.status, "blocked")
            self.assertFalse(result.quality_gate.allow_user_export)
            self.assertIn("process_step:P10", result.quality_gate.needs_confirmation_items)
            self.assertFalse(output_path.exists())

    def test_pipeline_export_blocks_ai_only_item_without_writing(self):
        from minos_core.pipeline import export_fixture
        from minos_core.quality_gates import ExportGateError, evaluate_export_gate

        fixture = _load_fixture()
        fixture["ai_inferred_items"] = [
            {"item_id": "AI-ONLY-P10", "ai_inferred": True}
        ]

        gate = evaluate_export_gate(fixture)
        self.assertTrue(gate.can_continue)
        self.assertFalse(gate.allow_user_export)
        self.assertIn("AI-ONLY-P10", gate.ai_inferred_items)

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "blocked.xlsx"

            with self.assertRaises(ExportGateError):
                export_fixture(fixture, output_path)

            self.assertFalse(output_path.exists())

    def test_pipeline_export_preserves_validation_hard_failure(self):
        from minos_core.pipeline import export_fixture
        from minos_core.quality_gates import ExportGateError

        fixture = _load_fixture()
        fixture["control_plan"]["rows"] = [
            row
            for row in fixture["control_plan"]["rows"]
            if row["pfmea_id"] != "PFMEA-P20-002"
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "blocked.xlsx"

            with self.assertRaises(ExportGateError) as context:
                export_fixture(fixture, output_path)

            self.assertIn("APQP chain validation failed", str(context.exception))
            self.assertFalse(output_path.exists())

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

    def test_validate_reports_three_table_linkage_gaps(self):
        from minos_core.validation import validate_chain

        fixture = _load_fixture()
        fixture.setdefault("metadata", {})["strict_three_table_linkage"] = True
        fixture["process_flow"]["steps"].append(
            {
                "process_step_id": "P40",
                "sequence": 40,
                "operation": "Special check",
                "process_function": "Verify special feature",
                "special_characteristics": ["SC-EXTRA"],
                "evidence_refs": ["EV-PACK-SCAN-001"],
            }
        )
        fixture["control_plan"]["rows"][0]["process_step_id"] = "P99"
        fixture["control_plan"]["rows"][1]["sample_frequency"] = ""

        result = validate_chain(fixture)
        messages = "\n".join(result.messages)

        self.assertFalse(result.ok)
        self.assertIn("process step 'P40' has no PFMEA row", messages)
        self.assertIn("has characteristics but no PFMEA risk row", messages)
        self.assertIn("control plan 'CP-P10-001' references missing process step 'P99'", messages)
        self.assertIn("control plan 'CP-P20-001' is missing sample_frequency", messages)

    def test_validate_reports_special_characteristic_not_carried_through(self):
        from minos_core.validation import validate_chain

        fixture = _load_fixture()
        fixture.setdefault("metadata", {})["strict_three_table_linkage"] = True
        fixture["pfmea"]["rows"][0]["classification"] = ""
        fixture["pfmea"]["rows"][0]["characteristic_refs"] = []
        fixture["control_plan"]["rows"][0]["classification"] = ""
        fixture["control_plan"]["rows"][0]["characteristic_refs"] = []
        fixture["control_plan"]["rows"][0]["source_special_characteristics"] = []

        result = validate_chain(fixture)
        messages = "\n".join(result.messages)

        self.assertFalse(result.ok)
        self.assertIn("missing from PFMEA: SC-THICKNESS", messages)
        self.assertIn("missing from control plan: SC-THICKNESS", messages)

    def test_validate_does_not_treat_ordinary_characteristics_as_special(self):
        from minos_core.validation import validate_chain

        chain = {
            "document_type": "apqp_chain",
            "process_steps": [
                {
                    "process_step_id": "P10",
                    "operation": "检验",
                    "process_function": "确认尺寸",
                    "product_characteristics": ["孔径"],
                    "process_characteristics": ["检验频次"],
                    "special_characteristics": [],
                    "evidence_refs": ["EV-1"],
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P10-001",
                    "process_step_id": "P10",
                    "process_function": "确认尺寸",
                    "failure_mode": "漏检",
                    "failure_effect": "不合格流出",
                    "severity": 6,
                    "failure_cause": "检具失准",
                    "occurrence": 2,
                    "prevention_control": "检具校准",
                    "detection_control": "首件检验",
                    "detection": 3,
                    "action_priority": "L",
                    "evidence_refs": ["EV-1"],
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P10-001",
                    "process_step_id": "P10",
                    "pfmea_id": "PFMEA-P10-001",
                    "product_process_characteristic": "尺寸",
                    "specification": "按图纸",
                    "measurement_method": "卡尺",
                    "sample_frequency": "每批",
                    "reaction_plan": "隔离并通知质量",
                    "evidence_refs": ["EV-1"],
                }
            ],
            "evidence": [{"evidence_id": "EV-1", "source": "fixture", "content": "图纸"}],
            "metadata": {"strict_three_table_linkage": True},
        }

        result = validate_chain(chain)

        self.assertTrue(result.ok, "\n".join(result.messages))


if __name__ == "__main__":
    unittest.main()
