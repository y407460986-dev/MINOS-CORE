"""Unified closure task helpers for generated three-table runs."""

from __future__ import annotations

import copy
import re
from typing import Any

from minos_core._table_constants import TABLE_ROW_FIELDS as _TABLE_ROW_FIELDS, TABLE_ID_FIELDS as _ID_FIELDS, row_id as _row_id

from ._text_utils import string_list, text
from .edit_patch import EDIT_PATCH_VERSION


_TARGET_PREFIX = {
    "process_flow": "process_step",
    "pfmea": "failure_mode",
    "control_plan": "control_item",
}
_RESOLVED_STATUSES = {
    "已处理",
    "已确认",
    "已采纳",
    "已接受",
    "已应用",
    "已完成",
    "已关闭",
    "无影响",
    "closed",
    "done",
    "resolved",
    "applied",
}
_IGNORED_STATUSES = {"已忽略", "ignored"}


def build_closure_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a flat closure task list from a three-table generation result."""

    if not isinstance(result, dict):
        raise TypeError("result must be a JSON object")

    tasks: dict[str, dict[str, Any]] = {}
    for builder in (
        _drawing_review_tasks,
        _family_confirmation_tasks,
        _process_flow_confirmation_tasks,
        _knowledge_recommendation_tasks,
        _linkage_gap_tasks,
        _change_impact_tasks,
        _action_item_tasks,
        _automation_review_tasks,
    ):
        for task in builder(result):
            tasks.setdefault(task["task_id"], task)
    return list(tasks.values())


def apply_closure_action(
    result: dict[str, Any],
    task_id: str,
    action: str | dict[str, Any],
) -> dict[str, Any]:
    """Return an edit patch that resolves or applies the requested closure task."""

    if not isinstance(result, dict):
        raise TypeError("result must be a JSON object")
    action_payload = _action_payload(action)
    tasks = {task["task_id"]: task for task in build_closure_tasks(result)}
    task = tasks.get(str(task_id).strip())
    if task is None:
        raise KeyError(f"closure task not found: {task_id}")

    item = _patch_item_for_task(task, action_payload)
    return {
        "edit_patch_version": EDIT_PATCH_VERSION,
        "source": "closure_tasks",
        "reason": _action_reason(action_payload),
        "items": [item],
    }


def _drawing_review_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    drawing = result.get("drawing_analysis")
    if not isinstance(drawing, dict):
        return []
    tasks: list[dict[str, Any]] = []
    for block_name in (
        "materials",
        "dimensions",
        "special_characteristics",
        "technical_requirements",
        "manufacturing_clues",
        "uncertainties",
    ):
        rows = drawing.get(block_name, [])
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            confidence = _float(row.get("confidence"))
            needs_confirmation = bool(row.get("needs_confirmation")) or (
                confidence is not None and confidence < 0.75
            )
            if not needs_confirmation:
                continue
            label = _analysis_item_label(block_name, index, row)
            tasks.append(
                _task(
                    task_type="drawing_review",
                    target_table="drawing_analysis",
                    target_row_id=label,
                    severity="review",
                    message=f"图纸识别项 {label} 需要人工确认。",
                    evidence=_evidence_refs(row),
                    recommended_action="confirm_drawing_review",
                    status=_synthetic_status(result, _task_id("drawing_review", label)),
                )
            )

    metadata = drawing.get("metadata", {})
    if isinstance(metadata, dict):
        for index, repair in enumerate(_list(metadata.get("evidence_ref_repairs"))):
            if not isinstance(repair, dict):
                continue
            label = str(repair.get("label") or repair.get("block") or f"repair[{index}]")
            tasks.append(
                _task(
                    task_type="drawing_review",
                    target_table="drawing_analysis",
                    target_row_id=label,
                    severity="review",
                    message=str(
                        repair.get(
                            "message",
                            "图纸证据引用曾被自动修复，需要人工确认。",
                        )
                    ),
                    evidence=_evidence_refs(repair),
                    recommended_action="confirm_drawing_review",
                    status=_synthetic_status(result, _task_id("drawing_review", label)),
                )
            )
    return tasks


def _family_confirmation_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    family = _family_context(result)
    if not family:
        return []
    if not bool(family.get("needs_confirmation")):
        return []
    family_key = text(family.get("family_key"), family.get("key"), default="unknown")
    family_name = text(family.get("family_name"), family.get("name"), default=family_key)
    return [
        _task(
            task_type="family_confirmation",
            target_table="metadata",
            target_row_id=family_key,
            severity="review",
            message=f"零件族 {family_name or family_key} 需要人工确认。",
            evidence=string_list(family.get("knowledge_source_refs", [])),
            recommended_action="confirm_part_family",
            status=_synthetic_status(result, _task_id("family_confirmation", family_key)),
        )
    ]


def _process_flow_confirmation_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for row in _table_rows(result, "process_flow"):
        if not isinstance(row, dict) or _deleted(row) or not row.get("needs_confirmation"):
            continue
        row_id = _row_id("process_flow", row)
        if not row_id:
            continue
        tasks.append(
            _task(
                task_type="process_flow_confirmation",
                target_table="process_flow",
                target_row_id=row_id,
                severity="blocker",
                message=f"PFD 工序 {row_id} 需要人工确认。",
                evidence=_evidence_refs(row),
                recommended_action="confirm_process_flow",
            )
        )
    return tasks


def _knowledge_recommendation_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for item in _metadata_items(result, "knowledge_recommendations"):
        rec_id = text(item.get("recommendation_id"))
        if not rec_id:
            continue
        status = _recommendation_status(item)
        tasks.append(
            _task(
                task_type="knowledge_recommendation",
                target_table=text(item.get("target_table"), default="metadata"),
                target_row_id=text(item.get("target_id"), default=rec_id),
                severity="blocker" if status == "open" else "review",
                message=text(
                    item.get("reason"),
                    item.get("message"),
                    default="知识库推荐需要采纳、应用或填写忽略原因。",
                ),
                evidence=string_list(item.get("knowledge_source_refs", item.get("source", []))),
                recommended_action="accept_or_ignore_recommendation",
                status=status,
                task_id=_task_id("knowledge_recommendation", rec_id),
            )
        )
    return tasks


def _linkage_gap_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for index, item in enumerate(_linkage_items(result)):
        if not isinstance(item, dict):
            continue
        status = _status_from_source(item)
        if status == "resolved":
            continue
        gap_id = text(
            item.get("gap_id"),
            item.get("issue_id"),
            item.get("impact_id"),
            item.get("item_id"),
            default=f"linkage-{index + 1}",
        )
        target_table, target_row_id = _target_from_linkage_item(item)
        tasks.append(
            _task(
                task_type="linkage_gap",
                target_table=target_table,
                target_row_id=target_row_id or gap_id,
                severity=_severity(item.get("severity"), default="blocker"),
                message=text(
                    item.get("message"),
                    item.get("description"),
                    default="三表联动关系需要处理。",
                ),
                evidence=string_list(item.get("evidence_refs", [])),
                recommended_action=text(
                    item.get("recommended_action"),
                    default="apply_sync_or_manual_fix",
                ),
                status=_synthetic_status(result, _task_id("linkage_gap", gap_id)),
                task_id=_task_id("linkage_gap", gap_id),
            )
        )
    return tasks


def _change_impact_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for item in _metadata_items(result, "change_impacts"):
        item_id = text(item.get("item_id"))
        if not item_id:
            continue
        status = _status_from_source(item)
        tasks.append(
            _task(
                task_type="change_impact",
                target_table="metadata",
                target_row_id=item_id,
                severity=_severity(item.get("severity"), default="blocker" if status == "open" else "review"),
                message=text(
                    item.get("message"),
                    default="人工编辑带来的下游影响需要处理。",
                ),
                evidence=string_list(item.get("evidence_refs", [])),
                recommended_action="resolve_change_impact",
                status=status,
                resolution_note=text(item.get("resolution_note"), item.get("ignore_reason")),
                task_id=_task_id("change_impact", item_id),
            )
        )
    return tasks


def _action_item_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    action_items = _metadata_items(result, "action_items")
    unresolved_ids = {
        str(item.get("action_id", "")).strip()
        for item in _unresolved_action_items(action_items)
        if isinstance(item, dict)
    }
    for item in action_items:
        action_id = text(item.get("action_id"))
        if not action_id:
            continue
        status = "open" if action_id in unresolved_ids else _status_from_source(item)
        tasks.append(
            _task(
                task_type="action_item",
                target_table="metadata",
                target_row_id=action_id,
                severity="blocker" if status == "open" else "review",
                message=text(
                    item.get("description"),
                    item.get("recommended_action"),
                    default="PFMEA 行动项需要闭环。",
                ),
                evidence=string_list(item.get("closure_evidence_refs", [])),
                recommended_action="resolve_action_item",
                status=status,
                owner=text(item.get("owner")),
                due_date=text(item.get("due_date")),
                resolution_note=text(item.get("manual_confirmation_event"), item.get("ignore_reason")),
                task_id=_task_id("action_item", action_id),
            )
        )
    return tasks


def _automation_review_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    review = result.get("automation_review")
    if not isinstance(review, dict):
        review = _build_automation_review_safe(result)
    tasks: list[dict[str, Any]] = []
    for item in _list(review.get("automation_tasks")):
        if not isinstance(item, dict):
            continue
        task_id = text(item.get("task_id"), default="")
        row_id = text(item.get("target_id"), default=task_id)
        if item.get("can_batch_confirm"):
            severity = "review"
            action = "batch_confirm"
        else:
            severity = "blocker"
            action = "resolve_automation_review"
        tasks.append(
            _task(
                task_type="automation_review",
                target_table=text(item.get("table"), item.get("target_table"), default="metadata"),
                target_row_id=row_id,
                severity=severity,
                message=text(item.get("message"), default="AI 预审项需要处理。"),
                evidence=string_list(item.get("evidence_refs", [])),
                recommended_action=action,
                status=_synthetic_status(result, _task_id("automation_review", task_id or row_id)),
                task_id=_task_id("automation_review", task_id or row_id),
            )
        )
    for item in _list(review.get("blocking_issues")) + _list(review.get("review_issues")):
        if not isinstance(item, dict):
            continue
        issue_id = text(item.get("issue_id"), item.get("item_id"), item.get("target"))
        if not issue_id:
            continue
        target_table, target_row_id = _table_and_row_from_target(text(item.get("target")))
        tasks.append(
            _task(
                task_type="automation_review",
                target_table=target_table or "metadata",
                target_row_id=target_row_id or issue_id,
                severity=_severity(item.get("severity"), default="blocker"),
                message=text(item.get("message"), default="AI 预审问题需要处理。"),
                evidence=string_list(item.get("evidence_refs", [])),
                recommended_action="resolve_automation_review",
                status=_synthetic_status(result, _task_id("automation_review", issue_id)),
                task_id=_task_id("automation_review", issue_id),
            )
        )
    return tasks


def _task(
    *,
    task_type: str,
    target_table: str,
    target_row_id: str,
    severity: str,
    message: str,
    evidence: list[Any],
    recommended_action: str,
    status: str = "open",
    owner: str = "",
    due_date: str = "",
    resolution_note: str = "",
    task_id: str | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task_id or _task_id(task_type, target_row_id),
        "task_type": task_type,
        "target_table": target_table,
        "target_row_id": target_row_id,
        "severity": _severity(severity),
        "message": message,
        "evidence": evidence,
        "recommended_action": recommended_action,
        "status": status,
        "owner": owner,
        "due_date": due_date,
        "resolution_note": resolution_note,
    }


def _patch_item_for_task(task: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    task_type = task["task_type"]
    target_id = task["target_row_id"]
    action_name = text(action.get("action"), default="resolve")
    reason = _action_reason(action)

    if task_type == "process_flow_confirmation":
        return _confirm_item("process_flow", target_id, reason)
    if task_type == "knowledge_recommendation":
        if action_name == "apply":
            edit_action = "apply_recommendation"
        elif action_name == "ignore":
            edit_action = "ignore_recommendation"
        else:
            edit_action = "accept_recommendation"
        item = {
            "action": edit_action,
            "table": "metadata",
            "target_id": _suffix_id(task["task_id"]),
            "reason": reason,
        }
        return item
    if task_type == "change_impact":
        return {
            "action": "resolve_change_impact",
            "table": "metadata",
            "target_id": target_id,
            "changes": {"status": text(action.get("status"), default="已处理")},
            "reason": reason,
        }
    if task_type == "action_item":
        changes = copy.deepcopy(action.get("changes", {})) if isinstance(action.get("changes"), dict) else {}
        if not changes:
            changes = {
                "status": "closed",
                "manual_confirmation_event": _manual_event(action, task),
            }
        elif changes.get("status") == "closed" and not (
            changes.get("closure_evidence_refs") or changes.get("manual_confirmation_event")
        ):
            changes["manual_confirmation_event"] = _manual_event(action, task)
        return {
            "action": "resolve_action_item",
            "table": "metadata",
            "target_id": target_id,
            "changes": changes,
            "reason": reason,
        }
    if task_type == "automation_review" and task["target_table"] in _TABLE_ROW_FIELDS:
        if action_name in {"confirm", "batch_confirm", "resolve"}:
            return _confirm_item(task["target_table"], target_id, reason)
    return {
        "action": "resolve_review_issue",
        "table": "metadata",
        "target_id": task["task_id"],
        "changes": {"status": text(action.get("status"), default="已处理")},
        "reason": reason,
    }


def _confirm_item(table: str, target_id: str, reason: str) -> dict[str, Any]:
    return {
        "action": "confirm",
        "table": table,
        "target": f"{_TARGET_PREFIX[table]}:{target_id}",
        "target_id": target_id,
        "row_id": target_id,
        "reason": reason,
        "metadata": {"source": "closure_tasks"},
    }


def _metadata(result: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    chain = result.get("chain")
    if isinstance(chain, dict) and isinstance(chain.get("metadata"), dict):
        metadata.update(chain["metadata"])
    if isinstance(result.get("metadata"), dict):
        metadata.update(result["metadata"])
    return metadata


def _metadata_items(result: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for source in (_metadata(result), result):
        items = source.get(key, []) if isinstance(source, dict) else []
        if isinstance(items, list):
            values.extend(item for item in items if isinstance(item, dict))
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in values:
        marker = str(
            item.get("recommendation_id")
            or item.get("item_id")
            or item.get("action_id")
            or item
        )
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped


def _family_context(result: dict[str, Any]) -> dict[str, Any]:
    for source in (
        ((result.get("process_flow") or {}).get("metadata") if isinstance(result.get("process_flow"), dict) else {}),
        _metadata(result),
        result.get("part_family"),
    ):
        if isinstance(source, dict):
            family = source.get("family_context", source)
            if isinstance(family, dict) and (
                family.get("family_key") or family.get("key") or family.get("needs_confirmation")
            ):
                return family
    return {}


def _table_rows(result: dict[str, Any], table: str) -> list[Any]:
    document = result.get(table)
    if isinstance(document, dict):
        for field_name in _TABLE_ROW_FIELDS[table]:
            rows = document.get(field_name)
            if isinstance(rows, list):
                return rows
    chain_key = {"process_flow": "process_steps", "pfmea": "failure_modes", "control_plan": "controls"}[table]
    rows = result.get(chain_key)
    return rows if isinstance(rows, list) else []


def _linkage_items(result: dict[str, Any]) -> list[Any]:
    items: list[Any] = []
    for key in ("linkage_gaps", "live_linkage_issues"):
        value = result.get(key)
        if isinstance(value, list):
            items.extend(value)
    linkage_map = result.get("linkage_map")
    if isinstance(linkage_map, dict) and isinstance(linkage_map.get("gaps"), list):
        items.extend(linkage_map["gaps"])
    linkage_report = result.get("linkage_report")
    if isinstance(linkage_report, dict):
        report_map = linkage_report.get("linkage_map")
        if isinstance(report_map, dict) and isinstance(report_map.get("gaps"), list):
            items.extend(report_map["gaps"])
        if isinstance(linkage_report.get("sync_issues"), list):
            items.extend(linkage_report["sync_issues"])
    return items


def _target_from_linkage_item(item: dict[str, Any]) -> tuple[str, str]:
    table = text(item.get("target_table"))
    row_id = text(item.get("target_id"))
    if table or row_id:
        return table or "metadata", row_id
    return _table_and_row_from_target(text(item.get("target")))


def _table_and_row_from_target(target: str) -> tuple[str, str]:
    if ":" not in target:
        return "", target
    prefix, row_id = target.split(":", 1)
    table = {
        "process_step": "process_flow",
        "process_flow": "process_flow",
        "failure_mode": "pfmea",
        "pfmea": "pfmea",
        "control_item": "control_plan",
        "control_plan": "control_plan",
    }.get(prefix, prefix)
    return table, row_id.split(".", 1)[0]


def _unresolved_action_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        from .action_tracking import unresolved_action_items
    except ImportError:
        return [
            item
            for item in items
            if _status_from_source(item) == "open"
        ]
    return unresolved_action_items(items)


def _build_automation_review_safe(result: dict[str, Any]) -> dict[str, Any]:
    try:
        from .automation_review import build_automation_review
    except ImportError:
        return {}
    try:
        return build_automation_review(result)
    except (ValueError, TypeError, KeyError, AttributeError):
        return {}


def _status_from_source(item: dict[str, Any]) -> str:
    status = text(item.get("status"), item.get("lifecycle_status"))
    if status in _IGNORED_STATUSES:
        if text(item.get("ignore_reason"), item.get("reason")):
            return "ignored"
        return "open"
    if status in _RESOLVED_STATUSES:
        return "resolved"
    return "open"


def _recommendation_status(item: dict[str, Any]) -> str:
    lifecycle = text(item.get("lifecycle_status"))
    status = text(item.get("status"), default="待确认")
    if lifecycle == "applied" or status == "已应用":
        return "resolved"
    if lifecycle == "ignored" or status == "已忽略":
        return "ignored" if text(item.get("ignore_reason")) else "open"
    return "open"


def _synthetic_status(result: dict[str, Any], task_id: str) -> str:
    for item in _metadata_items(result, "review_issues"):
        if text(item.get("issue_id"), item.get("item_id")) != task_id:
            continue
        status = _status_from_source(item)
        if status != "open":
            return status
    return "open"


def _analysis_item_label(block_name: str, index: int, item: dict[str, Any]) -> str:
    for field_name in ("item_id", "evidence_id", "id", "characteristic_id", "operation"):
        value = text(item.get(field_name))
        if value:
            return f"{block_name}[{value}]"
    return f"{block_name}[{index}]"


def _evidence_refs(item: dict[str, Any]) -> list[Any]:
    for key in ("evidence_refs", "evidence", "source_refs"):
        refs = item.get(key)
        if isinstance(refs, list):
            return [copy.deepcopy(ref) for ref in refs]
        if isinstance(refs, str) and refs.strip():
            return [refs.strip()]
    return []




def _task_id(task_type: str, value: str) -> str:
    prefixes = {
        "drawing_review": "CT-DRAWING",
        "family_confirmation": "CT-FAMILY",
        "process_flow_confirmation": "CT-PROCESS",
        "knowledge_recommendation": "CT-KNOWLEDGE",
        "linkage_gap": "CT-LINKAGE",
        "change_impact": "CT-CHANGE",
        "action_item": "CT-ACTION",
        "automation_review": "CT-AUTO",
    }
    return f"{prefixes[task_type]}-{_slug(value)}"


def _suffix_id(task_id: str) -> str:
    for prefix in ("CT-KNOWLEDGE-",):
        if task_id.startswith(prefix):
            return task_id[len(prefix):].replace("__", ":")
    return task_id


def _slug(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "UNKNOWN"
    text = text.replace(":", "__")
    text = re.sub(r"[^0-9A-Za-z_.\-\[\]__]+", "-", text)
    return text.strip("-") or "UNKNOWN"


def _severity(value: Any, *, default: str = "review") -> str:
    result = text(value, default=default).lower()
    return {
        "critical": "blocker",
        "high": "blocker",
        "blocker": "blocker",
        "warning": "warning",
        "warn": "warning",
        "review": "review",
        "medium": "review",
        "low": "review",
    }.get(result, default)


def _action_payload(action: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(action, dict):
        payload = copy.deepcopy(action)
    else:
        payload = {"action": str(action or "resolve")}
    payload.setdefault("action", "resolve")
    return payload


def _action_reason(action: dict[str, Any]) -> str:
    return text(
        action.get("resolution_note"),
        action.get("reason"),
        default="闭环任务已处理",
    )


def _manual_event(action: dict[str, Any], task: dict[str, Any]) -> str:
    return text(
        action.get("manual_confirmation_event"),
        action.get("resolution_note"),
        action.get("reason"),
        default=f"closure-task:{task['task_id']}",
    )


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _deleted(row: dict[str, Any]) -> bool:
    return bool(row.get("deleted") or row.get("soft_deleted"))


def _float(value: Any) -> float | None:
    try:
        return None if value in {None, ""} else float(value)
    except (TypeError, ValueError):
        return None


