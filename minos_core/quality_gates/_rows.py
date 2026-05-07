"""Shared row-level checks for PFMEA and Control Plan."""
from __future__ import annotations

from typing import Any

from ..audit import AuditItem
from ._support import (
    _flagged_evidence_ids,
    _float_value,
    _pending_field_paths,
)


def _document_rows_report(
    *,
    rows: Any,
    evidence: Any,
    pending_fields: Any,
    ai_inferred_items: Any,
    stage_mode: str,
    next_stage: str,
    row_label: str,
    id_field: str,
    required_fields: tuple[str, ...],
    review_fields: tuple[str, ...],
) -> dict[str, Any]:
    document_rows = rows if isinstance(rows, list) else []
    evidence_rows = evidence if isinstance(evidence, list) else []
    evidence_by_id = {
        str(item.get("evidence_id", "")): item
        for item in evidence_rows
        if isinstance(item, dict) and item.get("evidence_id")
    }
    upstream_pending = _pending_field_paths(pending_fields)
    blocking_pending: list[str] = []
    uncovered_items: list[str] = []
    missing_refs: list[str] = []
    needs_confirmation_refs: list[str] = []
    review_items: list[str] = []
    referenced_evidence_ids: set[str] = set()
    referenced_non_ai_evidence_ids: set[str] = set()
    ai_inferred_refs = set(_flagged_evidence_ids(ai_inferred_items, "ai_inferred"))
    row_ids: set[str] = set()

    if not document_rows:
        uncovered_items.append(f"{row_label}:min_count")

    for index, row in enumerate(document_rows):
        if not isinstance(row, dict):
            blocking_pending.append(f"{row_label}[{index}]")
            continue
        row_id = str(row.get(id_field, "")).strip()
        label = f"{row_label}:{row_id}" if row_id else f"{row_label}[{index}]"
        if row_id:
            row_ids.add(row_id)
        if row.get("ai_inferred") and row_id:
            ai_inferred_refs.add(row_id)
        for field_name in required_fields:
            if field_name == "evidence_refs":
                _check_document_evidence_refs(
                    label,
                    row.get("evidence_refs", []),
                    evidence_by_id,
                    blocking_pending,
                    missing_refs,
                    uncovered_items,
                    ai_inferred_refs,
                    needs_confirmation_refs,
                    referenced_evidence_ids,
                    referenced_non_ai_evidence_ids,
                )
                continue
            if not str(row.get(field_name, "")).strip():
                blocking_pending.append(f"{label}.{field_name}")
        for field_name in review_fields:
            if not str(row.get(field_name, "")).strip() or row.get(field_name) in {0, "0"}:
                review_items.append(f"{label}.{field_name}")
        if _document_row_needs_confirmation(row):
            needs_confirmation_refs.append(row_id or label)

    all_referenced_evidence_ai = (
        bool(referenced_evidence_ids) and not referenced_non_ai_evidence_ids
    )
    if all_referenced_evidence_ai:
        uncovered_items.append("all_referenced_evidence_ai_inferred")

    required_count = max(len(document_rows), 1)
    covered_count = (
        required_count
        - len(uncovered_items)
        - len(blocking_pending)
        - len(missing_refs)
    )
    evidence_sufficient = bool(
        referenced_evidence_ids
        and referenced_non_ai_evidence_ids
        and not missing_refs
        and not all_referenced_evidence_ai
    )
    ok = bool(
        document_rows
        and not blocking_pending
        and not uncovered_items
        and not missing_refs
        and evidence_sufficient
    )
    pending = upstream_pending + blocking_pending
    return {
        "stage_mode": stage_mode,
        "next_stage": next_stage,
        "required_items": required_count,
        "covered_items": max(covered_count, 0),
        "coverage_ratio": max(covered_count, 0) / required_count
        if required_count
        else 0.0,
        "row_count": len(document_rows),
        "row_ids": sorted(row_ids),
        "pending_fields": pending,
        "blocking_pending_fields": blocking_pending,
        "uncovered_items": uncovered_items,
        "missing_refs": missing_refs,
        "ai_inferred_refs": sorted(ai_inferred_refs),
        "needs_confirmation_refs": sorted(set(needs_confirmation_refs)),
        "review_items": sorted(set(review_items)),
        "referenced_evidence_ids": sorted(referenced_evidence_ids),
        "referenced_non_ai_evidence_ids": sorted(referenced_non_ai_evidence_ids),
        "evidence_sufficient": evidence_sufficient,
        "legacy_mode": False,
        "ok": ok,
    }


def _check_document_evidence_refs(
    label: str,
    refs: Any,
    evidence_by_id: dict[str, dict[str, Any]],
    pending_fields: list[str],
    missing_refs: list[str],
    uncovered_items: list[str],
    ai_inferred_refs: set[str],
    needs_confirmation_refs: list[str],
    referenced_evidence_ids: set[str],
    referenced_non_ai_evidence_ids: set[str],
) -> None:
    evidence_refs = [str(ref).strip() for ref in refs or [] if str(ref).strip()]
    if not evidence_refs:
        pending_fields.append(f"{label}.evidence_refs")
        return
    row_non_ai_refs: set[str] = set()
    row_referenced_refs: set[str] = set()
    for ref in evidence_refs:
        evidence_item = evidence_by_id.get(ref)
        if evidence_item is None:
            missing_refs.append(f"{label} -> {ref}")
            continue
        referenced_evidence_ids.add(ref)
        row_referenced_refs.add(ref)
        if evidence_item.get("ai_inferred"):
            ai_inferred_refs.add(ref)
        else:
            referenced_non_ai_evidence_ids.add(ref)
            row_non_ai_refs.add(ref)
        if evidence_item.get("needs_confirmation"):
            needs_confirmation_refs.append(ref)
        if _refers_to_confirmable_requirement(evidence_item, label):
            needs_confirmation_refs.append(ref)
    if row_referenced_refs and not row_non_ai_refs:
        uncovered_items.append(f"{label}.all_evidence_ai_inferred")


def _refers_to_confirmable_requirement(evidence_item: dict[str, Any], label: str) -> bool:
    if not evidence_item.get("needs_confirmation"):
        return False
    content = str(evidence_item.get("content", "")).lower()
    source = str(evidence_item.get("source", "")).lower()
    target = label.lower()
    return any(term in source or term in content for term in _label_terms(target))


def _label_terms(label: str) -> tuple[str, ...]:
    if any(term in label for term in ("p20", "rivet", "joint")):
        return ("rivet", "push-out", "push out", "force")
    if any(term in label for term in ("p10", "incoming", "material")):
        return ("material", "thickness")
    if any(term in label for term in ("p30", "final", "inspection", "pack")):
        return ("revision", "barcode", "pack", "quantity")
    return ()


def _document_row_needs_confirmation(row: dict[str, Any]) -> bool:
    if row.get("needs_confirmation"):
        return True
    if not row.get("ai_inferred"):
        return False
    risk_level = str(row.get("source_risk_level", row.get("risk_level", ""))).strip().lower()
    classification = str(row.get("classification", "")).strip()
    confidence = _float_value(row.get("confidence"))
    evidence_refs = [str(ref).strip() for ref in row.get("evidence_refs", []) if str(ref).strip()]
    if risk_level == "high" or classification:
        return True
    if confidence is not None and confidence < 0.75:
        return True
    if not evidence_refs:
        return True
    return _row_ai_reasoning_is_uncertain(row)


def _row_ai_reasoning_is_uncertain(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(field_name, "")).strip()
        for field_name in (
            "ai_reasoning",
            "reasoning",
            "uncertainty",
            "uncertainties",
            "recommended_action",
        )
        if row.get(field_name) is not None
    ).lower()
    return any(
        token in text
        for token in (
            "uncertain",
            "not confirmed",
            "requires engineer",
            "requires engineering",
            "requires quality",
            "requires review",
            "pending",
            "待确认",
            "不确定",
            "需复核",
        )
    )


def _document_manual_review_items(
    report: dict[str, Any],
    *,
    incomplete_category: str,
    missing_ref_category: str,
    pending_category: str,
    needs_confirmation_category: str,
    ai_category: str,
    review_category: str,
    message_prefix: str,
) -> list[AuditItem]:
    items: list[AuditItem] = []
    for value in report["uncovered_items"]:
        items.append(
            AuditItem(value, incomplete_category, f"{message_prefix} 缺少进入下一阶段的必要内容", "blocker")
        )
    for value in report["missing_refs"]:
        items.append(
            AuditItem(value, missing_ref_category, f"{message_prefix} evidence_refs 引用了不存在的顶层证据", "blocker")
        )
    for value in report["pending_fields"]:
        items.append(
            AuditItem(value, pending_category, f"{message_prefix} 存在必填字段缺失", "blocker")
        )
    for value in report["needs_confirmation_refs"]:
        items.append(
            AuditItem(value, needs_confirmation_category, f"{message_prefix} 引用内容需要人工确认", "review")
        )
    row_ids = {str(value).strip() for value in report.get("row_ids", [])}
    for value in report["ai_inferred_refs"]:
        if str(value).strip() in row_ids:
            continue
        items.append(
            AuditItem(value, ai_category, f"{message_prefix} 引用了 AI 推断证据", "review")
        )
    for value in report.get("review_items", []):
        items.append(
            AuditItem(value, review_category, f"{message_prefix} 字段为空，需要人工复核", "review")
        )
    return items
