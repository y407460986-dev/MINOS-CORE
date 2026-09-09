from __future__ import annotations

import unittest
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from minos_core.automation_review import build_automation_review
from minos_core.change_management import _changed_any
from minos_core.edit_patch import (
    EDIT_PATCH_VERSION,
    EditPatchError,
    apply_edit_patch,
    evaluate_edit_export_gate,
)
from minos_core.knowledge_recommendation import recommend_from_knowledge
from tests.edit_patch.conftest import NS, _three_table_result

ROOT_FIXTURE = "D:/MINOS-CORE/tests/fixtures/apqp_chain"


class EditPatchTests(unittest.TestCase):
    @staticmethod
    def _find_row_by_id(rows, id_field, target_id):
        for row in rows:
            if isinstance(row, dict) and row.get(id_field) == target_id:
                return row
        return None

    def test_update_patch_populates_changed_fields_and_changed_any_detects_relevant_fields(self):
        """Apply an update patch and verify row-level changed_fields is populated."""
        source = _three_table_result()

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "process.engineer",
                "edited_at": "2026-04-27T10:00:00Z",
                "reason": "修改 PFMEA 失效原因和严重度",
                "items": [
                    {
                        "action": "update",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-001",
                        "changes": {
                            "failure_cause": "人工修正后的原因",
                            "severity": 7,
                        },
                    },
                ],
            },
        )

        updated_row = edited["pfmea"]["rows"][0]
        self.assertEqual(updated_row["failure_cause"], "人工修正后的原因")
        self.assertEqual(updated_row["severity"], 7)

        # changed_fields must contain the field names from the update patch
        self.assertIn("failure_cause", updated_row["changed_fields"])
        self.assertIn("severity", updated_row["changed_fields"])
        self.assertEqual(len(updated_row["changed_fields"]), 2)

        # _changed_any returns True when a changed field matches
        self.assertTrue(_changed_any(updated_row, ("failure_cause",)))
        self.assertTrue(_changed_any(updated_row, ("severity",)))
        self.assertTrue(_changed_any(updated_row, ("failure_cause", "severity")))

        # _changed_any returns False when none of the fields were changed
        self.assertFalse(_changed_any(updated_row, ("operation",)))
        self.assertFalse(_changed_any(updated_row, ()))

    def test_process_flow_sequence_updates_reorder_steps_and_chain(self):
        source = _three_table_result()

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "process.engineer",
                "edited_at": "2026-05-10T10:00:00Z",
                "reason": "拖拽调整 PFD 顺序",
                "items": [
                    {
                        "action": "update",
                        "table": "process_flow",
                        "target_id": "P30",
                        "changes": {"sequence": 10},
                    },
                    {
                        "action": "update",
                        "table": "process_flow",
                        "target_id": "P10",
                        "changes": {"sequence": 20},
                    },
                    {
                        "action": "update",
                        "table": "process_flow",
                        "target_id": "P20",
                        "changes": {"sequence": 30},
                    },
                ],
            },
        )

        self.assertEqual(
            [row["process_step_id"] for row in edited["process_flow"]["steps"]],
            ["P30", "P10", "P20"],
        )
        self.assertEqual(
            [row["process_step_id"] for row in edited["chain"]["process_steps"]],
            ["P30", "P10", "P20"],
        )

    def test_add_action_initializes_changed_fields_empty(self):
        """Add action sets changed_fields to empty list on the new row."""
        source = _three_table_result()

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "process.engineer",
                "edited_at": "2026-04-27T10:00:00Z",
                "reason": "新增 PFD 工序",
                "items": [
                    {
                        "action": "add",
                        "table": "process_flow",
                        "row": {
                            "process_step_id": "P50",
                            "sequence": 50,
                            "operation": "Final inspection",
                            "process_function": "Verify label and packaging",
                            "evidence_refs": ["EV-LABEL-001"],
                        },
                    },
                ],
            },
        )

        added_row = edited["process_flow"]["steps"][-1]
        self.assertEqual(added_row["process_step_id"], "P50")
        self.assertEqual(added_row["changed_fields"], [])

    def test_unconfirmed_rows_block_final_until_every_active_row_is_confirmed(self):
        source = _three_table_result()
        before = evaluate_edit_export_gate(source)
        self.assertFalse(before["final_export_allowed"])
        self.assertIn("process_flow:P10", before["unconfirmed_items"])
        self.assertIn("pfmea:PFMEA-P10-001", before["unconfirmed_items"])
        self.assertIn("control_plan:CP-P10-001", before["unconfirmed_items"])

        confirmed = apply_edit_patch(source, _confirm_all_patch(source))
        after = evaluate_edit_export_gate(confirmed)

        self.assertTrue(after["final_export_allowed"])
        self.assertEqual(after["unconfirmed_items"], [])

    def test_ai_batch_confirmation_audit_blocks_ineligible_rows(self):
        base = _three_table_result()
        source = apply_edit_patch(base, _confirm_all_patch(base))
        source["pfmea"]["rows"][0]["action_priority"] = "H"
        source["pfmea"]["rows"][0]["confidence"] = 0.96
        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "automation.review",
                "metadata": {
                    "source": "automation_review",
                    "confirmation_mode": "ai_recommended_batch",
                },
                "items": [
                    {
                        "action": "confirm",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-001",
                    }
                ],
            },
        )

        history = edited["metadata"]["edit_history"][-1]
        gate = evaluate_edit_export_gate(edited)

        self.assertEqual(edited["pfmea"]["rows"][0]["confirmation_mode"], "ai_recommended_batch")
        self.assertEqual(history["metadata"]["source"], "automation_review")
        self.assertEqual(history["metadata"]["confirmation_mode"], "ai_recommended_batch")
        self.assertFalse(gate["final_export_allowed"])
        self.assertIn("pfmea:PFMEA-P10-001:AI批量确认不适用", gate["review_issues"])

    def test_automation_review_builds_core_batch_confirm_candidates(self):
        source = _automation_chain()
        review = build_automation_review(source)

        candidate_targets = {item["target"] for item in review["batch_confirm_candidates"]}
        self.assertIn("process_step:P10", candidate_targets)
        self.assertIn("failure_mode:PFMEA-P10-OK", candidate_targets)
        self.assertNotIn("control_item:CP-P10-OK", candidate_targets)
        self.assertNotIn("process_step:P20", candidate_targets)
        self.assertNotIn("failure_mode:PFMEA-P10-HIGH", candidate_targets)
        self.assertNotIn("failure_mode:PFMEA-P10-LOW", candidate_targets)
        messages = "；".join(item["message"] for item in review["automation_tasks"])
        self.assertIn("特殊特性必须人工确认", messages)
        self.assertIn("高 AP 风险必须人工确认", messages)
        self.assertIn("置信度低于 0.85", messages)

    def test_ai_fix_proposal_source_is_recorded_for_normal_patch_action(self):
        edited = apply_edit_patch(
            _automation_chain(),
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "items": [
                    {
                        "action": "update",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-LOW",
                        "changes": {"confidence": 0.86},
                        "metadata": {"source": "ai_fix_proposal"},
                    }
                ],
            },
        )

        self.assertEqual(edited["metadata"]["edit_history"][0]["source"], "ai_fix_proposal")

    # ── knowledge recommendation edit-loop tests ────────────────────────

    @staticmethod
    def _find_row_by_id(rows, id_field, target_id):
        for row in rows:
            if isinstance(row, dict) and row.get(id_field) == target_id:
                return row
        return None

    def test_apply_with_written_fields_sets_applied(self):
        """apply_recommendation that writes fields sets lifecycle_status=applied."""
        source = _knowledge_test_payload()
        rec = source["metadata"]["knowledge_recommendations"][1]  # KR-TEST-002: classification empty
        self.assertEqual(rec["target_id"], "PFMEA-P30-001")

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "应用并写入字段",
                "items": [
                    {
                        "action": "apply_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        updated_rec = edited["metadata"]["knowledge_recommendations"][1]
        self.assertEqual(updated_rec["status"], "已应用")
        self.assertEqual(updated_rec["lifecycle_status"], "applied")
        self.assertIn("applied_fields", updated_rec)
        self.assertTrue(updated_rec["applied_fields"])

    def test_ignore_without_reason_still_errors(self):
        """ignore_recommendation without reason still raises EditPatchError."""
        source = _knowledge_test_payload()
        rec = source["metadata"]["knowledge_recommendations"][0]

        with self.assertRaises(EditPatchError) as ctx:
            apply_edit_patch(
                source,
                {
                    "edit_patch_version": EDIT_PATCH_VERSION,
                    "edited_by": "qe",
                    "items": [
                        {
                            "action": "ignore_recommendation",
                            "table": "metadata",
                            "target_id": rec["recommendation_id"],
                        }
                    ],
                },
            )
        self.assertIn("ignore_recommendation requires reason", str(ctx.exception))

    def test_edit_history_records_apply_before_after(self):
        """edit_history captures field-level before/after for apply_recommendation."""
        source = _knowledge_test_payload()
        rec = source["metadata"]["knowledge_recommendations"][1]  # targets PFMEA-P30-001

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "记录 before/after",
                "items": [
                    {
                        "action": "apply_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        history_entry = edited["metadata"]["edit_history"][0]
        self.assertEqual(history_entry["action"], "apply_recommendation")
        field_changes = history_entry.get("field_changes", [])
        # classification change: before="" → after="SC-LABEL"
        classification_change = _find_field_change(field_changes, "pfmea.classification")
        self.assertIsNotNone(classification_change)
        self.assertEqual(classification_change["before"], "")
        self.assertEqual(classification_change["after"], "SC-LABEL")
        # inspection_tool change (linked CP): before="" → after="视觉检测仪"
        tool_change = _find_field_change(field_changes, "control_plan.inspection_tool")
        self.assertIsNotNone(tool_change)
        self.assertEqual(tool_change["before"], "")
        self.assertEqual(tool_change["after"], "视觉检测仪")
        # detection_control must NOT appear (it was non-empty and preserved)
        detection_change = _find_field_change(field_changes, "pfmea.detection_control")
        self.assertIsNone(detection_change)

    def test_score_field_with_positive_value_not_overwritten(self):
        """FMEA score fields with positive values are NOT overwritten by recommendation."""
        source = _knowledge_test_payload()
        # PFMEA-P10-001 already has severity=8 (positive)
        rec = {
            "recommendation_id": "KR-SCORE-POSITIVE:PFMEA-P10-001",
            "target_table": "pfmea",
            "target_id": "PFMEA-P10-001",
            "recommendation_type": "rating_hint",
            "source": "KR-SCORE-POSITIVE",
            "reason": "建议评分",
            "confidence": 0.9,
            "suggested_fields": {"severity": 5, "occurrence": 3, "detection": 2},
            "linked_control_plan_suggestion": None,
            "ai_inferred": False,
            "needs_confirmation": True,
            "status": "待确认",
            "ignore_reason": "",
            "process_step_id": "P10",
        }
        source.setdefault("metadata", {}).setdefault("knowledge_recommendations", []).append(rec)

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "采纳评分推荐（正值不应被覆盖）",
                "items": [
                    {
                        "action": "accept_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        pfmea_row = self._find_row_by_id(edited["pfmea"]["rows"], "pfmea_id", "PFMEA-P10-001")
        # Existing positive values must be preserved.
        self.assertEqual(pfmea_row["severity"], 8)
        self.assertEqual(pfmea_row["occurrence"], 3)



def _confirm_all_patch(source: dict) -> dict:
    items = []
    for row in source["process_flow"]["steps"]:
        items.append(
            {
                "action": "confirm",
                "table": "process_flow",
                "target_id": row["process_step_id"],
            }
        )
    for row in source["pfmea"]["rows"]:
        items.append(
            {
                "action": "update",
                "table": "pfmea",
                "target_id": row["pfmea_id"],
                "changes": {
                    "recommended_action": row.get("recommended_action")
                    or "工程确认措施有效性",
                    "responsibility": row.get("responsibility") or "质量工程师",
                    "target_date": row.get("target_date") or "2026-12-31",
                    "action_status": "已完成",
                    "after_severity": row.get("severity", 1) or 1,
                    "after_occurrence": 2,
                    "after_detection": 3,
                    "after_ap": "M" if (row.get("severity", 1) or 1) >= 7 else "L",
                },
            }
        )
        items.append(
            {
                "action": "confirm",
                "table": "pfmea",
                "target_id": row["pfmea_id"],
            }
        )
    for row in source["control_plan"]["rows"]:
        items.append(
            {
                "action": "confirm",
                "table": "control_plan",
                "target_id": row["control_plan_id"],
            }
        )
    generated_recs = recommend_from_knowledge(source)
    # Store recommendations in metadata so edit_patch can find them.
    source.setdefault("metadata", {}).setdefault("knowledge_recommendations", []).extend(generated_recs)
    for recommendation in generated_recs:
        items.append(
            {
                "action": "ignore_recommendation",
                "table": "metadata",
                "target_id": recommendation["recommendation_id"],
                "reason": "单元测试中确认该知识库推荐暂不采纳",
            }
        )
    return {
        "edit_patch_version": EDIT_PATCH_VERSION,
        "edited_by": "quality.engineer",
        "edited_at": "2026-04-26T13:30:00Z",
        "reason": "逐行人工确认",
        "items": items,
    }


def _automation_chain() -> dict:
    return {
        "document_type": "apqp_chain",
        "schema_version": "minos-core.generated.v1",
        "product": {},
        "process_steps": [
            {
                "process_step_id": "P10",
                "sequence": 10,
                "operation": "检验",
                "process_function": "确认尺寸",
                "evidence_refs": ["EV-1"],
                "confidence": 0.93,
                "needs_confirmation": True,
            },
            {
                "process_step_id": "P20",
                "sequence": 20,
                "operation": "关键检验",
                "process_function": "确认特殊特性",
                "special_characteristics": ["SC-1"],
                "evidence_refs": ["EV-1"],
                "confidence": 0.95,
                "needs_confirmation": True,
            },
        ],
        "failure_modes": [
            {
                "pfmea_id": "PFMEA-P10-OK",
                "process_step_id": "P10",
                "process_function": "确认尺寸",
                "failure_mode": "漏检",
                "failure_effect": "不合格流出",
                "severity": 6,
                "failure_cause": "检具失准",
                "occurrence": 2,
                "prevention_control": "检具校准",
                "detection_control": "首件检验",
                "rpn": 36,
                "detection": 3,
                "action_priority": "L",
                "recommended_action": "无需新增措施",
                "action_status": "已完成",
                "after_severity": 6,
                "after_occurrence": 2,
                "after_detection": 3,
                "after_ap": "L",
                "evidence_refs": ["EV-1"],
                "confidence": 0.91,
                "needs_confirmation": True,
            },
            {
                "pfmea_id": "PFMEA-P10-LOW",
                "process_step_id": "P10",
                "process_function": "确认尺寸",
                "failure_mode": "错判",
                "failure_effect": "返工",
                "severity": 5,
                "failure_cause": "标准不清",
                "occurrence": 2,
                "prevention_control": "作业指导书",
                "detection_control": "复核",
                "rpn": 30,
                "detection": 3,
                "action_priority": "L",
                "recommended_action": "补充确认",
                "action_status": "已完成",
                "after_severity": 5,
                "after_occurrence": 2,
                "after_detection": 3,
                "after_ap": "L",
                "evidence_refs": ["EV-1"],
                "confidence": 0.7,
                "needs_confirmation": True,
            },
            {
                "pfmea_id": "PFMEA-P10-HIGH",
                "process_step_id": "P10",
                "process_function": "确认尺寸",
                "failure_mode": "高风险失效",
                "failure_effect": "客户停线",
                "severity": 9,
                "failure_cause": "过程失控",
                "occurrence": 4,
                "prevention_control": "防错",
                "detection_control": "全检",
                "rpn": 108,
                "detection": 3,
                "action_priority": "H",
                "recommended_action": "停机隔离",
                "action_status": "已完成",
                "after_severity": 9,
                "after_occurrence": 2,
                "after_detection": 3,
                "after_ap": "M",
                "evidence_refs": ["EV-1"],
                "confidence": 0.96,
                "needs_confirmation": True,
            },
        ],
        "controls": [
            {
                "control_plan_id": "CP-P10-OK",
                "process_step_id": "P10",
                "pfmea_id": "PFMEA-P10-OK",
                "product_process_characteristic": "尺寸",
                "specification": "按图纸",
                "measurement_method": "卡尺",
                "sample_size": "1 件",
                "sample_frequency": "每批",
                "control_method": "首件检验",
                "reaction_plan": "隔离并通知质量",
                "evidence_refs": ["EV-1"],
                "confidence": 0.9,
                "needs_confirmation": True,
            }
        ],
        "evidence": [{"evidence_id": "EV-1", "source": "fixture", "content": "确认记录"}],
        "links": [],
        "pending_fields": [],
        "ai_inferred_items": [],
        "metadata": {"strict_aiag_vda_pfmea_gate": True},
    }


def _knowledge_test_payload() -> dict:
    """Build a three_table_result with knowledge_recommendations for testing the edit loop."""
    source = _three_table_result()
    recs = [
        {
            "recommendation_id": "KR-TEST-001:PFMEA-P10-001",
            "target_table": "pfmea",
            "target_id": "PFMEA-P10-001",
            "recommendation_type": "detection_control",
            "source": "KR-TEST-001",
            "reason": "建议补充探测控制",
            "confidence": 0.85,
            "suggested_fields": {
                "detection_control": "视觉检测补充",
                "classification": "SC-TEST-NEW",
            },
            "linked_control_plan_suggestion": {
                "measurement_method": "视觉检测设备",
                "sample_frequency": "每批次首件",
            },
            "ai_inferred": False,
            "needs_confirmation": True,
            "status": "待确认",
            "ignore_reason": "",
            "process_step_id": "P10",
        },
        {
            "recommendation_id": "KR-TEST-002:PFMEA-P30-001",
            "target_table": "pfmea",
            "target_id": "PFMEA-P30-001",
            "recommendation_type": "failure_cause",
            "source": "KR-TEST-002",
            "reason": "建议补充失效原因细节",
            "confidence": 0.75,
            "suggested_fields": {
                "classification": "SC-LABEL",
                "detection_control": "新增探测控制",
            },
            "linked_control_plan_suggestion": {
                "control_method": "NEW CONTROL METHOD",
                "inspection_tool": "视觉检测仪",
            },
            "ai_inferred": False,
            "needs_confirmation": True,
            "status": "待确认",
            "ignore_reason": "",
            "process_step_id": "P30",
        },
    ]
    source.setdefault("metadata", {})["knowledge_recommendations"] = recs
    return source


def _find_field_change(field_changes: list, field: str) -> dict | None:
    """Find a field change entry by field name, or None."""
    for fc in field_changes:
        if isinstance(fc, dict) and fc.get("field") == field:
            return fc
    return None


def _workbook_text(path: str | Path) -> str:
    with ZipFile(path) as archive:
        return "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xml")
        )


def _sheet_names(path: str | Path) -> list[str]:
    with ZipFile(path) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    return [node.attrib["name"] for node in workbook.findall(".//main:sheet", NS)]


def _sheet_text(path: str | Path, sheet_name: str) -> str:
    with ZipFile(path) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.findall(".//main:sheet", NS)
        for index, node in enumerate(sheets, start=1):
            if node.attrib["name"] == sheet_name:
                return archive.read(f"xl/worksheets/sheet{index}.xml").decode("utf-8")
    raise AssertionError(f"sheet not found: {sheet_name}")


if __name__ == "__main__":
    unittest.main()
