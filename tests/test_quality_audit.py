import copy
import importlib
import json
import unittest
from pathlib import Path

from minos_core.adapters.fixture_json import load_fixture_payload


ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "tests" / "fixtures"
FIXTURE_NAMES = ("apqp_chain", "door_hinge", "stamping", "limiter")


def _import_first(*module_names):
    errors = []
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            errors.append(f"{module_name}: {exc}")
    raise AssertionError(
        "Cannot import expected MINOS-CORE module:\n" + "\n".join(errors)
    )


def _get_first(module, *names):
    for name in names:
        value = getattr(module, name, None)
        if value is not None:
            return value
    raise AssertionError(f"{module.__name__} must expose one of: {', '.join(names)}")


def _load_fixture(name):
    return load_fixture_payload(FIXTURES_DIR / name)


def _as_mapping(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return vars(value)
    raise AssertionError(f"Unsupported audit report type: {type(value)!r}")


def _validation_ok(result):
    if result is None:
        return True
    if isinstance(result, bool):
        return result
    if isinstance(result, tuple):
        return bool(result[0])
    if isinstance(result, dict):
        return bool(result.get("ok", result.get("valid", False)))
    if hasattr(result, "ok"):
        return bool(result.ok)
    if hasattr(result, "valid"):
        return bool(result.valid)
    return bool(result)


def _audit_chain():
    audit_module = _import_first("minos_core.audit", "minos_core.quality_audit")
    return _get_first(
        audit_module, "audit_chain", "audit_apqp_chain", "run_quality_audit"
    )


def _validate_chain():
    validation_module = _import_first("minos_core.validation")
    return _get_first(
        validation_module,
        "validate_chain",
        "validate_apqp_chain",
        "validate_domain_bundle",
    )


def _report_counts(report):
    mapping = _as_mapping(report)
    counts = mapping.get("counts")
    if counts is None and hasattr(report, "counts"):
        counts = getattr(report, "counts")
    self_describing = _as_mapping(counts)
    return self_describing


def _manual_review_items(report):
    mapping = _as_mapping(report)
    items = mapping.get("manual_review_items")
    if items is None and hasattr(report, "manual_review_items"):
        items = getattr(report, "manual_review_items")
    if items is None:
        raise AssertionError("audit report must expose manual_review_items")
    return list(items)


def _report_text(report):
    return json.dumps(_as_mapping(report), ensure_ascii=False, default=str).lower()


def _minimal_weak_link_chain():
    chain = copy.deepcopy(_load_fixture("apqp_chain"))
    chain["process_flow"]["steps"] = [copy.deepcopy(chain["process_flow"]["steps"][0])]
    chain["pfmea"]["rows"] = [copy.deepcopy(chain["pfmea"]["rows"][0])]
    chain["control_plan"]["rows"] = [copy.deepcopy(chain["control_plan"]["rows"][0])]

    failure = chain["pfmea"]["rows"][0]
    control = chain["control_plan"]["rows"][0]
    failure.update(
        {
            "pfmea_id": "PFMEA-WEAK-001",
            "process_step_id": "P10",
            "failure_mode": "Bracket thickness may drift without a defined engineering basis",
            "failure_effect": "Assembly stack height may be unreliable",
            "severity": 8,
            "occurrence": 4,
            "detection": 4,
            "action_priority": "M",
            "classification": "",
            "linked_control_plan_id": "CP-WEAK-001",
        }
    )
    control.update(
        {
            "control_plan_id": "CP-WEAK-001",
            "process_step_id": "P10",
            "pfmea_id": "PFMEA-WEAK-001",
            "product_process_characteristic": "Bracket thickness",
            "specification": "",
            "measurement_method": "Visual check",
            "sample_size": "",
            "sample_frequency": "",
            "control_method": "Operator judgement",
            "reaction_plan": "",
        }
    )
    return chain


class QualityAuditContractTests(unittest.TestCase):
    def test_audit_chain_runs_for_all_standard_fixtures(self):
        audit_chain = _audit_chain()

        for fixture_name in FIXTURE_NAMES:
            with self.subTest(fixture=fixture_name):
                report = audit_chain(_load_fixture(fixture_name))

                counts = _report_counts(report)
                self.assertIn("counts", _as_mapping(report))
                self.assertIn("manual_review_items", _as_mapping(report))
                self.assertIsInstance(counts, dict)
                self.assertIsInstance(_manual_review_items(report), list)

    def test_audit_finds_weak_mechanical_manual_review_without_validation_failure(self):
        weak_chain = _minimal_weak_link_chain()
        validate_chain = _validate_chain()
        audit_chain = _audit_chain()

        validation_result = validate_chain(weak_chain)
        report = audit_chain(weak_chain)
        text = _report_text(report)

        self.assertTrue(_validation_ok(validation_result), str(validation_result))
        self.assertIn("mechanical", text)
        self.assertIn("weak", text)
        self.assertIn("manual", text)
        self.assertGreaterEqual(len(_manual_review_items(report)), 1)

    def test_limiter_audit_stays_within_phase_four_quality_gate(self):
        audit_chain = _audit_chain()

        report = audit_chain(_load_fixture("limiter"))
        counts = _report_counts(report)

        self.assertLessEqual(counts["mechanical_links"], 3)
        self.assertLessEqual(counts["weak_links"], 10)
        self.assertLessEqual(counts["manual_review_items"], 18)

    def test_stage_quality_gate_reports_next_stage_and_export_readiness(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")

        gate = evaluate_stage_gate(_load_fixture("apqp_chain"), stage="validate")

        self.assertTrue(gate.can_continue)
        self.assertTrue(gate.allow_user_export)
        self.assertTrue(gate.evidence_sufficient)
        self.assertEqual(gate.pending_fields, [])
        self.assertEqual(gate.missing_evidence_refs, [])
        self.assertEqual(gate.uncovered_evidence_items, [])
        self.assertTrue(gate.model_dump()["evidence_coverage"]["ok"])
        self.assertIn("process_steps", gate.audit.counts)

    def test_stage_quality_gate_blocks_missing_evidence_ref(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        chain = copy.deepcopy(_load_fixture("apqp_chain"))
        chain["pfmea"]["rows"][0]["evidence_refs"] = ["EV-NOT-FOUND"]

        gate = evaluate_stage_gate(chain, stage="validate")

        self.assertFalse(gate.evidence_sufficient)
        self.assertFalse(gate.can_continue)
        self.assertTrue(
            any("EV-NOT-FOUND" in item for item in gate.missing_evidence_refs)
        )

    def test_stage_quality_gate_blocks_ai_inferred_evidence_ref(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        chain = copy.deepcopy(_load_fixture("apqp_chain"))
        chain["evidence"].append(
            {
                "evidence_id": "EV-AI-001",
                "source": "llm",
                "content": "AI inferred control basis",
                "ai_inferred": True,
            }
        )
        chain["control_plan"]["rows"][0]["evidence_refs"] = ["EV-AI-001"]

        gate = evaluate_stage_gate(chain, stage="validate")

        self.assertFalse(gate.evidence_sufficient)
        self.assertFalse(gate.can_continue)
        self.assertIn("EV-AI-001", gate.ai_inferred_items)
        self.assertTrue(gate.model_dump()["evidence_coverage"]["ai_inferred_refs"])


if __name__ == "__main__":
    unittest.main()
