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
from minos_core.knowledge_recommendation import recommend_from_knowledge
from minos_core.quality_gates import evaluate_export_gate


ROOT_FIXTURE = "D:/MINOS-CORE/tests/fixtures/apqp_chain"
NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _fixture() -> dict:
    return load_fixture_payload(ROOT_FIXTURE)


def _three_table_result() -> dict:
    payload = _fixture()
    return {
        "document_type": "three_table_generation_result",
        "schema_version": "minos-core.three_table_generation_result.v1",
        "status": "needs_review",
        "status_display": "待人工复核",
        "blocked_stage": None,
        "drawing_analysis": {"evidence": copy.deepcopy(payload["evidence"])},
        "process_flow": copy.deepcopy(payload["process_flow"]),
        "pfmea": copy.deepcopy(payload["pfmea"]),
        "control_plan": copy.deepcopy(payload["control_plan"]),
        "chain": {
            "document_type": "apqp_chain",
            "schema_version": "minos-core.generated.v1",
            "product": copy.deepcopy(payload["process_flow"]["product"]),
            "process_steps": copy.deepcopy(payload["process_flow"]["steps"]),
            "failure_modes": copy.deepcopy(payload["pfmea"]["rows"]),
            "controls": copy.deepcopy(payload["control_plan"]["rows"]),
            "evidence": copy.deepcopy(payload["evidence"]),
            "links": copy.deepcopy(payload["process_flow"]["links"]),
            "metadata": {},
        },
        "quality_gate": {},
        "quality_gates": {},
        "exports": {},
        "manifest": {},
        "manual_review": {"required": True, "items": []},
        "warnings": [],
    }


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
            with self.assertRaises(EditPatchError):
                export_edited_three_tables(edited, Path(tmpdir), export_mode="final")

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

    def test_final_export_raises_when_unconfirmed_and_succeeds_after_confirmed(self):
        source = _three_table_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(EditPatchError):
                export_edited_three_tables(source, Path(tmpdir), export_mode="final")

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

    def test_ai_batch_confirmation_audit_blocks_ineligible_rows(self):
        source = apply_edit_patch(_three_table_result(), _confirm_all_patch(_three_table_result()))
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

    def test_automation_review_builds_core_batch_confirm_candidates(self):
        source = _automation_chain()
        review = build_automation_review(source)

        candidate_targets = {item["target"] for item in review["batch_confirm_candidates"]}
        self.assertIn("process_step:P10", candidate_targets)
        self.assertIn("failure_mode:PFMEA-P10-OK", candidate_targets)
        self.assertIn("control_item:CP-P10-OK", candidate_targets)
        self.assertNotIn("process_step:P20", candidate_targets)
        self.assertNotIn("failure_mode:PFMEA-P10-HIGH", candidate_targets)
        self.assertNotIn("failure_mode:PFMEA-P10-LOW", candidate_targets)
        messages = "；".join(item["message"] for item in review["automation_tasks"])
        self.assertIn("特殊特性必须人工确认", messages)
        self.assertIn("高 AP 风险必须人工确认", messages)
        self.assertIn("置信度低于 0.85", messages)

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
    for recommendation in recommend_from_knowledge(source):
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
