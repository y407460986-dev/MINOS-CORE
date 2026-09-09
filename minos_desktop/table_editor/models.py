"""View models, navigation, and review helpers for the three-table editor."""
from __future__ import annotations

from datetime import date
from typing import Any

from minos_core.change_management import analyze_change_impacts
from minos_core.knowledge_recommendation import unresolved_recommendations

from .specs import (
    TABLE_SPECS,
    _control_plan_rows,
    _evidence_text_for_item,
    _first_text_nonempty,
    _knowledge_recommendations,
    _manual_review_question,
    _pfmea_lookup,
    _process_step_lookup,
    row_to_display_text,
)

# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------


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
    table_spec = TABLE_SPECS.get(table_key)
    title = table_spec.title if table_spec is not None else table_key
    return f"跳转到 {title}：{row_id}"


# ---------------------------------------------------------------------------
# Action management model
# ---------------------------------------------------------------------------


def _pfmea_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    pfmea = result.get("pfmea", {}) if isinstance(result, dict) else {}
    rows = pfmea.get("rows", []) if isinstance(pfmea, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def _missing_after_evaluation(row: dict[str, Any]) -> list[str]:
    status = _first_text_nonempty(row.get("status"), row.get("action_status"))
    if status not in {"已完成", "已验证", "已关闭"}:
        return []
    return [
        field
        for field in ("after_severity", "after_occurrence", "after_detection", "after_ap")
        if row.get(field) in {None, ""}
    ]


def _pending_action(row: dict[str, Any], ap: str) -> bool:
    action = _first_text_nonempty(row.get("optimization_action"), row.get("recommended_action"))
    responsibility = _first_text_nonempty(row.get("responsible_person"), row.get("responsibility"))
    if ap == "H" and not action:
        return True
    if ap in {"H", "M"}:
        return not responsibility or not str(row.get("target_date", "")).strip()
    return False


def _is_overdue(target_date: str, status: str, today: date) -> bool:
    if status in {"已关闭", "已验证"}:
        return False
    try:
        return bool(target_date) and date.fromisoformat(target_date[:10]) < today
    except ValueError:
        return False


def _is_date_overdue(due_date_str: str, today: date) -> bool:
    if not due_date_str or not due_date_str.strip():
        return False
    try:
        return date.fromisoformat(due_date_str[:10]) < today
    except ValueError:
        return False


def _action_items_lookup(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
    items = metadata.get("action_items", []) if isinstance(metadata, dict) else []
    if not items:
        try:
            from minos_core.action_tracking import build_action_items
            items = build_action_items(result)
        except ImportError:
            return {}
    lookup: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        pfmea_id = str(item.get("source_pfmea_id", "")).strip()
        if pfmea_id:
            lookup[pfmea_id] = item
    return lookup


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


def action_management_model(result: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    rows: list[dict[str, Any]] = []
    action_by_pfmea = _action_items_lookup(result)
    for row in _pfmea_rows(result):
        ap = str(row.get("action_priority", row.get("AP", ""))).upper()
        action = _first_text_nonempty(row.get("optimization_action"), row.get("recommended_action"))
        responsibility = _first_text_nonempty(row.get("responsible_person"), row.get("responsibility"))
        status = _first_text_nonempty(row.get("status"), row.get("action_status"))
        target_date = str(row.get("target_date", ""))
        overdue = _is_overdue(target_date, status, today)
        pending_after = bool(_missing_after_evaluation(row))
        pending_action = _pending_action(row, ap)
        pfmea_id = str(row.get("pfmea_id", ""))
        action_item = action_by_pfmea.get(pfmea_id, {})
        rows.append(
            {
                "action_id": action_item.get("action_id", ""),
                "pfmea_id": pfmea_id,
                "process_step_id": row.get("process_step_id", ""),
                "failure_mode": row.get("failure_mode", ""),
                "action_priority": ap,
                "recommended_action": action,
                "responsibility": responsibility,
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
                "is_overdue": _is_date_overdue(action_item.get("due_date", ""), today),
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
            "action_id",
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
            "is_overdue",
            "status_display",
            "jump_label",
        ),
        "column_labels": (
            "行动编号",
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
            "行动项逾期",
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
        status = _first_text_nonempty(row.get("status"), row.get("action_status"))
        row_id = str(row.get("pfmea_id", ""))
        if (
            filter_key == "AP 高" and ap == "H"
            or filter_key == "AP 中" and ap == "M"
            or filter_key == "逾期" and _is_overdue(str(row.get("target_date", "")), status, today)
            or filter_key == "待措施" and _pending_action(row, ap)
            or filter_key == "待措施后评价" and _missing_after_evaluation(row)
            or filter_key == "待确认" and row.get("needs_confirmation")
            or filter_key == "知识库推荐待处理" and row_id in recommendation_targets
            or filter_key == "变更影响待处理" and row_id in change_targets
        ):
            filtered.append(row)
    return filtered


# ---------------------------------------------------------------------------
# Change impact model
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Knowledge recommendation model
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Patch item builders (recommendation / change-impact actions)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Manual review model
# ---------------------------------------------------------------------------


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


def review_dashboard_text(result: dict[str, Any]) -> str:
    """将 review_dashboard.next_actions 格式化为可读中文文本。

    用于 V1.10 复核页面顶部的"下一步建议"区域。
    旧数据没有 review_dashboard 字段时返回空字符串，调用方降级显示旧摘要。
    """
    dashboard = result.get("review_dashboard", {}) if isinstance(result, dict) else {}
    if not isinstance(dashboard, dict) or not dashboard:
        return ""
    lines = [f"状态：{dashboard.get('status_display', '未知')}"]
    next_actions = dashboard.get("next_actions", [])
    if isinstance(next_actions, list) and next_actions:
        lines.append("")
        lines.append("下一步建议：")
        for i, action in enumerate(next_actions, 1):
            lines.append(f"  {i}. {action}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Row relation helpers
# ---------------------------------------------------------------------------


def compute_related_row_ids(
    table_key: str,
    row_id: str,
    result: dict[str, Any],
) -> dict[str, set[str]]:
    """Given a table_key and row_id, return sets of related row IDs for each other table.

    Returns a dict mapping table keys ("process_flow", "pfmea", "control_plan") to
    sets of row IDs that are related to the given row.  The relation follows the
    PFD -> PFMEA -> CP hierarchy via process_step_id and pfmea_id fields.
    """
    if not row_id:
        return {}

    _process_step_lookup(result)
    pfmea_rows_by_id = _pfmea_lookup(result)
    cp_rows = _control_plan_rows(result)

    if table_key == "process_flow":
        related: dict[str, set[str]] = {"pfmea": set(), "control_plan": set()}
        for pf_row in pfmea_rows_by_id.values():
            if str(pf_row.get("process_step_id", "")) == row_id:
                related["pfmea"].add(str(pf_row.get("pfmea_id", "")))
        for cp_row in cp_rows:
            if str(cp_row.get("process_step_id", "")) == row_id:
                related["control_plan"].add(str(cp_row.get("control_plan_id", "")))
        return {k: v for k, v in related.items() if v}

    if table_key == "pfmea":
        selected_pfmea_row = pfmea_rows_by_id.get(row_id)
        if selected_pfmea_row is None:
            return {}
        step_id = str(selected_pfmea_row.get("process_step_id", ""))
        pfmea_related: dict[str, set[str]] = {}
        if step_id:
            pfmea_related["process_flow"] = {step_id}
        cp_ids: set[str] = set()
        for cp_row in cp_rows:
            if str(cp_row.get("pfmea_id", "")) == row_id:
                cp_ids.add(str(cp_row.get("control_plan_id", "")))
        if cp_ids:
            pfmea_related["control_plan"] = cp_ids
        return pfmea_related

    if table_key == "control_plan":
        selected_cp_row: dict[str, Any] | None = None
        for row in cp_rows:
            if str(row.get("control_plan_id", "")) == row_id:
                selected_cp_row = row
                break
        if selected_cp_row is None:
            return {}
        pfmea_id = str(selected_cp_row.get("pfmea_id", ""))
        control_related: dict[str, set[str]] = {}
        if pfmea_id:
            control_related["pfmea"] = {pfmea_id}
            linked_pfmea_row = pfmea_rows_by_id.get(pfmea_id)
            if linked_pfmea_row is not None:
                step_id = str(linked_pfmea_row.get("process_step_id", ""))
                if step_id:
                    control_related["process_flow"] = {step_id}
        return control_related

    return {}
