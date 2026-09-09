"""PFD bundle report and manual review items."""
from __future__ import annotations

from typing import Any

from ..audit import AuditItem
from ._support import (
    _flagged_evidence_ids,
    _pending_field_paths,
)


def _pfd_bundle_report(
    pfd_bundle: dict[str, Any],
    stage_mode: str = "generate_pfd",
    next_stage: str = "brainstorm_failure_modes",
    require_operation: bool = True,
) -> dict[str, Any]:
    """Produce a coverage report for a PFD (Process Flow Diagram) bundle."""
    steps = pfd_bundle.get("steps", pfd_bundle.get("process_steps", []))
    links = pfd_bundle.get("links", [])
    pending_fields = _pending_field_paths(pfd_bundle.get("pending_fields", []))
    pfd_blocking_fields: list[str] = []
    ai_inferred_refs = set(
        _flagged_evidence_ids(pfd_bundle.get("ai_inferred_items", []), "ai_inferred")
    )
    evidence = pfd_bundle.get("evidence", [])
    evidence_by_id = {
        str(item.get("evidence_id", "")): item
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_id")
    }
    step_ids: set[str] = set()
    uncovered_items: list[str] = []
    missing_refs: list[str] = []
    needs_confirmation_refs: list[str] = []
    review_items: list[str] = []
    referenced_evidence_ids: set[str] = set()
    referenced_non_ai_evidence_ids: set[str] = set()
    mapped_special_characteristics: set[str] = set()
    if len(steps) < 2:
        uncovered_items.append("process_steps:min_count")
    if len(links) < 1:
        uncovered_items.append("links:min_count")

    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            pfd_blocking_fields.append(f"process_step[{index}]")
            continue
        step_id = str(step.get("process_step_id", step.get("id", ""))).strip()
        operation = str(step.get("operation", step.get("name", ""))).strip()
        if not step_id:
            pfd_blocking_fields.append(f"process_step[{index}].id")
            continue
        step_ids.add(step_id)
        if not operation and require_operation:
            pfd_blocking_fields.append(f"process_step:{step_id}.operation")
        elif not operation:
            review_items.append(f"process_step:{step_id}.operation")
        _check_pfd_evidence_refs(
            f"process_step:{step_id}",
            step.get("evidence_refs", []),
            evidence_by_id,
            pfd_blocking_fields,
            missing_refs,
            ai_inferred_refs,
            needs_confirmation_refs,
            referenced_evidence_ids,
            referenced_non_ai_evidence_ids,
        )
        if not str(step.get("process_function", "")).strip():
            review_items.append(f"process_step:{step_id}.process_function")
        if not step.get("special_characteristics") and step.get("needs_confirmation"):
            review_items.append(f"process_step:{step_id}.special_characteristics")
        mapped_special_characteristics.update(
            _special_characteristic_refs(step.get("special_characteristics"))
        )

    unmapped_special_characteristics = _unmapped_special_characteristics(
        pfd_bundle.get("characteristics", []), mapped_special_characteristics
    )
    if unmapped_special_characteristics:
        review_items.append("process_flow.characteristics.unmapped")

    for index, link in enumerate(links):
        if not isinstance(link, dict):
            pfd_blocking_fields.append(f"trace_link[{index}]")
            continue
        from_id = str(link.get("from", link.get("from_id", ""))).strip()
        to_id = str(link.get("to", link.get("to_id", ""))).strip()
        link_type = str(link.get("link_type", "")).strip()
        if not link_type:
            pfd_blocking_fields.append(f"trace_link[{index}].link_type")
        elif link_type != "sequence":
            uncovered_items.append(f"trace_link[{index}].link_type_invalid:{link_type}")
        if not from_id:
            pfd_blocking_fields.append(f"trace_link[{index}].from")
        elif from_id not in step_ids:
            uncovered_items.append(f"trace_link[{index}].from_missing:{from_id}")
        if not to_id:
            pfd_blocking_fields.append(f"trace_link[{index}].to")
        elif to_id not in step_ids:
            uncovered_items.append(f"trace_link[{index}].to_missing:{to_id}")
        _check_pfd_evidence_refs(
            f"trace_link[{index}]",
            link.get("evidence_refs", []),
            evidence_by_id,
            pfd_blocking_fields,
            missing_refs,
            ai_inferred_refs,
            needs_confirmation_refs,
            referenced_evidence_ids,
            referenced_non_ai_evidence_ids,
        )

    required_count = max(len(steps) + len(links), 1)
    pending_fields.extend(pfd_blocking_fields)
    all_referenced_evidence_ai = (
        bool(referenced_evidence_ids) and not referenced_non_ai_evidence_ids
    )
    if all_referenced_evidence_ai:
        uncovered_items.append("all_referenced_evidence_ai_inferred")
    covered_count = (
        required_count
        - len(uncovered_items)
        - len(pfd_blocking_fields)
        - len(missing_refs)
    )
    evidence_sufficient = bool(
        referenced_evidence_ids
        and referenced_non_ai_evidence_ids
        and not any(item.endswith(".evidence_refs") for item in pfd_blocking_fields)
        and not missing_refs
        and not all_referenced_evidence_ai
    )
    ok = bool(
        len(steps) >= 2
        and len(links) >= 1
        and not pfd_blocking_fields
        and not uncovered_items
        and not missing_refs
        and evidence_sufficient
    )
    return {
        "stage_mode": stage_mode,
        "next_stage": next_stage,
        "required_items": required_count,
        "covered_items": max(covered_count, 0),
        "coverage_ratio": max(covered_count, 0) / required_count
        if required_count
        else 0.0,
        "step_count": len(steps),
        "link_count": len(links),
        "required_step_count": 2,
        "required_link_count": 1,
        "pending_fields": pending_fields,
        "uncovered_items": uncovered_items,
        "missing_refs": missing_refs,
        "ai_inferred_refs": sorted(ai_inferred_refs),
        "needs_confirmation_refs": sorted(set(needs_confirmation_refs)),
        "review_items": sorted(set(review_items)),
        "unmapped_special_characteristics": unmapped_special_characteristics,
        "step_ids": sorted(step_ids),
        "evidence_sufficient": evidence_sufficient,
        "legacy_mode": False,
        "ok": ok,
    }


def _special_characteristic_refs(value: Any) -> set[str]:
    """Extract characteristic references from a string or list of characteristic dicts."""
    if isinstance(value, str):
        return {value.strip()} if value.strip() else set()
    if not isinstance(value, list):
        return set()
    refs: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            ref = str(
                item.get("characteristic_id")
                or item.get("id")
                or item.get("name")
                or ""
            ).strip()
        else:
            ref = str(item).strip()
        if ref:
            refs.add(ref)
    return refs


def _unmapped_special_characteristics(
    characteristics: Any, mapped_refs: set[str]
) -> list[str]:
    """Return characteristic refs that exist in the bundle but are not mapped to any step."""
    if not isinstance(characteristics, list):
        return []
    characteristic_refs: list[str] = []
    for index, item in enumerate(characteristics, start=1):
        if isinstance(item, dict):
            ref = str(
                item.get("characteristic_id")
                or item.get("id")
                or item.get("name")
                or f"characteristics[{index - 1}]"
            ).strip()
        else:
            ref = str(item).strip()
        if ref:
            characteristic_refs.append(ref)
    if not characteristic_refs:
        return []
    return [ref for ref in characteristic_refs if ref not in mapped_refs]


def _check_pfd_evidence_refs(
    label: str,
    refs: Any,
    evidence_by_id: dict[str, dict[str, Any]],
    pfd_blocking_fields: list[str],
    missing_refs: list[str],
    ai_inferred_refs: set[str],
    needs_confirmation_refs: list[str],
    referenced_evidence_ids: set[str],
    referenced_non_ai_evidence_ids: set[str],
) -> None:
    """Validate evidence references for a single PFD step or link."""
    evidence_refs = [str(ref).strip() for ref in refs or [] if str(ref).strip()]
    if not evidence_refs:
        pfd_blocking_fields.append(f"{label}.evidence_refs")
        return
    for ref in evidence_refs:
        evidence_item = evidence_by_id.get(ref)
        if evidence_item is None:
            missing_refs.append(f"{label} -> {ref}")
            continue
        referenced_evidence_ids.add(ref)
        if evidence_item.get("ai_inferred"):
            ai_inferred_refs.add(ref)
        else:
            referenced_non_ai_evidence_ids.add(ref)
        if evidence_item.get("needs_confirmation"):
            needs_confirmation_refs.append(ref)


def _evidence_ids(items: Any) -> list[str]:
    """Extract evidence_id strings from a list of dicts."""
    if not isinstance(items, list):
        return []
    return [
        str(item.get("evidence_id"))
        for item in items
        if isinstance(item, dict) and item.get("evidence_id")
    ]


def _pfd_manual_review_items(report: dict[str, Any]) -> list[AuditItem]:
    """Convert a PFD report into AuditItem objects for manual review."""
    items: list[AuditItem] = []
    for value in report["uncovered_items"]:
        items.append(
            AuditItem(
                value,
                "pfd_incomplete",
                "PFD 缺少进入 brainstorm_failure_modes 的必要内容",
                "blocker",
            )
        )
    for value in report["missing_refs"]:
        items.append(
            AuditItem(
                value,
                "pfd_missing_ref",
                "PFD evidence_refs 引用了不存在的顶层证据",
                "blocker",
            )
        )
    for value in report["pending_fields"]:
        items.append(
            AuditItem(value, "pfd_pending_field", "PFD 存在待补字段", "blocker")
        )
    for value in report["needs_confirmation_refs"]:
        items.append(
            AuditItem(
                value, "pfd_needs_confirmation", "PFD 引用内容需要人工确认", "review"
            )
        )
    for value in report["ai_inferred_refs"]:
        items.append(
            AuditItem(value, "pfd_ai_inferred", "PFD 输入包含 AI 推断证据", "review")
        )
    for value in report.get("review_items", []):
        items.append(
            AuditItem(value, "pfd_review_field", "PFD 字段为空，需要人工复核", "review")
        )
    return items
