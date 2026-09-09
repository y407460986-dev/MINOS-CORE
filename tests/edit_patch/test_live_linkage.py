from __future__ import annotations

import unittest
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from minos_core.edit_patch import (
    EDIT_PATCH_VERSION,
    apply_edit_patch,
    evaluate_edit_export_gate,
)
from minos_core.knowledge_recommendation import recommend_from_knowledge
from tests.edit_patch.conftest import NS, _three_table_result

ROOT_FIXTURE = "D:/MINOS-CORE/tests/fixtures/apqp_chain"


class LiveLinkageTests(unittest.TestCase):
    def test_live_linkage_add_sets_review_status_stub(self):
        """联动 add 后行 review_status='联动新增' 且 needs_confirmation=True。"""
        source = _three_table_result()
        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "linkage.engine",
                "edited_at": "2026-04-27T10:00:00Z",
                "reason": "联动新增 PFMEA stub",
                "items": [
                    {
                        "action": "add",
                        "table": "pfmea",
                        "row": {
                            "pfmea_id": "PFMEA-P10-LINKED",
                            "process_step_id": "P10",
                            "operation": "Test linked op",
                            "function_requirement": "Linked function",
                            "failure_mode": "Linked failure mode",
                            "failure_effect": "Linked effect",
                            "failure_cause": "Linked cause",
                            "severity": 5,
                            "occurrence": 5,
                            "detection": 5,
                            "needs_confirmation": True,
                            "review_status": "联动新增",
                        },
                        "source": "live_linkage",
                        "linkage_event_id": "EVT-001",
                        "linkage_impact_id": "LIVE-PROCESSFLOW-P10-PFMEA",
                    }
                ],
            },
        )
        added = edited["pfmea"]["rows"][-1]
        self.assertEqual(added["pfmea_id"], "PFMEA-P10-LINKED")
        self.assertEqual(added["review_status"], "联动新增")
        self.assertTrue(added["needs_confirmation"])
        # edit_history 保留 linkage 元数据
        history = edited["metadata"]["edit_history"]
        last_record = history[-1]
        self.assertEqual(last_record["linkage_event_id"], "EVT-001")
        self.assertEqual(last_record["linkage_impact_id"], "LIVE-PROCESSFLOW-P10-PFMEA")
        self.assertEqual(last_record["source"], "live_linkage")


    def test_live_linkage_update_records_linkage_metadata(self):
        """联动 update（sync_inherited_fields）后 edit_history 保留 linkage_event_id。"""
        source = _three_table_result()
        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "linkage.engine",
                "edited_at": "2026-04-27T10:00:00Z",
                "reason": "联动同步继承字段",
                "items": [
                    {
                        "action": "update",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-001",
                        "changes": {"operation": "同步后的操作"},
                        "needs_confirmation": True,
                        "review_status": "联动同步",
                        "source": "live_linkage",
                        "linkage_event_id": "EVT-002",
                        "linkage_impact_id": "LIVE-PROCESSFLOW-P10-PFMEA-SYNC",
                    }
                ],
            },
        )
        history = edited["metadata"]["edit_history"]
        last_record = history[-1]
        self.assertEqual(last_record["linkage_event_id"], "EVT-002")
        self.assertEqual(last_record["linkage_impact_id"], "LIVE-PROCESSFLOW-P10-PFMEA-SYNC")
        self.assertEqual(last_record["source"], "live_linkage")
        # 行应标记为联动同步
        updated = edited["pfmea"]["rows"][0]
        self.assertEqual(updated["pfmea_id"], "PFMEA-P10-001")
        self.assertEqual(updated["review_status"], "联动同步")
        self.assertTrue(updated["needs_confirmation"])


    def test_live_linkage_sync_does_not_confirm_row(self):
        """联动同步（mark_downstream_needs_review）不让行变成已确认。"""
        source = _three_table_result()
        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "linkage.engine",
                "edited_at": "2026-04-27T10:00:00Z",
                "reason": "联动标记下游需要复核",
                "items": [
                    {
                        "action": "update",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-001",
                        "changes": {"review_status": "待同步确认"},
                        "source": "live_linkage",
                        "linkage_event_id": "EVT-003",
                        "linkage_impact_id": "LIVE-PROCESSFLOW-P10-PFMEA-REVIEW",
                    }
                ],
            },
        )
        updated = edited["pfmea"]["rows"][0]
        self.assertEqual(updated["pfmea_id"], "PFMEA-P10-001")
        self.assertEqual(updated["review_status"], "待同步确认")
        self.assertNotEqual(updated["review_status"], "已确认")
        self.assertTrue(updated["needs_confirmation"])


    def test_manual_patch_unchanged(self):
        """普通人工 patch 行为不变（review_status=人工修改，无 linkage 元数据）。"""
        source = _three_table_result()
        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "manual.user",
                "edited_at": "2026-04-27T10:00:00Z",
                "reason": "普通人工patch",
                "items": [
                    {
                        "action": "update",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-001",
                        "changes": {"failure_cause": "人工修正后的原因"},
                    }
                ],
            },
        )
        updated = edited["pfmea"]["rows"][0]
        self.assertEqual(updated["review_status"], "人工修改")
        self.assertTrue(updated["needs_confirmation"])
        # 无 linkage 元数据
        history = edited["metadata"]["edit_history"]
        last_record = history[-1]
        self.assertEqual(last_record.get("linkage_event_id", ""), "")
        self.assertEqual(last_record.get("linkage_impact_id", ""), "")
        self.assertNotEqual(last_record.get("source", ""), "live_linkage")


    def test_unresolved_live_linkage_blocks_final_export(self):
        """存在待同步确认行时 final_export_allowed=False。"""
        source = _three_table_result()
        # 先全部确认
        confirmed = apply_edit_patch(source, _confirm_all_patch(source))
        # 再标记 PFMEA-P10-001 为待同步确认（模拟联动标记）
        edited = apply_edit_patch(
            confirmed,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "linkage.engine",
                "edited_at": "2026-04-27T10:00:00Z",
                "reason": "联动标记下游需要复核",
                "items": [
                    {
                        "action": "update",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-001",
                        "changes": {"review_status": "待同步确认"},
                        "source": "live_linkage",
                        "linkage_event_id": "EVT-004",
                        "linkage_impact_id": "LIVE-PROCESSFLOW-P10-PFMEA-REVIEW",
                    }
                ],
            },
        )
        gate = evaluate_edit_export_gate(edited)
        self.assertFalse(
            gate["final_export_allowed"],
            "存在待同步确认行应阻断正式导出",
        )
        # 质量门的 live_linkage_issues 应包含 blocker
        qg = gate["quality_gate"]
        live_issues = qg.get("live_linkage_issues", [])
        blockers = [i for i in live_issues if i.get("severity") == "blocker"]
        self.assertTrue(len(blockers) > 0, "live_linkage_issues 应包含 blocker")



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
