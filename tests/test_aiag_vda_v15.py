from __future__ import annotations

import copy
import unittest
from datetime import date

from minos_core.action_closure import action_closure_issues
from minos_core.aiag_vda_pfmea import calculate_ap, normalize_pfmea_row
from minos_core.change_management import analyze_change_impacts, blocking_change_impacts
from minos_core.edit_patch import EDIT_PATCH_VERSION, apply_edit_patch
from minos_core.knowledge_recommendation import recommend_from_knowledge, unresolved_recommendations
from minos_core.quality_gates import evaluate_export_gate


def _chain() -> dict:
    return {
        "document_type": "apqp_chain",
        "schema_version": "minos-core.generated.v1",
        "product": {},
        "process_steps": [
            {
                "process_step_id": "P10",
                "sequence": 10,
                "operation": "尺寸检验",
                "process_function": "确认特殊特性",
                "special_characteristics": ["SC-1"],
                "evidence_refs": ["EV-1"],
            }
        ],
        "failure_modes": [
            {
                "pfmea_id": "PFMEA-P10-001",
                "process_step_id": "P10",
                "process_function": "确认特殊特性",
                "failure_mode": "漏检",
                "failure_effect": "不合格流出",
                "severity": 9,
                "failure_cause": "检具未校准",
                "occurrence": 4,
                "prevention_control": "校准管理",
                "detection_control": "首件检验",
                "detection": 6,
                "action_priority": "H",
                "recommended_action": "",
                "responsibility": "",
                "target_date": "",
                "action_status": "未制定",
                "classification": "SC-1",
                "characteristic_refs": ["SC-1"],
                "evidence_refs": ["EV-1"],
                "review_status": "已确认",
                "needs_confirmation": False,
            }
        ],
        "controls": [
            {
                "control_plan_id": "CP-P10-001",
                "process_step_id": "P10",
                "pfmea_id": "PFMEA-P10-001",
                "product_process_characteristic": "SC-1",
                "specification": "按图纸",
                "classification": "SC-1",
                "measurement_method": "卡尺",
                "sample_size": "1 件",
                "sample_frequency": "每批",
                "control_method": "首件检验",
                "reaction_plan": "隔离并通知质量",
                "source_special_characteristics": ["SC-1"],
                "evidence_refs": ["EV-1"],
                "review_status": "已确认",
                "needs_confirmation": False,
            }
        ],
        "evidence": [{"evidence_id": "EV-1", "source": "fixture", "content": "确认记录"}],
        "links": [],
        "pending_fields": [],
        "ai_inferred_items": [],
        "metadata": {
            "strict_three_table_linkage": True,
            "strict_aiag_vda_pfmea_gate": True,
        },
    }


class AIAGVDAV15Tests(unittest.TestCase):
    def test_ap_calculation_and_pfmea_normalization(self):
        self.assertEqual(calculate_ap(9, 4, 6), "H")
        self.assertEqual(calculate_ap(7, 3, 4), "M")
        self.assertEqual(calculate_ap(4, 3, 3), "L")

        row = normalize_pfmea_row({"severity": 9, "occurrence": 4, "detection": 6})

        self.assertEqual(row["AP"], "H")
        self.assertEqual(row["action_priority"], "H")
        self.assertEqual(row["rpn"], 216)
        self.assertEqual(row["process_item"], "制造过程")

    def test_action_closure_blocks_high_ap_missing_owner_due_date_and_after_scores(self):
        row = normalize_pfmea_row(
            {
                "pfmea_id": "PFMEA-P10-001",
                "severity": 9,
                "occurrence": 4,
                "detection": 6,
                "recommended_action": "",
                "responsibility": "",
                "target_date": "2026-01-01",
                "action_status": "已完成",
            }
        )

        issues = action_closure_issues([row], today=date(2026, 4, 26))
        messages = "\n".join(item["message"] for item in issues)

        self.assertIn("高 AP 必须填写推荐措施", messages)
        self.assertIn("高/中 AP 必须填写责任人", messages)
        self.assertIn("措施完成后必须填写措施后 S/O/D/AP", messages)

    def test_export_gate_blocks_high_ap_action_debt(self):
        chain = _chain()

        gate = evaluate_export_gate(chain)
        messages = "\n".join(item.message for item in gate.manual_review_items)

        self.assertFalse(gate.allow_user_export)
        self.assertIn("高 AP 必须填写推荐措施", messages)

    def test_change_management_flags_downstream_impacts(self):
        source = {
            "process_steps": [
                {
                    "process_step_id": "P20",
                    "operation": "新增压装",
                    "review_status": "人工新增",
                }
            ],
            "failure_modes": [],
            "controls": [],
            "metadata": {},
        }

        impacts = analyze_change_impacts(source)

        self.assertEqual(len(blocking_change_impacts(impacts)), 2)
        self.assertTrue(any("PFMEA 需补风险" in item["message"] for item in impacts))
        self.assertTrue(any("CP 需补控制" in item["message"] for item in impacts))

    def test_knowledge_recommendations_require_accept_or_ignore_reason(self):
        chain = _chain()
        recommendations = recommend_from_knowledge(chain)

        self.assertTrue(recommendations)
        self.assertTrue(unresolved_recommendations(recommendations))

        source = copy.deepcopy(chain)
        source["metadata"]["knowledge_recommendations"] = recommendations
        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "确认知识库推荐",
                "items": [
                    {
                        "action": "accept_recommendation",
                        "table": "metadata",
                        "target_id": recommendations[0]["recommendation_id"],
                    }
                ],
            },
        )

        self.assertEqual(
            edited["metadata"]["knowledge_recommendations"][0]["status"],
            "已采纳",
        )

    def test_edit_patch_records_field_level_before_after_values(self):
        source = _chain()
        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "补措施",
                "items": [
                    {
                        "action": "update",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-001",
                        "changes": {"responsibility": "张三"},
                    }
                ],
            },
        )

        history = edited["metadata"]["edit_history"][0]
        self.assertEqual(history["field_changes"][0]["field"], "responsibility")
        self.assertEqual(history["field_changes"][0]["before"], "")
        self.assertEqual(history["field_changes"][0]["after"], "张三")


if __name__ == "__main__":
    unittest.main()
