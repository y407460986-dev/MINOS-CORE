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


class EditPatchTests(unittest.TestCase):
    def test_edit_patch_add_update_soft_delete_confirm_and_reassembles_chain(self):
        source = _three_table_result()

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "process.engineer",
                "edited_at": "2026-04-26T12:00:00Z",
                "reason": "桌面端人工三表编辑",
                "items": [
                    {
                        "action": "add",
                        "table": "process_flow",
                        "row": {
                            "process_step_id": "P40",
                            "sequence": 40,
                            "operation": "Audit pack",
                            "process_function": "Confirm pack label and count",
                            "evidence_refs": ["EV-PACK-SCAN-001"],
                        },
                    },
                    {
                        "action": "update",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-001",
                        "changes": {"failure_cause": "人工修正后的原因"},
                    },
                    {
                        "action": "soft_delete",
                        "table": "control_plan",
                        "target_id": "CP-P30-001",
                    },
                    {
                        "action": "confirm",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-001",
                    },
                ],
            },
        )

        self.assertEqual(source["process_flow"]["steps"][-1]["process_step_id"], "P30")
        added = edited["process_flow"]["steps"][-1]
        self.assertEqual(added["process_step_id"], "P40")
        self.assertEqual(added["review_status"], "人工新增")
        self.assertTrue(added["needs_confirmation"])
        self.assertFalse(added["ai_inferred"])
        updated = edited["pfmea"]["rows"][0]
        self.assertEqual(updated["failure_cause"], "人工修正后的原因")
        self.assertEqual(updated["review_status"], "已确认")
        self.assertFalse(updated["needs_confirmation"])
        deleted = edited["control_plan"]["rows"][-1]
        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["review_status"], "软删除")
        self.assertNotIn("CP-P30-001", {row["control_plan_id"] for row in edited["chain"]["controls"]})
        self.assertEqual(len(edited["metadata"]["edit_history"]), 4)

    def test_process_flow_soft_delete_creates_downstream_change_impacts_and_blocks_final_export(self):
        edited = apply_edit_patch(
            _three_table_result(),
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "process.engineer",
                "edited_at": "2026-04-26T12:30:00Z",
                "reason": "删除 PFD 工序 P10",
                "items": [
                    {
                        "action": "soft_delete",
                        "table": "process_flow",
                        "target_id": "P10",
                    }
                ],
            },
        )

        impacts = edited["metadata"]["change_impacts"]
        p10_impacts = [
            item
            for item in impacts
            if item.get("target") == "process_flow:P10"
            and item.get("category") == "变更影响"
            and item.get("status") not in {"已处理", "无影响"}
        ]
        messages = {item.get("message") for item in p10_impacts}
        self.assertIn("PFMEA 关联风险需处理", messages)
        self.assertIn("CP 关联控制项需处理", messages)
        self.assertTrue(
            all("PFD 删除工序" in item.get("item_id", "") for item in p10_impacts)
        )
        self.assertNotIn(
            "PFMEA-P10-001",
            {row["pfmea_id"] for row in edited["chain"]["failure_modes"]},
        )
        self.assertNotIn(
            "CP-P10-001",
            {row["control_plan_id"] for row in edited["chain"]["controls"]},
        )

        gate = evaluate_edit_export_gate(edited)
        self.assertFalse(edited["quality_gate"]["allow_user_export"])
        self.assertFalse(gate["quality_gate"]["allow_user_export"])
        self.assertFalse(gate["final_export_allowed"])
        for item in p10_impacts:
            self.assertIn(item["item_id"], gate["change_impacts"])
        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_edited_three_tables(edited, Path(tmpdir), export_mode="final")
            self.assertFalse(result["final_export_allowed"])

        restored = apply_edit_patch(
            edited,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "process.engineer",
                "edited_at": "2026-04-26T12:45:00Z",
                "reason": "误删后恢复 PFD 工序 P10",
                "items": [
                    {
                        "action": "update",
                        "table": "process_flow",
                        "target_id": "P10",
                        "changes": {"deleted": False, "soft_deleted": False},
                    }
                ],
            },
        )
        restored_impacts = [
            item for item in restored["metadata"]["change_impacts"]
            if item.get("target") == "process_flow:P10"
        ]
        self.assertTrue(restored_impacts)
        self.assertTrue(all(item.get("status") == "无影响" for item in restored_impacts))
        self.assertIn(
            "PFMEA-P10-001",
            {row["pfmea_id"] for row in restored["chain"]["failure_modes"]},
        )

    def test_soft_deleted_rows_are_not_exported(self):
        source = apply_edit_patch(
            _three_table_result(),
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "quality.engineer",
                "edited_at": "2026-04-26T13:00:00Z",
                "reason": "删除不再适用的控制计划行",
                "items": [
                    {
                        "action": "soft_delete",
                        "table": "control_plan",
                        "target_id": "CP-P30-001",
                    }
                ],
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_edited_three_tables(source, Path(tmpdir), export_mode="draft")
            control_plan_text = _workbook_text(result["exports"]["control_plan"])

        self.assertIn("CP-P10-001", control_plan_text)
        self.assertNotIn("CP-P30-001", control_plan_text)
        self.assertIn("control_plan:CP-P30-001", result["soft_deleted_items"])

    def test_apqp_chain_input_returns_chain_and_keeps_soft_deleted_audit_row(self):
        source = _three_table_result()["chain"]

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "quality.engineer",
                "edited_at": "2026-04-26T14:00:00Z",
                "reason": "链路输入补丁",
                "items": [
                    {
                        "action": "soft_delete",
                        "table": "pfmea",
                        "target_id": "PFMEA-P30-001",
                    }
                ],
            },
        )

        self.assertEqual(edited["document_type"], "apqp_chain")
        self.assertTrue(edited["failure_modes"][-1]["deleted"])
        gate = evaluate_edit_export_gate(edited)
        self.assertIn("pfmea:PFMEA-P30-001", gate["soft_deleted_items"])

    def test_soft_deleted_rows_excluded_from_final_export(self):
        """软删除行不进入正式导出表（控制计划工作表不含已删行）。"""
        source = apply_edit_patch(
            _three_table_result(),
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "quality.engineer",
                "edited_at": "2026-04-26T14:00:00Z",
                "reason": "删除不再适用的控制计划行",
                "items": [
                    {
                        "action": "soft_delete",
                        "table": "control_plan",
                        "target_id": "CP-P10-001",
                    }
                ],
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_edited_three_tables(source, Path(tmpdir), export_mode="final")
            workbook = Path(result["exports"]["unified_workbook"])
            self.assertTrue(workbook.exists())
            # 检查控制计划工作表（不含已删行）
            cp_sheet_text = _sheet_text(workbook, "控制计划")

        # 已存在的行仍在控制计划工作表中（通过规格文本识别）
        self.assertIn("1.50", cp_sheet_text)  # CP-P20-001 Rivet height
        self.assertIn("Released revision", cp_sheet_text)  # CP-P30-001
        # 软删除的行不在控制计划工作表中
        self.assertNotIn("2.00 +/- 0.10 mm", cp_sheet_text)  # CP-P10-001 Material thickness
        # 软删除行 ID 出现在结果元数据中
        self.assertIn("control_plan:CP-P10-001", result["soft_deleted_items"])



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
