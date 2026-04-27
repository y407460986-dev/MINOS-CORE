import copy
import unittest

from minos_desktop.table_editor import (
    AUTOMATION_BATCH_CONFIRM_MODE,
    AUTOMATION_REVIEW_SOURCE,
    action_management_model,
    automation_batch_confirm_patch,
    automation_fix_suggestion_patch,
    automation_review_model,
    build_edit_patch,
    change_impact_model,
    change_impact_patch_item,
    confirm_filtered_table_rows,
    confirm_table_row,
    filter_table_rows,
    filter_pfmea_rows,
    knowledge_recommendation_model,
    manual_review_model,
    manual_review_text,
    navigation_target_from_ref,
    new_table_row,
    recommendation_action_patch_item,
    restore_soft_delete_table_row,
    ROW_STATUS_COLUMN,
    soft_delete_table_row,
    table_row_status,
    table_rows_to_edit_patch_items,
    three_table_to_table_model,
)


def _result():
    return {
        "document_type": "three_table_generation_result",
        "process_flow": {
            "steps": [
                {
                    "process_step_id": "P10",
                    "sequence": 10,
                    "operation": "Incoming inspection",
                    "process_function": "Check material",
                    "product_characteristics": ["Material grade"],
                    "process_characteristics": ["Inspection coverage"],
                    "equipment": "Inspection bench",
                    "tooling": "Receiving fixture",
                    "gauges": ["Caliper"],
                    "document_refs": ["WI-001"],
                    "flow_type": "检验",
                    "owner": "IQC",
                    "input_refs": ["DRAWING-001"],
                    "output_refs": ["PFMEA-P10"],
                    "special_characteristics": ["SC-1"],
                    "evidence_refs": ["EV-1"],
                    "needs_confirmation": True,
                }
            ]
        },
        "pfmea": {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-001",
                    "process_step_id": "P10",
                    "process_item": "制造过程",
                    "process_step": "Incoming inspection",
                    "process_work_element": "Inspection bench",
                    "function_requirement": "Check material",
                    "failure_mode": "Wrong material accepted",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                    "recommended_action": "确认来料检验方法",
                    "responsibility": "IQC",
                    "target_date": "2026-05-10",
                    "action_status": "待执行",
                    "actual_completion_date": "",
                    "after_severity": "",
                    "after_occurrence": "",
                    "after_detection": "",
                    "after_ap": "",
                    "needs_confirmation": True,
                }
            ]
        },
        "control_plan": {
            "rows": [
                {
                    "control_plan_id": "CP-P10-001",
                    "process_step_id": "P10",
                    "pfmea_id": "PFMEA-P10-001",
                    "specification": "2.00 +/- 0.10 mm",
                    "measurement_method": "Caliper check",
                    "sample_frequency": "Each lot",
                    "reaction_plan": "隔离并通知质量工程师",
                    "needs_confirmation": True,
                }
            ]
        },
        "metadata": {
            "knowledge_recommendations": [
                {
                    "recommendation_id": "KR-1:PFMEA-P10-001",
                    "target_table": "pfmea",
                    "target_id": "PFMEA-P10-001",
                    "recommendation_type": "反应计划",
                    "source": "KR-1",
                    "reason": "建议补充反应计划",
                    "confidence": 0.9,
                    "suggested_fields": {"reaction_plan": "隔离"},
                    "status": "待确认",
                }
            ],
            "change_impacts": [
                {
                    "item_id": "pfmea:PFMEA-P10-001.PFMEA 控制/特性修改",
                    "category": "变更影响",
                    "target": "pfmea:PFMEA-P10-001",
                    "message": "CP 控制方法需同步确认",
                    "status": "待同步",
                    "ignore_reason": "",
                    "severity": "blocker",
                }
            ],
        },
        "drawing_analysis": {
            "evidence": [
                {
                    "evidence_id": "EV-1",
                    "page": 1,
                    "text": "Drawing note confirms incoming inspection requirement.",
                }
            ]
        },
        "manual_review": {
            "required": True,
            "summary": {"message": "需要复核"},
            "items": [
                {
                    "item_id": "failure_mode:PFMEA-P10-001",
                    "category": "失效模式复核",
                    "severity_display": "阻断",
                    "message": "确认失效模式是否覆盖图纸要求",
                    "evidence_refs": ["EV-1"],
                }
            ],
            "raw_count": 1,
        },
        "quality_gate": {
            "needs_confirmation_items": ["process_step:P10"],
        },
    }


def _result_without_open_change_impacts():
    result = _result()
    result["metadata"]["change_impacts"] = []
    return result


class DesktopTableEditorTests(unittest.TestCase):
    def test_three_table_result_converts_to_table_rows(self):
        model = three_table_to_table_model(_result(), "process_flow")

        self.assertEqual(model["row_id_field"], "process_step_id")
        self.assertEqual(model["columns"][0], ROW_STATUS_COLUMN)
        self.assertIn("operation", model["columns"])
        self.assertIn("product_characteristics", model["columns"])
        self.assertIn("process_characteristics", model["columns"])
        self.assertIn("equipment", model["columns"])
        self.assertIn("tooling", model["columns"])
        self.assertIn("gauges", model["columns"])
        self.assertIn("document_refs", model["columns"])
        self.assertIn("flow_type", model["columns"])
        self.assertEqual(model["column_labels"][model["columns"].index("operation")], "工序名称")
        self.assertEqual(
            model["column_labels"][model["columns"].index("process_function")],
            "工序目的/过程功能",
        )
        self.assertEqual(
            model["column_labels"][model["columns"].index("gauges")],
            "检具",
        )
        self.assertEqual(
            model["column_labels"][model["columns"].index("needs_confirmation")],
            "待人工确认",
        )
        self.assertEqual(model["rows"][0]["process_step_id"], "P10")
        self.assertEqual(model["rows"][0][ROW_STATUS_COLUMN], "待确认")
        self.assertEqual(model["rows"][0]["evidence_refs"], ["EV-1"])
        self.assertEqual(model["rows"][0]["document_refs"], ["WI-001"])
        self.assertEqual(model["rows"][0]["gauges"], ["Caliper"])

    def test_pfmea_model_displays_inherited_pfd_context(self):
        model = three_table_to_table_model(_result(), "pfmea")

        self.assertIn("operation", model["columns"])
        self.assertIn("process_item", model["columns"])
        self.assertIn("process_work_element", model["columns"])
        self.assertIn("function_requirement", model["columns"])
        self.assertIn("product_characteristics", model["columns"])
        self.assertIn("process_characteristics", model["columns"])
        self.assertEqual(model["rows"][0]["operation"], "Incoming inspection")
        self.assertEqual(model["rows"][0]["function_requirement"], "Check material")
        self.assertEqual(model["rows"][0]["product_characteristics"], ["Material grade"])

    def test_pfmea_model_refreshes_when_pfd_master_fields_change(self):
        result = _result()
        result["process_flow"]["steps"][0]["operation"] = "来料检验-已修改"
        result["process_flow"]["steps"][0]["process_function"] = "确认材料和版本已更新"
        result["process_flow"]["steps"][0]["equipment"] = "更新后的检验台"
        result["process_flow"]["steps"][0]["product_characteristics"] = ["更新后的材料牌号"]
        result["pfmea"]["rows"][0]["operation"] = "Incoming inspection"
        result["pfmea"]["rows"][0]["process_step"] = "Incoming inspection"
        result["pfmea"]["rows"][0]["function_requirement"] = "Check material"
        result["pfmea"]["rows"][0]["process_work_element"] = "Inspection bench"
        result["pfmea"]["rows"][0]["product_characteristics"] = ["Material grade"]

        model = three_table_to_table_model(result, "pfmea")

        self.assertEqual(model["rows"][0]["operation"], "来料检验-已修改")
        self.assertEqual(model["rows"][0]["process_step"], "来料检验-已修改")
        self.assertEqual(model["rows"][0]["function_requirement"], "确认材料和版本已更新")
        self.assertEqual(model["rows"][0]["process_work_element"], "更新后的检验台")
        self.assertEqual(model["rows"][0]["product_characteristics"], ["更新后的材料牌号"])

    def test_control_plan_model_displays_pfmea_source_and_controls(self):
        model = three_table_to_table_model(_result(), "control_plan")

        self.assertIn("pfmea_id", model["columns"])
        self.assertIn("failure_mode", model["columns"])
        self.assertIn("product_process_characteristic", model["columns"])
        self.assertIn("measurement_method", model["columns"])
        self.assertIn("sample_frequency", model["columns"])
        self.assertIn("reaction_plan", model["columns"])
        self.assertIn("gauges", model["columns"])
        self.assertEqual(model["column_labels"][model["columns"].index("pfmea_id")], "PFMEA 编号")
        self.assertEqual(model["rows"][0]["failure_mode"], "Wrong material accepted")
        self.assertEqual(model["rows"][0]["product_process_characteristic"], ["Material grade"])
        self.assertEqual(model["rows"][0]["measurement_method"], "Caliper check")
        self.assertEqual(model["rows"][0]["gauges"], ["Caliper"])

    def test_pfmea_and_control_plan_rows_hide_when_pfd_step_deleted(self):
        result = _result()
        result["process_flow"]["steps"][0]["deleted"] = True
        result["process_flow"]["steps"][0]["review_status"] = "软删除"

        pfmea_model = three_table_to_table_model(result, "pfmea")
        cp_model = three_table_to_table_model(result, "control_plan")

        self.assertEqual(pfmea_model["rows"], [])
        self.assertEqual(cp_model["rows"], [])

    def test_restore_soft_deleted_row_generates_update_patch(self):
        result = _result()
        result["process_flow"]["steps"][0]["deleted"] = True
        result["process_flow"]["steps"][0]["review_status"] = "软删除"
        model = three_table_to_table_model(result, "process_flow")

        restored = restore_soft_delete_table_row(model["rows"][0])
        items = table_rows_to_edit_patch_items("process_flow", [restored])

        self.assertEqual(restored[ROW_STATUS_COLUMN], "待确认")
        self.assertEqual(items[0]["action"], "update")
        self.assertEqual(items[0]["target_id"], "P10")
        self.assertFalse(items[0]["changes"]["deleted"])

    def test_inherited_display_fields_do_not_generate_patch_without_user_change(self):
        model = three_table_to_table_model(_result(), "pfmea")

        items = table_rows_to_edit_patch_items("pfmea", copy.deepcopy(model["rows"]))

        self.assertEqual(items, [])

    def test_modified_row_generates_update_patch(self):
        model = three_table_to_table_model(_result(), "pfmea")
        rows = copy.deepcopy(model["rows"])
        rows[0]["failure_mode"] = "Wrong grade material accepted"

        items = table_rows_to_edit_patch_items("pfmea", rows)

        self.assertEqual(items[0]["action"], "update")
        self.assertEqual(items[0]["target"], "failure_mode:PFMEA-P10-001")
        self.assertEqual(items[0]["target_id"], "PFMEA-P10-001")
        self.assertEqual(
            items[0]["changes"]["failure_mode"],
            "Wrong grade material accepted",
        )

    def test_confirm_generates_confirm_patch(self):
        model = three_table_to_table_model(_result(), "pfmea")
        row = confirm_table_row(model["rows"][0])

        items = table_rows_to_edit_patch_items("pfmea", [row])

        self.assertEqual(items[-1]["action"], "confirm")
        self.assertEqual(items[-1]["target"], "failure_mode:PFMEA-P10-001")
        self.assertEqual(items[-1]["target_id"], "PFMEA-P10-001")

    def test_soft_delete_generates_soft_delete_patch(self):
        model = three_table_to_table_model(_result(), "control_plan")
        row = soft_delete_table_row(model["rows"][0])

        items = table_rows_to_edit_patch_items("control_plan", [row])

        self.assertEqual(items[0]["action"], "soft_delete")
        self.assertEqual(items[0]["target"], "control_item:CP-P10-001")
        self.assertEqual(items[0]["target_id"], "CP-P10-001")

    def test_row_status_filter_and_batch_confirm_helpers(self):
        model = three_table_to_table_model(_result_without_open_change_impacts(), "pfmea")
        rows = copy.deepcopy(model["rows"])
        rows.append(new_table_row("pfmea", rows, {"pfmea_id": "PFMEA-P20-001"}))

        self.assertEqual(table_row_status("pfmea", rows[0]), "待确认")
        self.assertEqual(table_row_status("pfmea", rows[1]), "新增")
        self.assertEqual(len(filter_table_rows("pfmea", rows, "待确认")), 1)

        confirmed = confirm_filtered_table_rows("pfmea", rows, "待确认")

        self.assertEqual(confirmed[0][ROW_STATUS_COLUMN], "已确认")
        self.assertFalse(confirmed[0]["needs_confirmation"])
        self.assertEqual(confirmed[1][ROW_STATUS_COLUMN], "新增")

    def test_automation_review_statuses_display_in_chinese(self):
        result = _result_without_open_change_impacts()
        result["manual_review"] = {"required": False, "items": []}
        result["quality_gate"] = {}
        result["pfmea"]["rows"][0]["review_status"] = "AI建议确认"
        result["pfmea"]["rows"][0]["confidence"] = 0.91
        result["pfmea"]["rows"][0]["evidence_refs"] = ["EV-1"]

        model = three_table_to_table_model(result, "pfmea")
        review = automation_review_model(result)

        self.assertEqual(model["rows"][0][ROW_STATUS_COLUMN], "AI建议确认")
        self.assertEqual(review["title"], "AI 预审")
        self.assertEqual(review["column_labels"][0], "预审分类")
        self.assertTrue(review["rows"])
        self.assertIn("suggested_changes_display", review["columns"])

    def test_automation_batch_confirm_patch_marks_each_candidate(self):
        result = _result_without_open_change_impacts()
        result["process_flow"]["steps"][0]["special_characteristics"] = []
        result["manual_review"] = {"required": False, "items": []}
        result["quality_gate"] = {}
        result["metadata"]["knowledge_recommendations"] = []
        result["pfmea"]["rows"][0]["review_status"] = "AI建议确认"
        result["pfmea"]["rows"][0]["action_priority"] = "L"
        result["pfmea"]["rows"][0]["confidence"] = 0.91
        result["pfmea"]["rows"][0]["evidence_refs"] = ["EV-1"]

        patch = automation_batch_confirm_patch(automation_review_model(result))

        item = next(item for item in patch["items"] if item["target_id"] == "PFMEA-P10-001")
        self.assertEqual(item["action"], "confirm")
        self.assertEqual(item["source"], AUTOMATION_REVIEW_SOURCE)
        self.assertEqual(item["confirmation_mode"], AUTOMATION_BATCH_CONFIRM_MODE)

    def test_automation_fix_suggestion_patch_updates_row_and_accepts_recommendation(self):
        patch = automation_fix_suggestion_patch(
            {
                "target_table": "pfmea",
                "target_id": "PFMEA-P10-001",
                "suggested_changes": {"recommended_action": "追加防错确认"},
                "recommendation_id": "KR-1:PFMEA-P10-001",
            }
        )

        self.assertEqual(patch["items"][0]["action"], "update")
        self.assertEqual(patch["items"][0]["changes"]["recommended_action"], "追加防错确认")
        self.assertEqual(patch["items"][1]["action"], "accept_recommendation")

    def test_automation_review_displays_no_auto_fix_text_instead_of_empty_dict(self):
        result = _result_without_open_change_impacts()
        result["manual_review"] = {
            "required": True,
            "items": [
                {
                    "item_id": "RI-global",
                    "category": "人工复核问题",
                    "severity": "blocker",
                    "severity_display": "阻断",
                    "message": "正式导出前，未处理的人工复核问题必须先关闭。",
                }
            ],
        }

        review = automation_review_model(result)
        row = next(item for item in review["rows"] if item["issue_id"] == "RI-global")

        self.assertEqual(row["suggested_changes"], {})
        self.assertEqual(
            row["suggested_changes_display"],
            "暂无可一键采纳的字段修改；请按预审说明人工确认或在对应表格中修改。",
        )
        self.assertFalse(automation_fix_suggestion_patch(row)["items"])

    def test_automation_review_expands_review_issue_to_concrete_row(self):
        result = _result_without_open_change_impacts()
        issue_id = "RI-ai-batch-blocker"
        result["manual_review"] = {
            "required": True,
            "items": [
                {
                    "item_id": issue_id,
                    "category": "人工复核问题",
                    "severity": "blocker",
                    "severity_display": "阻断",
                    "message": "正式导出前，未处理的人工复核问题必须先关闭。",
                }
            ],
        }
        result["quality_gate"] = {
            "review_issues": [
                {
                    "issue_id": issue_id,
                    "category": "AI批量确认",
                    "message": "PFMEA 高 AP 风险不能批量确认，需要人工复核。",
                    "severity": "blocker",
                    "target": "failure_mode:PFMEA-P10-001",
                }
            ]
        }

        review = automation_review_model(result)

        row = next(item for item in review["rows"] if item["issue_id"] == issue_id)
        self.assertEqual(row["target_table"], "pfmea")
        self.assertEqual(row["target_id"], "PFMEA-P10-001")
        self.assertEqual(row["review_message"], "PFMEA 高 AP 风险不能批量确认，需要人工复核。")
        self.assertEqual(row["jump_label"], "跳转到 PFMEA：PFMEA-P10-001")
        self.assertFalse(
            any(not item["target_table"] and not item["target_id"] for item in review["rows"])
        )

    def test_automation_review_unlocated_issue_points_to_manual_review_page(self):
        result = _result_without_open_change_impacts()
        result["manual_review"] = {
            "required": True,
            "items": [
                {
                    "item_id": "RI-global",
                    "category": "人工复核问题",
                    "severity": "blocker",
                    "severity_display": "阻断",
                    "message": "正式导出前，未处理的人工复核问题必须先关闭。",
                }
            ],
        }

        review = automation_review_model(result)

        row = next(item for item in review["rows"] if item["issue_id"] == "RI-global")
        self.assertEqual(row["target_table"], "人工复核")
        self.assertEqual(row["target_id"], "RI-global")
        self.assertEqual(row["jump_label"], "查看人工复核页")

    def test_new_row_generates_add_patch(self):
        row = new_table_row(
            "process_flow",
            values={
                "process_step_id": "P20",
                "sequence": 20,
                "operation": "Assembly",
            },
        )

        items = table_rows_to_edit_patch_items("process_flow", [row])

        self.assertEqual(items[0]["action"], "add")
        self.assertEqual(items[0]["target"], "process_step:P20")
        self.assertEqual(items[0]["target_id"], "P20")
        self.assertEqual(items[0]["row"]["operation"], "Assembly")

    def test_action_management_model_flags_pending_and_filters_pfmea(self):
        result = _result()
        result["pfmea"]["rows"][0]["action_priority"] = "H"
        result["pfmea"]["rows"][0]["recommended_action"] = ""

        model = action_management_model(result)
        filtered = filter_pfmea_rows(result, "AP 高")

        self.assertEqual(model["rows"][0]["status_display"], "待制定措施")
        self.assertEqual(filtered[0]["pfmea_id"], "PFMEA-P10-001")

    def test_knowledge_and_change_models_build_metadata_patch_items(self):
        result = _result()

        knowledge = knowledge_recommendation_model(result)
        impacts = change_impact_model(result)
        recommendation_item = recommendation_action_patch_item(
            "KR-1:PFMEA-P10-001",
            "ignore_recommendation",
            reason="已有等效控制",
        )
        impact_item = change_impact_patch_item(
            "pfmea:PFMEA-P10-001.PFMEA 控制/特性修改",
            status="已处理",
        )
        patch = build_edit_patch([recommendation_item, impact_item])

        self.assertEqual(knowledge["rows"][0]["reason"], "建议补充反应计划")
        self.assertEqual(knowledge["rows"][0]["jump_target"], "pfmea:PFMEA-P10-001")
        self.assertEqual(impacts["rows"][0]["status"], "待同步")
        self.assertEqual(impacts["rows"][0]["jump_target"], "pfmea:PFMEA-P10-001")
        self.assertEqual(patch["items"][0]["action"], "ignore_recommendation")
        self.assertEqual(patch["items"][1]["action"], "resolve_change_impact")

    def test_actions_change_and_recommendation_models_include_jump_info(self):
        result = _result()

        actions = action_management_model(result)
        impacts = change_impact_model(result)
        knowledge = knowledge_recommendation_model(result)

        self.assertEqual(actions["rows"][0]["jump_target"], "pfmea:PFMEA-P10-001")
        self.assertEqual(impacts["rows"][0]["jump_label"], "跳转到 PFMEA：PFMEA-P10-001")
        self.assertEqual(knowledge["rows"][0]["jump_label"], "跳转到 PFMEA：PFMEA-P10-001")
        self.assertEqual(navigation_target_from_ref("failure_mode:PFMEA-P10-001"), "pfmea:PFMEA-P10-001")

    def test_manual_review_model_builds_chinese_questions_with_evidence(self):
        display = manual_review_model(_result())
        text = manual_review_text(_result())

        self.assertTrue(display["需要人工复核"])
        self.assertEqual(display["问题列表"][0]["问题"], "失效模式复核（阻断）")
        self.assertIn("EV-1", display["问题列表"][0]["证据信息"])
        self.assertIn("确认失效模式是否覆盖图纸要求", text)
        self.assertIn("跳转到 PFD：P10", text)


if __name__ == "__main__":
    unittest.main()
