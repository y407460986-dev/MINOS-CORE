"""Change impact analysis for PFD/PFMEA/CP three-table edits."""

from __future__ import annotations

from typing import Any


def field_diff(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    keys = sorted(set(before) | set(after))
    return [
        {"field": key, "before": before.get(key, ""), "after": after.get(key, "")}
        for key in keys
        if before.get(key, "") != after.get(key, "")
    ]


def analyze_change_impacts(source: dict[str, Any]) -> list[dict[str, str]]:
    process_rows = _rows(source, "process_flow", "process_steps", "steps")
    pfmea_rows = _rows(source, "pfmea", "failure_modes", "rows")
    cp_rows = _rows(source, "control_plan", "controls", "rows")
    pfmea_by_step = _group(pfmea_rows, "process_step_id")
    cp_by_step = _group(cp_rows, "process_step_id")
    cp_by_pfmea = _group(cp_rows, "pfmea_id")
    impacts: list[dict[str, str]] = []

    for step in process_rows:
        if not isinstance(step, dict):
            continue
        step_id = _text(step.get("process_step_id"))
        status = _text(step.get("change_impact_status"))
        if step.get("deleted"):
            linked_pfmea_ids = {
                _text(row.get("pfmea_id"))
                for row in pfmea_by_step.get(step_id, [])
                if _text(row.get("pfmea_id"))
            }
            if pfmea_by_step.get(step_id):
                impacts.append(
                    _impact(
                        "PFD 删除工序",
                        f"process_flow:{step_id}",
                        "PFMEA 关联风险需处理",
                        status or "待人工确认",
                    )
                )
            if cp_by_step.get(step_id) or any(cp_by_pfmea.get(pfmea_id) for pfmea_id in linked_pfmea_ids):
                impacts.append(
                    _impact(
                        "PFD 删除工序",
                        f"process_flow:{step_id}",
                        "CP 关联控制项需处理",
                        status or "待人工确认",
                    )
                )
            continue
        if step.get("review_status") == "人工新增" or step.get("change_type") == "pfd_added":
            if not pfmea_by_step.get(step_id):
                impacts.append(_impact("PFD 新增工序", f"process_flow:{step_id}", "PFMEA 需补风险", status))
            if not cp_by_step.get(step_id):
                impacts.append(_impact("PFD 新增工序", f"process_flow:{step_id}", "CP 需补控制", status))
        if step.get("review_status") == "人工修改" or _changed_any(step, ("operation", "process_function", "product_characteristics", "process_characteristics", "special_characteristics")):
            impacts.append(_impact("PFD 关键字段修改", f"process_flow:{step_id}", "PFMEA 继承字段需同步确认", status or "待人工确认"))

    for row in pfmea_rows:
        if not isinstance(row, dict) or row.get("deleted"):
            continue
        pfmea_id = _text(row.get("pfmea_id"))
        ap = _text(row.get("action_priority"), row.get("AP")).upper()
        status = _text(row.get("change_impact_status"))
        if ap == "H" and not cp_by_pfmea.get(pfmea_id):
            impacts.append(_impact("PFMEA 高 AP", f"pfmea:{pfmea_id}", "CP 必须新增控制", status))
        if row.get("review_status") == "人工修改" and _changed_any(row, ("prevention_control", "detection_control", "classification", "action_priority")):
            impacts.append(_impact("PFMEA 控制/特性修改", f"pfmea:{pfmea_id}", "CP 控制方法需同步确认", status or "待人工确认"))

    active_pfmea_ids = {_text(row.get("pfmea_id")) for row in pfmea_rows if isinstance(row, dict) and not row.get("deleted")}
    for control in cp_rows:
        if not isinstance(control, dict):
            continue
        pfmea_id = _text(control.get("pfmea_id"))
        if control.get("deleted") and pfmea_id in active_pfmea_ids:
            impacts.append(_impact("CP 删除控制项", f"control_plan:{_text(control.get('control_plan_id'))}", "检查是否留下未控制高风险", _text(control.get("change_impact_status"))))
    return impacts


def blocking_change_impacts(impacts: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        impact
        for impact in impacts
        if impact.get("status") not in {"已处理", "无影响"}
        and not (impact.get("status") == "已忽略" and impact.get("ignore_reason"))
    ]


def _rows(source: dict[str, Any], table: str, chain_key: str, table_key: str) -> list[Any]:
    if table in source and isinstance(source.get(table), dict):
        rows = source[table].get(table_key)
        if isinstance(rows, list):
            return rows
    rows = source.get(chain_key)
    return rows if isinstance(rows, list) else []


def _group(rows: list[Any], key: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if isinstance(row, dict) and not row.get("deleted"):
            result.setdefault(_text(row.get(key)), []).append(row)
    return result


def _impact(kind: str, target: str, message: str, status: str) -> dict[str, str]:
    return {
        "item_id": f"{target}.{kind}.{message}",
        "category": "变更影响",
        "target": target,
        "message": message,
        "status": status or "待同步",
        "ignore_reason": "",
        "severity": "blocker",
    }


def _changed_any(row: dict[str, Any], fields: tuple[str, ...]) -> bool:
    changes = row.get("changed_fields")
    if isinstance(changes, list):
        return any(field in changes for field in fields)
    return False


def _text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
