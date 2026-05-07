"""Tests for CP field modification impact analysis in change_management."""

from __future__ import annotations

import unittest

from minos_core.change_management import analyze_change_impacts


class ChangeManagementTests(unittest.TestCase):
    """Unit tests for analyze_change_impacts CP modification/addition checks."""

    @staticmethod
    def _base_payload() -> dict:
        """Minimal three-table payload: one step, one PFMEA row, one CP row."""
        return {
            "process_flow": {
                "steps": [
                    {
                        "process_step_id": "P10",
                        "sequence": 10,
                        "operation": "IQC inspection",
                        "process_function": "Verify material thickness",
                    }
                ]
            },
            "pfmea": {
                "rows": [
                    {
                        "pfmea_id": "PFMEA-P10-001",
                        "process_step_id": "P10",
                        "process_function": "Verify material thickness",
                        "failure_mode": "Wrong thickness accepted",
                        "failure_effect": "Assembly out of spec",
                        "severity": 8,
                        "failure_cause": "Supplier lot mixed",
                        "occurrence": 3,
                        "prevention_control": "Supplier CoC check",
                        "detection_control": "Incoming thickness measurement",
                        "detection": 4,
                        "action_priority": "M",
                        "classification": "SC-THICKNESS",
                    }
                ]
            },
            "control_plan": {
                "rows": [
                    {
                        "control_plan_id": "CP-P10-001",
                        "process_step_id": "P10",
                        "pfmea_id": "PFMEA-P10-001",
                        "product_process_characteristic": "Material thickness",
                        "specification": "2.00 +/- 0.10 mm",
                        "classification": "SC-THICKNESS",
                        "measurement_method": "Digital thickness gauge",
                        "sample_size": "5 pieces",
                        "sample_frequency": "Each incoming lot",
                        "control_method": "Record lot result and quarantine",
                        "reaction_plan": "Stop use, notify SQE",
                    }
                ]
            },
        }

    # --- CP addition ---

    def test_cp_addition_generates_impact(self):
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["review_status"] = "人工新增"

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        self.assertTrue(cp_impacts)
        messages = {i["message"] for i in cp_impacts}
        self.assertIn("PFMEA 需确认控制覆盖", messages)

    # --- CP modification (measurement / control fields) ---

    def test_cp_modification_measurement_method_generates_impact(self):
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["review_status"] = "人工修改"
        payload["control_plan"]["rows"][0]["changed_fields"] = ["measurement_method"]

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        messages = {i["message"] for i in cp_impacts}
        self.assertIn("测量/控制方法变更需质量确认", messages)

    def test_cp_modification_sample_size_generates_impact(self):
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["review_status"] = "人工修改"
        payload["control_plan"]["rows"][0]["changed_fields"] = ["sample_size"]

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        messages = {i["message"] for i in cp_impacts}
        self.assertIn("测量/控制方法变更需质量确认", messages)

    def test_cp_modification_sample_frequency_generates_impact(self):
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["review_status"] = "人工修改"
        payload["control_plan"]["rows"][0]["changed_fields"] = ["sample_frequency"]

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        messages = {i["message"] for i in cp_impacts}
        self.assertIn("测量/控制方法变更需质量确认", messages)

    def test_cp_modification_control_method_generates_impact(self):
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["review_status"] = "人工修改"
        payload["control_plan"]["rows"][0]["changed_fields"] = ["control_method"]

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        messages = {i["message"] for i in cp_impacts}
        self.assertIn("测量/控制方法变更需质量确认", messages)

    def test_cp_modification_without_review_status_no_impact(self):
        """changed_fields exists but review_status is not 人工修改 -> no modification impact."""
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["changed_fields"] = ["measurement_method"]

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        messages = {i["message"] for i in cp_impacts}
        self.assertNotIn("测量/控制方法变更需质量确认", messages)

    def test_cp_no_changes_no_impact(self):
        """No changed_fields and no review_status -> no CP impact at all."""
        payload = self._base_payload()

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        self.assertEqual(len(cp_impacts), 0)

    # --- CP characteristic / specification change -> PFMEA sync ---

    def test_cp_classification_change_generates_pfmea_sync_impact(self):
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["changed_fields"] = ["classification"]

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        messages = {i["message"] for i in cp_impacts}
        self.assertIn("PFMEA 特性分类需同步确认", messages)

    def test_cp_product_process_characteristic_change_generates_pfmea_sync_impact(self):
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["changed_fields"] = [
            "product_process_characteristic"
        ]

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        messages = {i["message"] for i in cp_impacts}
        self.assertIn("PFMEA 特性分类需同步确认", messages)

    def test_cp_specification_change_generates_both_impacts(self):
        """specification appears in both the modification tuple and the characteristic tuple."""
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["review_status"] = "人工修改"
        payload["control_plan"]["rows"][0]["changed_fields"] = ["specification"]

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        messages = {i["message"] for i in cp_impacts}
        self.assertIn("测量/控制方法变更需质量确认", messages)
        self.assertIn("PFMEA 特性分类需同步确认", messages)

    # --- CP deletion: keep existing behaviour and guard against double-fire ---

    def test_cp_deletion_generates_impact(self):
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["deleted"] = True

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        self.assertTrue(cp_impacts)
        messages = {i["message"] for i in cp_impacts}
        self.assertIn("检查是否留下未控制高风险", messages)

    def test_cp_deletion_skips_modification_impacts(self):
        """Deleted CP row must only produce a deletion impact, not modification ones."""
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["deleted"] = True
        payload["control_plan"]["rows"][0]["review_status"] = "人工修改"
        payload["control_plan"]["rows"][0]["changed_fields"] = [
            "measurement_method",
            "classification",
        ]

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        self.assertEqual(len(cp_impacts), 1)
        self.assertIn("检查是否留下未控制高风险", cp_impacts[0]["message"])

    # --- Impact item structure matches _impact() contract ---

    def test_impact_structure_follows_impact_helper_contract(self):
        payload = self._base_payload()
        payload["control_plan"]["rows"][0]["review_status"] = "人工新增"

        impacts = analyze_change_impacts(payload)

        cp_impacts = [i for i in impacts if "control_plan:CP-P10-001" in i["target"]]
        self.assertEqual(len(cp_impacts), 1)
        impact = cp_impacts[0]
        self.assertEqual(impact["category"], "变更影响")
        self.assertEqual(impact["target"], "control_plan:CP-P10-001")
        self.assertEqual(impact["message"], "PFMEA 需确认控制覆盖")
        self.assertEqual(impact["status"], "待人工确认")
        self.assertEqual(impact["ignore_reason"], "")
        self.assertEqual(impact["severity"], "blocker")


if __name__ == "__main__":
    unittest.main()
