"""Edit patch building and automation review for the three-table editor."""
from __future__ import annotations

import copy
import json
from typing import Any

from .models import (
    change_impact_model,
    manual_review_model,
    navigation_label,
    navigation_label_from_target,
    navigation_target,
    navigation_target_from_ref,
)
from .specs import (
    AUTOMATION_BATCH_CONFIRM_MODE,
    AUTOMATION_REVIEW_SOURCE,
    EDIT_PATCH_VERSION,
    META_CONFIRMED,
    META_IS_NEW,
    META_ORIGINAL,
    META_ROW_ID,
    META_SOFT_DELETED,
    TABLE_SPECS,
    TableSpec,
    _changed_fields,
    _knowledge_recommendations,
    _normalize_row_values,
    _review_issue_lookup,
    table_spec,
)

# ---------------------------------------------------------------------------
# Edit patch building
# ---------------------------------------------------------------------------


def _effective_row_id(
    spec: TableSpec,
    row: dict[str, Any],
    normalized: dict[str, Any],
) -> str:
    return str(row.get(META_ROW_ID) or normalized.get(spec.row_id_field) or "")


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


# ---------------------------------------------------------------------------
# Automation review model
# ---------------------------------------------------------------------------


def _ensure_automation_model(result_or_model: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result_or_model, dict) and "summary" in result_or_model and "rows" in result_or_model:
        return result_or_model
    return automation_review_model(result_or_model)


def _automation_review_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
    candidates: list[Any] = []
    if isinstance(metadata, dict):
        candidates.extend(
            metadata.get(key, [])
            for key in ("automation_review", "automation_review_items", "ai_pre_review")
        )
    if isinstance(result, dict):
        review = result.get("automation_review", [])
        if isinstance(review, dict):
            review_items: list[dict[str, Any]] = []
            for item in review.get("batch_confirm_candidates", []):
                if isinstance(item, dict):
                    review_items.append({**item, "review_category": "可批量确认"})
            for item in review.get("automation_tasks", []):
                if isinstance(item, dict):
                    review_items.append(item)
            for item in review.get("blocking_issues", []):
                if isinstance(item, dict):
                    review_items.append({**item, "review_category": "阻断问题"})
            for item in review.get("review_issues", []):
                if isinstance(item, dict):
                    review_items.append(item)
            candidates.append(review_items)
        else:
            candidates.append(review)
    for value in candidates:
        if isinstance(value, dict):
            value = value.get("items", [])
        if isinstance(value, list):
            items = [item for item in value if isinstance(item, dict)]
            if items:
                return items
    return []


def _automation_category(item: dict[str, Any]) -> str:
    category = str(item.get("review_category") or item.get("category") or "").strip()
    if category in {"可批量确认", "需要人工判断", "阻断问题"}:
        return category
    action = str(item.get("recommended_action") or item.get("action") or "").strip()
    if item.get("can_batch_confirm") is True:
        return "可批量确认"
    risk = str(item.get("risk_level") or item.get("risk") or item.get("severity") or "").lower()
    if action in {"batch_confirm", "confirm"} or risk in {"low", "低", "low_risk"}:
        return "可批量确认"
    if risk in {"blocker", "blocking", "阻断", "必须修复", "error"}:
        return "阻断问题"
    return "需要人工判断"


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
    confidence = row.get("confidence", row.get("ai_confidence"))
    try:
        return bool(row.get("ai_inferred")) and confidence is not None and float(confidence) >= 0.85
    except (TypeError, ValueError):
        return False


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


def _automation_review_rows_from_review_issues(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue in _review_issue_lookup(result).values():
        issue_id = str(issue.get("issue_id", "")).strip()
        if not issue_id or issue_id in seen:
            continue
        seen.add(issue_id)
        rows.append(_automation_review_row(issue, result))
    return rows


def _automation_review_rows_from_metadata(result: dict[str, Any]) -> list[dict[str, Any]]:
    from minos_core.knowledge_recommendation import unresolved_recommendations

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


def _dedupe_automation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"阻断问题": 3, "可批量确认": 2, "需要人工判断": 1}
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("target_table", "")),
            str(row.get("target_id", "") or row.get("issue_id", "")),
        )
        existing = by_key.get(key)
        row_priority = priority.get(str(row.get("review_category")), 0)
        existing_priority = (
            priority.get(str(existing.get("review_category")), 0)
            if existing is not None
            else -1
        )
        if (
            existing is None
            or row_priority > existing_priority
            or (
                row_priority == existing_priority
                and row.get("issue_id")
                and not existing.get("issue_id")
            )
        ):
            by_key[key] = row
    return list(by_key.values())


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


def automation_review_model(result: dict[str, Any]) -> dict[str, Any]:
    """Build a UI-neutral AI pre-review model for desktop review screens."""

    rows: list[dict[str, Any]] = []
    explicit_items = _automation_review_items(result)
    if explicit_items:
        rows.extend(_automation_review_row(item, result) for item in explicit_items)
    else:
        rows.extend(_automation_review_rows_from_tables(result))
        rows.extend(_automation_review_rows_from_manual_review(result))
        rows.extend(_automation_review_rows_from_review_issues(result))
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
        from .models import recommendation_action_patch_item
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


# ---------------------------------------------------------------------------
# V1.11 工作包 E：联动预览辅助
# ---------------------------------------------------------------------------


def build_temp_edit_patch(
    rows_by_table: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """从当前表格行数据构建临时 edit patch，用于联动预览。

    与 ``table_rows_to_edit_patch`` 相同，但不会持久化。
    """
    return table_rows_to_edit_patch(rows_by_table)


def try_preview_live_linkage(
    before: dict[str, Any],
    rows_by_table: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """尝试预览联动影响；失败时返回空 dict（降级安全）。"""
    patch = build_temp_edit_patch(rows_by_table)
    if not patch.get("items"):
        return {}
    try:
        from minos_core.live_linkage import preview_live_linkage_impacts
        return preview_live_linkage_impacts(before, patch)
    except (ImportError, Exception):
        return {}
