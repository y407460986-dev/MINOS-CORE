from __future__ import annotations

import unittest
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

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

    def test_apply_recommendation_writes_empty_fields(self):
        """apply_recommendation writes suggested_fields to empty fields on the PFMEA row."""
        source = _knowledge_test_payload()
        # PFMEA-P30-001 has classification="" (empty string)
        rec = source["metadata"]["knowledge_recommendations"][1]  # KR-TEST-002 targets PFMEA-P30-001
        self.assertEqual(rec["target_id"], "PFMEA-P30-001")

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "应用知识库推荐",
                "items": [
                    {
                        "action": "apply_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        pfmea_row = self._find_row_by_id(edited["pfmea"]["rows"], "pfmea_id", "PFMEA-P30-001")
        self.assertIsNotNone(pfmea_row)
        # classification was "" → should be filled
        self.assertEqual(pfmea_row["classification"], "SC-LABEL")
        # detection_control was "Final barcode scan before pack close" → should NOT be overwritten
        self.assertEqual(pfmea_row["detection_control"], "Final barcode scan before pack close")
        # recommendation status updated
        updated_rec = edited["metadata"]["knowledge_recommendations"][1]
        self.assertEqual(updated_rec["status"], "已应用")
        self.assertEqual(updated_rec["lifecycle_status"], "applied")
        self.assertIn("pfmea.classification", updated_rec.get("applied_fields", []))

    def test_accept_recommendation_does_not_write_fields(self):
        """accept_recommendation records acceptance without writing any fields to PFMEA/CP."""
        source = _knowledge_test_payload()
        # KR-TEST-001 targets PFMEA-P10-001 which has non-empty detection_control and classification
        rec = source["metadata"]["knowledge_recommendations"][0]
        self.assertEqual(rec["target_id"], "PFMEA-P10-001")

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "采纳推荐（不应写入字段）",
                "items": [
                    {
                        "action": "accept_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        pfmea_row = edited["pfmea"]["rows"][0]  # PFMEA-P10-001
        # Existing non-empty values must be preserved
        self.assertEqual(pfmea_row["detection_control"], "Incoming thickness measurement per lot")
        self.assertEqual(pfmea_row["classification"], "SC-THICKNESS")

    def test_apply_recommendation_writes_linked_cp_suggestion_to_cp_row(self):
        """linked_control_plan_suggestion fields are written to the CP row linked via pfmea_id."""
        source = _knowledge_test_payload()
        # KR-TEST-002:PFMEA-P30-001 → linked CP row CP-P30-001 (pfmea_id="PFMEA-P30-001")
        rec = source["metadata"]["knowledge_recommendations"][1]

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "应用并写入 CP 建议",
                "items": [
                    {
                        "action": "apply_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        cp_row = self._find_row_by_id(edited["control_plan"]["rows"], "pfmea_id", "PFMEA-P30-001")
        self.assertIsNotNone(cp_row)
        self.assertEqual(cp_row["control_plan_id"], "CP-P30-001")
        # inspection_tool was absent → should be written
        self.assertEqual(cp_row["inspection_tool"], "视觉检测仪")
        # control_method was "System scan required before pack close" → should NOT be overwritten
        self.assertEqual(cp_row["control_method"], "System scan required before pack close")

    def test_ignore_recommendation_requires_reason(self):
        """ignore_recommendation without a reason must raise EditPatchError."""
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

    def test_ignore_recommendation_with_reason_sets_ignored_status(self):
        """ignore_recommendation with a reason sets status='已忽略'."""
        source = _knowledge_test_payload()
        rec = source["metadata"]["knowledge_recommendations"][0]

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "当前产线不需要",
                "items": [
                    {
                        "action": "ignore_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                        "reason": "当前产线已有等效控制",
                    }
                ],
            },
        )

        updated_rec = edited["metadata"]["knowledge_recommendations"][0]
        self.assertEqual(updated_rec["status"], "已忽略")
        self.assertEqual(updated_rec["ignore_reason"], "当前产线已有等效控制")
        # Row fields must NOT have been touched (ignore does not write)
        pfmea_row = edited["pfmea"]["rows"][0]
        self.assertEqual(pfmea_row["detection_control"], "Incoming thickness measurement per lot")

    def test_accept_recommendation_sets_lifecycle_accepted(self):
        """Accept a recommendation that cannot write fields sets lifecycle_status=accepted."""
        source = _knowledge_test_payload()
        rec = source["metadata"]["knowledge_recommendations"][0]  # KR-TEST-001: all fields non-empty
        self.assertEqual(rec["target_id"], "PFMEA-P10-001")

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "采纳但无可写字段",
                "items": [
                    {
                        "action": "accept_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        updated_rec = edited["metadata"]["knowledge_recommendations"][0]
        self.assertEqual(updated_rec["status"], "已接受")
        self.assertEqual(updated_rec["lifecycle_status"], "accepted")
        self.assertEqual(updated_rec["accepted_by"], "qe")

    def test_ignore_recommendation_sets_lifecycle_ignored(self):
        """Ignore a recommendation sets lifecycle_status=ignored."""
        source = _knowledge_test_payload()
        rec = source["metadata"]["knowledge_recommendations"][0]

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "不需要此推荐",
                "items": [
                    {
                        "action": "ignore_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                        "reason": "已有等效控制，无需改动",
                    }
                ],
            },
        )

        updated_rec = edited["metadata"]["knowledge_recommendations"][0]
        self.assertEqual(updated_rec["status"], "已忽略")
        self.assertEqual(updated_rec["lifecycle_status"], "ignored")
        self.assertEqual(updated_rec["ignore_reason"], "已有等效控制，无需改动")
        self.assertEqual(updated_rec["ignored_by"], "qe")

    def test_unresolved_recommendations_appear_in_edit_export_gate(self):
        """Unresolved recommendations are reported in evaluate_edit_export_gate."""
        source = _knowledge_test_payload()
        gate = evaluate_edit_export_gate(source)
        self.assertIn("KR-TEST-001:PFMEA-P10-001", gate["knowledge_recommendations"])
        self.assertIn("KR-TEST-002:PFMEA-P30-001", gate["knowledge_recommendations"])

    def test_accepted_recommendations_removed_from_edit_export_gate(self):
        """After resolving all recommendations, only applied or ignored ones no longer block."""
        source = _knowledge_test_payload()
        recs = source["metadata"]["knowledge_recommendations"]
        # KR-TEST-001: all fields non-empty → accept (no write) → accepted but still unresolved
        # KR-TEST-002: classification empty → apply (writes fields) → applied → resolved
        items = [
            {
                "action": "accept_recommendation",
                "table": "metadata",
                "target_id": recs[0]["recommendation_id"],
            },
            {
                "action": "apply_recommendation",
                "table": "metadata",
                "target_id": recs[1]["recommendation_id"],
            },
        ]
        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "采纳/应用知识推荐",
                "items": items,
            },
        )
        gate = evaluate_edit_export_gate(edited)
        # KR-TEST-001: accepted but no fields written (all target fields already non-empty) → still blocks
        # KR-TEST-002: applied and fields written (classification was empty) → resolved → does not block
        self.assertIn("KR-TEST-001:PFMEA-P10-001", gate["knowledge_recommendations"])
        self.assertNotIn("KR-TEST-002:PFMEA-P30-001", gate["knowledge_recommendations"])

    def test_ignored_recommendations_with_reason_removed_from_edit_export_gate(self):
        """After ignoring all recommendations with a reason they no longer block the gate."""
        source = _knowledge_test_payload()
        recs = source["metadata"]["knowledge_recommendations"]
        items = [
            {
                "action": "ignore_recommendation",
                "table": "metadata",
                "target_id": r["recommendation_id"],
                "reason": "单元测试忽略原因",
            }
            for r in recs
        ]
        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "items": items,
            },
        )
        gate = evaluate_edit_export_gate(edited)
        self.assertEqual(gate["knowledge_recommendations"], [])

    def test_score_field_zero_is_overwritten_by_recommendation(self):
        """FMEA score fields with value 0 are treated as empty and overwritten."""
        source = _knowledge_test_payload()
        # Set severity=0 on PFMEA-P30-001 (should be overwritable)
        for row in source["pfmea"]["rows"]:
            if row.get("pfmea_id") == "PFMEA-P30-001":
                row["severity"] = 0
                row["occurrence"] = 0
                row["detection"] = 0

        # Create a recommendation targeting PFMEA-P30-001 with score fields
        rec = {
            "recommendation_id": "KR-SCORE-TEST:PFMEA-P30-001",
            "target_table": "pfmea",
            "target_id": "PFMEA-P30-001",
            "recommendation_type": "rating_hint",
            "source": "KR-SCORE-TEST",
            "reason": "建议评分",
            "confidence": 0.9,
            "suggested_fields": {"severity": 7, "occurrence": 4, "detection": 3},
            "linked_control_plan_suggestion": None,
            "ai_inferred": False,
            "needs_confirmation": True,
            "status": "待确认",
            "ignore_reason": "",
            "process_step_id": "P30",
        }
        source.setdefault("metadata", {}).setdefault("knowledge_recommendations", []).append(rec)

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "应用评分推荐（0 值应被覆盖）",
                "items": [
                    {
                        "action": "apply_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        pfmea_row = self._find_row_by_id(edited["pfmea"]["rows"], "pfmea_id", "PFMEA-P30-001")
        self.assertEqual(pfmea_row["severity"], 7)
        self.assertEqual(pfmea_row["occurrence"], 4)
        self.assertEqual(pfmea_row["detection"], 3)

    def test_score_field_string_zero_is_overwritten_by_recommendation(self):
        """FMEA score fields with string '0' are treated as empty and overwritten."""
        source = _knowledge_test_payload()
        for row in source["pfmea"]["rows"]:
            if row.get("pfmea_id") == "PFMEA-P30-001":
                row["severity"] = "0"
                row["detection"] = "0"

        rec = {
            "recommendation_id": "KR-SCORE-STRZERO:PFMEA-P30-001",
            "target_table": "pfmea",
            "target_id": "PFMEA-P30-001",
            "recommendation_type": "rating_hint",
            "source": "KR-SCORE-STRZERO",
            "reason": "建议评分",
            "confidence": 0.9,
            "suggested_fields": {"severity": 6, "detection": 4},
            "linked_control_plan_suggestion": None,
            "ai_inferred": False,
            "needs_confirmation": True,
            "status": "待确认",
            "ignore_reason": "",
            "process_step_id": "P30",
        }
        source.setdefault("metadata", {}).setdefault("knowledge_recommendations", []).append(rec)

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "应用评分推荐（字符串 '0' 应被覆盖）",
                "items": [
                    {
                        "action": "apply_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        pfmea_row = self._find_row_by_id(edited["pfmea"]["rows"], "pfmea_id", "PFMEA-P30-001")
        self.assertEqual(pfmea_row["severity"], 6)
        self.assertEqual(pfmea_row["detection"], 4)

    # --- 工作包 D: apply_recommendation 测试 -------------------------------------------------

    def test_accept_recommendation_keeps_empty_field_empty(self):
        """accept 后 PFMEA/CP 字段不变（包括空字段也不被填充）。"""
        source = _knowledge_test_payload()
        rec = source["metadata"]["knowledge_recommendations"][1]  # KR-TEST-002: targets PFMEA-P30-001
        # Save original values
        pfmea_row_before = self._find_row_by_id(source["pfmea"]["rows"], "pfmea_id", "PFMEA-P30-001")
        self.assertEqual(pfmea_row_before["classification"], "")

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "采纳但不写入字段",
                "items": [
                    {
                        "action": "accept_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        pfmea_row = self._find_row_by_id(edited["pfmea"]["rows"], "pfmea_id", "PFMEA-P30-001")
        # classification was "" → accept does NOT fill it
        self.assertEqual(pfmea_row["classification"], "")
        # detection_control stays unchanged
        self.assertEqual(pfmea_row["detection_control"], "Final barcode scan before pack close")

    def test_accept_recommendation_still_unresolved(self):
        """accept 后 recommendation 仍在 unresolved 中。"""
        source = _knowledge_test_payload()
        rec = source["metadata"]["knowledge_recommendations"][1]

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "采纳知识推荐",
                "items": [
                    {
                        "action": "accept_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        updated_rec = edited["metadata"]["knowledge_recommendations"][1]
        self.assertEqual(updated_rec["status"], "已接受")
        self.assertEqual(updated_rec["lifecycle_status"], "accepted")
        self.assertEqual(updated_rec["decision"], "accepted")
        # accept without apply → still unresolved in gate
        gate = evaluate_edit_export_gate(edited)
        self.assertIn("KR-TEST-002:PFMEA-P30-001", gate["knowledge_recommendations"])

    def test_apply_recommendation_no_writable_fields_stays_accepted(self):
        """apply 无字段可写时保持 accepted 状态。"""
        source = _knowledge_test_payload()
        rec = source["metadata"]["knowledge_recommendations"][0]  # KR-TEST-001: all fields non-empty

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "应用推荐（无字段可写）",
                "items": [
                    {
                        "action": "apply_recommendation",
                        "table": "metadata",
                        "target_id": rec["recommendation_id"],
                    }
                ],
            },
        )

        updated_rec = edited["metadata"]["knowledge_recommendations"][0]
        self.assertEqual(updated_rec["status"], "已接受")
        self.assertEqual(updated_rec["lifecycle_status"], "accepted")

    def test_apply_recommendation_not_in_unresolved(self):
        """apply 写入字段后不在 unresolved 中。"""
        source = _knowledge_test_payload()
        rec = source["metadata"]["knowledge_recommendations"][1]  # KR-TEST-002: classification empty

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "应用推荐",
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
        self.assertIn("pfmea.classification", updated_rec.get("applied_fields", []))
        # applied recommendation should NOT be in unresolved gate
        gate = evaluate_edit_export_gate(edited)
        self.assertNotIn("KR-TEST-002:PFMEA-P30-001", gate["knowledge_recommendations"])

    # --- 工作包 G: resolve_action_item 测试 -------------------------------------------------



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
