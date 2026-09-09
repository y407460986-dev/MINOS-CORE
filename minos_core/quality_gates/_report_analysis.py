"""Analysis bundle and failure mode candidates reports."""
from __future__ import annotations

import re
from typing import Any

from ..audit import AuditItem
from ._support import (
    _pending_field_paths,
)


def _failure_mode_candidates_report(
    candidates_bundle: dict[str, Any],
) -> dict[str, Any]:
    """Analyse the failure mode candidates bundle and return a coverage report."""
    process_steps = candidates_bundle.get(
        "process_steps", candidates_bundle.get("steps", [])
    )
    candidates = candidates_bundle.get(
        "candidates", candidates_bundle.get("failure_mode_candidates", [])
    )
    evidence = candidates_bundle.get("evidence", [])
    evidence_by_id = {
        str(item.get("evidence_id", "")): item
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_id")
    }
    step_ids = {
        str(step.get("process_step_id", step.get("id", ""))).strip()
        for step in process_steps
        if isinstance(step, dict)
        and str(step.get("process_step_id", step.get("id", ""))).strip()
    }
    candidate_count_by_step = {step_id: 0 for step_id in step_ids}
    upstream_pending_fields = _pending_field_paths(
        candidates_bundle.get("pending_fields", [])
    )
    blocking_pending_fields: list[str] = []
    uncovered_items: list[str] = []
    missing_refs: list[str] = []
    ai_inferred_refs: set[str] = set()
    needs_confirmation_refs: list[str] = []
    referenced_evidence_ids: set[str] = set()
    referenced_non_ai_evidence_ids: set[str] = set()
    candidate_ids: set[str] = set()

    if not candidates:
        uncovered_items.append("failure_mode_candidates:min_count")

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            blocking_pending_fields.append(f"failure_mode_candidate[{index}]")
            continue
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        label = (
            f"failure_mode_candidate:{candidate_id}"
            if candidate_id
            else f"failure_mode_candidate[{index}]"
        )
        step_id = str(candidate.get("process_step_id", "")).strip()
        failure_mode = str(
            candidate.get("failure_mode", candidate.get("candidate_failure_mode", ""))
        ).strip()
        evidence_refs = candidate.get("evidence_refs", [])
        if not candidate_id:
            blocking_pending_fields.append(
                f"failure_mode_candidate[{index}].candidate_id"
            )
        else:
            candidate_ids.add(candidate_id)
        if not step_id:
            blocking_pending_fields.append(f"{label}.process_step_id")
        elif step_id not in step_ids:
            uncovered_items.append(f"{label}.process_step_missing:{step_id}")
        else:
            candidate_count_by_step[step_id] = (
                candidate_count_by_step.get(step_id, 0) + 1
            )
        if not failure_mode:
            blocking_pending_fields.append(f"{label}.failure_mode")
        if candidate.get("needs_confirmation"):
            needs_confirmation_refs.append(candidate_id or label)
        _check_candidate_evidence_refs(
            label,
            evidence_refs,
            evidence_by_id,
            blocking_pending_fields,
            missing_refs,
            uncovered_items,
            ai_inferred_refs,
            needs_confirmation_refs,
            referenced_evidence_ids,
            referenced_non_ai_evidence_ids,
        )

    for step_id in sorted(step_ids):
        if candidate_count_by_step.get(step_id, 0) < 1:
            uncovered_items.append(
                f"process_step:{step_id}.failure_mode_candidates:min_count"
            )

    all_referenced_evidence_ai = (
        bool(referenced_evidence_ids) and not referenced_non_ai_evidence_ids
    )
    if all_referenced_evidence_ai:
        uncovered_items.append("all_referenced_evidence_ai_inferred")

    required_count = max(len(process_steps) + len(candidates), 1)
    covered_count = (
        required_count
        - len(uncovered_items)
        - len(blocking_pending_fields)
        - len(missing_refs)
    )
    evidence_sufficient = bool(
        referenced_evidence_ids
        and referenced_non_ai_evidence_ids
        and not missing_refs
        and not all_referenced_evidence_ai
    )
    ok = bool(
        candidates
        and not blocking_pending_fields
        and not uncovered_items
        and not missing_refs
        and evidence_sufficient
    )
    pending_fields = upstream_pending_fields + blocking_pending_fields
    return {
        "stage_mode": "brainstorm_failure_modes",
        "next_stage": "generate_pfmea",
        "required_items": required_count,
        "covered_items": max(covered_count, 0),
        "coverage_ratio": max(covered_count, 0) / required_count
        if required_count
        else 0.0,
        "step_count": len(process_steps),
        "candidate_count": len(candidates),
        "required_candidate_count": 1,
        "step_ids": sorted(step_ids),
        "candidate_ids": sorted(candidate_ids),
        "candidate_count_by_step": candidate_count_by_step,
        "pending_fields": pending_fields,
        "blocking_pending_fields": blocking_pending_fields,
        "uncovered_items": uncovered_items,
        "missing_refs": missing_refs,
        "ai_inferred_refs": sorted(ai_inferred_refs),
        "needs_confirmation_refs": sorted(set(needs_confirmation_refs)),
        "referenced_evidence_ids": sorted(referenced_evidence_ids),
        "referenced_non_ai_evidence_ids": sorted(referenced_non_ai_evidence_ids),
        "evidence_sufficient": evidence_sufficient,
        "legacy_mode": False,
        "ok": ok,
    }


def _check_candidate_evidence_refs(
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
    """Validate evidence references for a single failure mode candidate."""
    evidence_refs = [str(ref).strip() for ref in refs or [] if str(ref).strip()]
    if not evidence_refs:
        pending_fields.append(f"{label}.evidence_refs")
        return
    candidate_non_ai_refs: set[str] = set()
    candidate_referenced_refs: set[str] = set()
    for ref in evidence_refs:
        evidence_item = evidence_by_id.get(ref)
        if evidence_item is None:
            missing_refs.append(f"{label} -> {ref}")
            continue
        referenced_evidence_ids.add(ref)
        candidate_referenced_refs.add(ref)
        if evidence_item.get("ai_inferred"):
            ai_inferred_refs.add(ref)
        else:
            referenced_non_ai_evidence_ids.add(ref)
            candidate_non_ai_refs.add(ref)
        if evidence_item.get("needs_confirmation"):
            needs_confirmation_refs.append(ref)
    if candidate_referenced_refs and not candidate_non_ai_refs:
        uncovered_items.append(f"{label}.all_evidence_ai_inferred")


def _failure_mode_candidates_manual_review_items(
    report: dict[str, Any],
) -> list[AuditItem]:
    """Convert a failure-mode-candidates report into AuditItem objects."""
    items: list[AuditItem] = []
    for value in report["uncovered_items"]:
        items.append(
            AuditItem(
                value,
                "failure_mode_candidate_incomplete",
                "失效模式候选缺少进入 generate_pfmea 的必要内容",
                "blocker",
            )
        )
    for value in report["missing_refs"]:
        items.append(
            AuditItem(
                value,
                "failure_mode_candidate_missing_ref",
                "失效模式候选 evidence_refs 引用了不存在的顶层证据",
                "blocker",
            )
        )
    for value in report["pending_fields"]:
        items.append(
            AuditItem(
                value,
                "failure_mode_candidate_pending_field",
                "失效模式候选存在必填字段缺失",
                "blocker",
            )
        )
    for value in report["needs_confirmation_refs"]:
        items.append(
            AuditItem(
                value,
                "failure_mode_candidate_needs_confirmation",
                "失效模式候选引用内容需要人工确认",
                "review",
            )
        )
    for value in report["ai_inferred_refs"]:
        items.append(
            AuditItem(
                value,
                "failure_mode_candidate_ai_inferred",
                "失效模式候选引用了 AI 推断证据",
                "review",
            )
        )
    return items


def _analysis_bundle_report(analysis_bundle: dict[str, Any]) -> dict[str, Any]:
    """Analyse the analysis bundle and return a coverage report."""
    required_blocks = [
        "evidence",
        "drawings",
        "characteristics",
        "process_clues",
        "pending_fields",
        "ai_inferred_items",
    ]
    missing_blocks = [name for name in required_blocks if name not in analysis_bundle]
    evidence = analysis_bundle.get("evidence", [])
    drawings = analysis_bundle.get("drawings", [])
    characteristics = analysis_bundle.get("characteristics", [])
    process_clues = analysis_bundle.get("process_clues", [])
    pending_fields = _pending_field_paths(analysis_bundle.get("pending_fields", []))
    uncovered_items: list[str] = []
    if missing_blocks:
        uncovered_items.extend(f"missing_block:{name}" for name in missing_blocks)
    if not drawings:
        uncovered_items.append("drawings")
    if not characteristics:
        uncovered_items.append("characteristics")
    if not process_clues:
        uncovered_items.append("process_clues")

    evidence_ids = [
        str(item.get("evidence_id", "")) for item in evidence if isinstance(item, dict)
    ]
    evidence_id_set = {item for item in evidence_ids if item}
    ai_evidence_ids = {
        str(item.get("evidence_id"))
        for item in evidence
        if isinstance(item, dict)
        and item.get("evidence_id")
        and item.get("ai_inferred")
    }
    missing_refs: list[str] = []
    valid_route_clues: list[dict[str, Any]] = []
    for index, clue in enumerate(process_clues):
        if not isinstance(clue, dict):
            continue
        step_id = str(clue.get("process_step_id", "")).strip().upper()
        operation = str(clue.get("operation", "")).strip()
        source_ref = str(clue.get("source_ref", "")).strip()
        if source_ref and source_ref not in evidence_id_set:
            missing_refs.append(f"process_clues[{index}].source_ref -> {source_ref}")
            continue
        if (
            re.match(r"^P\d+$", step_id)
            and operation
            and source_ref
            and source_ref not in ai_evidence_ids
            and not clue.get("ai_inferred")
        ):
            valid_route_clues.append(clue)
    if len(valid_route_clues) < 2:
        uncovered_items.append("process_clues:min_valid_pxx_count")
    non_ai_evidence = [
        item
        for item in evidence
        if isinstance(item, dict)
        and item.get("evidence_id")
        and item.get("content")
        and not item.get("ai_inferred", False)
    ]
    needs_confirmation_refs = [
        str(item.get("evidence_id"))
        for item in evidence
        if isinstance(item, dict)
        and item.get("needs_confirmation")
        and item.get("evidence_id")
    ]
    ai_inferred_refs = sorted(ai_evidence_ids)
    all_ai = bool(evidence) and not non_ai_evidence
    if all_ai:
        uncovered_items.append("all_evidence_ai_inferred")

    required_count = len(required_blocks)
    covered_count = required_count - len(missing_blocks)
    evidence_sufficient = bool(evidence and non_ai_evidence)
    ok = bool(
        not missing_blocks
        and drawings
        and characteristics
        and len(valid_route_clues) >= 2
        and evidence_sufficient
        and not all_ai
        and not missing_refs
    )
    return {
        "stage_mode": "analyze",
        "next_stage": "generate_pfd",
        "required_items": required_count,
        "covered_items": covered_count,
        "coverage_ratio": covered_count / required_count if required_count else 0.0,
        "required_blocks": required_blocks,
        "missing_blocks": missing_blocks,
        "route_candidate_count": len(process_clues),
        "usable_route_candidate_count": len(valid_route_clues),
        "drawing_count": len(drawings),
        "characteristic_count": len(characteristics),
        "evidence_count": len(evidence),
        "non_inferred_evidence_count": len(non_ai_evidence),
        "pending_fields": pending_fields,
        "uncovered_items": uncovered_items,
        "missing_refs": missing_refs,
        "ai_inferred_refs": ai_inferred_refs,
        "needs_confirmation_refs": needs_confirmation_refs,
        "evidence_ids": evidence_ids,
        "legacy_mode": False,
        "evidence_sufficient": evidence_sufficient,
        "ok": ok,
    }


def _analysis_manual_review_items(
    report: dict[str, Any], analysis_bundle: dict[str, Any]
) -> list[AuditItem]:
    """Convert an analysis report into AuditItem objects for manual review."""
    items: list[AuditItem] = []
    for value in report["uncovered_items"]:
        items.append(
            AuditItem(
                value,
                "analysis_incomplete",
                "分析结果缺少进入 generate_pfd 的必要内容",
                "blocker",
            )
        )
    for value in report["pending_fields"]:
        items.append(
            AuditItem(
                value, "analysis_pending_field", "分析结果存在待确认字段", "review"
            )
        )
    for value in report["ai_inferred_refs"]:
        items.append(
            AuditItem(
                value, "analysis_ai_inferred", "分析输入包含 AI 推断证据", "review"
            )
        )
    for value in report["needs_confirmation_refs"]:
        items.append(
            AuditItem(
                value, "analysis_needs_confirmation", "分析输入包含待确认证据", "review"
            )
        )
    for index, item in enumerate(analysis_bundle.get("risksAndUncertainties", [])):
        if isinstance(item, dict):
            items.append(
                AuditItem(
                    f"risksAndUncertainties[{index}]",
                    str(item.get("type", "risk")),
                    str(item.get("description", item)),
                    "review",
                )
            )
    return items
