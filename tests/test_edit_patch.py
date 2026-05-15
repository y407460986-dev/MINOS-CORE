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

    def test_final_export_raises_when_unconfirmed_and_succeeds_after_confirmed(self):
        source = _three_table_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_edited_three_tables(source, Path(tmpdir), export_mode="final")
            self.assertFalse(result["final_export_allowed"])

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

    # ── knowledge recommendation edit-loop tests ────────────────────────

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
