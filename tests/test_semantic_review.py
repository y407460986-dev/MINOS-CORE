"""Tests for minos_core.semantic_review — semantic validation of AI-generated APQP drafts."""

from __future__ import annotations

import unittest

from minos_core.semantic_review import (
    check_cause_effect_logic,
    check_cross_table_step_name_consistency,
    check_detection_vs_failure_type,
    check_measurement_vs_tolerance,
    check_rpn_arithmetic,
    semantic_review_cross_table,
    semantic_review_row,
)


class CheckRpnArithmeticTests(unittest.TestCase):
    """Tests for check_rpn_arithmetic."""

    def test_rpn_mismatch_is_flagged(self):
        """S=5, O=4, D=3 -> RPN should be 60.  If RPN=0, flag it."""
        row = {"severity": 5, "occurrence": 4, "detection": 3, "rpn": 0}
        issues = check_rpn_arithmetic(row)
        self.assertEqual(len(issues), 1)
        self.assertIn("60", issues[0])  # expected 60
        self.assertIn("0", issues[0])   # got 0

    def test_rpn_correct_is_clean(self):
        """S=5, O=4, D=3, RPN=60 -> no issues."""
        row = {"severity": 5, "occurrence": 4, "detection": 3, "rpn": 60}
        issues = check_rpn_arithmetic(row)
        self.assertEqual(issues, [])

    def test_rpn_handles_chinese_field_names(self):
        """Chinese field names 严重度/频度/探测度."""
        row = {"严重度": 5, "频度": 4, "探测度": 3, "RPN": 0}
        issues = check_rpn_arithmetic(row)
        self.assertEqual(len(issues), 1)
        self.assertIn("60", issues[0])

    def test_rpn_handles_short_field_names(self):
        """Short field names S/O/D."""
        row = {"S": 3, "O": 2, "D": 2, "RPN": 12}
        issues = check_rpn_arithmetic(row)
        self.assertEqual(issues, [])

    def test_missing_severity_is_reported(self):
        """When severity is missing, report the gap."""
        row = {"occurrence": 4, "detection": 3, "rpn": 12}
        issues = check_rpn_arithmetic(row)
        self.assertEqual(len(issues), 1)
        self.assertIn("S/severity", issues[0])

    def test_missing_rpn_is_reported(self):
        """When RPN is missing entirely, report it."""
        row = {"severity": 5, "occurrence": 4, "detection": 3}
        issues = check_rpn_arithmetic(row)
        self.assertEqual(len(issues), 1)
        self.assertIn("RPN 值为空", issues[0])

    def test_float_rpn_close_enough_is_clean(self):
        """Floating-point RPN that is very close: S=5, O=4, D=3 -> 60.0."""
        row = {"severity": 5, "occurrence": 4, "detection": 3, "rpn": 60.0}
        issues = check_rpn_arithmetic(row)
        self.assertEqual(issues, [])

    def test_float_rpn_slightly_off_is_flagged(self):
        """S=5, O=4, D=3 -> RPN=59 is wrong."""
        row = {"severity": 5, "occurrence": 4, "detection": 3, "rpn": 59}
        issues = check_rpn_arithmetic(row)
        self.assertEqual(len(issues), 1)


class CheckCauseEffectLogicTests(unittest.TestCase):
    """Tests for check_cause_effect_logic."""

    def test_identical_cause_and_mode_flagged(self):
        """Cause == Mode should be flagged as suspicious."""
        row = {
            "failure_cause": "操作失误",
            "failure_mode": "操作失误",
            "failure_effect": "产品报废",
        }
        issues = check_cause_effect_logic(row)
        self.assertGreaterEqual(len(issues), 1)
        self.assertTrue(
            any("failure_cause" in i and "failure_mode" in i for i in issues)
        )

    def test_identical_cause_and_effect_flagged(self):
        """Cause == Effect should be flagged."""
        row = {
            "failure_cause": "操作失误",
            "failure_mode": "漏检",
            "failure_effect": "操作失误",
        }
        issues = check_cause_effect_logic(row)
        self.assertGreaterEqual(len(issues), 1)
        self.assertTrue(
            any("failure_cause" in i and "failure_effect" in i for i in issues)
        )

    def test_identical_mode_and_effect_flagged(self):
        """Mode == Effect should be flagged."""
        row = {
            "failure_cause": "操作失误",
            "failure_mode": "漏检",
            "failure_effect": "漏检",
        }
        issues = check_cause_effect_logic(row)
        self.assertGreaterEqual(len(issues), 1)
        self.assertTrue(
            any("failure_mode" in i and "failure_effect" in i for i in issues)
        )

    def test_all_three_identical_flagged(self):
        """All three identical -> multiple issues."""
        row = {
            "failure_cause": "漏检",
            "failure_mode": "漏检",
            "failure_effect": "漏检",
        }
        issues = check_cause_effect_logic(row)
        self.assertEqual(len(issues), 3)

    def test_all_distinct_is_clean(self):
        """Different cause, mode, effect -> no issues."""
        row = {
            "failure_cause": "检具未校准",
            "failure_mode": "尺寸超差",
            "failure_effect": "装配不良",
        }
        issues = check_cause_effect_logic(row)
        self.assertEqual(issues, [])

    def test_empty_fields_are_skipped(self):
        """If any field is empty, skip (cannot evaluate)."""
        row = {
            "failure_cause": "",
            "failure_mode": "漏检",
            "failure_effect": "产品报废",
        }
        issues = check_cause_effect_logic(row)
        self.assertEqual(issues, [])

    def test_chinese_field_names_respected(self):
        """Chinese field names 失效原因/失效模式/失效后果."""
        row = {
            "失效原因": "操作失误",
            "失效模式": "操作失误",
            "失效后果": "产品报废",
        }
        issues = check_cause_effect_logic(row)
        self.assertGreaterEqual(len(issues), 1)

    def test_normalized_whitespace_ignored(self):
        """Extra whitespace should not cause false mismatch."""
        row = {
            "failure_cause": "  操作失误  ",
            "failure_mode": "操作失误",
            "failure_effect": "产品报废",
        }
        issues = check_cause_effect_logic(row)
        self.assertGreaterEqual(len(issues), 1)


class CheckDetectionVsFailureTypeTests(unittest.TestCase):
    """Tests for check_detection_vs_failure_type."""

    def test_visual_failure_without_visual_detection_flagged(self):
        """外观划伤 without 目视检查 -> flagged."""
        row = {
            "failure_mode": "外观划伤",
            "detection_control": "卡尺测量",
        }
        issues = check_detection_vs_failure_type(row)
        self.assertGreaterEqual(len(issues), 1)
        self.assertIn("目视", issues[0])

    def test_visual_failure_with_visual_detection_clean(self):
        """外观划伤 with 目视检查 -> clean."""
        row = {
            "failure_mode": "外观划伤",
            "detection_control": "目视检查",
        }
        issues = check_detection_vs_failure_type(row)
        self.assertEqual(issues, [])

    def test_dimensional_failure_without_measurement_flagged(self):
        """尺寸超差 without 卡尺/测量 -> flagged."""
        row = {
            "failure_mode": "尺寸超差",
            "detection_control": "目视检查",
        }
        issues = check_detection_vs_failure_type(row)
        self.assertGreaterEqual(len(issues), 1)
        self.assertIn("测量", issues[0])

    def test_dimensional_failure_with_measurement_clean(self):
        """尺寸超差 with 卡尺 -> clean."""
        row = {
            "failure_mode": "尺寸超差",
            "detection_control": "卡尺测量",
        }
        issues = check_detection_vs_failure_type(row)
        self.assertEqual(issues, [])

    def test_english_keywords_visual(self):
        """'scratch' failure mode, detection is 'gauge check' (no visual) -> flagged."""
        row = {
            "failure_mode": "surface scratch",
            "detection_control": "gauge check",
        }
        issues = check_detection_vs_failure_type(row)
        self.assertEqual(len(issues), 1)

    def test_poka_yoke_detection_skipped(self):
        """Poka-yoke / 防错 detection skips the check entirely."""
        row = {
            "failure_mode": "外观划伤",
            "detection_control": "防错装置自动检测",
        }
        issues = check_detection_vs_failure_type(row)
        self.assertEqual(issues, [])

    def test_empty_fields_skipped(self):
        """Missing mode or detection -> no issues."""
        row = {"failure_mode": "", "detection_control": "卡尺"}
        issues = check_detection_vs_failure_type(row)
        self.assertEqual(issues, [])

    def test_deform_keyword_triggers_visual(self):
        """'deform' is in the visual keyword list."""
        row = {
            "failure_mode": "part deformation",
            "detection_control": "micrometer",
        }
        issues = check_detection_vs_failure_type(row)
        self.assertEqual(len(issues), 1)


class CheckMeasurementVsToleranceTests(unittest.TestCase):
    """Tests for check_measurement_vs_tolerance."""

    def test_tight_tolerance_with_visual_inspection_flagged(self):
        """±0.01mm tolerance with 目视检查 -> flagged."""
        row = {
            "tolerance": "±0.01mm",
            "measurement_method": "目视检查",
        }
        issues = check_measurement_vs_tolerance(row)
        self.assertEqual(len(issues), 1)
        self.assertIn("0.01", issues[0])
        self.assertIn("目视", issues[0])

    def test_tight_tolerance_with_caliper_clean(self):
        """±0.01mm tolerance with 卡尺测量 -> clean."""
        row = {
            "tolerance": "±0.01mm",
            "measurement_method": "卡尺测量",
        }
        issues = check_measurement_vs_tolerance(row)
        self.assertEqual(issues, [])

    def test_loose_tolerance_with_visual_clean(self):
        """±1.0mm tolerance with 目视 -> clean (loose tolerance is OK visually)."""
        row = {
            "tolerance": "±1.0mm",
            "measurement_method": "目视检查",
        }
        issues = check_measurement_vs_tolerance(row)
        self.assertEqual(issues, [])

    def test_exactly_005mm_tolerance_is_tight(self):
        """±0.05mm is the boundary — still considered tight (<=0.05)."""
        row = {
            "tolerance": "±0.05mm",
            "measurement_method": "目视检查",
        }
        issues = check_measurement_vs_tolerance(row)
        self.assertEqual(len(issues), 1)

    def test_006mm_tolerance_is_not_tight(self):
        """±0.06mm > 0.05 -> clean."""
        row = {
            "tolerance": "±0.06mm",
            "measurement_method": "目视检查",
        }
        issues = check_measurement_vs_tolerance(row)
        self.assertEqual(issues, [])

    def test_cp_row_uses_detection_control_field(self):
        """Control Plan rows may have detection_control instead of measurement_method."""
        row = {
            "tolerance": "±0.01",
            "detection_control": "目视检查",
        }
        issues = check_measurement_vs_tolerance(row)
        self.assertEqual(len(issues), 1)

    def test_empty_tolerance_skipped(self):
        """No tolerance -> no issues."""
        row = {"measurement_method": "目视检查"}
        issues = check_measurement_vs_tolerance(row)
        self.assertEqual(issues, [])

    def test_poka_yoke_ignored_for_tight_tolerance(self):
        """Poka-yoke / sensor-based detection skips the check."""
        row = {
            "tolerance": "±0.01mm",
            "measurement_method": "防错传感器",
        }
        issues = check_measurement_vs_tolerance(row)
        self.assertEqual(issues, [])

    def test_non_standard_tolerance_format_extracted(self):
        """Tolerance like '10±0.02' should extract 0.02."""
        row = {
            "tolerance": "10±0.02",
            "measurement_method": "目视",
        }
        issues = check_measurement_vs_tolerance(row)
        self.assertEqual(len(issues), 1)
        self.assertIn("0.02", issues[0])

    def test_missing_measurement_method_skipped(self):
        """No measurement method -> no issues."""
        row = {"tolerance": "±0.01mm"}
        issues = check_measurement_vs_tolerance(row)
        self.assertEqual(issues, [])


class CheckCrossTableStepNameConsistencyTests(unittest.TestCase):
    """Tests for check_cross_table_step_name_consistency."""

    def test_matching_names_clean(self):
        """PFD has '清洗' and PFMEA row with same step_id also has '清洗' -> clean."""
        pfd_steps = [
            {"process_step_id": "P10", "operation": "清洗"},
        ]
        pfmea_rows = [
            {"pfmea_id": "PFMEA-1", "process_step_id": "P10", "process_step": "清洗"},
        ]
        issues = check_cross_table_step_name_consistency(pfd_steps, pfmea_rows)
        self.assertEqual(issues, [])

    def test_mismatched_names_flagged(self):
        """PFD '清洗' vs PFMEA '清洁' -> flagged."""
        pfd_steps = [
            {"process_step_id": "P10", "operation": "清洗"},
        ]
        pfmea_rows = [
            {"pfmea_id": "PFMEA-1", "process_step_id": "P10", "process_step": "清洁"},
        ]
        issues = check_cross_table_step_name_consistency(pfd_steps, pfmea_rows)
        self.assertEqual(len(issues), 1)
        self.assertIn("清洗", issues[0]["message"])
        self.assertIn("清洁", issues[0]["message"])

    def test_fallback_to_sequence_matching(self):
        """When step_id doesn't match, fall back to sequence number matching."""
        pfd_steps = [
            {"process_step_id": "P10", "sequence": 10, "operation": "清洗"},
        ]
        pfmea_rows = [
            {"pfmea_id": "PFMEA-1", "process_step_id": "P99", "sequence": 10, "process_step": "清洁"},
        ]
        issues = check_cross_table_step_name_consistency(pfd_steps, pfmea_rows)
        self.assertEqual(len(issues), 1)
        self.assertIn("seq=10", issues[0]["message"])

    def test_no_matching_id_or_seq_skipped(self):
        """PFMEA row with unknown step_id and no sequence -> skipped."""
        pfd_steps = [
            {"process_step_id": "P10", "operation": "清洗"},
        ]
        pfmea_rows = [
            {"pfmea_id": "PFMEA-1", "process_step_id": "P99", "process_step": "清洁"},
        ]
        issues = check_cross_table_step_name_consistency(pfd_steps, pfmea_rows)
        self.assertEqual(issues, [])

    def test_empty_inputs_handled(self):
        """Empty lists -> no issues."""
        self.assertEqual(check_cross_table_step_name_consistency([], []), [])
        self.assertEqual(check_cross_table_step_name_consistency([], [{"a": 1}]), [])
        self.assertEqual(
            check_cross_table_step_name_consistency(
                [{"process_step_id": "P10", "operation": "清洗"}], []
            ),
            [],
        )

    def test_issue_dict_structure(self):
        """Verify the structure of returned issue dicts."""
        pfd_steps = [
            {"process_step_id": "P10", "operation": "清洗"},
        ]
        pfmea_rows = [
            {"pfmea_id": "PFMEA-1", "process_step_id": "P10", "process_step": "清洁"},
        ]
        issues = check_cross_table_step_name_consistency(pfd_steps, pfmea_rows)
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertIn("item_id", issue)
        self.assertIn("category", issue)
        self.assertEqual(issue["category"], "cross_table_consistency")
        self.assertIn("message", issue)
        self.assertIn("severity", issue)
        self.assertEqual(issue["severity"], "review")


class SemanticReviewRowTests(unittest.TestCase):
    """Tests for semantic_review_row aggregate function."""

    def test_pfmea_row_runs_all_checks(self):
        """A PFMEA row should run RPN, cause-effect, detection, and measurement checks."""
        row = {
            "pfmea_id": "PFMEA-X",
            "severity": 5,
            "occurrence": 4,
            "detection": 3,
            "rpn": 0,
            "failure_cause": "漏检",
            "failure_mode": "漏检",
            "failure_effect": "漏检",
            "detection_control": "目视检查",
            "tolerance": "±0.01mm",
        }
        issues = semantic_review_row(row, table="pfmea")
        # Should have: RPN mismatch + 3 cause/effect issues + measurement warning
        # (detection vs failure type is clean here because mode is 漏检, which is
        # not in the visual keyword list)
        self.assertGreaterEqual(len(issues), 4)

    def test_control_plan_row_runs_measurement_check(self):
        """A CP row should run measurement vs tolerance."""
        row = {
            "control_plan_id": "CP-1",
            "tolerance": "±0.01mm",
            "measurement_method": "目视检查",
        }
        issues = semantic_review_row(row, table="control_plan")
        self.assertEqual(len(issues), 1)
        self.assertIn("0.01", issues[0])

    def test_control_plan_row_with_rpn_checks_arithmetic(self):
        """CP row that carries an RPN value should also check arithmetic."""
        row = {
            "control_plan_id": "CP-1",
            "severity": 3,
            "occurrence": 3,
            "detection": 3,
            "rpn": 0,
            "tolerance": "±1.0mm",
            "measurement_method": "卡尺",
        }
        issues = semantic_review_row(row, table="control_plan")
        self.assertEqual(len(issues), 1)  # only RPN mismatch
        self.assertIn("27", issues[0])  # 3*3*3 = 27

    def test_process_flow_row_skips_checks(self):
        """PFD rows are not checked individually by semantic_review_row."""
        row = {"process_step_id": "P10", "operation": "清洗"}
        issues = semantic_review_row(row, table="process_flow")
        self.assertEqual(issues, [])

    def test_unknown_table_skipped(self):
        """Unknown table type -> no checks."""
        row = {"id": "X"}
        issues = semantic_review_row(row, table="unknown")
        self.assertEqual(issues, [])


class SemanticReviewCrossTableTests(unittest.TestCase):
    """Tests for semantic_review_cross_table."""

    def test_pfd_pfmea_consistency_checked(self):
        """Cross-table check catches PFD-PFMEA step name mismatches."""
        pfd_steps = [
            {"process_step_id": "P10", "operation": "清洗"},
        ]
        pfmea_rows = [
            {"pfmea_id": "PFMEA-1", "process_step_id": "P10", "process_step": "清洁"},
        ]
        cp_rows: list[dict[str, Any]] = []
        issues = semantic_review_cross_table(pfd_steps, pfmea_rows, cp_rows)
        self.assertGreaterEqual(len(issues), 1)
        # At least one issue is about PFD-PFMEA mismatch
        self.assertTrue(
            any("PFD" in i["message"] and "PFMEA" in i["message"] for i in issues)
        )

    def test_pfd_cp_consistency_checked(self):
        """Cross-table also checks PFD-CP step name consistency."""
        pfd_steps = [
            {"process_step_id": "P10", "operation": "清洗"},
        ]
        pfmea_rows: list[dict[str, Any]] = []
        cp_rows = [
            {"control_plan_id": "CP-1", "process_step_id": "P10", "process_step": "清洁"},
        ]
        issues = semantic_review_cross_table(pfd_steps, pfmea_rows, cp_rows)
        self.assertEqual(len(issues), 1)
        self.assertIn("PFD", issues[0]["message"])

    def test_all_consistent_is_clean(self):
        """When everything matches, no issues."""
        pfd_steps = [
            {"process_step_id": "P10", "operation": "清洗"},
            {"process_step_id": "P20", "operation": "装配"},
        ]
        pfmea_rows = [
            {"pfmea_id": "PFMEA-1", "process_step_id": "P10", "process_step": "清洗"},
            {"pfmea_id": "PFMEA-2", "process_step_id": "P20", "process_step": "装配"},
        ]
        cp_rows = [
            {"control_plan_id": "CP-1", "process_step_id": "P10", "process_step": "清洗"},
            {"control_plan_id": "CP-2", "process_step_id": "P20", "process_step": "装配"},
        ]
        issues = semantic_review_cross_table(pfd_steps, pfmea_rows, cp_rows)
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
