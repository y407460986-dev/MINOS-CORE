from __future__ import annotations

import unittest

from minos_core.closure_tasks import apply_closure_action, build_closure_tasks


class ClosureTaskTests(unittest.TestCase):
    def test_build_closure_tasks_covers_v114_task_types(self) -> None:
        tasks = build_closure_tasks(_result())
        task_types = {task["task_type"] for task in tasks}

        self.assertTrue(
            {
                "drawing_review",
                "evidence_confirmation",
                "family_confirmation",
                "process_flow_confirmation",
                "knowledge_recommendation",
                "linkage_gap",
                "change_impact",
                "action_item",
                "automation_review",
            }.issubset(task_types)
        )
        for task in tasks:
            self.assertEqual(
                set(task),
                {
                    "task_id",
                    "task_type",
                    "target_table",
                    "target_row_id",
                    "severity",
                    "message",
                    "evidence",
                    "recommended_action",
                    "status",
                    "owner",
                    "due_date",
                    "resolution_note",
                },
            )

    def test_apply_closure_action_returns_existing_edit_patch_actions(self) -> None:
        result = _result()
        process_task = next(
            task
            for task in build_closure_tasks(result)
            if task["task_type"] == "process_flow_confirmation"
        )
        patch = apply_closure_action(result, process_task["task_id"], {"action": "resolve"})

        self.assertEqual(patch["edit_patch_version"], "minos-core.edit_patch.v1")
        self.assertEqual(patch["items"][0]["action"], "confirm")
        self.assertEqual(patch["items"][0]["table"], "process_flow")
        self.assertEqual(patch["items"][0]["target_id"], "P10")

    def test_apply_drawing_review_resolves_synthetic_review_issue(self) -> None:
        result = _result()
        drawing_task = next(
            task
            for task in build_closure_tasks(result)
            if task["task_type"] == "drawing_review"
        )
        patch = apply_closure_action(
            result,
            drawing_task["task_id"],
            {"action": "resolve", "reason": "图纸已复核"},
        )

        self.assertEqual(patch["items"][0]["action"], "resolve_review_issue")
        self.assertEqual(patch["items"][0]["target_id"], drawing_task["task_id"])

    def test_apply_evidence_confirmation_records_review_target(self) -> None:
        result = _result()
        evidence_task = next(
            task
            for task in build_closure_tasks(result)
            if task["task_type"] == "evidence_confirmation"
        )
        patch = apply_closure_action(
            result,
            evidence_task["task_id"],
            {"action": "resolve", "reason": "OCR 证据已复核"},
        )

        self.assertEqual(patch["items"][0]["action"], "confirm_review_target")
        self.assertEqual(patch["items"][0]["table"], "metadata")
        self.assertEqual(patch["items"][0]["target_id"], "evidence:EV-1")


def _result() -> dict:
    return {
        "document_type": "three_table_generation_result",
        "drawing_analysis": {
            "materials": [
                {
                    "item_id": "MAT-1",
                    "material": "SPCC",
                    "confidence": 0.6,
                    "needs_confirmation": True,
                    "evidence_refs": ["EV-1"],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "EV-1",
                    "content": "material callout",
                    "needs_confirmation": True,
                }
            ],
        },
        "process_flow": {
            "metadata": {
                "family_context": {
                    "family_key": "stamping",
                    "family_name": "冲压件",
                    "needs_confirmation": True,
                    "knowledge_source_refs": ["part_family:stamping:v1"],
                }
            },
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "冲孔",
                    "needs_confirmation": True,
                    "evidence_refs": ["EV-1"],
                }
            ],
        },
        "pfmea": {"rows": []},
        "control_plan": {"rows": []},
        "metadata": {
            "knowledge_recommendations": [
                {
                    "recommendation_id": "KR-1:PFMEA-P10-001",
                    "target_table": "pfmea",
                    "target_id": "PFMEA-P10-001",
                    "reason": "建议补充控制",
                    "status": "待确认",
                    "lifecycle_status": "proposed",
                }
            ],
            "change_impacts": [
                {
                    "item_id": "CI-1",
                    "target": "pfmea:PFMEA-P10-001",
                    "message": "PFD 修改后需同步 PFMEA",
                    "status": "待同步",
                }
            ],
            "action_items": [
                {
                    "action_id": "ACT-PFMEA-P10-001-001",
                    "description": "补充高风险措施并完成有效性验证",
                    "status": "open",
                    "priority": "high",
                    "owner": "QE",
                    "due_date": "2026-05-01",
                }
            ],
        },
        "linkage_gaps": [
            {
                "gap_id": "GAP-1",
                "target": "pfmea:PFMEA-P10-001",
                "severity": "blocker",
                "message": "PFD 工序缺少 PFMEA 覆盖",
            }
        ],
        "automation_review": {
            "automation_tasks": [
                {
                    "task_id": "AR-process_flow-P10",
                    "table": "process_flow",
                    "target_id": "P10",
                    "message": "置信度低于阈值",
                    "can_batch_confirm": False,
                }
            ]
        },
        "manual_review": {"required": True, "items": []},
    }


if __name__ == "__main__":
    unittest.main()
