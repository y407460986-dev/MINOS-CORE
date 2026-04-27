"""Helpers for the desktop three-table editor.

The Qt layer keeps these helpers UI-neutral so table edits can be tested without
starting a desktop session.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from minos_core.change_management import analyze_change_impacts
from minos_core.knowledge_recommendation import unresolved_recommendations


EDIT_PATCH_VERSION = "minos-core.edit_patch.v1"

META_ROW_ID = "_row_id"
META_ORIGINAL = "_original"
META_IS_NEW = "_is_new"
META_SOFT_DELETED = "_soft_deleted"
META_CONFIRMED = "_confirmed"
ROW_STATUS_COLUMN = "row_status"
AUTOMATION_REVIEW_SOURCE = "automation_review"
AUTOMATION_BATCH_CONFIRM_MODE = "ai_recommended_batch"


@dataclass(frozen=True)
class TableSpec:
    key: str
    result_key: str
    container_key: str
    row_id_field: str
    target_prefix: str
    title: str
    columns: tuple[str, ...]


COLUMN_LABELS: dict[str, str] = {
    "process_step_id": "工序编号",
    "sequence": "顺序",
    "operation": "工序名称",
    "process_function": "工序目的/过程功能",
    "process_item": "过程项",
    "process_step": "过程步骤",
    "process_work_element": "过程工作要素",
    "function_requirement": "功能/要求",
    "product_characteristic": "产品特性",
    "product_characteristics": "产品特性",
    "process_characteristic": "过程特性",
    "process_characteristics": "过程特性",
    "equipment": "设备",
    "tooling": "工装",
    "fixture": "工装",
    "gauge": "检具",
    "gauges": "检具",
    "gages": "检具",
    "inspection_equipment": "检具",
    "document_refs": "文件",
    "documents": "文件",
    "flow_type": "流程类型",
    "process_type": "流程类型",
    "owner": "责任岗位",
    "input_refs": "输入依据",
    "output_refs": "输出关联",
    "special_characteristics": "特殊特性",
    "evidence_refs": "证据",
    "needs_confirmation": "待人工确认",
    "pfmea_id": "PFMEA 编号",
    "source_pfmea_id": "PFMEA 来源",
    "failure_mode": "失效模式",
    "failure_effect": "失效后果",
    "severity": "严重度 S",
    "failure_cause": "失效原因",
    "occurrence": "发生度 O",
    "prevention_control": "预防控制",
    "detection_control": "探测控制",
    "detection": "探测度 D",
    "action_priority": "措施优先级 AP",
    "rpn": "RPN",
    "recommended_action": "推荐措施",
    "responsibility": "责任人",
    "target_date": "目标完成日期",
    "action_status": "措施状态",
    "actual_completion_date": "实际完成日期",
    "after_severity": "措施后 S",
    "after_occurrence": "措施后 O",
    "after_detection": "措施后 D",
    "after_ap": "措施后 AP",
    "after_rpn": "措施后 RPN",
    "remarks": "备注",
    "classification": "分类",
    "linked_control_plan_id": "关联控制计划",
    "control_plan_id": "控制计划编号",
    "product_process_characteristic": "产品/过程特性",
    "characteristic": "特性",
    "specification": "规格要求",
    "tolerance": "规格要求",
    "measurement_method": "测量方法",
    "sample_size": "样本容量",
    "sample_frequency": "检查频次",
    "frequency": "频次",
    "control_method": "控制方法",
    "reaction_plan": "反应计划",
    ROW_STATUS_COLUMN: "行状态",
    "jump_target": "跳转目标",
    "jump_label": "跳转",
    "review_category": "预审分类",
    "review_message": "预审说明",
    "risk_level": "风险等级",
    "suggested_changes": "建议修改",
    "recommendation_id": "建议编号",
}

ROW_STATUS_FILTERS = (
    "全部",
    "AI建议确认",
    "已批量确认",
    "需人工判断",
    "必须修复",
    "待确认",
    "已修改",
    "新增",
    "软删除",
    "已确认",
    "问题未处理",
)


TABLE_SPECS: dict[str, TableSpec] = {
    "process_flow": TableSpec(
        key="process_flow",
        result_key="process_flow",
        container_key="steps",
        row_id_field="process_step_id",
        target_prefix="process_step",
        title="PFD",
        columns=(
            "process_step_id",
            "sequence",
            "operation",
            "process_function",
            "product_characteristics",
            "process_characteristics",
            "equipment",
            "tooling",
            "gauges",
            "document_refs",
            "flow_type",
            "owner",
            "evidence_refs",
            "needs_confirmation",
        ),
    ),
    "pfmea": TableSpec(
        key="pfmea",
        result_key="pfmea",
        container_key="rows",
        row_id_field="pfmea_id",
        target_prefix="failure_mode",
        title="PFMEA",
        columns=(
            "pfmea_id",
            "process_step_id",
            "operation",
            "process_item",
            "process_step",
            "process_work_element",
            "function_requirement",
            "product_characteristics",
            "process_characteristics",
            "failure_mode",
            "failure_effect",
            "severity",
            "failure_cause",
            "occurrence",
            "prevention_control",
            "detection_control",
            "detection",
            "action_priority",
            "rpn",
            "recommended_action",
            "responsibility",
            "target_date",
            "action_status",
            "actual_completion_date",
            "after_severity",
            "after_occurrence",
            "after_detection",
            "after_ap",
            "classification",
            "linked_control_plan_id",
            "remarks",
            "evidence_refs",
            "needs_confirmation",
        ),
    ),
    "control_plan": TableSpec(
        key="control_plan",
        result_key="control_plan",
        container_key="rows",
        row_id_field="control_plan_id",
        target_prefix="control_item",
        title="控制计划",
        columns=(
            "control_plan_id",
            "process_step_id",
            "pfmea_id",
            "failure_mode",
            "product_process_characteristic",
            "specification",
            "classification",
            "measurement_method",
            "sample_size",
            "sample_frequency",
            "control_method",
            "reaction_plan",
            "gauges",
            "inspection_equipment",
            "evidence_refs",
            "needs_confirmation",
        ),
    ),
}


def table_spec(table_key: str) -> TableSpec:
    try:
        return TABLE_SPECS[table_key]
    except KeyError as exc:
        raise ValueError(f"unknown editable table: {table_key}") from exc


def column_label(column: str) -> str:
    return COLUMN_LABELS.get(column, f"扩展字段（{column}）")


def three_table_to_table_model(
    result: dict[str, Any],
    table_key: str,
) -> dict[str, Any]:
    spec = table_spec(table_key)
    document = result.get(spec.result_key, {}) if isinstance(result, dict) else {}
    rows = document.get(spec.container_key, []) if isinstance(document, dict) else []
    columns = [ROW_STATUS_COLUMN, *_columns_for_rows(spec, rows)]
    table_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        enriched = _with_inherited_display_fields(result, spec, row)
        if enriched.get("_hidden_by_upstream_deleted"):
            continue
        table_rows.append(document_row_to_table_row(spec, enriched))
    return {
        "table_key": spec.key,
        "title": spec.title,
        "row_id_field": spec.row_id_field,
        "columns": columns,
        "column_labels": [column_label(column) for column in columns],
        "rows": table_rows,
    }


def document_row_to_table_row(spec: TableSpec, row: dict[str, Any]) -> dict[str, Any]:
    row_copy = copy.deepcopy(row)
    table_row: dict[str, Any] = {
        META_ROW_ID: str(row.get(spec.row_id_field, "")),
        META_ORIGINAL: row_copy,
        META_IS_NEW: False,
        META_SOFT_DELETED: bool(row.get("soft_deleted", False) or row.get("deleted", False)),
        META_CONFIRMED: row.get("review_status") == "已确认" and row.get("needs_confirmation") is False,
        "_has_open_issue": bool(row.get("_has_open_issue", False)),
        "_open_issue": str(row.get("_open_issue", "")),
    }
    for column in _columns_for_rows(spec, [row]):
        table_row[column] = _cell_value(row.get(column, ""))
    table_row[ROW_STATUS_COLUMN] = table_row_status(spec.key, table_row)
    return table_row


def new_table_row(
    table_key: str,
    existing_rows: list[dict[str, Any]] | None = None,
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = table_spec(table_key)
    values = dict(values or {})
    row_id = str(values.get(spec.row_id_field) or _next_new_row_id(spec, existing_rows or []))
    values[spec.row_id_field] = row_id
    row: dict[str, Any] = {
        META_ROW_ID: row_id,
        META_ORIGINAL: {},
        META_IS_NEW: True,
        META_SOFT_DELETED: False,
        META_CONFIRMED: False,
    }
    for column in spec.columns:
        row[column] = _cell_value(values.get(column, False if column == "needs_confirmation" else ""))
    row[ROW_STATUS_COLUMN] = table_row_status(table_key, row)
    return row


def soft_delete_table_row(row: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(row)
    updated[META_SOFT_DELETED] = True
    updated[ROW_STATUS_COLUMN] = table_row_status("", updated)
    return updated


def restore_soft_delete_table_row(row: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(row)
    updated[META_SOFT_DELETED] = False
    updated["deleted"] = False
    updated["soft_deleted"] = False
    if updated.get("review_status") == "软删除":
        updated["review_status"] = "待确认"
    updated[ROW_STATUS_COLUMN] = table_row_status("", updated)
    return updated


def confirm_table_row(row: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(row)
    updated[META_CONFIRMED] = True
    if "needs_confirmation" in updated:
        updated["needs_confirmation"] = False
    updated[ROW_STATUS_COLUMN] = table_row_status("", updated)
    return updated


def table_row_status(table_key: str, row: dict[str, Any]) -> str:
    if row.get(META_SOFT_DELETED):
        return "软删除"
    review_status = str(row.get("review_status", "")).strip()
    automation_status = str(row.get("automation_review_status", "")).strip()
    if review_status == "已批量确认" or automation_status == "已批量确认":
        return "已批量确认"
    if row.get("_has_open_issue"):
        return "问题未处理"
    if review_status in {"必须修复", "阻断问题"} or automation_status in {"必须修复", "阻断问题"}:
        return "必须修复"
    if review_status in {"需人工判断", "需要人工判断"} or automation_status in {"需人工判断", "需要人工判断"}:
        return "需人工判断"
    if review_status == "AI建议确认" or automation_status == "AI建议确认":
        return "AI建议确认"
    if row.get(META_IS_NEW):
        return "新增"
    if row.get(META_CONFIRMED):
        return "已确认"
    if row.get("needs_confirmation"):
        return "待确认"
    if table_key and _table_row_changed(table_key, row):
        return "已修改"
    return "未修改"


def refresh_table_row_status(table_key: str, row: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(row)
    updated[ROW_STATUS_COLUMN] = table_row_status(table_key, updated)
    return updated


def filter_table_rows(
    table_key: str,
    rows: list[dict[str, Any]],
    filter_key: str = "全部",
) -> list[dict[str, Any]]:
    if filter_key in {"", "全部"}:
        return list(rows)
    return [
        row
        for row in rows
        if isinstance(row, dict) and table_row_status(table_key, row) == filter_key
    ]


def filtered_table_row_indexes(
    table_key: str,
    rows: list[dict[str, Any]],
    filter_key: str = "全部",
) -> list[int]:
    if filter_key in {"", "全部"}:
        return list(range(len(rows)))
    return [
        index
        for index, row in enumerate(rows)
        if isinstance(row, dict) and table_row_status(table_key, row) == filter_key
    ]


def confirm_filtered_table_rows(
    table_key: str,
    rows: list[dict[str, Any]],
    filter_key: str = "全部",
) -> list[dict[str, Any]]:
    indexes = set(filtered_table_row_indexes(table_key, rows, filter_key))
    confirmed: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        confirmed.append(confirm_table_row(row) if index in indexes else copy.deepcopy(row))
    return confirmed


def table_rows_to_edit_patch_items(
    table_key: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    spec = table_spec(table_key)
    items: list[dict[str, Any]] = []
    for row in rows:
        normalized = _normalize_row_values(spec, row)
        row_id = _effective_row_id(spec, row, normalized)
        target = f"{spec.target_prefix}:{row_id}"
        is_new = bool(row.get(META_IS_NEW))
        soft_deleted = bool(row.get(META_SOFT_DELETED))
        confirmed = bool(row.get(META_CONFIRMED))

        if is_new:
            if not soft_deleted:
                items.append(
                    {
                        "action": "add",
                        "table": spec.key,
                        "target": target,
                        "target_id": row_id,
                        "row_id": row_id,
                        "row": normalized,
                    }
                )
            continue

        if soft_deleted:
            items.append(
                {
                    "action": "soft_delete",
                    "table": spec.key,
                    "target": target,
                    "target_id": row_id,
                    "row_id": row_id,
                }
            )
        else:
            original = row.get(META_ORIGINAL, {})
            changes = _changed_fields(spec, normalized, original if isinstance(original, dict) else {})
            if changes:
                items.append(
                    {
                        "action": "update",
                        "table": spec.key,
                        "target": target,
                        "target_id": row_id,
                        "row_id": row_id,
                        "changes": changes,
                        "row": normalized,
                    }
                )

        if confirmed:
            items.append(
                {
                    "action": "confirm",
                    "table": spec.key,
                    "target": target,
                    "target_id": row_id,
                    "row_id": row_id,
                }
            )
    return items


def build_edit_patch(
    items: list[dict[str, Any]],
    *,
    patch_version: str = EDIT_PATCH_VERSION,
) -> dict[str, Any]:
    return {
        "edit_patch_version": patch_version,
        "items": list(items),
    }


def table_rows_to_edit_patch(
    rows_by_table: dict[str, list[dict[str, Any]]],
    *,
    patch_version: str = EDIT_PATCH_VERSION,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for table_key in ("process_flow", "pfmea", "control_plan"):
        items.extend(table_rows_to_edit_patch_items(table_key, rows_by_table.get(table_key, [])))
    return build_edit_patch(items, patch_version=patch_version)


def automation_review_model(result: dict[str, Any]) -> dict[str, Any]:
    """Build a UI-neutral AI pre-review model for desktop review screens."""

    rows: list[dict[str, Any]] = []
    explicit_items = _automation_review_items(result)
    if explicit_items:
        rows.extend(_automation_review_row(item, result) for item in explicit_items)
    else:
        rows.extend(_automation_review_rows_from_tables(result))
        rows.extend(_automation_review_rows_from_manual_review(result))
        rows.extend(_automation_review_rows_from_metadata(result))
    rows = _dedupe_automation_rows(rows)
    return {
        "title": "AI 预审",
        "summary": {
            "可批量确认数量": sum(1 for row in rows if row.get("review_category") == "可批量确认"),
            "需要人工判断数量": sum(1 for row in rows if row.get("review_category") == "需要人工判断"),
            "阻断数量": sum(1 for row in rows if row.get("review_category") == "阻断问题"),
        },
        "columns": (
            "review_category",
            "target_table",
            "target_id",
            "review_message",
            "risk_level",
            "confidence",
            "suggested_changes_display",
            "recommendation_id",
            "jump_label",
        ),
        "column_labels": (
            "预审分类",
            "目标表",
            "目标行",
            "预审说明",
            "风险等级",
            "置信度",
            "AI 修复建议",
            "建议编号",
            "跳转",
        ),
        "rows": [_with_suggestion_display(row) for row in rows],
    }


def automation_batch_confirm_patch_items(
    result_or_model: dict[str, Any],
) -> list[dict[str, Any]]:
    model = _ensure_automation_model(result_or_model)
    items: list[dict[str, Any]] = []
    for row in model.get("rows", []):
        if not isinstance(row, dict) or row.get("review_category") != "可批量确认":
            continue
        table = str(row.get("target_table", ""))
        if table not in TABLE_SPECS:
            continue
        target_id = str(row.get("target_id", "")).strip()
        if not target_id:
            continue
        spec = TABLE_SPECS[table]
        items.append(
            {
                "action": "confirm",
                "table": table,
                "target": f"{spec.target_prefix}:{target_id}",
                "target_id": target_id,
                "row_id": target_id,
                "confirmation_mode": AUTOMATION_BATCH_CONFIRM_MODE,
                "source": AUTOMATION_REVIEW_SOURCE,
            }
        )
    return items


def automation_batch_confirm_patch(
    result_or_model: dict[str, Any],
    *,
    patch_version: str = EDIT_PATCH_VERSION,
) -> dict[str, Any]:
    return build_edit_patch(
        automation_batch_confirm_patch_items(result_or_model),
        patch_version=patch_version,
    )


def automation_fix_suggestion_patch_items(
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    table = str(row.get("target_table", "")).strip()
    target_id = str(row.get("target_id", "")).strip()
    changes = row.get("suggested_changes", {})
    if isinstance(changes, str):
        try:
            changes = json.loads(changes)
        except json.JSONDecodeError:
            changes = {}
    if table not in TABLE_SPECS or not target_id or not isinstance(changes, dict) or not changes:
        return []
    spec = TABLE_SPECS[table]
    items: list[dict[str, Any]] = [
        {
            "action": "update",
            "table": table,
            "target": f"{spec.target_prefix}:{target_id}",
            "target_id": target_id,
            "row_id": target_id,
            "changes": copy.deepcopy(changes),
            "source": AUTOMATION_REVIEW_SOURCE,
        }
    ]
    recommendation_id = str(row.get("recommendation_id", "")).strip()
    if recommendation_id:
        items.append(
            recommendation_action_patch_item(
                recommendation_id,
                "accept_recommendation",
                reason="采纳 AI 预审修复建议",
            )
        )
    issue_id = str(row.get("issue_id", "")).strip()
    if issue_id:
        items.append(
            {
                "action": "resolve_review_issue",
                "table": "metadata",
                "target_id": issue_id,
                "changes": {"status": "已处理"},
                "reason": "采纳 AI 预审修复建议",
            }
        )
    return items


def automation_fix_suggestion_patch(
    row: dict[str, Any],
    *,
    patch_version: str = EDIT_PATCH_VERSION,
) -> dict[str, Any]:
    return build_edit_patch(
        automation_fix_suggestion_patch_items(row),
        patch_version=patch_version,
    )


def _with_suggestion_display(row: dict[str, Any]) -> dict[str, Any]:
    updated = dict(row)
    updated["suggested_changes_display"] = _suggested_changes_text(row)
    return updated


def _suggested_changes_text(row: dict[str, Any]) -> str:
    changes = row.get("suggested_changes", {})
    if isinstance(changes, dict) and changes:
        return json.dumps(changes, ensure_ascii=False)
    if isinstance(changes, str) and changes.strip():
        return changes.strip()
    if row.get("review_category") == "可批量确认":
        return "无需改表，AI 建议可批量确认。"
    return "暂无可一键采纳的字段修改；请按预审说明人工确认或在对应表格中修改。"


def action_management_model(result: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    rows: list[dict[str, Any]] = []
    for row in _pfmea_rows(result):
        ap = str(row.get("action_priority", row.get("AP", ""))).upper()
        status = str(row.get("action_status", ""))
        target_date = str(row.get("target_date", ""))
        overdue = _is_overdue(target_date, status, today)
        pending_after = bool(_missing_after_evaluation(row))
        pending_action = _pending_action(row, ap)
        pfmea_id = str(row.get("pfmea_id", ""))
        rows.append(
            {
                "pfmea_id": pfmea_id,
                "process_step_id": row.get("process_step_id", ""),
                "failure_mode": row.get("failure_mode", ""),
                "action_priority": ap,
                "recommended_action": row.get("recommended_action", ""),
                "responsibility": row.get("responsibility", ""),
                "target_date": target_date,
                "action_status": status,
                "actual_completion_date": row.get("actual_completion_date", ""),
                "after_severity": row.get("after_severity", ""),
                "after_occurrence": row.get("after_occurrence", ""),
                "after_detection": row.get("after_detection", ""),
                "after_ap": row.get("after_ap", ""),
                "overdue": overdue,
                "pending_action": pending_action,
                "pending_after_evaluation": pending_after,
                "status_display": _action_status_display(
                    ap,
                    overdue=overdue,
                    pending_action=pending_action,
                    pending_after=pending_after,
                ),
                "jump_target": navigation_target("pfmea", pfmea_id),
                "jump_label": navigation_label("pfmea", pfmea_id),
            }
        )
    return {
        "title": "措施管理",
        "columns": (
            "pfmea_id",
            "process_step_id",
            "failure_mode",
            "action_priority",
            "recommended_action",
            "responsibility",
            "target_date",
            "action_status",
            "actual_completion_date",
            "after_severity",
            "after_occurrence",
            "after_detection",
            "after_ap",
            "status_display",
            "jump_label",
        ),
        "column_labels": (
            "PFMEA 编号",
            "工序编号",
            "失效模式",
            "AP",
            "推荐措施",
            "责任人",
            "目标完成日期",
            "措施状态",
            "实际完成日期",
            "措施后 S",
            "措施后 O",
            "措施后 D",
            "措施后 AP",
            "状态",
            "跳转",
        ),
        "rows": rows,
    }


def filter_pfmea_rows(result: dict[str, Any], filter_key: str, *, today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    rows = list(_pfmea_rows(result))
    if filter_key in {"", "全部"}:
        return rows
    recommendation_targets = {
        str(item.get("target_id", ""))
        for item in unresolved_recommendations(_knowledge_recommendations(result))
    }
    change_targets = {
        str(item.get("target", "")).split(":", 1)[-1]
        for item in change_impact_model(result)["rows"]
        if item.get("status") not in {"已处理", "无影响"}
    }
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ap = str(row.get("action_priority", row.get("AP", ""))).upper()
        status = str(row.get("action_status", ""))
        row_id = str(row.get("pfmea_id", ""))
        if filter_key == "AP 高" and ap == "H":
            filtered.append(row)
        elif filter_key == "AP 中" and ap == "M":
            filtered.append(row)
        elif filter_key == "逾期" and _is_overdue(str(row.get("target_date", "")), status, today):
            filtered.append(row)
        elif filter_key == "待措施" and _pending_action(row, ap):
            filtered.append(row)
        elif filter_key == "待措施后评价" and _missing_after_evaluation(row):
            filtered.append(row)
        elif filter_key == "待确认" and row.get("needs_confirmation"):
            filtered.append(row)
        elif filter_key == "知识库推荐待处理" and row_id in recommendation_targets:
            filtered.append(row)
        elif filter_key == "变更影响待处理" and row_id in change_targets:
            filtered.append(row)
    return filtered


def change_impact_model(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
    impacts = metadata.get("change_impacts", []) if isinstance(metadata, dict) else []
    if not isinstance(impacts, list) or not impacts:
        impacts = analyze_change_impacts(result)
    rows = []
    for item in impacts:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["jump_target"] = navigation_target_from_ref(str(row.get("target", "")))
        row["jump_label"] = navigation_label_from_target(row["jump_target"])
        rows.append(row)
    return {
        "title": "变更影响",
        "columns": ("item_id", "category", "target", "message", "status", "ignore_reason", "severity", "jump_label"),
        "column_labels": ("影响编号", "类别", "对象", "影响说明", "状态", "忽略原因", "严重度", "跳转"),
        "rows": rows,
    }


def knowledge_recommendation_model(result: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in _knowledge_recommendations(result):
        row = dict(item)
        row["jump_target"] = navigation_target(str(row.get("target_table", "")), str(row.get("target_id", "")))
        row["jump_label"] = navigation_label_from_target(row["jump_target"])
        rows.append(row)
    return {
        "title": "知识库推荐",
        "columns": (
            "recommendation_id",
            "target_table",
            "target_id",
            "recommendation_type",
            "source",
            "reason",
            "confidence",
            "suggested_fields",
            "status",
            "ignore_reason",
            "jump_label",
        ),
        "column_labels": (
            "推荐编号",
            "目标表",
            "目标行",
            "推荐类型",
            "来源",
            "推荐理由",
            "置信度",
            "建议字段",
            "状态",
            "忽略原因",
            "跳转",
        ),
        "rows": rows,
    }


def recommendation_action_patch_item(
    recommendation_id: str,
    action: str,
    *,
    reason: str = "",
) -> dict[str, Any]:
    if action not in {"accept_recommendation", "ignore_recommendation"}:
        raise ValueError("recommendation action must be accept_recommendation or ignore_recommendation")
    return {"action": action, "table": "metadata", "target_id": recommendation_id, "reason": reason}


def change_impact_patch_item(
    item_id: str,
    *,
    status: str = "已处理",
    reason: str = "",
) -> dict[str, Any]:
    return {
        "action": "resolve_change_impact",
        "table": "metadata",
        "target_id": item_id,
        "changes": {"status": status},
        "reason": reason,
    }


def row_to_display_text(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "是" if value else "否"
    if value is None:
        return ""
    return str(value)


def parse_cell_text(text: str, original_value: Any = "") -> Any:
    stripped = text.strip()
    if stripped == "":
        return ""
    if isinstance(original_value, bool):
        return stripped.lower() in {"1", "true", "yes", "y", "是"}
    if isinstance(original_value, int) and not isinstance(original_value, bool):
        try:
            return int(stripped)
        except ValueError:
            return stripped
    if isinstance(original_value, float):
        try:
            return float(stripped)
        except ValueError:
            return stripped
    if isinstance(original_value, (list, dict)) or stripped[:1] in {"[", "{"}:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
    lowered = stripped.lower()
    if lowered in {"true", "false", "yes", "no"} or stripped in {"是", "否"}:
        return lowered in {"true", "yes"} or stripped == "是"
    try:
        return int(stripped)
    except ValueError:
        return stripped


def navigation_target(table_key: str, row_id: str) -> str:
    table_key = {
        "process_step": "process_flow",
        "process_flow": "process_flow",
        "failure_mode": "pfmea",
        "pfmea": "pfmea",
        "control_item": "control_plan",
        "control_plan": "control_plan",
    }.get(table_key, table_key)
    if table_key not in TABLE_SPECS or not row_id:
        return ""
    return f"{table_key}:{row_id}"


def navigation_target_from_ref(ref: str) -> str:
    text = str(ref or "").strip()
    if not text:
        return ""
    if ":" not in text:
        return ""
    prefix, row_id = text.split(":", 1)
    row_id = row_id.split(".", 1)[0].split(":", 1)[0].strip()
    return navigation_target(prefix, row_id)


def navigation_label(table_key: str, row_id: str) -> str:
    target = navigation_target(table_key, row_id)
    return navigation_label_from_target(target)


def navigation_label_from_target(target: str) -> str:
    if ":" not in str(target):
        return ""
    table_key, row_id = str(target).split(":", 1)
    title = TABLE_SPECS.get(table_key).title if table_key in TABLE_SPECS else table_key
    return f"跳转到 {title}：{row_id}"


def manual_review_model(result: dict[str, Any]) -> dict[str, Any]:
    manual_review = result.get("manual_review") if isinstance(result, dict) else {}
    quality_gate = result.get("quality_gate") if isinstance(result, dict) else {}
    if not isinstance(manual_review, dict):
        manual_review = {}
    if not isinstance(quality_gate, dict):
        quality_gate = {}
    raw_items = manual_review.get("items", [])
    questions = [_manual_review_question(item, result) for item in raw_items if item]
    for target in quality_gate.get("needs_confirmation_items", []):
        questions.append(
            {
                "问题": "该对象需要人工确认",
                "对象": str(target),
                "详情": "质量门仍标记该对象为待确认，正式导出前需要复核并确认。",
                "证据信息": _evidence_text_for_item({"target": target}, result),
                "跳转目标": navigation_target_from_ref(str(target)),
                "跳转": navigation_label_from_target(navigation_target_from_ref(str(target))),
            }
        )
    return {
        "需要人工复核": bool(manual_review.get("required", False) or questions),
        "复核摘要": manual_review.get("summary", {}),
        "问题列表": questions,
        "原始明细数量": manual_review.get("raw_count", len(raw_items) if isinstance(raw_items, list) else 0),
        "说明": "按问题、详情、证据信息展示；完整原始内容仍保留在运行结果 JSON 中。",
    }


def manual_review_text(result: dict[str, Any]) -> str:
    model = manual_review_model(result)
    lines = [
        f"需要人工复核：{'是' if model['需要人工复核'] else '否'}",
        f"问题数量：{len(model['问题列表'])}",
    ]
    summary = model.get("复核摘要")
    if summary:
        lines.append(f"复核摘要：{row_to_display_text(summary)}")
    if not model["问题列表"]:
        lines.append("当前没有待展示的人工复核问题。")
    for index, item in enumerate(model["问题列表"], start=1):
        lines.extend(
            [
                "",
                f"{index}. {item.get('问题', '')}",
                f"对象：{item.get('对象', '')}",
                f"详情：{item.get('详情', '')}",
                f"证据：{item.get('证据信息', '')}",
            ]
        )
        if item.get("跳转"):
            lines.append(str(item["跳转"]))
    return "\n".join(lines)


def _ensure_automation_model(result_or_model: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result_or_model, dict) and "summary" in result_or_model and "rows" in result_or_model:
        return result_or_model
    return automation_review_model(result_or_model)


def _automation_review_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
    candidates = []
    if isinstance(metadata, dict):
        candidates.extend(
            metadata.get(key, [])
            for key in ("automation_review", "automation_review_items", "ai_pre_review")
        )
    candidates.append(result.get("automation_review", []) if isinstance(result, dict) else [])
    for value in candidates:
        if isinstance(value, dict):
            value = value.get("items", [])
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _automation_review_row(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    target_table = str(item.get("target_table") or item.get("table") or "")
    target_id = str(item.get("target_id") or item.get("row_id") or "")
    target = str(item.get("target") or "")
    if (not target_table or not target_id) and target:
        nav_target = navigation_target_from_ref(target)
        if ":" in nav_target:
            target_table, target_id = nav_target.split(":", 1)
    category = _automation_category(item)
    row = {
        "review_category": category,
        "target_table": target_table,
        "target_id": target_id,
        "review_message": str(item.get("message") or item.get("reason") or item.get("detail") or category),
        "risk_level": str(item.get("risk_level") or item.get("risk") or item.get("severity") or ""),
        "confidence": item.get("confidence", ""),
        "suggested_changes": copy.deepcopy(item.get("suggested_changes", item.get("suggested_fields", {}))),
        "recommendation_id": str(item.get("recommendation_id", "")),
        "issue_id": str(item.get("issue_id", "")),
        "jump_target": navigation_target(target_table, target_id),
    }
    row["jump_label"] = navigation_label_from_target(row["jump_target"])
    if not row["review_message"] and row["jump_target"]:
        row["review_message"] = _row_display_name(result, target_table, target_id)
    return row


def _automation_category(item: dict[str, Any]) -> str:
    category = str(item.get("review_category") or item.get("category") or "").strip()
    if category in {"可批量确认", "需要人工判断", "阻断问题"}:
        return category
    action = str(item.get("recommended_action") or item.get("action") or "").strip()
    risk = str(item.get("risk_level") or item.get("risk") or item.get("severity") or "").lower()
    if action in {"batch_confirm", "confirm"} or risk in {"low", "低", "low_risk"}:
        return "可批量确认"
    if risk in {"blocker", "blocking", "阻断", "必须修复", "error"}:
        return "阻断问题"
    return "需要人工判断"


def _automation_review_rows_from_tables(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table_key, spec in TABLE_SPECS.items():
        document = result.get(spec.result_key, {}) if isinstance(result, dict) else {}
        source_rows = document.get(spec.container_key, []) if isinstance(document, dict) else []
        for row in source_rows:
            if not isinstance(row, dict) or row.get("deleted") or row.get("soft_deleted"):
                continue
            target_id = str(row.get(spec.row_id_field, "")).strip()
            review_status = str(row.get("review_status", "")).strip()
            if review_status == "已批量确认":
                continue
            if row.get("_has_open_issue") or review_status in {"必须修复", "阻断问题"}:
                category = "阻断问题"
                message = str(row.get("_open_issue") or "该行存在阻断问题，必须修复后才能继续。")
            elif review_status in {"需人工判断", "需要人工判断"}:
                category = "需要人工判断"
                message = "AI 预审认为该行需要人工判断。"
            elif _is_low_risk_ai_confirmation_row(row):
                category = "可批量确认"
                message = "AI 预审判断为低风险，可批量确认。"
            elif row.get("needs_confirmation"):
                category = "需要人工判断"
                message = "该行仍需要人工确认。"
            else:
                continue
            rows.append(
                {
                    "review_category": category,
                    "target_table": table_key,
                    "target_id": target_id,
                    "review_message": message,
                    "risk_level": "低" if category == "可批量确认" else "",
                    "confidence": row.get("confidence", row.get("ai_confidence", "")),
                    "suggested_changes": copy.deepcopy(row.get("suggested_changes", {})),
                    "recommendation_id": str(row.get("recommendation_id", "")),
                    "issue_id": str(row.get("issue_id", "")),
                    "jump_target": navigation_target(table_key, target_id),
                    "jump_label": navigation_label(table_key, target_id),
                }
            )
    return rows


def _automation_review_rows_from_manual_review(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for question in manual_review_model(result).get("问题列表", []):
        if not isinstance(question, dict):
            continue
        target = str(question.get("跳转目标") or navigation_target_from_ref(str(question.get("对象", ""))))
        table_key, target_id = target.split(":", 1) if ":" in target else ("", "")
        title = str(question.get("问题", ""))
        category = "阻断问题" if "阻断" in title else "需要人工判断"
        issue_id = str(question.get("问题ID", "")).strip()
        if not target:
            table_key = "人工复核"
            target_id = issue_id or str(question.get("对象", "") or "全局问题")
        rows.append(
            {
                "review_category": category,
                "target_table": table_key,
                "target_id": target_id,
                "review_message": str(question.get("详情", "")),
                "risk_level": "阻断" if category == "阻断问题" else "",
                "confidence": "",
                "suggested_changes": {},
                "recommendation_id": "",
                "issue_id": issue_id,
                "jump_target": target,
                "jump_label": navigation_label_from_target(target) if target else "查看人工复核页",
            }
        )
    return rows


def _automation_review_rows_from_metadata(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in unresolved_recommendations(_knowledge_recommendations(result)):
        row = dict(item)
        target_table = str(row.get("target_table", ""))
        target_id = str(row.get("target_id", ""))
        rows.append(
            {
                "review_category": "需要人工判断",
                "target_table": target_table,
                "target_id": target_id,
                "review_message": str(row.get("reason") or "存在未处理的知识库推荐。"),
                "risk_level": "",
                "confidence": row.get("confidence", ""),
                "suggested_changes": copy.deepcopy(row.get("suggested_fields", {})),
                "recommendation_id": str(row.get("recommendation_id", "")),
                "issue_id": "",
                "jump_target": navigation_target(target_table, target_id),
                "jump_label": navigation_label(target_table, target_id),
            }
        )
    for item in change_impact_model(result).get("rows", []):
        if not isinstance(item, dict) or item.get("status") in {"已处理", "无影响"}:
            continue
        target = str(item.get("jump_target") or navigation_target_from_ref(str(item.get("target", ""))))
        table_key, target_id = target.split(":", 1) if ":" in target else ("", "")
        rows.append(
            {
                "review_category": "阻断问题",
                "target_table": table_key,
                "target_id": target_id,
                "review_message": str(item.get("message") or "存在未处理的变更影响。"),
                "risk_level": str(item.get("severity", "阻断")),
                "confidence": "",
                "suggested_changes": {},
                "recommendation_id": "",
                "issue_id": "",
                "jump_target": target,
                "jump_label": navigation_label_from_target(target),
            }
        )
    return rows


def _is_low_risk_ai_confirmation_row(row: dict[str, Any]) -> bool:
    if not row.get("needs_confirmation"):
        return False
    review_status = str(row.get("review_status", "")).strip()
    automation_status = str(row.get("automation_review_status", "")).strip()
    if review_status == "AI建议确认" or automation_status == "AI建议确认":
        return True
    risk = str(row.get("risk_level") or row.get("automation_risk") or "").lower()
    if risk in {"low", "低", "low_risk"}:
        return True
    confidence = row.get("confidence", row.get("ai_confidence", None))
    try:
        return bool(row.get("ai_inferred")) and confidence is not None and float(confidence) >= 0.85
    except (TypeError, ValueError):
        return False


def _dedupe_automation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"阻断问题": 3, "需要人工判断": 2, "可批量确认": 1}
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("target_table", "")),
            str(row.get("target_id", "") or row.get("issue_id", "")),
        )
        existing = by_key.get(key)
        if existing is None or priority.get(str(row.get("review_category")), 0) > priority.get(str(existing.get("review_category")), 0):
            by_key[key] = row
    return list(by_key.values())


def _row_display_name(result: dict[str, Any], table_key: str, target_id: str) -> str:
    try:
        spec = table_spec(table_key)
    except ValueError:
        return target_id
    document = result.get(spec.result_key, {}) if isinstance(result, dict) else {}
    source_rows = document.get(spec.container_key, []) if isinstance(document, dict) else []
    for row in source_rows:
        if isinstance(row, dict) and str(row.get(spec.row_id_field, "")) == target_id:
            return str(row.get("operation") or row.get("failure_mode") or row.get("specification") or target_id)
    return target_id


def _pfmea_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    pfmea = result.get("pfmea", {}) if isinstance(result, dict) else {}
    rows = pfmea.get("rows", []) if isinstance(pfmea, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def _knowledge_recommendations(result: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
    items = metadata.get("knowledge_recommendations", []) if isinstance(metadata, dict) else []
    return [item for item in items if isinstance(item, dict)]


def _manual_review_question(item: Any, result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, dict):
        payload = _expand_review_issue_item(item, result)
        target = str(payload.get("target") or payload.get("item_id") or payload.get("source_ref") or "")
        message = str(payload.get("message") or payload.get("reason") or payload.get("detail") or payload)
        category = str(payload.get("category") or payload.get("review_category") or "人工复核")
        severity = str(payload.get("severity_display") or payload.get("severity") or "")
        issue_id = str(payload.get("issue_id") or payload.get("item_id") or "")
    else:
        target = str(item)
        message = str(item)
        category = "人工复核"
        severity = ""
        issue_id = ""
    if category == "Review Issue":
        category = "人工复核问题"
    if message == "正式导出前，所有 review_issue 都必须处理。":
        message = "正式导出前，未处理的人工复核问题必须先关闭。"
    nav_target = navigation_target_from_ref(target)
    return {
        "问题ID": issue_id,
        "问题": category if not severity else f"{category}（{severity}）",
        "对象": target,
        "详情": message,
        "证据信息": _evidence_text_for_item(item, result),
        "跳转目标": nav_target,
        "跳转": navigation_label_from_target(nav_target),
    }


def _expand_review_issue_item(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item)
    item_id = str(payload.get("item_id") or payload.get("issue_id") or "").strip()
    category = str(payload.get("category", "")).strip()
    if category != "Review Issue" and not item_id.startswith("RI-"):
        return payload
    issue = _review_issue_lookup(result).get(item_id)
    if not issue:
        return payload
    expanded = dict(payload)
    expanded.update(
        {
            "issue_id": issue.get("issue_id", item_id),
            "category": issue.get("category") or "人工复核问题",
            "message": issue.get("message") or payload.get("message", ""),
            "severity": issue.get("severity", payload.get("severity", "")),
            "target": issue.get("target") or payload.get("target") or payload.get("item_id", ""),
            "field": issue.get("field", payload.get("field", "")),
            "evidence_refs": issue.get("evidence_refs", payload.get("evidence_refs", [])),
        }
    )
    return expanded


def _review_issue_lookup(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for container in _review_issue_containers(result):
        issues = container.get("review_issues", []) if isinstance(container, dict) else []
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            issue_id = str(issue.get("issue_id", "")).strip()
            if issue_id and issue_id not in lookup:
                lookup[issue_id] = issue
    return lookup


def _review_issue_containers(result: dict[str, Any]) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = []
    if not isinstance(result, dict):
        return containers
    metadata = result.get("metadata", {})
    if isinstance(metadata, dict):
        containers.append(metadata)
    chain = result.get("chain", {})
    if isinstance(chain, dict) and isinstance(chain.get("metadata"), dict):
        containers.append(chain["metadata"])
    for key in ("quality_gate", "quality_gates"):
        value = result.get(key)
        if isinstance(value, dict):
            containers.append(value)
            containers.extend(nested for nested in value.values() if isinstance(nested, dict))
    return containers


def _evidence_text_for_item(item: Any, result: dict[str, Any]) -> str:
    refs: list[str] = []
    if isinstance(item, dict):
        raw_refs = item.get("evidence_refs", item.get("evidence", []))
        if isinstance(raw_refs, list):
            refs.extend(str(ref) for ref in raw_refs)
        elif raw_refs:
            refs.append(str(raw_refs))
    evidence = _evidence_lookup(result)
    if not refs:
        return "未提供证据引用"
    details = []
    for ref in refs:
        payload = evidence.get(ref)
        if not payload:
            details.append(ref)
            continue
        text = payload.get("text") or payload.get("content") or payload.get("description") or ""
        page = payload.get("page", payload.get("page_index", ""))
        prefix = f"{ref}"
        if page not in {"", None}:
            prefix += f"（页 {page}）"
        details.append(f"{prefix}: {text}" if text else prefix)
    return "；".join(details)


def _evidence_lookup(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    drawing_analysis = result.get("drawing_analysis", {}) if isinstance(result, dict) else {}
    items = drawing_analysis.get("evidence", []) if isinstance(drawing_analysis, dict) else []
    lookup: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("evidence_id") or item.get("id") or item.get("ref") or "")
        if ref:
            lookup[ref] = item
    return lookup


def _missing_after_evaluation(row: dict[str, Any]) -> list[str]:
    status = str(row.get("action_status", "")).strip()
    if status not in {"已完成", "已验证", "已关闭"}:
        return []
    return [
        field
        for field in ("after_severity", "after_occurrence", "after_detection", "after_ap")
        if row.get(field) in {None, ""}
    ]


def _pending_action(row: dict[str, Any], ap: str) -> bool:
    if ap == "H" and not str(row.get("recommended_action", "")).strip():
        return True
    if ap in {"H", "M"}:
        return not str(row.get("responsibility", "")).strip() or not str(row.get("target_date", "")).strip()
    return False


def _is_overdue(target_date: str, status: str, today: date) -> bool:
    if status in {"已关闭", "已验证"}:
        return False
    try:
        return bool(target_date) and date.fromisoformat(target_date[:10]) < today
    except ValueError:
        return False


def _action_status_display(
    ap: str,
    *,
    overdue: bool,
    pending_action: bool,
    pending_after: bool,
) -> str:
    if overdue:
        return "已逾期"
    if pending_action:
        return "待制定措施"
    if pending_after:
        return "待措施后评价"
    if ap == "H":
        return "高 AP 已有措施"
    if ap == "M":
        return "中 AP 已有措施"
    return "正常"


def _columns_for_rows(spec: TableSpec, rows: list[Any]) -> tuple[str, ...]:
    extra: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row:
            if key == ROW_STATUS_COLUMN:
                continue
            if key not in spec.columns and not key.startswith("_"):
                extra.append(key)
    return tuple(dict.fromkeys([*spec.columns, *extra]))


def _cell_value(value: Any) -> Any:
    return copy.deepcopy(value)


def _with_inherited_display_fields(
    result: dict[str, Any],
    spec: TableSpec,
    row: dict[str, Any],
) -> dict[str, Any]:
    if spec.key == "process_flow":
        return copy.deepcopy(row)
    enriched = copy.deepcopy(row)
    pfd_row = _process_step_lookup(result).get(str(row.get("process_step_id", "")))
    if spec.key == "pfmea":
        _mark_inherited_issue(enriched, result, spec.key, pfd_row=pfd_row)
        _override_from_pfd_master(enriched, pfd_row)
        _copy_missing_fields(
            enriched,
            pfd_row,
            (
                "operation",
                "process_function",
                "process_item",
                "process_step",
                "process_work_element",
                "function_requirement",
                "product_characteristics",
                "process_characteristics",
                "product_characteristic",
                "process_characteristic",
            ),
        )
        return enriched
    if spec.key == "control_plan":
        pfmea_row = _pfmea_lookup(result).get(str(row.get("pfmea_id", "")))
        _mark_inherited_issue(enriched, result, spec.key, pfd_row=pfd_row, pfmea_row=pfmea_row)
        _copy_missing_fields(enriched, pfmea_row, ("failure_mode", "classification"))
        if not enriched.get("product_process_characteristic"):
            enriched["product_process_characteristic"] = _first_nonempty(
                enriched.get("characteristic"),
                pfmea_row.get("product_process_characteristic") if pfmea_row else "",
                pfmea_row.get("process_characteristics") if pfmea_row else "",
                pfd_row.get("product_characteristics") if pfd_row else "",
                pfd_row.get("process_characteristics") if pfd_row else "",
            )
        _copy_missing_fields(enriched, pfd_row, ("operation", "process_function", "gauges", "inspection_equipment"))
        _override_cp_from_pfd_master(enriched, pfd_row)
        return enriched
    return enriched


def _override_from_pfd_master(target: dict[str, Any], pfd_row: dict[str, Any] | None) -> None:
    if not pfd_row:
        return
    mappings = (
        ("operation", "operation"),
        ("operation", "process_step"),
        ("process_function", "process_function"),
        ("process_function", "function_requirement"),
        ("equipment", "process_work_element"),
        ("product_characteristics", "product_characteristics"),
        ("process_characteristics", "process_characteristics"),
        ("product_characteristic", "product_characteristic"),
        ("process_characteristic", "process_characteristic"),
    )
    for source_field, target_field in mappings:
        value = pfd_row.get(source_field)
        if value not in ("", None, [], {}):
            target[target_field] = copy.deepcopy(value)


def _override_cp_from_pfd_master(target: dict[str, Any], pfd_row: dict[str, Any] | None) -> None:
    if not pfd_row:
        return
    for source_field, target_field in (
        ("operation", "operation"),
        ("process_function", "process_function"),
        ("gauges", "gauges"),
        ("inspection_equipment", "inspection_equipment"),
    ):
        value = pfd_row.get(source_field)
        if value not in ("", None, [], {}):
            target[target_field] = copy.deepcopy(value)


def _mark_inherited_issue(
    row: dict[str, Any],
    result: dict[str, Any],
    table_key: str,
    *,
    pfd_row: dict[str, Any] | None = None,
    pfmea_row: dict[str, Any] | None = None,
) -> None:
    messages: list[str] = []
    step_id = str(row.get("process_step_id", "")).strip()
    pfmea_id = str(row.get("pfmea_id", "")).strip()
    if table_key in {"pfmea", "control_plan"}:
        if pfd_row is not None and (pfd_row.get("deleted") or pfd_row.get("soft_deleted")):
            row["_hidden_by_upstream_deleted"] = True
            messages.append(f"PFD 工序 {step_id} 已软删除，下游行需要处理。")
        if pfd_row is None and step_id:
            messages.append(f"PFD 工序 {step_id} 不存在，下游行需要处理。")
    if table_key == "control_plan":
        if pfmea_row is not None and (pfmea_row.get("deleted") or pfmea_row.get("soft_deleted")):
            row["_hidden_by_upstream_deleted"] = True
            messages.append(f"PFMEA 来源 {pfmea_id} 已软删除，控制计划行需要处理。")
        if pfmea_row is None and pfmea_id:
            messages.append(f"PFMEA 来源 {pfmea_id} 不存在，控制计划行需要处理。")
    for impact in _open_change_impacts_for_row(result, table_key, step_id, pfmea_id, str(row.get("control_plan_id", ""))):
        message = str(impact.get("message", "")).strip()
        if message and message not in messages:
            messages.append(message)
    if messages:
        row["_has_open_issue"] = True
        row["_open_issue"] = "；".join(messages)


def _open_change_impacts_for_row(
    result: dict[str, Any],
    table_key: str,
    step_id: str,
    pfmea_id: str,
    control_plan_id: str,
) -> list[dict[str, Any]]:
    metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
    impacts = metadata.get("change_impacts", []) if isinstance(metadata, dict) else []
    rows = impacts if isinstance(impacts, list) else []
    refs = {
        f"{table_key}:{control_plan_id or pfmea_id or step_id}",
        f"process_flow:{step_id}",
        f"pfmea:{pfmea_id}",
        f"control_plan:{control_plan_id}",
    }
    return [
        item
        for item in rows
        if isinstance(item, dict)
        and str(item.get("target", "")).strip() in refs
        and str(item.get("status", "")).strip() not in {"已处理", "无影响"}
        and not (
            str(item.get("status", "")).strip() == "已忽略"
            and str(item.get("ignore_reason", "")).strip()
        )
    ]


def _process_step_lookup(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    document = result.get("process_flow", {}) if isinstance(result, dict) else {}
    rows = document.get("steps", []) if isinstance(document, dict) else []
    return {
        str(row.get("process_step_id", "")): row
        for row in rows
        if isinstance(row, dict) and str(row.get("process_step_id", ""))
    }


def _pfmea_lookup(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    document = result.get("pfmea", {}) if isinstance(result, dict) else {}
    rows = document.get("rows", []) if isinstance(document, dict) else []
    return {
        str(row.get("pfmea_id", "")): row
        for row in rows
        if isinstance(row, dict) and str(row.get("pfmea_id", ""))
    }


def _copy_missing_fields(
    target: dict[str, Any],
    source: dict[str, Any] | None,
    fields: tuple[str, ...],
) -> None:
    if not source:
        return
    for field in fields:
        if not target.get(field) and source.get(field):
            target[field] = copy.deepcopy(source[field])


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in ("", None, [], {}):
            return copy.deepcopy(value)
    return ""


def _next_new_row_id(spec: TableSpec, existing_rows: list[dict[str, Any]]) -> str:
    prefix = {
        "process_flow": "NEW-PFD",
        "pfmea": "NEW-PFMEA",
        "control_plan": "NEW-CP",
    }[spec.key]
    return f"{prefix}-{len(existing_rows) + 1:03d}"


def _normalize_row_values(spec: TableSpec, row: dict[str, Any]) -> dict[str, Any]:
    original = row.get(META_ORIGINAL, {})
    normalized: dict[str, Any] = {}
    for column in _columns_for_rows(spec, [original if isinstance(original, dict) else {}, row]):
        if column.startswith("_") or column == ROW_STATUS_COLUMN:
            continue
        original_value = original.get(column, "") if isinstance(original, dict) else ""
        value = row.get(column, "")
        normalized[column] = parse_cell_text(value, original_value) if isinstance(value, str) else value
    return normalized


def _changed_fields(
    spec: TableSpec,
    normalized: dict[str, Any],
    original: dict[str, Any],
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for column in _columns_for_rows(spec, [original, normalized]):
        if column == ROW_STATUS_COLUMN:
            continue
        if normalized.get(column, "") != original.get(column, ""):
            changes[column] = normalized.get(column, "")
    return changes


def _table_row_changed(table_key: str, row: dict[str, Any]) -> bool:
    try:
        spec = table_spec(table_key)
    except ValueError:
        return False
    original = row.get(META_ORIGINAL, {})
    if not isinstance(original, dict):
        original = {}
    normalized = _normalize_row_values(spec, row)
    return bool(_changed_fields(spec, normalized, original))


def _effective_row_id(
    spec: TableSpec,
    row: dict[str, Any],
    normalized: dict[str, Any],
) -> str:
    return str(row.get(META_ROW_ID) or normalized.get(spec.row_id_field) or "")
