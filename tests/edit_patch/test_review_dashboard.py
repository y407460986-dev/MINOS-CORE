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


class ReviewDashboardTests(unittest.TestCase):
    def test_review_dashboard_has_required_fields(self):
        """dashboard 包含所有必需字段。"""
        source = _three_table_result()
        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "dashboard 结构验证",
                "items": [
                    {
                        "action": "confirm",
                        "table": "process_flow",
                        "target_id": "P10",
                    }
                ],
            },
        )
        dashboard = edited.get("review_dashboard")
        self.assertIsInstance(dashboard, dict)
        required_fields = [
            "status",
            "status_display",
            "final_export_allowed",
            "sync_blocker_count",
            "open_action_count",
            "unresolved_action_count",
            "overdue_action_count",
            "unconfirmed_row_count",
            "unresolved_recommendation_count",
            "unresolved_change_impact_count",
            "manual_review_count",
            "next_actions",
        ]
        for field in required_fields:
            with self.subTest(field=field):
                self.assertIn(field, dashboard)


    def test_review_dashboard_shows_unconfirmed_rows(self):
        """有未确认行时 dashboard 提示确认。"""
        source = _three_table_result()
        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "未确认行测试",
                "items": [
                    {
                        "action": "update",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-001",
                        "changes": {"detection_control": "目视检查"},
                    }
                ],
            },
        )
        dashboard = edited["review_dashboard"]
        self.assertGreater(dashboard["unconfirmed_row_count"], 0)
        self.assertEqual(dashboard["status"], "needs_review")
        self.assertFalse(dashboard["final_export_allowed"])
        # 第一条 next_action 应该是确认行
        self.assertGreater(len(dashboard["next_actions"]), 0)
        first_action = dashboard["next_actions"][0]
        self.assertEqual(first_action["priority"], 1)
        self.assertIn("确认", first_action["action"])


    def test_review_dashboard_shows_can_export_when_all_ok(self):
        """全部确认且无阻断时 next_actions 显示可以导出。"""
        source = _three_table_result()
        # 解决所有 knowledge_recommendations（先忽略）
        recs = recommend_from_knowledge(source)
        source.setdefault("metadata", {})["knowledge_recommendations"] = recs

        items = []
        for row in source["process_flow"]["steps"]:
            items.append({
                "action": "confirm",
                "table": "process_flow",
                "target_id": row["process_step_id"],
            })
        for row in source["pfmea"]["rows"]:
            items.append({
                "action": "update",
                "table": "pfmea",
                "target_id": row["pfmea_id"],
                "changes": {
                    "recommended_action": row.get("recommended_action") or "已确认无需新增措施",
                    "responsibility": row.get("responsibility") or "质量工程师",
                    "target_date": row.get("target_date") or "2026-12-31",
                    "action_status": "已完成",
                    "after_severity": row.get("severity", 1) or 1,
                    "after_occurrence": 2,
                    "after_detection": 3,
                    "after_ap": "L",
                },
            })
            items.append({
                "action": "confirm",
                "table": "pfmea",
                "target_id": row["pfmea_id"],
            })
        for row in source["control_plan"]["rows"]:
            items.append({
                "action": "confirm",
                "table": "control_plan",
                "target_id": row["control_plan_id"],
            })
        for rec in recs:
            items.append({
                "action": "ignore_recommendation",
                "table": "metadata",
                "target_id": rec["recommendation_id"],
                "reason": "单元测试中确认暂不采纳",
            })

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "全部确认后检查导出",
                "items": items,
            },
        )
        dashboard = edited["review_dashboard"]
        self.assertTrue(dashboard["final_export_allowed"])
        self.assertEqual(dashboard["status"], "ok")
        # next_actions 最后一条应为可导出
        export_hint = next(
            (a for a in dashboard["next_actions"] if "导出" in a.get("action", "")),
            None,
        )
        self.assertIsNotNone(export_hint)
        self.assertEqual(export_hint["priority"], 10)



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
