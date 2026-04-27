from __future__ import annotations

import copy
import unittest

from minos_core.automation_review import build_automation_review, build_batch_confirm_patch
from minos_core.edit_patch import EDIT_PATCH_VERSION, apply_edit_patch, evaluate_edit_export_gate
from minos_desktop.table_editor import (
    AUTOMATION_BATCH_CONFIRM_MODE,
    AUTOMATION_REVIEW_SOURCE,
    automation_fix_suggestion_patch,
)


def _minimal_three_table() -> dict:
    return {
        "document_type": "three_table_generation_result",
        "schema_version": "minos-core.three_table_generation_result.v1",
        "status": "needs_review",
        "drawing_analysis": {
            "evidence": [
                {"evidence_id": "EV-OK", "source": "fixture", "content": "低风险尺寸确认"},
                {"evidence_id": "EV-HIGH", "source": "fixture", "content": "高 AP 风险证据"},
                {"evidence_id": "EV-SC", "source": "fixture", "content": "特殊特性证据"},
                {"evidence_id": "EV-LOWCONF", "source": "fixture", "content": "低置信证据"},
            ]
        },
        "process_flow": {
            "steps": [
                {
                    "process_step_id": "P10",
                    "sequence": 10,
                    "operation": "尺寸检验",
                    "process_function": "确认尺寸",
                    "evidence_refs": ["EV-OK"],
                    "needs_confirmation": True,
                    "ai_inferred": True,
                    "confidence": 0.93,
                },
                {
                    "process_step_id": "P20",
                    "sequence": 20,
                    "operation": "关键尺寸检验",
                    "process_function": "确认关键尺寸",
                    "special_characteristics": ["SC-1"],
                    "evidence_refs": ["EV-SC"],
                    "needs_confirmation": True,
                    "ai_inferred": True,
                    "confidence": 0.94,
                },
            ]
        },
        "pfmea": {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-OK",
                    "process_step_id": "P10",
                    "failure_mode": "漏检",
                    "failure_effect": "不合格流出",
                    "severity": 5,
                    "failure_cause": "检具未校准",
                    "occurrence": 2,
                    "prevention_control": "校准计划",
                    "detection_control": "首件确认",
                    "detection": 3,
                    "action_priority": "L",
                    "evidence_refs": ["EV-OK"],
                    "needs_confirmation": True,
                    "ai_inferred": True,
                    "confidence": 0.92,
                },
                {
                    "pfmea_id": "PFMEA-P10-HIGH",
                    "process_step_id": "P10",
                    "failure_mode": "高风险漏检",
                    "failure_effect": "客户停线",
                    "severity": 9,
                    "failure_cause": "参数漂移",
                    "occurrence": 5,
                    "prevention_control": "参数点检",
                    "detection_control": "终检",
                    "detection": 5,
                    "action_priority": "H",
                    "evidence_refs": ["EV-HIGH"],
                    "needs_confirmation": True,
                    "ai_inferred": True,
                    "confidence": 0.95,
                },
                {
                    "pfmea_id": "PFMEA-P20-SC",
                    "process_step_id": "P20",
                    "failure_mode": "特殊特性超差",
                    "failure_effect": "装配失效",
                    "severity": 8,
                    "failure_cause": "夹具磨损",
                    "occurrence": 3,
                    "prevention_control": "夹具寿命管理",
                    "detection_control": "SPC",
                    "detection": 3,
                    "action_priority": "M",
                    "classification": "特殊特性",
                    "evidence_refs": ["EV-SC"],
                    "needs_confirmation": True,
                    "ai_inferred": True,
                    "confidence": 0.95,
                },
                {
                    "pfmea_id": "PFMEA-P10-LOWCONF",
                    "process_step_id": "P10",
                    "failure_mode": "低置信识别",
                    "failure_effect": "返工",
                    "severity": 4,
                    "failure_cause": "光照影响",
                    "occurrence": 2,
                    "prevention_control": "照明点检",
                    "detection_control": "复核",
                    "detection": 4,
                    "action_priority": "L",
                    "evidence_refs": ["EV-LOWCONF"],
                    "needs_confirmation": True,
                    "ai_inferred": True,
                    "confidence": 0.72,
                },
                {
                    "pfmea_id": "PFMEA-P10-NOEVID",
                    "process_step_id": "P10",
                    "failure_mode": "缺少证据",
                    "failure_effect": "返工",
                    "severity": 4,
                    "failure_cause": "记录缺失",
                    "occurrence": 2,
                    "prevention_control": "记录检查",
                    "detection_control": "复核",
                    "detection": 4,
                    "action_priority": "L",
                    "evidence_refs": [],
                    "needs_confirmation": True,
                    "ai_inferred": True,
                    "confidence": 0.93,
                },
                {
                    "pfmea_id": "PFMEA-P99-BROKEN",
                    "process_step_id": "P99",
                    "failure_mode": "断链行",
                    "failure_effect": "下游无法追溯",
                    "severity": 4,
                    "failure_cause": "工序不存在",
                    "occurrence": 2,
                    "prevention_control": "链路检查",
                    "detection_control": "复核",
                    "detection": 4,
                    "action_priority": "L",
                    "evidence_refs": ["EV-OK"],
                    "needs_confirmation": True,
                    "ai_inferred": True,
                    "confidence": 0.93,
                },
            ]
        },
        "control_plan": {"rows": []},
        "metadata": {"knowledge_recommendations": [], "change_impacts": []},
        "manual_review": {"required": False, "items": []},
        "quality_gate": {},
        "quality_gates": {},
        "exports": {},
        "manifest": {},
    }


class AutomationReviewTests(unittest.TestCase):
    def test_only_low_risk_high_confidence_rows_with_evidence_enter_batch_candidates(self):
        review = build_automation_review(_minimal_three_table())
        candidates = {item["target"] for item in review["batch_confirm_candidates"]}
        tasks = {
            item["target"]: item["message"]
            for item in review["automation_tasks"]
            if item.get("target")
        }

        self.assertIn("failure_mode:PFMEA-P10-OK", candidates)
        self.assertNotIn("failure_mode:PFMEA-P10-HIGH", candidates)
        self.assertNotIn("failure_mode:PFMEA-P20-SC", candidates)
        self.assertNotIn("failure_mode:PFMEA-P10-LOWCONF", candidates)
        self.assertNotIn("failure_mode:PFMEA-P10-NOEVID", candidates)
        self.assertNotIn("failure_mode:PFMEA-P99-BROKEN", candidates)
        self.assertIn("高 AP 风险必须人工确认", tasks["failure_mode:PFMEA-P10-HIGH"])
        self.assertIn("特殊特性必须人工确认", tasks["failure_mode:PFMEA-P20-SC"])
        self.assertIn("置信度低于 0.85", tasks["failure_mode:PFMEA-P10-LOWCONF"])
        self.assertIn("缺少 evidence_refs", tasks["failure_mode:PFMEA-P10-NOEVID"])
        self.assertIn("上下游链路不完整", tasks["failure_mode:PFMEA-P99-BROKEN"])

    def test_batch_confirm_patch_is_per_row_and_keeps_ai_batch_audit_metadata(self):
        source = _minimal_three_table()
        review = build_automation_review(source)
        patch = build_batch_confirm_patch(review["batch_confirm_candidates"])
        target_ids = {item["target_id"] for item in patch["items"]}

        self.assertEqual(patch["edit_patch_version"], EDIT_PATCH_VERSION)
        self.assertIn("PFMEA-P10-OK", target_ids)
        self.assertNotIn("PFMEA-P10-HIGH", target_ids)
        self.assertTrue(all(item["action"] == "confirm" for item in patch["items"]))
        for item in patch["items"]:
            self.assertEqual(item.get("metadata", {}).get("confirmation_mode"), AUTOMATION_BATCH_CONFIRM_MODE)
            self.assertEqual(item.get("metadata", {}).get("source"), AUTOMATION_REVIEW_SOURCE)

        edited = apply_edit_patch(copy.deepcopy(source), patch)
        confirmed = next(row for row in edited["pfmea"]["rows"] if row["pfmea_id"] == "PFMEA-P10-OK")
        self.assertFalse(confirmed["needs_confirmation"])
        self.assertEqual(confirmed.get("confirmation_mode"), AUTOMATION_BATCH_CONFIRM_MODE)
        self.assertEqual(edited["metadata"]["edit_history"][0]["metadata"]["confirmation_mode"], AUTOMATION_BATCH_CONFIRM_MODE)

    def test_adopting_ai_fix_suggestion_generates_patch_without_overwriting_original_draft(self):
        source = _minimal_three_table()
        row = {
            "target_table": "pfmea",
            "target_id": "PFMEA-P10-LOWCONF",
            "suggested_changes": {"prevention_control": "增加每日点检记录"},
        }

        patch = automation_fix_suggestion_patch(row)
        edited = apply_edit_patch(copy.deepcopy(source), patch)
        original = next(row for row in source["pfmea"]["rows"] if row["pfmea_id"] == "PFMEA-P10-LOWCONF")
        updated = next(row for row in edited["pfmea"]["rows"] if row["pfmea_id"] == "PFMEA-P10-LOWCONF")

        self.assertEqual(patch["items"][0]["action"], "update")
        self.assertEqual(patch["items"][0]["source"], AUTOMATION_REVIEW_SOURCE)
        self.assertEqual(original["prevention_control"], "照明点检")
        self.assertEqual(updated["prevention_control"], "增加每日点检记录")

    def test_final_export_gate_blocks_bad_ai_batch_confirmation_until_resolved(self):
        source = _minimal_three_table()
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [
                {
                    "action": "confirm",
                    "table": "pfmea",
                    "target_id": "PFMEA-P10-HIGH",
                    "metadata": {"confirmation_mode": AUTOMATION_BATCH_CONFIRM_MODE},
                }
            ],
        }
        edited = apply_edit_patch(source, patch)
        gate = evaluate_edit_export_gate(edited)

        self.assertFalse(gate["final_export_allowed"])
        self.assertIn("pfmea:PFMEA-P10-HIGH:AI批量确认不适用", gate["review_issues"])


if __name__ == "__main__":
    unittest.main()
