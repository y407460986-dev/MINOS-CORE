from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree

from minos_core.adapters.fixture_json import load_fixture_payload
from minos_core.edit_patch import (
    EDIT_PATCH_VERSION,
    EditPatchError,
    apply_edit_patch,
    evaluate_edit_export_gate,
    export_edited_three_tables,
)
from minos_core.automation_review import build_automation_review, build_batch_confirm_patch
from minos_core.change_management import _changed_any
from minos_core.knowledge_recommendation import recommend_from_knowledge
from minos_core.quality_gates import evaluate_export_gate


ROOT_FIXTURE = "D:/MINOS-CORE/tests/fixtures/apqp_chain"

from tests.edit_patch.conftest import _fixture, _three_table_result, ROOT_FIXTURE, NS


class ActionItemTests(unittest.TestCase):
    def test_close_action_with_evidence_succeeds(self):
        """close action 有 evidence 成功。"""
        source = _three_table_result()
        # Pre-populate action items
        action_id = "ACT-P10-001"
        source.setdefault("metadata", {})["action_items"] = [
            {
                "action_id": action_id,
                "source_pfmea_id": "PFMEA-P10-001",
                "status": "open",
                "priority": "high",
                "description": "补充高风险措施",
                "owner": "",
                "due_date": "",
                "closure_evidence_refs": [],
                "manual_confirmation_event": "",
                "ignore_reason": "",
                "created_from": "pfmea",
                "closed_at": "",
                "closed_by": "",
            }
        ]

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "edited_at": "2026-04-28T10:00:00Z",
                "reason": "关闭行动项",
                "items": [
                    {
                        "action": "resolve_action_item",
                        "table": "metadata",
                        "target_id": action_id,
                        "changes": {
                            "status": "closed",
                            "closure_evidence_refs": ["EV-CLOSE-001"],
                            "closed_at": "2026-04-28T10:00:00Z",
                            "closed_by": "qe",
                        },
                    }
                ],
            },
        )

        item = edited["metadata"]["action_items"][0]
        self.assertEqual(item["status"], "closed")
        self.assertEqual(item["closure_evidence_refs"], ["EV-CLOSE-001"])
        self.assertEqual(item["resolved_by"], "qe")
        self.assertEqual(item["resolved_at"], "2026-04-28T10:00:00Z")


    def test_close_action_without_evidence_errors(self):
        """close action 无 evidence 报错。"""
        source = _three_table_result()
        action_id = "ACT-NO-EVID"
        source.setdefault("metadata", {})["action_items"] = [
            {
                "action_id": action_id,
                "status": "open",
                "priority": "high",
                "description": "高风险措施",
                "closure_evidence_refs": [],
                "manual_confirmation_event": "",
                "ignore_reason": "",
                "created_from": "pfmea",
                "closed_at": "",
                "closed_by": "",
            }
        ]

        with self.assertRaises(EditPatchError) as ctx:
            apply_edit_patch(
                source,
                {
                    "edit_patch_version": EDIT_PATCH_VERSION,
                    "edited_by": "qe",
                    "reason": "关闭行动项（无证据）",
                    "items": [
                        {
                            "action": "resolve_action_item",
                            "table": "metadata",
                            "target_id": action_id,
                            "changes": {"status": "closed"},
                        }
                    ],
                },
            )
        self.assertIn("requires closure_evidence_refs or manual_confirmation_event", str(ctx.exception))


    def test_ignore_action_without_reason_errors(self):
        """ignore action 无 reason 报错。"""
        source = _three_table_result()
        action_id = "ACT-NO-REASON"
        source.setdefault("metadata", {})["action_items"] = [
            {
                "action_id": action_id,
                "status": "open",
                "priority": "high",
                "description": "高风险措施",
                "closure_evidence_refs": [],
                "manual_confirmation_event": "",
                "ignore_reason": "",
                "created_from": "pfmea",
                "closed_at": "",
                "closed_by": "",
            }
        ]

        with self.assertRaises(EditPatchError) as ctx:
            apply_edit_patch(
                source,
                {
                    "edit_patch_version": EDIT_PATCH_VERSION,
                    "edited_by": "qe",
                    "items": [
                        {
                            "action": "resolve_action_item",
                            "table": "metadata",
                            "target_id": action_id,
                            "changes": {"status": "ignored"},
                        }
                    ],
                },
            )
        self.assertIn("requires reason", str(ctx.exception))


    def test_ignore_action_with_reason_succeeds(self):
        """ignore action 有 reason 成功。"""
        source = _three_table_result()
        action_id = "ACT-IGNORE-OK"
        source.setdefault("metadata", {})["action_items"] = [
            {
                "action_id": action_id,
                "status": "open",
                "priority": "medium",
                "description": "一般风险措施",
                "closure_evidence_refs": [],
                "manual_confirmation_event": "",
                "ignore_reason": "",
                "created_from": "pfmea",
                "closed_at": "",
                "closed_by": "",
            }
        ]

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "edited_at": "2026-04-28T10:00:00Z",
                "reason": "忽略行动项",
                "items": [
                    {
                        "action": "resolve_action_item",
                        "table": "metadata",
                        "target_id": action_id,
                        "changes": {"status": "ignored", "owner": "skip"},
                        "reason": "当前产线不适用",
                    }
                ],
            },
        )

        item = edited["metadata"]["action_items"][0]
        self.assertEqual(item["status"], "ignored")
        self.assertEqual(item["ignore_reason"], "当前产线不适用")
        self.assertEqual(item["resolved_by"], "qe")
        self.assertEqual(item["resolved_at"], "2026-04-28T10:00:00Z")


    def test_resolve_action_item_recorded_in_edit_history(self):
        """edit_history 记录了 resolve_action_item。"""
        source = _three_table_result()
        action_id = "ACT-RECORD-001"
        source.setdefault("metadata", {})["action_items"] = [
            {
                "action_id": action_id,
                "status": "open",
                "priority": "high",
                "description": "高风险措施",
                "closure_evidence_refs": [],
                "manual_confirmation_event": "",
                "ignore_reason": "",
                "created_from": "pfmea",
                "closed_at": "",
                "closed_by": "",
            }
        ]

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "edited_at": "2026-04-28T10:00:00Z",
                "reason": "关闭行动项",
                "items": [
                    {
                        "action": "resolve_action_item",
                        "table": "metadata",
                        "target_id": action_id,
                        "changes": {
                            "status": "closed",
                            "closure_evidence_refs": ["EV-EVID-001"],
                            "closed_at": "2026-04-28T10:00:00Z",
                            "closed_by": "qe",
                        },
                    }
                ],
            },
        )

        history = edited["metadata"]["edit_history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["action"], "resolve_action_item")
        self.assertEqual(history[0]["target_id"], action_id)
        self.assertEqual(history[0]["edited_by"], "qe")

    # --- review_dashboard tests -------------------------------------------------


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
