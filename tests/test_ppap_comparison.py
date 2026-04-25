import copy
import unittest
from pathlib import Path

from minos_core.adapters.fixture_json import load_fixture_payload
from minos_core.ppap_comparison import (
    EXTRA_GENERATED_ITEM,
    MATCHED,
    MISSING_CONTROL_ITEM,
    MISSING_PROCESS_STEP,
    compare_to_approved_ppap,
)


ROOT = Path(__file__).resolve().parents[1]
GENERATED_FIXTURE = ROOT / "tests" / "fixtures" / "apqp_chain"
APPROVED_BASELINE = (
    ROOT
    / "tests"
    / "fixtures"
    / "approved_baseline"
    / "apqp_chain_approved_baseline.json"
)


def _generated_chain():
    return load_fixture_payload(GENERATED_FIXTURE)


def _approved_baseline():
    return load_fixture_payload(APPROVED_BASELINE)


def _categories(report):
    return [item.category for item in report.differences]


class PPAPComparisonTests(unittest.TestCase):
    def test_approved_baseline_matches_standard_generated_fixture(self):
        report = compare_to_approved_ppap(_generated_chain(), _approved_baseline())

        self.assertTrue(report.ok, report.model_dump())
        self.assertEqual(report.counts[MATCHED], 11)
        self.assertEqual(report.counts[MISSING_PROCESS_STEP], 0)
        self.assertEqual(report.counts[MISSING_CONTROL_ITEM], 0)
        self.assertEqual(report.counts[EXTRA_GENERATED_ITEM], 0)

    def test_reports_missing_process_step_against_approved_baseline(self):
        generated = _generated_chain()
        generated["process_flow"]["steps"] = [
            item
            for item in generated["process_flow"]["steps"]
            if item["process_step_id"] != "P30"
        ]

        report = compare_to_approved_ppap(generated, _approved_baseline())
        missing_steps = [
            item
            for item in report.differences
            if item.category == MISSING_PROCESS_STEP
        ]

        self.assertFalse(report.ok)
        self.assertEqual(len(missing_steps), 1)
        self.assertEqual(missing_steps[0].baseline_id, "P30")
        self.assertTrue(missing_steps[0].review["required"])

    def test_reports_missing_control_item_against_approved_baseline(self):
        generated = _generated_chain()
        generated["control_plan"]["rows"] = [
            item
            for item in generated["control_plan"]["rows"]
            if item["control_plan_id"] != "CP-P20-002"
        ]

        report = compare_to_approved_ppap(generated, _approved_baseline())
        missing_controls = [
            item
            for item in report.differences
            if item.category == MISSING_CONTROL_ITEM
        ]

        self.assertFalse(report.ok)
        self.assertEqual(len(missing_controls), 1)
        self.assertEqual(missing_controls[0].baseline_id, "CP-P20-002")
        self.assertIn("APP-CP-003", missing_controls[0].evidence)
        self.assertTrue(missing_controls[0].review["required"])

    def test_difference_report_contains_evidence_and_review_fields(self):
        generated = copy.deepcopy(_generated_chain())
        generated["control_plan"]["rows"][0]["control_plan_id"] = "CP-P10-EXTRA"

        report = compare_to_approved_ppap(generated, _approved_baseline())
        dump = report.model_dump()
        categories = _categories(report)

        self.assertIn(MISSING_CONTROL_ITEM, categories)
        self.assertIn(EXTRA_GENERATED_ITEM, categories)
        self.assertIn("differences", dump)
        for item in dump["differences"]:
            self.assertIn("evidence", item)
            self.assertIn("review", item)
            self.assertIsInstance(item["evidence"], list)
            self.assertIsInstance(item["review"], dict)


if __name__ == "__main__":
    unittest.main()
