"""Tests for minos_core.three_table_linkage."""

import unittest

from minos_core.three_table_linkage import (
    build_three_table_linkage_map,
    evaluate_three_table_linkage,
    find_linkage_gaps,
)


def _make_fixture(*, steps=None, pfmea=None, control_plan=None):
    """Build a minimal three-table payload dict."""
    payload: dict = {}
    if steps is not None:
        payload["process_flow"] = {"steps": steps}
    if pfmea is not None:
        payload["pfmea"] = {"rows": pfmea}
    if control_plan is not None:
        payload["control_plan"] = {"rows": control_plan}
    return payload


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

P10_STEP = {
    "process_step_id": "P10",
    "operation": "Incoming material verification",
    "process_function": "Verify material cert and dimensions",
    "special_characteristics": ["SC-MAT-THICKNESS"],
    "characteristic_refs": ["CHAR-001"],
}

P20_STEP = {
    "process_step_id": "P20",
    "operation": "Rivet assembly",
    "process_function": "Assemble rivet joints with press tool",
    "special_characteristics": ["SC-RIVET-HEIGHT", "SC-PUSH-OUT-FORCE"],
    "characteristic_refs": ["CHAR-002", "CHAR-003"],
}

P30_STEP = {
    "process_step_id": "P30",
    "operation": "Final inspection and pack",
    "process_function": "Inspect dimensions and pack",
    "special_characteristics": [],
    "characteristic_refs": [],
}

PFMEA_P10_001 = {
    "pfmea_id": "PFMEA-P10-001",
    "process_step_id": "P10",
    "failure_mode": "Material thickness out of spec",
    "failure_effect": "Part strength below requirement",
    "failure_cause": "Supplier material deviation",
    "severity": 8,
    "occurrence": 3,
    "detection": 4,
    "action_priority": "M",
    "prevention_control": "Incoming inspection checklist",
    "detection_control": "CMM measurement",
    "characteristic_refs": ["CHAR-001"],
    "evidence_refs": ["EV-001"],
}

PFMEA_P20_001 = {
    "pfmea_id": "PFMEA-P20-001",
    "process_step_id": "P20",
    "failure_mode": "Rivet height below spec",
    "failure_effect": "Joint loose, potential field failure",
    "failure_cause": "Press tool force too low",
    "severity": 9,
    "occurrence": 5,
    "detection": 3,
    "action_priority": "H",
    "prevention_control": "Force monitor on press",
    "detection_control": "Go/no-go gauge",
    "characteristic_refs": ["CHAR-002"],
    "evidence_refs": ["EV-002"],
}

CP_P10_001 = {
    "control_plan_id": "CP-P10-001",
    "process_step_id": "P10",
    "pfmea_id": "PFMEA-P10-001",
    "product_process_characteristic": "Material thickness",
    "specification": "2.00 +/- 0.10 mm",
    "measurement_method": "CMM",
    "sample_size": "5",
    "sample_frequency": "Per lot",
    "control_method": "SPC chart",
    "reaction_plan": "Quarantine lot, notify supplier",
    "characteristic_refs": ["CHAR-001"],
}

CP_P20_001 = {
    "control_plan_id": "CP-P20-001",
    "process_step_id": "P20",
    "pfmea_id": "PFMEA-P20-001",
    "product_process_characteristic": "Rivet height",
    "specification": "1.50 +0.50/-0.00 mm",
    "measurement_method": "Height gauge",
    "sample_size": "3",
    "sample_frequency": "Per shift",
    "control_method": "Go/no-go gauge",
    "reaction_plan": "Adjust press force, reinspect",
    "characteristic_refs": ["CHAR-002"],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class BuildThreeTableLinkageMapTests(unittest.TestCase):
    """Tests for build_three_table_linkage_map()."""

    def test_normal_three_table_generates_linkage_map_with_correct_links(self):
        """Full three-table payload produces correct link counts."""
        fixture = _make_fixture(
            steps=[P10_STEP, P20_STEP, P30_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P20_001],
            control_plan=[CP_P10_001, CP_P20_001],
        )
        result = build_three_table_linkage_map(fixture)

        self.assertEqual(result["document_type"], "three_table_linkage_map")
        self.assertEqual(result["schema_version"], "minos-core.three_table_linkage.v1")

        # 3 steps, 2 pfmea rows, 2 cp rows
        self.assertEqual(len(result["process_steps"]), 3)
        self.assertEqual(len(result["pfmea_rows"]), 2)
        self.assertEqual(len(result["control_plan_rows"]), 2)

        # Links: 2 pfd_to_pfmea + 2 pfmea_to_control_plan + characteristic_to_step
        links = result["links"]
        pfd_pfmea_links = [l for l in links if l["link_type"] == "pfd_to_pfmea"]
        pfmea_cp_links = [l for l in links if l["link_type"] == "pfmea_to_control_plan"]
        char_step_links = [l for l in links if l["link_type"] == "characteristic_to_step"]

        self.assertEqual(len(pfd_pfmea_links), 2)
        self.assertEqual(len(pfmea_cp_links), 2)
        # P10 has 2 characteristic refs (CHAR-001 + MAT-THICKNESS special),
        # P20 has 3 (CHAR-002, CHAR-003, RIVET-HEIGHT, PUSH-OUT-FORCE), P30 has 0
        self.assertGreaterEqual(len(char_step_links), 3)

        # Check link structure
        first_link = pfd_pfmea_links[0]
        self.assertIn("trace_link_id", first_link)
        self.assertIn("from_type", first_link)
        self.assertIn("from_id", first_link)
        self.assertIn("to_type", first_link)
        self.assertIn("to_id", first_link)
        self.assertIn("link_type", first_link)
        self.assertIn("evidence_refs", first_link)
        self.assertIn("ai_inferred", first_link)
        self.assertIn("needs_confirmation", first_link)
        self.assertEqual(first_link["from_type"], "process_step")
        self.assertEqual(first_link["to_type"], "failure_mode")
        self.assertEqual(first_link["link_type"], "pfd_to_pfmea")

        # Gaps: P30 has no PFMEA, so at least 1 gap expected
        gaps = result["gaps"]
        self.assertGreaterEqual(len(gaps), 1)

    def test_pfd_step_without_pfmea_reports_gap(self):
        """A PFD step with no PFMEA row yields a blocker gap."""
        fixture = _make_fixture(
            steps=[P10_STEP, P30_STEP],
            pfmea=[PFMEA_P10_001],
            control_plan=[CP_P10_001],
        )
        result = build_three_table_linkage_map(fixture)

        gaps = result["gaps"]
        p30_gaps = [g for g in gaps if "P30" in g.get("source", "")]
        self.assertEqual(len(p30_gaps), 1)
        self.assertEqual(p30_gaps[0]["severity"], "blocker")
        self.assertIn("PFMEA", p30_gaps[0]["message"])

    def test_high_ap_pfmea_without_cp_reports_blocker_gap(self):
        """AP=H PFMEA without control plan yields a blocker gap."""
        fixture = _make_fixture(
            steps=[P10_STEP, P20_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P20_001],  # P20 has AP=H
            control_plan=[CP_P10_001],  # only P10 has CP
        )
        result = build_three_table_linkage_map(fixture)

        gaps = result["gaps"]
        pfmea_cp_gaps = [
            g for g in gaps
            if g.get("category_key", "") == "pfmea_cp_coverage"
        ]
        # Re-build after the internal keys are stripped, so check severity + target
        blocker_cp_gaps = [
            g for g in gaps
            if g["severity"] == "blocker" and "PFMEA-P20-001" in g.get("source", "")
            and "control_plan" in g.get("target", "")
        ]
        self.assertGreaterEqual(len(blocker_cp_gaps), 1)
        self.assertIn("没有关联控制计划行", blocker_cp_gaps[0]["message"])

    def test_cp_with_nonexistent_pfmea_id_reports_orphan_gap(self):
        """CP referencing a non-existent pfmea_id yields an orphan warning gap."""
        cp_orphan = {
            "control_plan_id": "CP-ORPHAN-001",
            "process_step_id": "P10",
            "pfmea_id": "PFMEA-NONEXISTENT",
            "product_process_characteristic": "Some char",
            "specification": "1.0",
            "measurement_method": "Visual",
            "sample_size": "1",
            "sample_frequency": "Per lot",
            "control_method": "Check",
            "reaction_plan": "Rework",
        }
        fixture = _make_fixture(
            steps=[P10_STEP],
            pfmea=[PFMEA_P10_001],
            control_plan=[CP_P10_001, cp_orphan],
        )
        result = build_three_table_linkage_map(fixture)

        gaps = result["gaps"]
        orphan_gaps = [
            g for g in gaps
            if "CP-ORPHAN-001" in g.get("source", "")
        ]
        self.assertGreaterEqual(len(orphan_gaps), 1)
        self.assertEqual(orphan_gaps[0]["severity"], "blocker")
        self.assertIn("不存在的 PFMEA", orphan_gaps[0]["message"])

    def test_pfmea_with_nonexistent_process_step_id_reports_orphan_gap(self):
        """PFMEA referencing a non-existent process_step_id yields an orphan blocker gap."""
        pfmea_orphan = {
            "pfmea_id": "PFMEA-ORPHAN-001",
            "process_step_id": "P99",
            "failure_mode": "Unknown step failure",
            "failure_effect": "Unknown effect",
            "failure_cause": "Unknown cause",
            "severity": 5,
            "occurrence": 3,
            "detection": 2,
            "action_priority": "L",
        }
        fixture = _make_fixture(
            steps=[P10_STEP],
            pfmea=[PFMEA_P10_001, pfmea_orphan],
            control_plan=[CP_P10_001],
        )
        result = build_three_table_linkage_map(fixture)

        gaps = result["gaps"]
        orphan_gaps = [
            g for g in gaps
            if "PFMEA-ORPHAN-001" in g.get("source", "")
        ]
        self.assertGreaterEqual(len(orphan_gaps), 1)
        self.assertEqual(orphan_gaps[0]["severity"], "blocker")
        self.assertIn("P99", orphan_gaps[0]["message"])

    def test_special_characteristics_in_pfd_not_pfmea_reports_gap(self):
        """PFD step with special characteristics but PFMEA without them yields a gap."""
        # PFMEA_P10_001 only has CHAR-001, but P10_STEP has MAT-THICKNESS special
        # Actually it does have MAT-THICKNESS in special_characteristics of step
        # but PFMEA_P10_001 only has CHAR-001 in characteristic_refs
        fixture = _make_fixture(
            steps=[P10_STEP, P20_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P20_001],
            control_plan=[CP_P10_001, CP_P20_001],
        )
        result = build_three_table_linkage_map(fixture)

        gaps = result["gaps"]
        # P10 has special_characteristics ["MAT-THICKNESS"] but PFMEA-P10-001 has ["CHAR-001"]
        spec_gaps = [
            g for g in gaps
            if g["severity"] == "blocker"
            and "特殊特性" in g.get("message", "")
        ]
        self.assertGreaterEqual(len(spec_gaps), 1)
        # At least one gap should mention MAT-THICKNESS
        mat_gaps = [g for g in spec_gaps if "MAT-THICKNESS" in g["message"]]
        self.assertGreaterEqual(len(mat_gaps), 1)

    def test_special_characteristics_in_pfmea_not_cp_reports_gap(self):
        """PFMEA with special-characteristic refs but CP without them yields blocker gap."""
        # PFMEA_P20_001 has characteristic_refs including SC-TEST
        # Create PFMEA with an SC-xxx characteristic
        pfmea_with_sc = dict(PFMEA_P20_001)
        pfmea_with_sc["characteristic_refs"] = ["SC-TEST", "CHAR-002"]
        cp_no_char = dict(CP_P20_001)
        cp_no_char["characteristic_refs"] = []
        fixture = _make_fixture(
            steps=[P10_STEP, P20_STEP],
            pfmea=[PFMEA_P10_001, pfmea_with_sc],
            control_plan=[CP_P10_001, cp_no_char],
        )
        result = build_three_table_linkage_map(fixture)

        gaps = result["gaps"]
        # SC-xxx characteristics missing from CP should be blocker
        sc_cp_gaps = [
            g for g in gaps
            if "PFMEA-P20-001" in g.get("source", "")
            and "SC-TEST" in g.get("message", "")
        ]
        self.assertGreaterEqual(len(sc_cp_gaps), 1)
        self.assertEqual(sc_cp_gaps[0]["severity"], "blocker")

        # Regular CHR-xxx characteristics missing from CP should be review only
        chr_cp_gaps = [
            g for g in gaps
            if "PFMEA-P20-001" in g.get("source", "")
            and "CHAR-002" in g.get("message", "")
        ]
        self.assertGreaterEqual(len(chr_cp_gaps), 1)
        self.assertEqual(chr_cp_gaps[0]["severity"], "review")

    def test_summary_statistics_are_correct(self):
        """Summary counts match actual data."""
        fixture = _make_fixture(
            steps=[P10_STEP, P20_STEP, P30_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P20_001],
            control_plan=[CP_P10_001, CP_P20_001],
        )
        result = build_three_table_linkage_map(fixture)
        summary = result["summary"]

        self.assertEqual(summary["process_step_count"], 3)
        self.assertEqual(summary["pfmea_row_count"], 2)
        self.assertEqual(summary["control_plan_row_count"], 2)
        # P30 has no PFMEA
        self.assertGreaterEqual(summary["uncovered_process_steps"], 1)
        # All mandatory PFMEA rows are covered by CP
        self.assertEqual(summary["uncontrolled_pfmea_rows"], 0)
        # No orphan CP items
        self.assertEqual(summary["orphan_control_items"], 0)
        # Special char gaps present (MAT-THICKNESS, RIVET-HEIGHT, PUSH-OUT-FORCE not in PFMEA)
        self.assertGreaterEqual(summary["special_characteristic_gaps"], 1)

    def test_empty_three_table_does_not_crash(self):
        """Empty input produces a valid linkage map without errors."""
        fixture: dict = {}
        result = build_three_table_linkage_map(fixture)

        self.assertEqual(result["document_type"], "three_table_linkage_map")
        self.assertEqual(len(result["process_steps"]), 0)
        self.assertEqual(len(result["pfmea_rows"]), 0)
        self.assertEqual(len(result["control_plan_rows"]), 0)
        self.assertEqual(len(result["links"]), 0)
        self.assertEqual(len(result["gaps"]), 0)
        self.assertEqual(result["summary"]["process_step_count"], 0)
        self.assertEqual(result["summary"]["pfmea_row_count"], 0)
        self.assertEqual(result["summary"]["control_plan_row_count"], 0)

    def test_evaluate_three_table_linkage_returns_complete_structure(self):
        """evaluate_three_table_linkage returns full report structure."""
        fixture = _make_fixture(
            steps=[P10_STEP, P20_STEP, P30_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P20_001],
            control_plan=[CP_P10_001, CP_P20_001],
        )
        report = evaluate_three_table_linkage(fixture)

        self.assertEqual(report["document_type"], "three_table_linkage_report")
        self.assertEqual(report["schema_version"], "minos-core.three_table_linkage.v1")
        self.assertIn("ok", report)
        self.assertIn("needs_review", report)
        self.assertIn("linkage_map", report)
        self.assertIn("blocker_count", report)
        self.assertIn("total_gap_count", report)
        # With gaps present, ok should be False
        self.assertFalse(report["ok"])
        self.assertTrue(report["needs_review"])

    def test_find_linkage_gaps_returns_list(self):
        """find_linkage_gaps returns a flat list of gaps."""
        fixture = _make_fixture(
            steps=[P10_STEP, P30_STEP],  # P30 has no PFMEA
            pfmea=[PFMEA_P10_001],
            control_plan=[CP_P10_001],
        )
        gaps = find_linkage_gaps(fixture)
        self.assertIsInstance(gaps, list)
        self.assertGreaterEqual(len(gaps), 1)
        for gap in gaps:
            self.assertIn("gap_id", gap)
            self.assertIn("severity", gap)
            self.assertIn("message", gap)

    def test_input_is_not_mutated(self):
        """The source dict must never be modified by any function."""
        fixture = _make_fixture(
            steps=[P10_STEP, P20_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P20_001],
            control_plan=[CP_P10_001, CP_P20_001],
        )
        before = _deep_copy(fixture)

        build_three_table_linkage_map(fixture)
        self.assertEqual(fixture, before)

        evaluate_three_table_linkage(fixture)
        self.assertEqual(fixture, before)

        find_linkage_gaps(fixture)
        self.assertEqual(fixture, before)

    def test_all_links_have_required_fields(self):
        """Every generated link has the expected top-level keys."""
        fixture = _make_fixture(
            steps=[P10_STEP, P20_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P20_001],
            control_plan=[CP_P10_001, CP_P20_001],
        )
        result = build_three_table_linkage_map(fixture)
        required = {
            "trace_link_id", "from_type", "from_id",
            "to_type", "to_id", "link_type",
            "evidence_refs", "ai_inferred", "needs_confirmation",
        }
        for link in result["links"]:
            missing = required - set(link)
            self.assertEqual(
                missing, set(),
                f"Link {link.get('trace_link_id')} missing fields: {missing}",
            )

    def test_evaluate_linkage_no_gaps(self):
        """When there are no gaps, evaluate returns ok=True."""
        # A minimal fixture where P20 has special chars and PFMEA covers them
        fixture = _make_fixture(
            steps=[P10_STEP],
            pfmea=[{
                "pfmea_id": "PFMEA-P10-001",
                "process_step_id": "P10",
                "failure_mode": "Material thickness out of spec",
                "failure_effect": "Part strength below requirement",
                "failure_cause": "Supplier material deviation",
                "severity": 5,
                "occurrence": 3,
                "detection": 4,
                "action_priority": "L",
                "characteristic_refs": ["CHAR-001", "SC-MAT-THICKNESS"],
            }],
            control_plan=[{
                "control_plan_id": "CP-P10-001",
                "process_step_id": "P10",
                "pfmea_id": "PFMEA-P10-001",
                "product_process_characteristic": "Material thickness",
                "specification": "2.00 +/- 0.10 mm",
                "measurement_method": "CMM",
                "sample_size": "5",
                "sample_frequency": "Per lot",
                "control_method": "SPC chart",
                "reaction_plan": "Quarantine lot, notify supplier",
                "characteristic_refs": ["CHAR-001", "SC-MAT-THICKNESS"],
            }],
        )
        report = evaluate_three_table_linkage(fixture)
        self.assertTrue(report["ok"])
        self.assertFalse(report["needs_review"])
        self.assertEqual(report["blocker_count"], 0)
        self.assertEqual(report["total_gap_count"], 0)

    def test_sync_snapshot_lists_uncovered_steps(self):
        """PFD 工序无 PFMEA 时 snapshot 能列出。"""
        fixture = _make_fixture(
            steps=[P10_STEP, P30_STEP],
            pfmea=[PFMEA_P10_001],
            control_plan=[CP_P10_001],
        )
        report = evaluate_three_table_linkage(fixture)
        snapshot = report["sync_snapshot"]
        # P30 has no PFMEA
        self.assertIn("process_flow:P30", snapshot["pfd_steps_without_pfmea"])
        self.assertEqual(snapshot["process_step_count"], 2)
        self.assertEqual(snapshot["pfmea_row_count"], 1)

    def test_sync_issue_blocker_for_orphan_cp(self):
        """CP 引用不存在的 PFMEA，sync issue 为 blocker。"""
        cp_orphan = {
            "control_plan_id": "CP-ORPHAN-001",
            "process_step_id": "P10",
            "pfmea_id": "PFMEA-NONEXISTENT",
            "product_process_characteristic": "Some char",
            "specification": "1.0",
            "measurement_method": "Visual",
            "sample_size": "1",
            "sample_frequency": "Per lot",
            "control_method": "Check",
            "reaction_plan": "Rework",
        }
        fixture = _make_fixture(
            steps=[P10_STEP],
            pfmea=[PFMEA_P10_001],
            control_plan=[CP_P10_001, cp_orphan],
        )
        report = evaluate_three_table_linkage(fixture)
        sync_issues = report["sync_issues"]
        orphan_issues = [
            i for i in sync_issues
            if "CP-ORPHAN-001" in i.get("source", "")
        ]
        self.assertGreaterEqual(len(orphan_issues), 1)
        self.assertEqual(orphan_issues[0]["severity"], "blocker")
        self.assertEqual(orphan_issues[0]["category"], "三表同步")

    def test_sync_suggestion_for_pfmea_without_cp(self):
        """高 AP PFMEA 无 CP，生成 add CP suggestion。"""
        fixture = _make_fixture(
            steps=[P10_STEP, P20_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P20_001],  # P20 has AP=H
            control_plan=[CP_P10_001],  # only P10 has CP
        )
        report = evaluate_three_table_linkage(fixture)
        suggestions = report["sync_suggestions"]
        # Should have a suggestion for PFMEA-P20-001
        cp_suggestions = [
            s for s in suggestions
            if s.get("suggested_action") == "add"
            and s.get("target_table") == "control_plan"
            and "PFMEA-P20-001" in s.get("suggestion_id", "")
        ]
        self.assertGreaterEqual(len(cp_suggestions), 1)
        self.assertEqual(cp_suggestions[0]["status"], "待确认")
        self.assertIn("pfmea_id", cp_suggestions[0].get("suggested_fields", {}))

    def test_evaluate_linkage_returns_sync_fields(self):
        """evaluate 返回包含 sync_snapshot, sync_issues, sync_suggestions。"""
        fixture = _make_fixture(
            steps=[P10_STEP, P20_STEP, P30_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P20_001],
            control_plan=[CP_P10_001, CP_P20_001],
        )
        report = evaluate_three_table_linkage(fixture)
        self.assertIn("sync_snapshot", report)
        self.assertIn("sync_issues", report)
        self.assertIn("sync_suggestions", report)
        self.assertIsInstance(report["sync_snapshot"], dict)
        self.assertIsInstance(report["sync_issues"], list)
        self.assertIsInstance(report["sync_suggestions"], list)


def _deep_copy(obj):
    """Recursive deep copy for simple JSON-like structures."""
    import copy
    return copy.deepcopy(obj)


if __name__ == "__main__":
    unittest.main()
