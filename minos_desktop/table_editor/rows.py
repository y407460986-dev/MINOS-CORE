"""Row-level CRUD operations for the three-table editor."""
from __future__ import annotations

import copy
from typing import Any

from .specs import (
    META_CONFIRMED,
    META_IS_NEW,
    META_ORIGINAL,
    META_ROW_ID,
    META_SOFT_DELETED,
    ROW_STATUS_COLUMN,
    TableSpec,
    _cell_value,
    _changed_fields,
    _columns_for_rows,
    _first_nonempty,
    _first_text_nonempty,
    _normalize_row_values,
    _pfmea_lookup,
    _process_step_lookup,
    column_label,
    table_spec,
)


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
    # Ensure new PFMEA rows carry valid defaults for validated numeric/enum fields.
    if table_key == "pfmea":
        if "severity" not in values:
            row["severity"] = 1
        if "occurrence" not in values:
            row["occurrence"] = 1
        if "detection" not in values:
            row["detection"] = 1
        if "action_priority" not in values:
            row["action_priority"] = "M"
    row[ROW_STATUS_COLUMN] = table_row_status(table_key, row)
    return row


def reorder_row(
    rows: list[dict[str, Any]],
    from_index: int,
    to_index: int,
) -> list[dict[str, Any]]:
    """Move a row from ``from_index`` to ``to_index`` and renumber sequences."""
    if from_index == to_index:
        return list(rows)
    if from_index < 0 or to_index < 0:
        return list(rows)
    n = len(rows)
    if from_index >= n or to_index >= n:
        return list(rows)
    new_rows = list(rows)
    moved = new_rows.pop(from_index)
    # When target > source, the list has already shifted after pop.
    insert_at = to_index if to_index <= from_index else to_index
    new_rows.insert(insert_at, moved)
    for i, row in enumerate(new_rows):
        if isinstance(row, dict):
            row["sequence"] = (i + 1) * 10
    return new_rows


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


# ---------------------------------------------------------------------------
# Private helpers — row processing
# ---------------------------------------------------------------------------


def _next_new_row_id(spec: TableSpec, existing_rows: list[dict[str, Any]]) -> str:
    prefix = {
        "process_flow": "NEW-PFD",
        "pfmea": "NEW-PFMEA",
        "control_plan": "NEW-CP",
    }[spec.key]
    return f"{prefix}-{len(existing_rows) + 1:03d}"


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
        _copy_alias_fields(
            enriched,
            (
                ("structure_process_item", "process_item"),
                ("process_item", "structure_process_item"),
                ("structure_process_step", "process_step", "operation"),
                ("process_step", "structure_process_step", "operation"),
                ("structure_work_element", "process_work_element", "equipment"),
                ("process_work_element", "structure_work_element", "equipment"),
                ("function_process_item", "function_requirement", "process_function"),
                ("function_process_step", "function_requirement", "process_function"),
                ("function_requirement", "function_process_step", "process_function"),
                ("function_work_element", "function_requirement", "process_function"),
                ("optimization_action", "recommended_action"),
                ("recommended_action", "optimization_action"),
                ("responsible_person", "responsibility", "owner"),
                ("responsibility", "responsible_person", "owner"),
                ("status", "action_status"),
                ("action_status", "status"),
            ),
        )
        return enriched
    if spec.key == "control_plan":
        pfmea_row = _pfmea_lookup(result).get(str(row.get("pfmea_id", "")))
        _mark_inherited_issue(enriched, result, spec.key, pfd_row=pfd_row, pfmea_row=pfmea_row)
        _copy_missing_fields(enriched, pfmea_row, ("failure_mode", "classification"))
        _copy_missing_fields(
            enriched,
            pfmea_row,
            (
                "product_characteristic",
                "process_characteristic",
                "special_characteristic_class",
                "specification_tolerance",
                "process_parameter",
                "parameter_specification",
                "process_control_method",
                "setup_verification",
                "poka_yoke_device",
                "poka_yoke_verification",
                "process_record",
            ),
        )
        if not enriched.get("process_parameter") and pfmea_row and pfmea_row.get("cause_process_parameter"):
            enriched["process_parameter"] = copy.deepcopy(pfmea_row["cause_process_parameter"])
        _copy_cp_standard_characteristics(enriched, pfmea_row=pfmea_row, pfd_row=pfd_row)
        if not enriched.get("product_process_characteristic"):
            enriched["product_process_characteristic"] = _first_nonempty(
                enriched.get("characteristic"),
                pfmea_row.get("product_process_characteristic") if pfmea_row else "",
                pfmea_row.get("process_characteristics") if pfmea_row else "",
                pfd_row.get("product_characteristics") if pfd_row else "",
                pfd_row.get("process_characteristics") if pfd_row else "",
                enriched.get("product_characteristic"),
                enriched.get("process_characteristic"),
                pfmea_row.get("product_characteristic") if pfmea_row else "",
                pfmea_row.get("process_characteristic") if pfmea_row else "",
                pfd_row.get("product_characteristic") if pfd_row else "",
                pfd_row.get("process_characteristic") if pfd_row else "",
            )
        _copy_missing_fields(
            enriched,
            pfd_row,
            (
                "operation",
                "process_function",
                "process_name",
                "equipment",
                "product_characteristic",
                "process_characteristic",
                "gauges",
                "inspection_equipment",
            ),
        )
        _override_cp_from_pfd_master(enriched, pfd_row)
        _copy_alias_fields(
            enriched,
            (
                ("process_name", "operation", "process_step"),
                ("process_parameter", "cause_process_parameter"),
                ("specification_tolerance", "specification", "tolerance"),
                ("specification", "specification_tolerance", "tolerance"),
                ("special_characteristic_class", "classification"),
                ("classification", "special_characteristic_class"),
                ("process_record", "record_form"),
            ),
        )
        return enriched
    return enriched


def _override_from_pfd_master(target: dict[str, Any], pfd_row: dict[str, Any] | None) -> None:
    if not pfd_row:
        return
    override_mappings = (
        ("operation", "operation"),
        ("operation", "process_step"),
        ("process_function", "process_function"),
        ("process_function", "function_requirement"),
        ("equipment", "process_work_element"),
        ("owner", "responsibility"),
        ("product_characteristics", "product_characteristics"),
        ("process_characteristics", "process_characteristics"),
    )
    for source_field, target_field in override_mappings:
        value = pfd_row.get(source_field)
        if value not in ("", None, [], {}):
            target[target_field] = copy.deepcopy(value)
    missing_only_mappings = (
        ("operation", "structure_process_step"),
        ("process_function", "function_process_step"),
        ("equipment", "structure_work_element"),
        ("owner", "responsible_person"),
        ("product_characteristic", "product_characteristic"),
        ("process_characteristic", "process_characteristic"),
    )
    for source_field, target_field in missing_only_mappings:
        value = pfd_row.get(source_field)
        if target.get(target_field) in ("", None, [], {}) and value not in ("", None, [], {}):
            target[target_field] = copy.deepcopy(value)


def _override_cp_from_pfd_master(target: dict[str, Any], pfd_row: dict[str, Any] | None) -> None:
    if not pfd_row:
        return
    for source_field, target_field in (
        ("operation", "operation"),
        ("process_name", "process_name"),
        ("process_function", "process_function"),
        ("gauges", "gauges"),
        ("inspection_equipment", "inspection_equipment"),
    ):
        value = pfd_row.get(source_field)
        if value not in ("", None, [], {}):
            target[target_field] = copy.deepcopy(value)
    for source_field, target_field in (
        ("operation", "process_name"),
        ("equipment", "equipment"),
        ("product_characteristic", "product_characteristic"),
        ("process_characteristic", "process_characteristic"),
    ):
        value = pfd_row.get(source_field)
        if target.get(target_field) in ("", None, [], {}) and value not in ("", None, [], {}):
            target[target_field] = copy.deepcopy(value)


def _copy_cp_standard_characteristics(
    target: dict[str, Any],
    *,
    pfmea_row: dict[str, Any] | None,
    pfd_row: dict[str, Any] | None,
) -> None:
    if not target.get("product_characteristic"):
        target["product_characteristic"] = _first_text_nonempty(
            target.get("product_characteristic"),
            pfmea_row.get("product_characteristic") if pfmea_row else "",
            pfd_row.get("product_characteristic") if pfd_row else "",
            pfmea_row.get("product_characteristics") if pfmea_row else "",
            pfd_row.get("product_characteristics") if pfd_row else "",
            target.get("product_process_characteristic"),
            target.get("characteristic"),
        )
    if not target.get("process_characteristic"):
        target["process_characteristic"] = _first_text_nonempty(
            target.get("process_characteristic"),
            pfmea_row.get("process_characteristic") if pfmea_row else "",
            pfd_row.get("process_characteristic") if pfd_row else "",
            pfmea_row.get("process_characteristics") if pfmea_row else "",
            pfd_row.get("process_characteristics") if pfd_row else "",
            target.get("product_process_characteristic"),
            target.get("characteristic"),
        )


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
    for impact in _open_change_impacts_for_row(
        result, table_key, step_id, pfmea_id, str(row.get("control_plan_id", ""))
    ):
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


def _copy_alias_fields(
    target: dict[str, Any],
    mappings: tuple[tuple[str, ...], ...],
) -> None:
    for fields in mappings:
        if not fields or target.get(fields[0]):
            continue
        value = _first_nonempty(*(target.get(field) for field in fields[1:]))
        if value not in ("", None, [], {}):
            target[fields[0]] = value
