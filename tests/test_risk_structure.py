"""Tests for minos_core.risk_structure."""

import unittest

from minos_core.risk_structure import build_risk_structure


def _make_fixture(*, steps=None, pfmea=None, control_plan=None, **extra):
    """Build a minimal three-table payload dict."""
    payload: dict = dict(extra)
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
    "operation": "IQC inspection",
    "process_function": "Verify raw material certification and dimensions",
    "characteristic_refs": ["SC-MAT-THICKNESS"],
}

P20_STEP = {
    "process_step_id": "P20",
    "operation": "Rivet assembly",
    "process_function": "Assemble rivet joints with press tool",
    "characteristic_refs": ["SC-RIVET-HEIGHT"],
}

PFMEA_P10_001 = {
    "pfmea_id": "PFMEA-P10-001",
    "process_step_id": "P10",
    "function_requirement": "Material thickness must be 2.00 +/- 0.10 mm",
    "failure_mode": "Material thickness out of spec",
    "failure_effect": "Part strength below requirement",
    "failure_cause": "Supplier material deviation",
    "severity": 8,
    "occurrence": 3,
    "detection": 4,
    "action_priority": "M",
    "prevention_control": "Supplier CoC check",
    "detection_control": "Incoming thickness measurement",
    "recommended_action": "",
    "responsibility": "",
    "target_date": "",
    "action_status": "",
    "needs_confirmation": False,
    "ai_inferred": False,
}

PFMEA_P10_002 = {
    "pfmea_id": "PFMEA-P10-002",
    "process_step_id": "P10",
    "function_requirement": "Surface must be free of rust",
    "failure_mode": "Surface rust detected",
    "failure_effect": "Coating adhesion failure",
    "failure_cause": "Improper storage",
    "severity": 5,
    "occurrence": 2,
    "detection": 2,
    "action_priority": "L",
    "prevention_control": "Visual inspection",
    "detection_control": "",
    "recommended_action": "",
    "responsibility": "",
    "target_date": "",
    "action_status": "",
    "needs_confirmation": False,
    "ai_inferred": False,
}

PFMEA_P20_001 = {
    "pfmea_id": "PFMEA-P20-001",
    "process_step_id": "P20",
    "function_requirement": "Rivet height 3.5 +0.2/-0.1 mm",
    "failure_mode": "Rivet height below spec",
    "failure_effect": "Joint loose, potential field failure",
    "failure_cause": "Press tool force too low",
    "severity": 7,
    "occurrence": 4,
    "detection": 5,
    "action_priority": "M",
    "prevention_control": "Force monitor on press",
    "detection_control": "Go/no-go gauge",
    "recommended_action": "",
    "responsibility": "",
    "target_date": "",
    "action_status": "",
    "needs_confirmation": True,
    "ai_inferred": True,
}

CP_P10_001_1 = {
    "control_plan_id": "CP-P10-001-1",
    "process_step_id": "P10",
    "pfmea_id": "PFMEA-P10-001",
    "product_process_characteristic": "Material thickness",
    "specification": "2.00 +/- 0.10 mm",
    "measurement_method": "Digital thickness gauge",
    "sample_frequency": "Each incoming lot",
    "reaction_plan": "Stop use, notify SQE",
}

CP_P10_001_2 = {
    "control_plan_id": "CP-P10-001-2",
    "process_step_id": "P10",
    "pfmea_id": "PFMEA-P10-001",
    "product_process_characteristic": "Material width",
    "specification": "100 +/- 1 mm",
    "measurement_method": "Caliper",
    "sample_frequency": "Each incoming lot",
    "reaction_plan": "Quarantine and re-measure",
}

CP_P20_001_1 = {
    "control_plan_id": "CP-P20-001-1",
    "process_step_id": "P20",
    "pfmea_id": "PFMEA-P20-001",
    "product_process_characteristic": "Rivet height",
    "specification": "3.5 +0.2/-0.1 mm",
    "measurement_method": "Height gauge",
    "sample_frequency": "First piece and every 50 pcs",
    "reaction_plan": "Adjust press, re-inspect",
}


class RiskStructureNormalTests(unittest.TestCase):
    """Tests for normal three-table build."""

    def test_normal_three_table_builds_structure_tree(self):
        """Normal three-table input builds process->risk->control tree."""
        payload = _make_fixture(
            steps=[P10_STEP, P20_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P10_002, PFMEA_P20_001],
            control_plan=[CP_P10_001_1, CP_P10_001_2, CP_P20_001_1],
        )
        result = build_risk_structure(payload)

        self.assertEqual(result["document_type"], "risk_structure")
        self.assertEqual(
            result["schema_version"], "minos-core.risk_structure.v1"
        )

        # Two process nodes
        nodes = result["process_nodes"]
        self.assertEqual(len(nodes), 2)

        # P10
        p10 = nodes[0]
        self.assertEqual(p10["process_step_id"], "P10")
        self.assertEqual(p10["operation"], "IQC inspection")
        self.assertEqual(p10["process_function"], "Verify raw material certification and dimensions")
        self.assertEqual(p10["characteristic_refs"], ["SC-MAT-THICKNESS"])

        # P10 should have 2 risk nodes
        self.assertEqual(len(p10["risk_nodes"]), 2)

        p10_risk_1 = p10["risk_nodes"][0]
        self.assertEqual(p10_risk_1["pfmea_id"], "PFMEA-P10-001")
        self.assertEqual(p10_risk_1["failure_mode"], "Material thickness out of spec")
        self.assertEqual(p10_risk_1["severity"], 8)
        self.assertEqual(p10_risk_1["action_priority"], "M")

        # PFMEA-P10-001 has 2 control nodes
        self.assertEqual(len(p10_risk_1["control_nodes"]), 2)
        cp_ids = {cn["control_plan_id"] for cn in p10_risk_1["control_nodes"]}
        self.assertIn("CP-P10-001-1", cp_ids)
        self.assertIn("CP-P10-001-2", cp_ids)

        # P20
        p20 = nodes[1]
        self.assertEqual(p20["process_step_id"], "P20")
        self.assertEqual(len(p20["risk_nodes"]), 1)

        # No orphans
        self.assertEqual(result["orphan_risk_nodes"], [])
        self.assertEqual(result["orphan_control_nodes"], [])

    def test_summary_counts_are_correct(self):
        """Summary counts reflect process, risk, control node totals."""
        payload = _make_fixture(
            steps=[P10_STEP, P20_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P10_002, PFMEA_P20_001],
            control_plan=[CP_P10_001_1, CP_P10_001_2, CP_P20_001_1],
        )
        result = build_risk_structure(payload)
        summary = result["summary"]

        self.assertEqual(summary["process_node_count"], 2)
        self.assertEqual(summary["risk_node_count"], 3)
        self.assertEqual(summary["control_node_count"], 3)
        # P20 has needs_confirmation=True, so needs_review
        self.assertEqual(summary["review_node_count"], 1)
        # No high AP or severity >= 9
        self.assertEqual(summary["open_action_count"], 0)


class OpenActionRequiredTests(unittest.TestCase):
    """Tests for open_action_required flag."""

    def test_high_ap_flags_open_action_required(self):
        """AP=H PFMEA row flags open_action_required."""
        pfmea_h = dict(PFMEA_P10_001, action_priority="H")
        payload = _make_fixture(
            steps=[P10_STEP],
            pfmea=[pfmea_h],
        )
        result = build_risk_structure(payload)
        risk = result["process_nodes"][0]["risk_nodes"][0]
        self.assertTrue(risk["open_action_required"])

    def test_severity_9_flags_open_action_required(self):
        """severity>=9 flags open_action_required."""
        pfmea_s9 = dict(PFMEA_P10_001, severity=9, action_priority="L")
        payload = _make_fixture(
            steps=[P10_STEP],
            pfmea=[pfmea_s9],
        )
        result = build_risk_structure(payload)
        risk = result["process_nodes"][0]["risk_nodes"][0]
        self.assertTrue(risk["open_action_required"])

    def test_recommended_action_without_owner_flags(self):
        """recommended_action non-empty with no responsibility/target_date flags open."""
        pfmea = dict(
            PFMEA_P10_001,
            action_priority="L",
            severity=1,
            recommended_action="Add force sensor",
            responsibility="",
            target_date="",
            action_status="",
        )
        payload = _make_fixture(steps=[P10_STEP], pfmea=[pfmea])
        result = build_risk_structure(payload)
        risk = result["process_nodes"][0]["risk_nodes"][0]
        self.assertTrue(risk["open_action_required"])

    def test_recommended_action_completed_does_not_flag(self):
        """recommended_action with filled fields and status=已关闭 does NOT flag."""
        pfmea = dict(
            PFMEA_P10_001,
            action_priority="L",
            severity=1,
            recommended_action="Add force sensor",
            responsibility="John",
            target_date="2026-06-01",
            action_status="已关闭",
        )
        payload = _make_fixture(steps=[P10_STEP], pfmea=[pfmea])
        result = build_risk_structure(payload)
        risk = result["process_nodes"][0]["risk_nodes"][0]
        self.assertFalse(risk["open_action_required"])

    def test_recommended_action_completed_status_flags(self):
        """recommended_action with status=进行中 still flags open."""
        pfmea = dict(
            PFMEA_P10_001,
            action_priority="L",
            severity=1,
            recommended_action="Add force sensor",
            responsibility="John",
            target_date="2026-06-01",
            action_status="进行中",
        )
        payload = _make_fixture(steps=[P10_STEP], pfmea=[pfmea])
        result = build_risk_structure(payload)
        risk = result["process_nodes"][0]["risk_nodes"][0]
        self.assertTrue(risk["open_action_required"])


class NeedsReviewTests(unittest.TestCase):
    """Tests for needs_review flag."""

    def test_unconfirmed_pfmea_flags_needs_review(self):
        """needs_confirmation=True flags needs_review."""
        pfmea = dict(PFMEA_P10_001, needs_confirmation=True)
        payload = _make_fixture(steps=[P10_STEP], pfmea=[pfmea])
        result = build_risk_structure(payload)
        risk = result["process_nodes"][0]["risk_nodes"][0]
        self.assertTrue(risk["needs_review"])

    def test_ai_inferred_flags_needs_review(self):
        """ai_inferred=True flags needs_review."""
        pfmea = dict(PFMEA_P10_001, ai_inferred=True)
        payload = _make_fixture(steps=[P10_STEP], pfmea=[pfmea])
        result = build_risk_structure(payload)
        risk = result["process_nodes"][0]["risk_nodes"][0]
        self.assertTrue(risk["needs_review"])

    def test_empty_controls_flags_needs_review(self):
        """Both prevention_control and detection_control empty flags needs_review."""
        pfmea = dict(
            PFMEA_P10_001,
            needs_confirmation=False,
            ai_inferred=False,
            prevention_control="",
            detection_control="",
        )
        payload = _make_fixture(steps=[P10_STEP], pfmea=[pfmea])
        result = build_risk_structure(payload)
        risk = result["process_nodes"][0]["risk_nodes"][0]
        self.assertTrue(risk["needs_review"])

    def test_has_controls_does_not_flag_needs_review(self):
        """Having at least one control avoids the empty-controls review flag."""
        pfmea = dict(
            PFMEA_P10_001,
            needs_confirmation=False,
            ai_inferred=False,
            prevention_control="Check",
            detection_control="",
        )
        payload = _make_fixture(steps=[P10_STEP], pfmea=[pfmea])
        result = build_risk_structure(payload)
        risk = result["process_nodes"][0]["risk_nodes"][0]
        self.assertFalse(risk["needs_review"])


class OrphanTests(unittest.TestCase):
    """Tests for orphan node classification."""

    def test_orphan_pfmea_in_orphan_risk_nodes(self):
        """PFMEA without matching PFD step goes to orphan_risk_nodes."""
        payload = _make_fixture(
            steps=[P10_STEP],
            pfmea=[PFMEA_P10_001, PFMEA_P20_001],  # P20 not in steps
        )
        result = build_risk_structure(payload)

        # P10 is in process_nodes
        self.assertEqual(len(result["process_nodes"]), 1)
        # PFMEA_P20_001 is orphan
        orphans = result["orphan_risk_nodes"]
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0]["pfmea_id"], "PFMEA-P20-001")
        self.assertEqual(orphans[0]["failure_mode"], "Rivet height below spec")

    def test_orphan_cp_in_orphan_control_nodes(self):
        """CP without matching PFMEA (at all) goes to orphan_control_nodes."""
        orphan_cp = {
            "control_plan_id": "CP-ORPHAN-001",
            "process_step_id": "P10",
            "pfmea_id": "PFMEA-NONEXISTENT",
            "product_process_characteristic": "Orphan char",
            "specification": "N/A",
            "measurement_method": "N/A",
            "sample_frequency": "N/A",
            "reaction_plan": "N/A",
        }
        payload = _make_fixture(
            steps=[P10_STEP],
            pfmea=[PFMEA_P10_001],
            control_plan=[CP_P10_001_1, orphan_cp],
        )
        result = build_risk_structure(payload)

        orphans = result["orphan_control_nodes"]
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0]["control_plan_id"], "CP-ORPHAN-001")

    def test_cp_with_orphan_pfmea_does_not_double_orphan(self):
        """CP belonging to an orphan PFMEA does not also go to orphan_control_nodes."""
        orphan_cp = {
            "control_plan_id": "CP-ORPHAN-001",
            "process_step_id": "P99",
            "pfmea_id": "PFMEA-P99-001",
            "product_process_characteristic": "Orphan char",
            "specification": "N/A",
            "measurement_method": "N/A",
            "sample_frequency": "N/A",
            "reaction_plan": "N/A",
        }
        orphan_pfmea = {
            "pfmea_id": "PFMEA-P99-001",
            "process_step_id": "P99",  # P99 not in steps
            "failure_mode": "Unknown failure",
            "failure_effect": "Unknown effect",
            "failure_cause": "Unknown cause",
            "severity": 1,
            "occurrence": 1,
            "detection": 1,
            "action_priority": "L",
            "prevention_control": "",
            "detection_control": "",
        }
        payload = _make_fixture(
            steps=[P10_STEP],
            pfmea=[PFMEA_P10_001, orphan_pfmea],
            control_plan=[CP_P10_001_1, orphan_cp],
        )
        result = build_risk_structure(payload)

        # orphan PFMEA goes to orphan_risk_nodes
        self.assertEqual(len(result["orphan_risk_nodes"]), 1)
        orphan_risk = result["orphan_risk_nodes"][0]
        self.assertEqual(orphan_risk["pfmea_id"], "PFMEA-P99-001")
        # The CP belongs to this orphan PFMEA, so it should be in the orphan
        # risk node's control_nodes, NOT in orphan_control_nodes
        self.assertEqual(len(orphan_risk["control_nodes"]), 1)
        self.assertEqual(
            orphan_risk["control_nodes"][0]["control_plan_id"],
            "CP-ORPHAN-001",
        )
        # orphan_control_nodes stays empty
        self.assertEqual(result["orphan_control_nodes"], [])


class EmptyInputTests(unittest.TestCase):
    """Tests for empty / missing input resilience."""

    def test_empty_input_does_not_crash(self):
        """Empty three-table input returns a minimal valid structure."""
        result = build_risk_structure({})
        self.assertEqual(result["document_type"], "risk_structure")
        self.assertEqual(result["process_nodes"], [])
        self.assertEqual(result["orphan_risk_nodes"], [])
        self.assertEqual(result["orphan_control_nodes"], [])
        summary = result["summary"]
        self.assertEqual(summary["process_node_count"], 0)
        self.assertEqual(summary["risk_node_count"], 0)
        self.assertEqual(summary["control_node_count"], 0)
        self.assertEqual(summary["open_action_count"], 0)
        self.assertEqual(summary["review_node_count"], 0)

    def test_missing_tables_does_not_crash(self):
        """Missing individual tables does not crash."""
        payload = _make_fixture(steps=[P10_STEP])  # no pfmea, no cp
        result = build_risk_structure(payload)
        self.assertEqual(len(result["process_nodes"]), 1)
        self.assertEqual(result["process_nodes"][0]["risk_nodes"], [])
        self.assertEqual(result["orphan_risk_nodes"], [])
        self.assertEqual(result["orphan_control_nodes"], [])

    def test_deleted_rows_are_skipped(self):
        """Rows marked as deleted are excluded from the structure."""
        deleted_step = dict(P10_STEP, deleted=True)
        active_step = dict(P20_STEP)
        payload = _make_fixture(
            steps=[deleted_step, active_step],
            pfmea=[PFMEA_P10_001, PFMEA_P20_001],
        )
        result = build_risk_structure(payload)
        # Only P20 is active
        self.assertEqual(len(result["process_nodes"]), 1)
        self.assertEqual(result["process_nodes"][0]["process_step_id"], "P20")
        # PFMEA_P10_001 becomes orphan since P10 is deleted
        self.assertEqual(len(result["orphan_risk_nodes"]), 1)
        self.assertEqual(
            result["orphan_risk_nodes"][0]["pfmea_id"], "PFMEA-P10-001"
        )


class LinkageGapsReviewTests(unittest.TestCase):
    """Tests for needs_review triggered by linkage_gaps."""

    def test_linkage_gap_flags_needs_review(self):
        """A linkage_gap targeting a PFMEA row flags needs_review."""
        pfmea = dict(
            PFMEA_P10_001,
            needs_confirmation=False,
            ai_inferred=False,
            prevention_control="Some control",
            detection_control="Some detection",
        )
        payload = _make_fixture(
            steps=[P10_STEP],
            pfmea=[pfmea],
            linkage_gaps=[
                {"pfmea_id": "PFMEA-P10-001", "message": "Missing CP coverage"},
            ],
        )
        result = build_risk_structure(payload)
        risk = result["process_nodes"][0]["risk_nodes"][0]
        self.assertTrue(risk["needs_review"])

    def test_linkage_gap_in_chain_metadata_flags_needs_review(self):
        """Linkage gaps stored inside chain.metadata are detected."""
        pfmea = dict(
            PFMEA_P10_001,
            needs_confirmation=False,
            ai_inferred=False,
            prevention_control="Some control",
            detection_control="Some detection",
        )
        payload = _make_fixture(
            steps=[P10_STEP],
            pfmea=[pfmea],
            chain={
                "metadata": {
                    "linkage_gaps": [
                        {"pfmea_id": "PFMEA-P10-001", "message": "Unlinked"},
                    ],
                },
            },
        )
        result = build_risk_structure(payload)
        risk = result["process_nodes"][0]["risk_nodes"][0]
        self.assertTrue(risk["needs_review"])


if __name__ == "__main__":
    unittest.main()
