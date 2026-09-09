"""Table specification definitions and shared helpers for the desktop three-table editor."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

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
    "process_name": "工序名称",
    "process_function": "工序目的/过程功能",
    "process_item": "过程项",
    "structure_process_item": "结构过程项",
    "structure_process_step": "结构过程步骤",
    "structure_work_element": "结构工作要素",
    "function_process_item": "功能过程项",
    "function_process_step": "功能过程步骤",
    "function_work_element": "功能工作要素",
    "process_step": "过程步骤",
    "process_work_element": "过程工作要素",
    "function_requirement": "功能/要求",
    "product_characteristic": "产品特性",
    "product_characteristics": "产品特性",
    "process_characteristic": "过程特性",
    "process_characteristics": "过程特性",
    "characteristic_number": "特性编号",
    "special_characteristic_class": "特殊特性分类",
    "specification_tolerance": "规格和公差",
    "equipment": "设备",
    "tooling": "工装",
    "fixture": "工装",
    "gauge": "检具",
    "gauges": "检具",
    "gages": "检具",
    "inspection_equipment": "检具",
    "document_refs": "文件",
    "documents": "文件",
    "flow_symbol": "流程符号",
    "flow_type": "流程类型",
    "flow_type_display": "流程类型显示",
    "process_type": "流程类型",
    "operation_type": "工序类型",
    "input_material": "输入物料",
    "output_result": "输出结果",
    "previous_step_ids": "前序工序",
    "next_step_ids": "后续工序",
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
    "cause_process_parameter": "原因过程参数",
    "occurrence": "发生度 O",
    "prevention_control": "预防控制",
    "prevention_control_target": "预防控制对象",
    "prevention_control_timing": "预防控制时机",
    "detection_control": "探测控制",
    "detection_control_target": "探测对象",
    "detection_control_timing": "探测时机",
    "detection": "探测度 D",
    "action_priority": "措施优先级 AP",
    "control_logic_review": "控制逻辑复核",
    "rpn": "RPN",
    "recommended_action": "推荐措施",
    "optimization_action": "优化措施",
    "responsibility": "责任人",
    "responsible_person": "责任人",
    "target_date": "目标完成日期",
    "action_status": "措施状态",
    "status": "状态",
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
    "process_parameter": "过程参数",
    "parameter_specification": "参数规格",
    "process_control_method": "过程控制方法",
    "setup_verification": "首件/换型确认",
    "poka_yoke_device": "防错装置",
    "poka_yoke_verification": "防错验证",
    "process_record": "过程记录",
    "record_form": "记录表单",
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
            "flow_symbol",
            "flow_type",
            "flow_type_display",
            "operation_type",
            "input_material",
            "output_result",
            "previous_step_ids",
            "next_step_ids",
            "process_function",
            "product_characteristics",
            "process_characteristics",
            "equipment",
            "tooling",
            "gauges",
            "document_refs",
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
            "structure_process_item",
            "structure_process_step",
            "structure_work_element",
            "function_process_item",
            "function_process_step",
            "function_work_element",
            "process_item",
            "process_step",
            "process_work_element",
            "function_requirement",
            "operation",
            "product_characteristics",
            "process_characteristics",
            "failure_mode",
            "failure_effect",
            "failure_cause",
            "cause_process_parameter",
            "prevention_control",
            "prevention_control_target",
            "prevention_control_timing",
            "severity",
            "occurrence",
            "detection_control",
            "detection_control_target",
            "detection_control_timing",
            "detection",
            "action_priority",
            "control_logic_review",
            "optimization_action",
            "recommended_action",
            "responsible_person",
            "responsibility",
            "target_date",
            "status",
            "action_status",
            "rpn",
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
            "process_name",
            "equipment",
            "characteristic_number",
            "product_characteristic",
            "process_characteristic",
            "special_characteristic_class",
            "specification_tolerance",
            "failure_mode",
            "product_process_characteristic",
            "specification",
            "classification",
            "measurement_method",
            "sample_size",
            "sample_frequency",
            "control_method",
            "process_parameter",
            "parameter_specification",
            "process_control_method",
            "setup_verification",
            "poka_yoke_device",
            "poka_yoke_verification",
            "process_record",
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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in ("", None, [], {}):
            return copy.deepcopy(value)
    return ""


def _first_text_nonempty(*values: Any) -> str:
    for value in values:
        if value in ("", None, [], {}):
            continue
        if isinstance(value, list):
            for item in value:
                text = str(item).strip()
                if text:
                    return text
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


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


def _control_plan_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    document = result.get("control_plan", {}) if isinstance(result, dict) else {}
    rows = document.get("rows", []) if isinstance(document, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def _knowledge_recommendations(result: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
    items = metadata.get("knowledge_recommendations", []) if isinstance(metadata, dict) else []
    return [item for item in items if isinstance(item, dict)]


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


# ---------------------------------------------------------------------------
# Evidence and review issue helpers (shared by patches and models)
# ---------------------------------------------------------------------------


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
    from .models import navigation_label_from_target, navigation_target_from_ref  # noqa: E402

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
