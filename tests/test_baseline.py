"""Tests for baseline snapshot creation and hashing."""

from __future__ import annotations

import unittest

from minos_core.baseline import baseline_hash, create_baseline


class BaselineCreationTests(unittest.TestCase):
    """Unit tests for create_baseline and baseline_hash."""

    @staticmethod
    def _minimal_result() -> dict:
        """Minimal three_table_generation_result fixture."""
        return {
            "document_type": "three_table_generation_result",
            "schema_version": "minos-core.three_table_generation_result.v1",
            "status": "draft_ready",
            "process_flow": {
                "steps": [
                    {
                        "process_step_id": "P10",
                        "sequence": 10,
                        "operation": "IQC inspection",
                        "review_status": "已确认",
                    }
                ]
            },
            "pfmea": {
                "rows": [
                    {
                        "pfmea_id": "PFMEA-P10-001",
                        "process_step_id": "P10",
                        "failure_mode": "Wrong thickness accepted",
                        "action_priority": "H",
                        "review_status": "已确认",
                    }
                ]
            },
            "control_plan": {
                "rows": [
                    {
                        "control_plan_id": "CP-P10-001",
                        "process_step_id": "P10",
                        "pfmea_id": "PFMEA-P10-001",
                        "product_process_characteristic": "Thickness",
                        "review_status": "已确认",
                    }
                ]
            },
            "metadata": {
                "action_items": [
                    {
                        "action_id": "ACT-001",
                        "pfmea_id": "PFMEA-P10-001",
                        "priority": "high",
                        "status": "open",
                    }
                ],
                "action_items_summary": {"unresolved": 1},
                "knowledge_recommendations": [
                    {"id": "REC-001", "status": "unresolved"}
                ],
            },
            "linkage_report": {
                "sync_issues": [
                    {"severity": "blocker", "message": "CP 行 CP-P10-001 缺少 PFD 链接"},
                ],
            },
        }

    # ------------------------------------------------------------------
    # test_create_baseline_from_result
    # ------------------------------------------------------------------

    def test_create_baseline_from_result(self):
        result = self._minimal_result()
        baseline = create_baseline(result, label="初版基线", created_at="2026-04-28T10:00:00")

        self.assertTrue(baseline["baseline_id"].startswith("BL-"))
        self.assertEqual(baseline["label"], "初版基线")
        self.assertEqual(baseline["created_at"], "2026-04-28T10:00:00")
        self.assertTrue(len(baseline["content_hash"]) == 64)  # SHA-256 hex
        self.assertIn("pfd", baseline["tables"])
        self.assertIn("pfmea", baseline["tables"])
        self.assertIn("control_plan", baseline["tables"])
        # tables contain rows
        self.assertEqual(len(baseline["tables"]["pfd"]), 1)
        self.assertEqual(len(baseline["tables"]["pfmea"]), 1)
        self.assertEqual(len(baseline["tables"]["control_plan"]), 1)
        # metadata preserved
        self.assertIsInstance(baseline["metadata"], dict)
        # readiness counters
        self.assertEqual(baseline["readiness"]["sync_blocker_count"], 1)
        self.assertEqual(baseline["readiness"]["open_action_count"], 1)
        self.assertEqual(baseline["readiness"]["unresolved_recommendation_count"], 1)

    # ------------------------------------------------------------------
    # test_create_baseline_from_chain_result
    # ------------------------------------------------------------------

    def test_create_baseline_from_chain_result(self):
        """Baseline can also be created from a result with chain-style rows."""
        result = {
            "document_type": "three_table_generation_result",
            "chain": {
                "process_steps": [
                    {"process_step_id": "P20", "operation": "Welding"},
                ],
                "failure_modes": [
                    {"pfmea_id": "PFMEA-P20-001", "failure_mode": "Weld crack"},
                ],
                "controls": [
                    {"control_plan_id": "CP-P20-001", "control_method": "Visual check"},
                ],
            },
            "metadata": {},
        }
        baseline = create_baseline(result, label="chain基线")
        self.assertEqual(len(baseline["tables"]["pfd"]), 1)
        self.assertEqual(len(baseline["tables"]["pfmea"]), 1)
        self.assertEqual(len(baseline["tables"]["control_plan"]), 1)

    # ------------------------------------------------------------------
    # test_baseline_hash_stable
    # ------------------------------------------------------------------

    def test_baseline_hash_stable(self):
        result = self._minimal_result()
        b1 = create_baseline(result, label="A")
        b2 = create_baseline(result, label="B")
        # Same tables content -> same hash
        self.assertEqual(baseline_hash(b1), baseline_hash(b2))
        # content_hash on baseline dict itself
        self.assertEqual(b1["content_hash"], baseline_hash(b1))

    # ------------------------------------------------------------------
    # test_baseline_hash_changes
    # ------------------------------------------------------------------

    def test_baseline_hash_changes(self):
        result = self._minimal_result()
        b1 = create_baseline(result, label="A")

        # mutate a row
        result["pfmea"]["rows"][0]["failure_mode"] = "Wrong color"
        b2 = create_baseline(result, label="A-modified")

        self.assertNotEqual(baseline_hash(b1), baseline_hash(b2))
