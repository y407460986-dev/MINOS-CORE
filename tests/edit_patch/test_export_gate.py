from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from minos_core.automation_review import build_automation_review, build_batch_confirm_patch
from minos_core.edit_patch import (
    EDIT_PATCH_VERSION,
    apply_edit_patch,
    evaluate_edit_export_gate,
    export_edited_three_tables,
)
from minos_core.knowledge_recommendation import recommend_from_knowledge
from minos_core.quality_gates import ExportGateError, evaluate_export_gate
from tests.edit_patch.conftest import NS, _three_table_result

ROOT_FIXTURE = "D:/MINOS-CORE/tests/fixtures/apqp_chain"


class ExportGateTests(unittest.TestCase):
    def test_export_gate_blocks_structural_audit_blockers(self):
        payload = {
            "product": {},
            "process_steps": [
                {
                    "process_step_id": "P10",
                    "operation": "Inspection",
                    "process_function": "Inspect critical feature",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P10-GENERIC",
                    "process_step_id": "P10",
                    "process_function": "Inspect critical feature",
                    "failure_mode": "Critical feature out of tolerance",
                    "failure_effect": "Customer fit issue",
                    "failure_cause": "Gauge setup drift",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                    "evidence_refs": [],
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P10-GENERIC",
                    "process_step_id": "P10",
                    "pfmea_id": "PFMEA-P10-GENERIC",
                    "product_process_characteristic": "Critical feature",
                    "specification": "按图纸",
                    "measurement_method": "按作业指导书",
                    "sample_size": "1",
                    "sample_frequency": "每批",
                    "control_method": "按规范",
                    "reaction_plan": "按工艺卡",
                    "evidence_refs": [],
                }
            ],
            "evidence": [],
            "links": [],
        }

        gate = evaluate_export_gate(payload)
        manual_items = [
            item if isinstance(item, dict) else item.__dict__
            for item in gate.manual_review_items
        ]

        self.assertFalse(gate.allow_user_export)
        self.assertTrue(
            any(item.get("category") == "generic_control_text" for item in manual_items)
        )
        self.assertTrue(
            any(
                item.get("category") == "generic_control_text"
                for item in gate.review_issues
            )
        )

    def test_final_export_raises_when_unconfirmed_and_succeeds_after_confirmed(self):
        source = _three_table_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            with self.assertRaises(ExportGateError):
                export_edited_three_tables(source, output_dir, export_mode="final")
            self.assertFalse(
                any(path.is_file() for path in output_dir.rglob("*")),
                "blocked final export must not leave formal files behind",
            )

        confirmed = apply_edit_patch(source, _confirm_all_patch(source))
        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_edited_three_tables(
                confirmed, Path(tmpdir), export_mode="final"
            )
            workbook = Path(result["exports"]["unified_workbook"])
            self.assertTrue(workbook.exists())
            self.assertIn("正式导出审计", _sheet_names(workbook))
            workbook_text = _workbook_text(workbook)
            self.assertIn("edit_history", workbook_text)
            self.assertIn("soft_deleted_items", workbook_text)

        self.assertTrue(result["final_export_allowed"])

    def test_draft_export_allows_unconfirmed_chain(self):
        source = _three_table_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_edited_three_tables(source, Path(tmpdir), export_mode="draft")
            self.assertFalse(result["final_export_allowed"])
            self.assertTrue(Path(result["exports"]["unified_workbook"]).exists())


    def test_ai_batch_confirm_history_and_core_export_blockers(self):
        source = _automation_chain()
        review = build_automation_review(source)
        edited = apply_edit_patch(
            source,
            build_batch_confirm_patch(
                review["batch_confirm_candidates"],
                edited_by="automation",
                edited_at="2026-04-27T10:00:00Z",
            ),
        )

        confirmed = edited["process_steps"][0]
        self.assertEqual(confirmed["confirmation_mode"], "ai_recommended_batch")
        self.assertEqual(confirmed["confirmation_source"], "automation_review")
        self.assertEqual(
            edited["metadata"]["edit_history"][0]["metadata"]["source"],
            "automation_review",
        )

        unsafe = apply_edit_patch(
            _automation_chain(),
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "items": [
                    {
                        "action": "confirm",
                        "table": "pfmea",
                        "target_id": "PFMEA-P10-HIGH",
                        "metadata": {
                            "confirmation_mode": "ai_recommended_batch",
                            "source": "automation_review",
                        },
                    }
                ],
            },
        )
        edit_gate = evaluate_edit_export_gate(unsafe)
        self.assertFalse(edit_gate["final_export_allowed"])
        self.assertIn("pfmea:PFMEA-P10-HIGH:AI批量确认不适用", edit_gate["review_issues"])
        core_gate = evaluate_export_gate(unsafe)
        self.assertFalse(core_gate.allow_user_export)
        self.assertTrue(
            any(item.get("category") == "AI批量确认" for item in core_gate.review_issues)
        )


    def test_sync_blockers_show_in_export_gate_and_block_final(self):
        """sync_issues 中的 blocker 会阻断正式导出。"""
        source = _three_table_result()
        # 新增工序步骤 P99 和对应的高严重度 PFMEA 行（故意不加 CP 行）
        # pfmea_cp_coverage 条件是 AP="H" 或 severity >= 9，此处用 severity=9
        new_step = {
            "process_step_id": "P99",
            "sequence": 99,
            "operation": "Test orphan step",
            "process_function": "Step with PFMEA but no CP coverage",
            "owner": "Test",
            "evidence_refs": [],
        }
        source["process_flow"]["steps"].append(new_step)
        source["chain"]["process_steps"].append(new_step)
        orphan_row = {
            "pfmea_id": "PFMEA-P99-001",
            "process_step_id": "P99",
            "process_function": "Test orphan step",
            "failure_mode": "Orphan PFMEA without CP creates sync gap",
            "failure_effect": "Gap in three-table linkage",
            "severity": 9,
            "occurrence": 1,
            "detection": 1,
            "action_priority": "H",
        }
        source["pfmea"]["rows"].append(orphan_row)
        source["chain"]["failure_modes"].append(orphan_row)

        # 全部确认行（含新加的行）
        edited = apply_edit_patch(source, _confirm_all_patch(source))
        dashboard = edited.get("review_dashboard", {})

        # sync_blocker_count 应 > 0（PFMEA-P99-001 缺少对应 CP 行）
        self.assertGreater(dashboard.get("sync_blocker_count", 0), 0,
                           "应有同步阻断项，因为 P99/PFMEA-P99-001 没有对应的 CP 行")

        gate = evaluate_edit_export_gate(edited)
        self.assertFalse(
            gate["final_export_allowed"],
            "有 sync blocker 时 final_export_allowed 应为 False",
        )
        self.assertIn("sync_blocker_count", dashboard)
        self.assertFalse(dashboard["final_export_allowed"])

    # ------------------------------------------------------------------
    # V1.11 工作包 D+G：联动审计元数据 + 质量门收紧
    # ------------------------------------------------------------------



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
