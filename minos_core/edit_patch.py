"""Human edit patch support for generated three-table drafts."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from minos_core._table_constants import TABLE_ROW_FIELDS as _TABLE_ROW_FIELDS, TABLE_ID_FIELDS as _ID_FIELDS, row_id as _row_id

from minos_core._text_utils import float_or_none

from .change_management import analyze_change_impacts
from .exporters.three_table_workbooks import (
    export_split_three_table_workbooks,
    export_three_table_workbook,
)
from .knowledge_recommendation import recommend_from_knowledge
from .quality_gates import evaluate_export_gate
from .edit_patch_reports import (
    build_manual_review_payload as _manual_review_payload,
    build_review_dashboard as _build_review_dashboard,
    manual_review_items_from_edit_gate as _manual_review_items_from_edit_gate,
)


EDIT_PATCH_VERSION = "minos-core.edit_patch.v1"
EDIT_HISTORY_KEY = "edit_history"

_TABLES = {"process_flow", "pfmea", "control_plan", "metadata"}
_ACTIONS = {
    "add",
    "update",
    "soft_delete",
    "confirm",
    "accept_recommendation",
    "apply_recommendation",
    "ignore_recommendation",
    "resolve_change_impact",
    "resolve_review_issue",
    "resolve_action_item",
}
_CHAIN_ROW_FIELDS = {
    "process_flow": "process_steps",
    "pfmea": "failure_modes",
    "control_plan": "controls",
}
_TARGET_TYPES = {
    "process_flow": "process_step",
    "pfmea": "failure_mode",
    "control_plan": "control_item",
}
_TARGET_ID_FIELD = {
    "process_flow": "process_step_id",
    "pfmea": "pfmea_id",
    "control_plan": "control_plan_id",
}


class EditPatchError(ValueError):
    """Raised when an edit patch cannot be applied safely."""


def apply_edit_patch(source: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply add/update/soft-delete/confirm edits without mutating the source."""

    if not isinstance(source, dict):
        raise TypeError("source must be a JSON object")
    if not isinstance(patch, dict):
        raise TypeError("edit patch must be a JSON object")
    if patch.get("edit_patch_version") != EDIT_PATCH_VERSION:
        raise EditPatchError(f"edit_patch_version must be {EDIT_PATCH_VERSION!r}")
    raw_items = patch.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise EditPatchError("edit patch items must be a non-empty list")

    payload = copy.deepcopy(source)
    records: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items):
        record = _normalize_item(patch, raw_item, index)
        _apply_normalized_item(payload, record)
        records.append(record)

    if any(record["table"] == "process_flow" for record in records):
        _sort_process_flow_rows_in_place(payload)

    _record_edit_history(payload, records)
    if _is_three_table_result(payload):
        return _refresh_three_table_result(payload)
    if _is_apqp_chain(payload):
        return payload
    raise EditPatchError(
        "source must be a three_table_generation_result or apqp_chain payload"
    )


def _unresolved_action_items(source: dict[str, Any]) -> list[dict[str, Any]]:
    from .action_tracking import unresolved_action_items

    items = source.get("metadata", {}).get("action_items", [])
    return unresolved_action_items(items)


def evaluate_edit_export_gate(source: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the stricter edited-three-table export gate."""

    chain = _filtered_chain_for_export(source)
    gate = evaluate_export_gate(chain)
    unconfirmed_items = _unconfirmed_row_items(source)
    soft_deleted_items = _soft_deleted_row_items(source)
    review_issues = _unresolved_review_issue_items(source, gate)
    review_issues = _dedupe_strings(review_issues + _ai_batch_confirmation_blockers(source))
    recommendation_items = _unresolved_recommendation_items(source, gate)
    change_impact_items = _unresolved_change_impact_items(source, gate)
    action_items = _unresolved_action_items(source)
    return {
        "final_export_allowed": bool(
            gate.allow_user_export
            and not unconfirmed_items
            and not review_issues
            and not recommendation_items
            and not change_impact_items
        ),
        "unconfirmed_items": unconfirmed_items,
        "soft_deleted_items": soft_deleted_items,
        "review_issues": review_issues,
        "knowledge_recommendations": recommendation_items,
        "change_impacts": change_impact_items,
        "action_items": [item["action_id"] for item in action_items],
        "quality_gate": gate.model_dump(),
    }


def export_edited_three_tables(
    source: dict[str, Any],
    output_dir: str | Path,
    export_mode: str = "draft",
) -> dict[str, Any]:
    """Export edited PFD/PFMEA/CP workbooks, filtering soft-deleted rows."""

    if export_mode not in {"draft", "final"}:
        raise EditPatchError("export_mode must be 'draft' or 'final'")
    gate_result = evaluate_edit_export_gate(source)
    if export_mode == "final" and not gate_result["final_export_allowed"]:
        raise EditPatchError("final export is blocked until the export gate is cleared")

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    chain = _filtered_chain_for_export(source)
    metadata = chain.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["soft_deleted_items"] = list(gate_result["soft_deleted_items"])
    quality_gate = evaluate_export_gate(chain)
    manual_review_items = _manual_review_items_from_edit_gate(gate_result)
    unified = export_three_table_workbook(
        chain,
        target_dir / "三表总工作簿.xlsx",
        export_mode=export_mode,
        require_gate=False,
        quality_gate=quality_gate,
        manual_review_items=manual_review_items,
    )
    split = export_split_three_table_workbooks(
        chain,
        target_dir / "三表独立文件",
        export_mode=export_mode,
    )
    return {
        "export_mode": export_mode,
        "final_export_allowed": gate_result["final_export_allowed"],
        "unconfirmed_items": gate_result["unconfirmed_items"],
        "soft_deleted_items": gate_result["soft_deleted_items"],
        "review_issues": gate_result["review_issues"],
        "knowledge_recommendations": gate_result["knowledge_recommendations"],
        "change_impacts": gate_result["change_impacts"],
        "quality_gate": gate_result["quality_gate"],
        "exports": {
            "unified_workbook": str(unified),
            "process_flow": str(split["process_flow"]),
            "pfmea": str(split["pfmea"]),
            "control_plan": str(split["control_plan"]),
        },
    }


def _normalize_item(
    patch: dict[str, Any],
    item: Any,
    index: int,
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise EditPatchError(f"edit patch item {index} must be an object")
    action = _required_text(item.get("action"), f"items[{index}].action")
    if action not in _ACTIONS:
        raise EditPatchError(
            f"items[{index}].action must be add, update, soft_delete, or confirm"
        )
    table = _required_text(item.get("table"), f"items[{index}].table")
    if table not in _TABLES:
        raise EditPatchError(
            f"items[{index}].table must be process_flow, pfmea, control_plan, or metadata"
        )
    if action in {
        "accept_recommendation",
        "apply_recommendation",
        "ignore_recommendation",
        "resolve_change_impact",
        "resolve_review_issue",
        "resolve_action_item",
    }:
        return {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "action": action,
            "table": table,
            "target_id": _required_text(item.get("target_id"), f"items[{index}].target_id"),
            "row": None,
            "changes": copy.deepcopy(item.get("changes", {})) if isinstance(item.get("changes", {}), dict) else {},
            "edited_by": _optional_text(item.get("edited_by", patch.get("edited_by", ""))),
            "edited_at": _optional_text(item.get("edited_at", patch.get("edited_at", ""))),
            "reason": _optional_text(item.get("reason", patch.get("reason", ""))),
            "metadata": _normalized_item_metadata(patch, item),
            "source": _record_source(patch, item),
            "linkage_event_id": _optional_text(item.get("linkage_event_id", "")),
            "linkage_impact_id": _optional_text(item.get("linkage_impact_id", "")),
        }

    row = item.get("row")
    if action == "add":
        if not isinstance(row, dict):
            raise EditPatchError(f"items[{index}].row is required for add")
        target_id = _optional_text(item.get("target_id")) or _row_id(table, row)
        if not target_id:
            raise EditPatchError(f"items[{index}].target_id is required for add")
    else:
        target_id = _required_text(item.get("target_id"), f"items[{index}].target_id")

    changes = item.get("changes", {})
    if action == "update" and not isinstance(changes, dict):
        raise EditPatchError(f"items[{index}].changes must be an object for update")
    if action != "update":
        changes = {}

    return {
        "edit_patch_version": EDIT_PATCH_VERSION,
        "action": action,
        "table": table,
        "target_id": target_id,
        "row": copy.deepcopy(row) if isinstance(row, dict) else None,
        "changes": copy.deepcopy(changes),
        "edited_by": _optional_text(item.get("edited_by", patch.get("edited_by", ""))),
        "edited_at": _optional_text(item.get("edited_at", patch.get("edited_at", ""))),
        "reason": _optional_text(item.get("reason", patch.get("reason", ""))),
        "metadata": _normalized_item_metadata(patch, item),
        "source": _record_source(patch, item),
        "review_status": _optional_text(item.get("review_status", "")),
        "linkage_event_id": _optional_text(item.get("linkage_event_id", "")),
        "linkage_impact_id": _optional_text(item.get("linkage_impact_id", "")),
    }


def _apply_normalized_item(payload: dict[str, Any], record: dict[str, Any]) -> None:
    action = record["action"]
    table = record["table"]
    target_id = record["target_id"]
    if action in {
        "accept_recommendation",
        "apply_recommendation",
        "ignore_recommendation",
        "resolve_change_impact",
        "resolve_review_issue",
        "resolve_action_item",
    }:
        _apply_metadata_action(payload, record)
        return
    if action == "add":
        rows = _editable_rows(payload, table)
        if _find_row(rows, table, target_id) is not None:
            raise EditPatchError(f"edit patch add target already exists: {table}:{target_id}")
        row = copy.deepcopy(record["row"])
        id_field = _TARGET_ID_FIELD[table]
        row.setdefault(id_field, target_id)
        if record.get("source") == "live_linkage":
            row.setdefault("review_status", "联动新增")
        else:
            row["review_status"] = "人工新增"
        row["needs_confirmation"] = True
        row["ai_inferred"] = False
        row["deleted"] = False
        row["changed_fields"] = []
        rows.append(row)
        return

    rows = _editable_rows(payload, table)
    row = _find_row(rows, table, target_id)
    if row is None:
        raise EditPatchError(f"edit patch target not found: {table}:{target_id}")

    if action == "update":
        record["field_changes"] = _field_changes(row, record["changes"])
        row.update(record["changes"])
        changed_field_names = list(record["changes"].keys())
        if isinstance(row.get("changed_fields"), list):
            row["changed_fields"].extend(
                name for name in changed_field_names if name not in row["changed_fields"]
            )
        else:
            row["changed_fields"] = changed_field_names
        row["modified_at"] = record.get("edited_at", "")
        row["modified_by"] = record.get("edited_by", "")
        row["version"] = row.get("version", 0) + 1
        if _is_restore_soft_delete_update(record["changes"]):
            if row.get("review_status") == "软删除":
                row["review_status"] = "待确认"
        elif record.get("source") == "live_linkage":
            if "review_status" not in record.get("changes", {}):
                row["review_status"] = record.get("review_status") or "联动同步"
        else:
            row["review_status"] = "人工修改"
        row["needs_confirmation"] = True
        row["deleted"] = False
        if "soft_deleted" in row and _is_restore_soft_delete_update(record["changes"]):
            row["soft_deleted"] = False
    elif action == "soft_delete":
        row["deleted"] = True
        row["review_status"] = "软删除"
    elif action == "confirm":
        row["review_status"] = "已确认"
        row["needs_confirmation"] = False
        row["ai_inferred"] = False
        metadata = record.get("metadata", {})
        if isinstance(metadata, dict):
            confirmation_mode = _optional_text(metadata.get("confirmation_mode"))
            source = _optional_text(metadata.get("source", record.get("source", "")))
            if confirmation_mode:
                row["confirmation_mode"] = confirmation_mode
            if source:
                row["confirmation_source"] = source
        _remove_confirmation_debt(payload, table, target_id)
        _resolve_matching_review_issues(payload, table, target_id, record)


def _normalized_item_metadata(patch: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    patch_metadata = patch.get("metadata")
    item_metadata = item.get("metadata")
    if isinstance(patch_metadata, dict):
        metadata.update(copy.deepcopy(patch_metadata))
    if isinstance(item_metadata, dict):
        metadata.update(copy.deepcopy(item_metadata))
    source = _optional_text(item.get("source", patch.get("source", "")))
    if source:
        metadata.setdefault("source", source)
    return metadata


def _record_source(patch: dict[str, Any], item: dict[str, Any]) -> str:
    metadata = _normalized_item_metadata(patch, item)
    return _optional_text(metadata.get("source"))


def _apply_metadata_action(payload: dict[str, Any], record: dict[str, Any]) -> None:
    metadata = payload.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise EditPatchError("metadata must be an object")
    action = record["action"]
    target_id = record["target_id"]
    dispatch = {
        "accept_recommendation": _apply_metadata_accept_recommendation,
        "apply_recommendation": _apply_metadata_apply_recommendation,
        "ignore_recommendation": _apply_metadata_ignore_recommendation,
        "resolve_change_impact": _apply_metadata_resolve_change_impact,
        "resolve_review_issue": _apply_metadata_resolve_review_issue,
        "resolve_action_item": _apply_metadata_resolve_action_item,
    }
    handler = dispatch.get(action)
    if handler is not None:
        handler(payload, metadata, record, target_id)


def _apply_metadata_accept_recommendation(
    payload: dict[str, Any], metadata: dict[str, Any], record: dict[str, Any], target_id: str
) -> None:
    rec = _find_recommendation(payload, target_id)
    if rec is None:
        raise EditPatchError(f"recommendation not found: {target_id}")
    rec["status"] = "已接受"
    rec["lifecycle_status"] = "accepted"
    rec["accepted_by"] = record.get("edited_by", "")
    rec["accepted_at"] = record.get("edited_at", "")
    rec["decision"] = "accepted"


def _apply_metadata_apply_recommendation(
    payload: dict[str, Any], metadata: dict[str, Any], record: dict[str, Any], target_id: str
) -> None:
    rec = _find_recommendation(payload, record["target_id"])
    if rec is None:
        raise EditPatchError(f"recommendation not found: {record['target_id']}")
    _apply_recommendation_fields(payload, record, rec)
    applied_fields = record.get("applied_fields", [])
    if applied_fields:
        rec["status"] = "已应用"
        rec["lifecycle_status"] = "applied"
        rec["applied_fields"] = list(applied_fields)
    else:
        rec["status"] = "已接受"
        rec["lifecycle_status"] = "accepted"
    rec["applied_by"] = record.get("edited_by", "")
    rec["applied_at"] = record.get("edited_at", "")


def _apply_metadata_ignore_recommendation(
    payload: dict[str, Any], metadata: dict[str, Any], record: dict[str, Any], target_id: str
) -> None:
    reason = record.get("reason", "").strip()
    if not reason:
        raise EditPatchError("ignore_recommendation requires reason")
    rec = _find_recommendation(payload, target_id)
    if rec is None:
        raise EditPatchError(f"recommendation not found: {target_id}")
    rec["status"] = "已忽略"
    rec["lifecycle_status"] = "ignored"
    rec["ignore_reason"] = reason
    rec["ignored_by"] = record.get("edited_by", "")
    rec["ignored_at"] = record.get("edited_at", "")


def _apply_metadata_resolve_change_impact(
    payload: dict[str, Any], metadata: dict[str, Any], record: dict[str, Any], target_id: str
) -> None:
    items = metadata.setdefault("change_impacts", [])
    _ensure_list(items, "metadata.change_impacts")
    item = _find_metadata_item(items, "item_id", target_id)
    if item is None:
        item = {"item_id": target_id}
        items.append(item)
    status = record.get("changes", {}).get("status") or "已处理"
    item["status"] = status
    if status == "已忽略":
        reason = record.get("reason", "")
        if not reason:
            raise EditPatchError("ignored change impact requires reason")
        item["ignore_reason"] = reason


def _apply_metadata_resolve_review_issue(
    payload: dict[str, Any], metadata: dict[str, Any], record: dict[str, Any], target_id: str
) -> None:
    items = metadata.setdefault("review_issues", [])
    _ensure_list(items, "metadata.review_issues")
    item = _find_metadata_item(items, "issue_id", target_id)
    if item is None:
        item = {"issue_id": target_id}
        items.append(item)
    status = record.get("changes", {}).get("status") or "已处理"
    item["status"] = status
    if record.get("edited_by"):
        item["resolved_by"] = record.get("edited_by", "")
    if record.get("edited_at"):
        item["resolved_at"] = record.get("edited_at", "")
    if status == "已忽略":
        reason = record.get("reason", "")
        if not reason:
            raise EditPatchError("ignored review issue requires reason")
        item["ignore_reason"] = reason


def _apply_metadata_resolve_action_item(
    payload: dict[str, Any], metadata: dict[str, Any], record: dict[str, Any], target_id: str
) -> None:
    action_id = record["target_id"]
    items = metadata.setdefault("action_items", [])
    _ensure_list(items, "metadata.action_items")
    target = None
    for item in items:
        if item.get("action_id") == action_id:
            target = item
            break
    if target is None:
        target = {"action_id": action_id, "created_from": "manual"}
        items.append(target)

    changes = record.get("changes", {})
    new_status = changes.get("status", "")

    if new_status == "closed":
        if not changes.get("closure_evidence_refs") and not changes.get("manual_confirmation_event"):
            raise EditPatchError(
                f"close action {action_id} requires closure_evidence_refs or manual_confirmation_event"
            )
    if new_status == "ignored":
        reason = record.get("reason", "").strip()
        if not reason:
            raise EditPatchError(f"ignore action {action_id} requires reason")
        target["ignore_reason"] = reason

    for key in ("status", "owner", "due_date", "closure_evidence_refs", "manual_confirmation_event", "closed_at", "closed_by"):
        if key in changes:
            target[key] = changes[key]

    if new_status in ("closed", "ignored"):
        target["resolved_by"] = record.get("edited_by", "")
        target["resolved_at"] = record.get("edited_at", "")


def _apply_recommendation_fields(
    payload: dict[str, Any],
    record: dict[str, Any],
    recommendation: dict[str, Any],
) -> None:
    """Write suggested_fields to the target row and linked_control_plan_suggestion to the associated CP row."""
    target_table = str(recommendation.get("target_table", "")).strip()
    target_row_id = str(recommendation.get("target_id", "")).strip()
    suggested_fields = recommendation.get("suggested_fields", {})
    linked_cp = recommendation.get("linked_control_plan_suggestion", {})

    field_changes: list[dict[str, Any]] = record.setdefault("field_changes", [])

    # Write suggested_fields to the target row (PFMEA or CP), skipping existing non-empty values.
    if target_table in _TABLES - {"metadata"} and target_row_id and isinstance(suggested_fields, dict):
        rows = _table_rows(payload, target_table)
        target_row = _find_row(rows, target_table, target_row_id)
        if target_row is not None:
            for field, value in suggested_fields.items():
                if not isinstance(field, str) or not field:
                    continue
                existing = target_row.get(field)
                # For FMEA score fields, treat 0, "0", None, "" as empty.
                _FMEA_SCORE_FIELDS = {"severity", "occurrence", "detection", "rpn",
                                       "after_severity", "after_occurrence", "after_detection", "after_rpn"}
                if field in _FMEA_SCORE_FIELDS:
                    if existing is not None and existing != "" and existing != 0 and existing != "0":
                        continue
                else:
                    if existing is not None and existing != "" and existing != []:
                        continue
                before = target_row.get(field, "")
                target_row[field] = value
                field_changes.append(
                    {"field": f"{target_table}.{field}", "before": before, "after": value}
                )

    # Write linked_control_plan_suggestion to the CP row associated with the PFMEA row.
    if isinstance(linked_cp, dict) and linked_cp:
        cp_rows = _table_rows(payload, "control_plan")
        cp_row = _find_cp_row_by_pfmea_id(cp_rows, target_row_id)
        if cp_row is not None:
            for field, value in linked_cp.items():
                if not isinstance(field, str) or not field:
                    continue
                existing = cp_row.get(field)
                if existing is not None and existing != "" and existing != []:
                    continue
                before = cp_row.get(field, "")
                cp_row[field] = value
                field_changes.append(
                    {"field": f"control_plan.{field}", "before": before, "after": value}
                )

    # Record which fields were actually written
    applied = [fc["field"] for fc in field_changes]
    record.setdefault("applied_fields", []).extend(applied)


def _find_cp_row_by_pfmea_id(rows: list[Any], pfmea_id: str) -> dict[str, Any] | None:
    """Find a control plan row whose pfmea_id matches the given value."""
    if not pfmea_id:
        return None
    for row in rows:
        if isinstance(row, dict) and str(row.get("pfmea_id", "")).strip() == pfmea_id:
            return row
    return None


def _field_changes(row: dict[str, Any], changes: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"field": field_name, "before": row.get(field_name, ""), "after": value}
        for field_name, value in changes.items()
    ]


def _is_restore_soft_delete_update(changes: dict[str, Any]) -> bool:
    if not changes:
        return False
    delete_keys = {"deleted", "soft_deleted"}
    relevant = {key: value for key, value in changes.items() if key in delete_keys}
    if not relevant:
        return False
    if any(bool(value) for value in relevant.values()):
        return False
    return set(changes).issubset(delete_keys | {"review_status"})


def _ensure_list(value: Any, label: str) -> None:
    if not isinstance(value, list):
        raise EditPatchError(f"{label} must be a list")


def _find_metadata_item(items: list[Any], key: str, value: str) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and str(item.get(key, "")).strip() == value:
            return item
    return None


def _find_recommendation(payload: dict[str, Any], target_id: str) -> dict[str, Any] | None:
    """Find a knowledge recommendation in metadata by recommendation_id."""
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        return None
    items = metadata.get("knowledge_recommendations", [])
    if not isinstance(items, list):
        return None
    return _find_metadata_item(items, "recommendation_id", target_id)


def _refresh_three_table_result(payload: dict[str, Any]) -> dict[str, Any]:
    _refresh_change_impacts(payload)
    _refresh_action_items(payload)
    chain = _assemble_chain_from_three_table_result(payload)
    payload["chain"] = chain
    from .risk_structure import build_risk_structure

    payload["risk_structure"] = build_risk_structure(payload)
    gate = evaluate_export_gate(chain)
    quality_gates = dict(payload.get("quality_gates") or {})
    quality_gates["final_three_table"] = gate.model_dump()
    payload["quality_gates"] = quality_gates
    payload["quality_gate"] = quality_gates["final_three_table"]
    edit_gate = evaluate_edit_export_gate(payload)
    payload["manual_review"] = _manual_review_payload(quality_gates, edit_gate)

    from .three_table_linkage import evaluate_three_table_linkage

    linkage_report = evaluate_three_table_linkage(payload)
    payload["linkage_report"] = linkage_report
    payload["linkage_map"] = linkage_report.get("linkage_map", {})
    payload["linkage_gaps"] = linkage_report.get("linkage_map", {}).get("gaps", [])

    payload["review_dashboard"] = _build_review_dashboard(
        payload, edit_gate, payload["risk_structure"], linkage_report,
    )

    payload["status"] = (
        "draft_ready" if edit_gate["final_export_allowed"] else "needs_review"
    )
    payload["status_display"] = {
        "draft_ready": "草案已就绪",
        "needs_review": "待人工复核",
    }[payload["status"]]
    payload["blocked_stage"] = None
    return payload


def _refresh_change_impacts(payload: dict[str, Any]) -> None:
    metadata = payload.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise EditPatchError("metadata must be an object")
    existing = metadata.get("change_impacts", [])
    existing_items = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
    generated = analyze_change_impacts(payload)
    generated_ids = {
        str(item.get("item_id", "")).strip()
        for item in generated
        if str(item.get("item_id", "")).strip()
    }
    by_id: dict[str, dict[str, Any]] = {
        str(item.get("item_id", "")): copy.deepcopy(item)
        for item in existing_items
        if str(item.get("item_id", "")).strip()
    }
    for item in generated:
        item_id = str(item.get("item_id", "")).strip()
        if not item_id:
            continue
        if item_id in by_id:
            merged = dict(item)
            merged.update(by_id[item_id])
            by_id[item_id] = merged
        else:
            by_id[item_id] = copy.deepcopy(item)
    for item_id, item in by_id.items():
        if item_id in generated_ids:
            continue
        if item.get("status") in {"待同步", "待人工确认", "待处理", ""}:
            item["status"] = "无影响"
            item.setdefault("ignore_reason", "")
            item["resolution_note"] = "上游变更已撤销或关联对象已恢复。"
    if by_id:
        metadata["change_impacts"] = list(by_id.values())


def _refresh_action_items(payload: dict[str, Any]) -> None:
    """Regenerate action items from PFMEA rows and merge with existing resolved ones."""
    from .action_tracking import build_action_items, action_items_summary

    metadata = payload.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise EditPatchError("metadata must be an object")
    existing = metadata.get("action_items", [])
    if not isinstance(existing, list):
        existing = []
    generated = build_action_items(payload)
    metadata["action_items"] = _merge_action_items(
        existing=existing,
        generated=generated,
    )
    metadata["action_items_summary"] = action_items_summary(metadata["action_items"])


def _merge_action_items(
    existing: list[dict[str, Any]],
    generated: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge existing action items with newly generated ones.

    Preserves manually resolved statuses (closed, ignored), owner, and due_date.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for item in existing:
        if isinstance(item, dict) and item.get("action_id"):
            by_id[item["action_id"]] = dict(item)
    for item in generated:
        aid = item.get("action_id", "")
        if not aid:
            continue
        if aid in by_id:
            old = by_id[aid]
            # Preserve manually closed/ignored status
            if old.get("status") in ("closed", "ignored"):
                item["status"] = old["status"]
                item["closure_evidence_refs"] = old.get("closure_evidence_refs", [])
                item["manual_confirmation_event"] = old.get("manual_confirmation_event", "")
                item["ignore_reason"] = old.get("ignore_reason", "")
                item["closed_at"] = old.get("closed_at", "")
                item["closed_by"] = old.get("closed_by", "")
            # Preserve manually set owner/due_date
            if old.get("owner"):
                item["owner"] = old["owner"]
            if old.get("due_date"):
                item["due_date"] = old["due_date"]
            # Preserve resolved tracking fields
            for key in ("resolved_by", "resolved_at"):
                if old.get(key):
                    item[key] = old[key]
        by_id[aid] = item
    return list(by_id.values())


def _assemble_chain_from_three_table_result(payload: dict[str, Any]) -> dict[str, Any]:
    process_flow = payload.get("process_flow") or {}
    pfmea = payload.get("pfmea") or {}
    control_plan = payload.get("control_plan") or {}
    original_chain = payload.get("chain") or {}
    drawing_analysis = payload.get("drawing_analysis") or {}
    metadata = dict(original_chain.get("metadata", {}))
    metadata.update(dict(payload.get("metadata", {})))
    chain_metadata = payload.get("chain", {}).get("metadata", {}) if isinstance(payload.get("chain"), dict) else {}
    if isinstance(chain_metadata, dict):
        for key in ("knowledge_recommendations", "change_impacts", "review_issues"):
            if key not in metadata and key in chain_metadata:
                metadata[key] = copy.deepcopy(chain_metadata[key])
    metadata.setdefault("generation_mode", "human_edited_three_table_generation")
    metadata["strict_three_table_linkage"] = True
    metadata["strict_aiag_vda_pfmea_gate"] = True
    process_steps = _filtered_rows(process_flow.get("steps", []))
    active_step_ids = {
        _row_id("process_flow", row)
        for row in process_steps
        if isinstance(row, dict) and _row_id("process_flow", row)
    }
    failure_modes = _filtered_rows_for_active_steps(pfmea.get("rows", []), active_step_ids)
    active_pfmea_ids = {
        _row_id("pfmea", row)
        for row in failure_modes
        if isinstance(row, dict) and _row_id("pfmea", row)
    }
    controls = _filtered_controls(control_plan.get("rows", []), active_step_ids, active_pfmea_ids)
    chain = {
        "document_type": "apqp_chain",
        "schema_version": original_chain.get("schema_version")
        or payload.get("schema_version")
        or "minos-core.generated.v1",
        "product": process_flow.get("product")
        or original_chain.get("product")
        or payload.get("product", {}),
        "drawings": process_flow.get("drawings", original_chain.get("drawings", [])),
        "characteristics": process_flow.get(
            "characteristics", original_chain.get("characteristics", [])
        ),
        "process_steps": process_steps,
        "failure_modes": failure_modes,
        "controls": controls,
        "evidence": drawing_analysis.get("evidence")
        or original_chain.get("evidence")
        or payload.get("evidence", []),
        "links": _filtered_links(
            process_flow.get("links", original_chain.get("links", [])),
            process_flow.get("steps", []),
        ),
        "pending_fields": _dedupe_strings(
            list(original_chain.get("pending_fields", []))
            + list(process_flow.get("pending_fields", []))
            + list(pfmea.get("pending_fields", []))
            + list(control_plan.get("pending_fields", []))
        ),
        "ai_inferred_items": _dedupe_strings(
            list(original_chain.get("ai_inferred_items", []))
            + list(process_flow.get("ai_inferred_items", []))
            + list(pfmea.get("ai_inferred_items", []))
            + list(control_plan.get("ai_inferred_items", []))
        ),
        "metadata": metadata,
    }
    metadata.setdefault("knowledge_recommendations", recommend_from_knowledge(chain))
    return chain


def _filtered_chain_for_export(source: dict[str, Any]) -> dict[str, Any]:
    if _is_three_table_result(source):
        return _assemble_chain_from_three_table_result(source)
    if _is_apqp_chain(source):
        chain = copy.deepcopy(source)
        chain["process_steps"] = _filtered_rows(chain.get("process_steps", []))
        active_step_ids = {
            _row_id("process_flow", row)
            for row in chain["process_steps"]
            if isinstance(row, dict) and _row_id("process_flow", row)
        }
        chain["failure_modes"] = _filtered_rows_for_active_steps(
            chain.get("failure_modes", []),
            active_step_ids,
        )
        active_pfmea_ids = {
            _row_id("pfmea", row)
            for row in chain["failure_modes"]
            if isinstance(row, dict) and _row_id("pfmea", row)
        }
        chain["controls"] = _filtered_controls(
            chain.get("controls", []),
            active_step_ids,
            active_pfmea_ids,
        )
        chain["links"] = _filtered_links(chain.get("links", []), chain["process_steps"])
        return chain
    raise EditPatchError(
        "source must be a three_table_generation_result or apqp_chain payload"
    )


def _editable_rows(payload: dict[str, Any], table: str) -> list[dict[str, Any]]:
    if _is_three_table_result(payload):
        document = payload.setdefault(table, {})
        if not isinstance(document, dict):
            raise EditPatchError(f"{table} must be an object")
        row_field = _TABLE_ROW_FIELDS[table][0]
        rows = document.setdefault(row_field, [])
    elif _is_apqp_chain(payload):
        row_field = _CHAIN_ROW_FIELDS[table]
        rows = payload.setdefault(row_field, [])
    else:
        raise EditPatchError(
            "source must be a three_table_generation_result or apqp_chain payload"
        )
    if not isinstance(rows, list):
        raise EditPatchError(f"{table} rows must be a list")
    return rows


def _table_rows(source: dict[str, Any], table: str) -> list[Any]:
    if _is_three_table_result(source):
        document = source.get(table) or {}
        if not isinstance(document, dict):
            return []
        for field_name in _TABLE_ROW_FIELDS[table]:
            rows = document.get(field_name)
            if isinstance(rows, list):
                return rows
        return []
    if _is_apqp_chain(source):
        rows = source.get(_CHAIN_ROW_FIELDS[table])
        return rows if isinstance(rows, list) else []
    return []


def _find_row(rows: list[Any], table: str, target_id: str) -> dict[str, Any] | None:
    for row in rows:
        if isinstance(row, dict) and _row_id(table, row) == target_id:
            return row
    return None




def _filtered_rows(rows: Any) -> list[Any]:
    if not isinstance(rows, list):
        return []
    return [copy.deepcopy(row) for row in rows if not _is_deleted(row)]


def _sort_process_flow_rows_in_place(payload: dict[str, Any]) -> None:
    rows = _editable_rows(payload, "process_flow")
    rows.sort(key=_process_flow_sort_key)


def _process_flow_sort_key(item: Any) -> tuple[int, float, int]:
    if not isinstance(item, dict):
        return (1, 0, 0)
    sequence = float_or_none(item.get("sequence"))
    if sequence is None:
        return (1, 0, 0)
    return (0, sequence, 0)


def _filtered_rows_for_active_steps(rows: Any, active_step_ids: set[str]) -> list[Any]:
    result = []
    for row in _filtered_rows(rows):
        if not isinstance(row, dict):
            continue
        step_id = _optional_text(row.get("process_step_id"))
        if active_step_ids and step_id and step_id not in active_step_ids:
            continue
        result.append(row)
    return result


def _filtered_controls(
    rows: Any,
    active_step_ids: set[str],
    active_pfmea_ids: set[str],
) -> list[Any]:
    result = []
    for row in _filtered_rows(rows):
        if not isinstance(row, dict):
            continue
        step_id = _optional_text(row.get("process_step_id"))
        pfmea_id = _optional_text(row.get("pfmea_id", row.get("source_pfmea_id", "")))
        if active_step_ids and step_id and step_id not in active_step_ids:
            continue
        if active_pfmea_ids and pfmea_id and pfmea_id not in active_pfmea_ids:
            continue
        result.append(row)
    return result


def _filtered_links(links: Any, process_rows: Any) -> list[Any]:
    if not isinstance(links, list):
        return []
    active_steps = {
        _row_id("process_flow", row)
        for row in process_rows
        if isinstance(row, dict) and not _is_deleted(row)
    }
    filtered = []
    for link in links:
        if not isinstance(link, dict) or _is_deleted(link):
            continue
        from_id = _optional_text(link.get("from", link.get("from_id", "")))
        to_id = _optional_text(link.get("to", link.get("to_id", "")))
        if active_steps and ((from_id and from_id not in active_steps) or (to_id and to_id not in active_steps)):
            continue
        filtered.append(copy.deepcopy(link))
    return filtered


def _is_deleted(row: Any) -> bool:
    return isinstance(row, dict) and bool(row.get("deleted") or row.get("soft_deleted"))


def _remove_confirmation_debt(
    payload: dict[str, Any],
    table: str,
    target_id: str,
) -> None:
    candidates = _confirmation_candidates(table, target_id)
    for container in _debt_containers(payload):
        _remove_ai_items(container, candidates)
        _remove_pending_fields(container, candidates)


def _resolve_matching_review_issues(
    payload: dict[str, Any],
    table: str,
    target_id: str,
    record: dict[str, Any],
) -> None:
    candidates = _confirmation_candidates(table, target_id)
    for container in _debt_containers(payload):
        metadata = container.get("metadata", {}) if isinstance(container, dict) else {}
        if not isinstance(metadata, dict):
            continue
        items = metadata.get("review_issues", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            target = _optional_text(item.get("target"))
            issue_id = _optional_text(item.get("issue_id"))
            if target in candidates or any(issue_id.endswith(candidate.lower()) for candidate in candidates):
                item["status"] = "已确认"
                if record.get("edited_by"):
                    item["resolved_by"] = record.get("edited_by", "")
                if record.get("edited_at"):
                    item["resolved_at"] = record.get("edited_at", "")


def _debt_containers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    containers = [payload]
    for key in ("process_flow", "pfmea", "control_plan", "chain"):
        value = payload.get(key)
        if isinstance(value, dict):
            containers.append(value)
    return containers


def _remove_ai_items(container: dict[str, Any], candidates: set[str]) -> None:
    items = container.get("ai_inferred_items")
    if isinstance(items, list):
        container["ai_inferred_items"] = [
            item for item in items if not _debt_item_matches(item, candidates)
        ]
    elif isinstance(items, str) and items.strip() in candidates:
        container["ai_inferred_items"] = []


def _remove_pending_fields(container: dict[str, Any], candidates: set[str]) -> None:
    items = container.get("pending_fields")
    if isinstance(items, list):
        container["pending_fields"] = [
            item for item in items if not _pending_item_matches(item, candidates)
        ]
    elif isinstance(items, str) and _pending_text_matches(items, candidates):
        container["pending_fields"] = []


def _debt_item_matches(item: Any, candidates: set[str]) -> bool:
    if isinstance(item, str):
        return item.strip() in candidates
    if isinstance(item, dict):
        for field_name in (
            "id",
            "item_id",
            "field",
            "process_step_id",
            "pfmea_id",
            "control_plan_id",
            "source_ref",
        ):
            if str(item.get(field_name, "")).strip() in candidates:
                return True
    return False


def _pending_item_matches(item: Any, candidates: set[str]) -> bool:
    if isinstance(item, str):
        return _pending_text_matches(item, candidates)
    if isinstance(item, dict):
        values = [
            str(item.get("path", "")).strip(),
            str(item.get("field", "")).strip(),
            f"{item.get('source_ref', '')}.{item.get('field', '')}".strip("."),
        ]
        return any(_pending_text_matches(value, candidates) for value in values)
    return False


def _pending_text_matches(value: str, candidates: set[str]) -> bool:
    text = value.strip()
    if not text:
        return False
    if text in candidates:
        return True
    if ":" in text:
        _, tail = text.split(":", 1)
        if tail in candidates:
            return True
    return any(text.startswith(f"{candidate}.") for candidate in candidates)


def _confirmation_candidates(table: str, target_id: str) -> set[str]:
    target_type = _TARGET_TYPES[table]
    return {
        target_id,
        f"{table}:{target_id}",
        f"{target_type}:{target_id}",
    }


def _record_edit_history(
    payload: dict[str, Any],
    records: list[dict[str, Any]],
) -> None:
    metadata = payload.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise EditPatchError("metadata must be an object")
    history = metadata.setdefault(EDIT_HISTORY_KEY, [])
    if not isinstance(history, list):
        raise EditPatchError(f"metadata.{EDIT_HISTORY_KEY} must be a list")
    history.extend(copy.deepcopy(records))

    chain = payload.get("chain")
    if isinstance(chain, dict):
        chain_metadata = chain.setdefault("metadata", {})
        if isinstance(chain_metadata, dict):
            chain_history = chain_metadata.setdefault(EDIT_HISTORY_KEY, [])
            if isinstance(chain_history, list):
                chain_history.extend(copy.deepcopy(records))


def _unconfirmed_row_items(source: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for table in ("process_flow", "pfmea", "control_plan"):
        for row in _table_rows(source, table):
            if not isinstance(row, dict) or _is_deleted(row) or not _row_active_for_export(source, table, row):
                continue
            if row.get("review_status") == "已确认" and row.get("needs_confirmation") is False:
                continue
            row_id = _row_id(table, row)
            items.append(f"{table}:{row_id}" if row_id else table)
    return _dedupe_strings(items)


def _ai_batch_confirmation_blockers(source: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for table in ("process_flow", "pfmea", "control_plan"):
        for row in _table_rows(source, table):
            if not isinstance(row, dict) or _is_deleted(row) or not _row_active_for_export(source, table, row):
                continue
            if _optional_text(row.get("confirmation_mode")) != "ai_recommended_batch":
                continue
            row_id = _row_id(table, row)
            label = f"{table}:{row_id}" if row_id else table
            if _ai_batch_confirmed_row_requires_human(source, table, row):
                items.append(f"{label}:AI批量确认不适用")
    return _dedupe_strings(items)


def _ai_batch_confirmed_row_requires_human(
    source: dict[str, Any],
    table: str,
    row: dict[str, Any],
) -> bool:
    if not _row_evidence_refs(row):
        return True
    confidence = float_or_none(row.get("confidence"))
    if confidence is None or confidence < 0.85:
        return True
    if _row_has_high_ap(row):
        return True
    if _row_has_special_characteristic(source, table, row):
        return True
    return False


def _row_evidence_refs(row: dict[str, Any]) -> list[str]:
    refs = row.get("evidence_refs", [])
    if not isinstance(refs, list):
        return []
    return [str(ref).strip() for ref in refs if str(ref).strip()]


def _row_has_high_ap(row: dict[str, Any]) -> bool:
    return _optional_text(row.get("action_priority", row.get("AP", ""))).upper() == "H"


def _row_has_special_characteristic(
    source: dict[str, Any],
    table: str,
    row: dict[str, Any],
) -> bool:
    if (
        row.get("classification")
        or row.get("characteristic_refs")
        or row.get("special_characteristics")
        or row.get("source_special_characteristics")
    ):
        return True
    if table == "process_flow":
        return False
    step_id = _optional_text(row.get("process_step_id"))
    if not step_id:
        return False
    for step in _table_rows(source, "process_flow"):
        if isinstance(step, dict) and _row_id("process_flow", step) == step_id:
            return bool(step.get("special_characteristics"))
    return False




def _soft_deleted_row_items(source: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for table in ("process_flow", "pfmea", "control_plan"):
        for row in _table_rows(source, table):
            if isinstance(row, dict) and (_is_deleted(row) or not _row_active_for_export(source, table, row)):
                row_id = _row_id(table, row)
                items.append(f"{table}:{row_id}" if row_id else table)
    return _dedupe_strings(items)


def _row_active_for_export(source: dict[str, Any], table: str, row: dict[str, Any]) -> bool:
    if table == "process_flow":
        return not _is_deleted(row)
    process_rows = _table_rows(source, "process_flow")
    has_process_rows = any(isinstance(item, dict) for item in process_rows)
    active_steps = {
        _row_id("process_flow", item)
        for item in process_rows
        if isinstance(item, dict) and not _is_deleted(item) and _row_id("process_flow", item)
    }
    step_id = _optional_text(row.get("process_step_id"))
    if has_process_rows and step_id and step_id not in active_steps:
        return False
    if table == "control_plan":
        pfmea_rows = _table_rows(source, "pfmea")
        has_pfmea_rows = any(isinstance(item, dict) for item in pfmea_rows)
        active_pfmea = {
            _row_id("pfmea", item)
            for item in pfmea_rows
            if isinstance(item, dict)
            and not _is_deleted(item)
            and _row_active_for_export(source, "pfmea", item)
            and _row_id("pfmea", item)
        }
        pfmea_id = _optional_text(row.get("pfmea_id", row.get("source_pfmea_id", "")))
        if has_pfmea_rows and pfmea_id and pfmea_id not in active_pfmea:
            return False
    return True


def _unresolved_review_issue_items(
    source: dict[str, Any],
    gate: Any,
) -> list[str]:
    items: list[str] = []
    for issue in _metadata_items_from_source(source, "review_issues"):
        if _metadata_debt_is_unresolved(issue):
            items.append(_optional_text(issue.get("issue_id")) or "review_issue")
    for issue in getattr(gate, "review_issues", []):
        if isinstance(issue, dict) and _metadata_debt_is_unresolved(issue):
            items.append(_optional_text(issue.get("issue_id")) or "review_issue")
    return _dedupe_strings(items)


def _unresolved_recommendation_items(source: dict[str, Any], gate: Any) -> list[str]:
    items: list[str] = []
    for recommendation in _metadata_items_from_source(source, "knowledge_recommendations"):
        if _metadata_debt_is_unresolved(recommendation):
            items.append(_optional_text(recommendation.get("recommendation_id")) or "knowledge_recommendation")
    gate_payload = gate.model_dump() if hasattr(gate, "model_dump") else {}
    for issue in gate_payload.get("review_issues", []):
        if isinstance(issue, dict) and issue.get("recommendation_id"):
            items.append(_optional_text(issue.get("recommendation_id")))
    return _dedupe_strings(items)


def _unresolved_change_impact_items(source: dict[str, Any], gate: Any) -> list[str]:
    items: list[str] = []
    for impact in _metadata_items_from_source(source, "change_impacts"):
        if _metadata_debt_is_unresolved(impact):
            items.append(_optional_text(impact.get("item_id")) or "change_impact")
    gate_payload = gate.model_dump() if hasattr(gate, "model_dump") else {}
    for issue in gate_payload.get("review_issues", []):
        if isinstance(issue, dict) and issue.get("change_impact_id"):
            items.append(_optional_text(issue.get("change_impact_id")))
    return _dedupe_strings(items)


def _metadata_items_from_source(source: dict[str, Any], key: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for container in _metadata_source_containers(source):
        metadata = container.get("metadata", {}) if isinstance(container, dict) else {}
        if not isinstance(metadata, dict):
            continue
        value = metadata.get(key, [])
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    return items


def _metadata_source_containers(source: dict[str, Any]) -> list[dict[str, Any]]:
    containers = [source]
    chain = source.get("chain") if isinstance(source, dict) else None
    if isinstance(chain, dict):
        containers.append(chain)
    return containers


def _metadata_debt_is_unresolved(item: dict[str, Any]) -> bool:
    status = _optional_text(item.get("status", "待处理"))
    lifecycle = _optional_text(item.get("lifecycle_status", ""))
    # applied / 已应用: resolved regardless of other state
    if lifecycle == "applied" or status == "已应用":
        return False
    # legacy compatibility for pre-lifecycle data
    if status in {"已处理", "已确认", "已采纳", "无影响"}:
        return False
    # ignored with reason: resolved
    if lifecycle == "ignored" or status == "已忽略":
        if _optional_text(item.get("ignore_reason")):
            return False
    return True


def _is_three_table_result(payload: dict[str, Any]) -> bool:
    return payload.get("document_type") == "three_table_generation_result"


def _is_apqp_chain(payload: dict[str, Any]) -> bool:
    return payload.get("document_type") == "apqp_chain" or {
        "process_steps",
        "failure_modes",
        "controls",
    }.issubset(payload)


def _required_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if not text:
        raise EditPatchError(f"{field_name} must be a non-empty string")
    return text


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _dedupe_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result
