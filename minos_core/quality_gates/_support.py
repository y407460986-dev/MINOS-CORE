"""Support utilities: evidence, confirmations, batch safety, review issues, tools."""
from __future__ import annotations

import copy
import re
from typing import Any

from ..audit import AuditItem, audit_chain
from ..domain import APQPChain
from ..review_patch import REVIEW_CONFIRMATIONS_KEY
from ..review_issues import (
    build_review_issue,
    review_issue_from_manual_item,
    unresolved_review_issues,
)
from ..validation import ChainValidationResult, validate_chain

__all__ = [
    "_ai_inferred_items",
    "_confirmation_matches_value",
    "_confirmed_field_paths",
    "_confirmed_targets",
    "_dedupe_preserve_order",
    "_dedupe_review_issues",
    "_dict_manual_review_items",
    "_evidence_coverage_report",
    "_evidence_manual_review_items",
    "_evidence_sufficient",
    "_flagged_evidence_ids",
    "_flagged_item_label",
    "_flagged_item_labels",
    "_float_value",
    "_ingest_evidence_report",
    "_is_confirmed",
    "_is_mechanical_trace_link",
    "_iter_evidence_required_items",
    "_metadata_list",
    "_pending_field_paths",
    "_pending_fields",
    "_recommendation_manual_review_items",
    "_review_confirmations",
    "_review_issues_from_gate_debts",
    "_row_mapping_id",
    "_row_needs_confirmation_items",
    "_row_needs_confirmation_manual_review_items",
    "_safe_ai_batch_confirmation_targets",
    "_safe_ai_batch_row",
    "_stage_validation",
    "_strict_aiag_vda_pfmea_gate_enabled",
    "_trace_link_label",
    "_unsafe_ai_batch_review_issues",
    "_with_safe_ai_batch_confirmations",
    "_without_confirmed",
]

def _metadata_list(chain: APQPChain, key: str) -> list[dict[str, Any]]:
    value = chain.metadata.get(key, []) if isinstance(chain.metadata, dict) else []
    return value if isinstance(value, list) else []


def _strict_aiag_vda_pfmea_gate_enabled(chain: APQPChain) -> bool:
    metadata = chain.metadata if isinstance(chain.metadata, dict) else {}
    if metadata.get("skip_strict_gate") is True:
        return False
    if metadata.get("strict_aiag_vda_pfmea_gate") is True:
        return True
    generation_mode = str(metadata.get("generation_mode", "")).strip()
    if generation_mode in {
        "ai_drawing_three_table_generation",
        "human_edited_three_table_generation",
    }:
        return True
    return False


def _dict_manual_review_items(items: list[dict[str, Any]]) -> list[AuditItem]:
    return [
        AuditItem(
            str(item.get("item_id", "")),
            str(item.get("category", "人工复核")),
            str(item.get("message", "")),
            str(item.get("severity", "review")),
        )
        for item in items
    ]


def _recommendation_manual_review_items(items: list[dict[str, Any]]) -> list[AuditItem]:
    return [
        AuditItem(
            str(item.get("recommendation_id", item.get("item_id", ""))),
            "知识库推荐",
            str(item.get("reason", "知识库推荐需要人工采纳或填写忽略原因。")),
            "review",
        )
        for item in items
    ]


def _review_issues_from_gate_debts(
    *,
    manual_review_items: list[Any],
    needs_confirmation_items: list[str],
    recommendation_blockers: list[dict[str, Any]],
    change_blockers: list[dict[str, Any]],
    existing_review_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in manual_review_items:
        issues.append(review_issue_from_manual_item(item))
    for item in needs_confirmation_items:
        issues.append(
            build_review_issue(
                category="人工确认",
                message="关键对象标记为待确认，需要人工确认后才能正式放行。",
                severity="review",
                source="quality_gate",
                target=item,
            )
        )
    for item in recommendation_blockers:
        issues.append(
            build_review_issue(
                category="知识库推荐",
                message=str(item.get("reason", "知识库推荐需要人工采纳或填写忽略原因。")),
                severity="blocker",
                source="knowledge_recommendation",
                target=str(item.get("target_id", "")),
                recommendation_id=str(item.get("recommendation_id", "")),
                confidence=item.get("confidence"),
            )
        )
    for item in change_blockers:
        issues.append(
            build_review_issue(
                category="变更影响",
                message=str(item.get("message", "变更影响需要处理后才能正式放行。")),
                severity=str(item.get("severity", "blocker")),
                source="change_management",
                target=str(item.get("target", "")),
                change_impact_id=str(item.get("item_id", "")),
            )
        )
    issues.extend(dict(item) for item in existing_review_issues)
    return _dedupe_review_issues(issues)


def _dedupe_review_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        issue_id = str(item.get("issue_id", "")).strip()
        if not issue_id:
            continue
        if issue_id in seen:
            continue
        result.append(item)
        seen.add(issue_id)
    return result


def _float_value(value: Any) -> float | None:
    try:
        return None if value in {None, ""} else float(value)
    except (TypeError, ValueError):
        return None


def _flagged_evidence_ids(items: Any, flag: str) -> list[str]:
    if isinstance(items, dict):
        iterable = [items]
    elif isinstance(items, list):
        iterable = items
    else:
        return []
    return [
        str(item.get("evidence_id") or item.get("item_id"))
        for item in iterable
        if isinstance(item, dict)
        and (item.get("evidence_id") or item.get("item_id"))
        and item.get(flag)
    ]


def _pending_field_paths(items: Any) -> list[str]:
    if items is None:
        return []
    if isinstance(items, str):
        value = items.strip()
        return [value] if value else []
    if not isinstance(items, list):
        return ["pending_fields"]
    paths: list[str] = []
    for item in items:
        if isinstance(item, str):
            value = item.strip()
            if value:
                paths.append(value)
            continue
        if isinstance(item, dict) and item.get("field"):
            paths.append(
                f"{item.get('source_ref', '')}.{item.get('field', '')}".strip(".")
            )
    return paths


def _evidence_sufficient(chain: APQPChain) -> bool:
    return bool(_evidence_coverage_report(chain)["ok"])


def _stage_validation(chain: APQPChain, stage: str) -> ChainValidationResult:
    if stage in {"ingest", "analyze"}:
        return ChainValidationResult(ok=True, messages=[], chain=chain)
    return validate_chain(chain)


def _ingest_evidence_report(chain: APQPChain) -> dict[str, Any]:
    missing_fields: list[str] = []
    duplicate_ids: list[str] = []
    seen_ids: set[str] = set()
    usable_non_ai = 0
    usable_count = 0
    ai_inferred_refs: list[str] = []
    needs_confirmation_refs: list[str] = []

    for index, evidence in enumerate(chain.evidence, start=1):
        label = evidence.evidence_id or f"evidence[{index}]"
        if not evidence.evidence_id:
            missing_fields.append(f"{label}.evidence_id")
        elif evidence.evidence_id in seen_ids:
            duplicate_ids.append(evidence.evidence_id)
        else:
            seen_ids.add(evidence.evidence_id)
        if not evidence.source.strip():
            missing_fields.append(f"{label}.source")
        if not evidence.content.strip():
            missing_fields.append(f"{label}.content")
        usable = bool(
            evidence.evidence_id
            and evidence.source.strip()
            and evidence.content.strip()
        )
        if usable:
            usable_count += 1
            if not evidence.ai_inferred:
                usable_non_ai += 1
        if evidence.ai_inferred:
            ai_inferred_refs.append(label)
        if evidence.needs_confirmation:
            needs_confirmation_refs.append(label)

    all_ai = bool(chain.evidence) and usable_count > 0 and usable_non_ai == 0
    uncovered_items = missing_fields + [f"duplicate:{item}" for item in duplicate_ids]
    if all_ai:
        uncovered_items.append("all_evidence_ai_inferred")

    required_count = max(len(chain.evidence), 1)
    ok = (
        bool(chain.evidence)
        and usable_count > 0
        and usable_non_ai > 0
        and not missing_fields
        and not duplicate_ids
    )
    return {
        "required_items": required_count,
        "covered_items": usable_count,
        "coverage_ratio": usable_count / required_count if required_count else 0.0,
        "uncovered_items": uncovered_items,
        "missing_refs": [],
        "ai_inferred_refs": ai_inferred_refs,
        "needs_confirmation_refs": needs_confirmation_refs,
        "legacy_mode": False,
        "stage_mode": "ingest",
        "ok": ok,
    }


def _evidence_coverage_report(chain: APQPChain) -> dict[str, Any]:
    if not chain.evidence:
        structurally_present = bool(
            chain.process_steps and chain.failure_modes and chain.controls
        )
        required_count = (
            len(chain.process_steps) + len(chain.failure_modes) + len(chain.controls)
        )
        return {
            "required_items": required_count,
            "covered_items": 0,
            "coverage_ratio": 0.0,
            "uncovered_items": [],
            "missing_refs": [],
            "ai_inferred_refs": [],
            "needs_confirmation_refs": [],
            "legacy_mode": True,
            "ok": structurally_present,
        }

    evidence_by_id = {
        item.evidence_id: item for item in chain.evidence if item.evidence_id
    }
    required_items = _iter_evidence_required_items(chain)
    uncovered_items: list[str] = []
    missing_refs: list[str] = []
    ai_inferred_refs: list[str] = []
    needs_confirmation_refs: list[str] = []

    for item_type, item_id, refs in required_items:
        label = f"{item_type}:{item_id}"
        normalized_refs = [str(ref).strip() for ref in refs if str(ref).strip()]
        if not normalized_refs:
            uncovered_items.append(label)
            continue
        for ref in normalized_refs:
            evidence = evidence_by_id.get(ref)
            if evidence is None:
                missing_refs.append(f"{label} -> {ref}")
                continue
            if evidence.ai_inferred:
                ai_inferred_refs.append(f"{label} -> {ref}")
            if evidence.needs_confirmation:
                needs_confirmation_refs.append(f"{label} -> {ref}")

    required_count = len(required_items)
    covered_count = required_count - len(uncovered_items)
    return {
        "required_items": required_count,
        "covered_items": covered_count,
        "coverage_ratio": covered_count / required_count if required_count else 0.0,
        "uncovered_items": uncovered_items,
        "missing_refs": missing_refs,
        "ai_inferred_refs": ai_inferred_refs,
        "needs_confirmation_refs": needs_confirmation_refs,
        "legacy_mode": False,
        "ok": bool(required_count)
        and not uncovered_items
        and not missing_refs
        and not ai_inferred_refs,
    }


def _iter_evidence_required_items(chain: APQPChain) -> list[tuple[str, str, list[str]]]:
    return [
        *[
            ("process_step", item.process_step_id, item.evidence_refs)
            for item in chain.process_steps
        ],
        *[
            ("failure_mode", item.pfmea_id, item.evidence_refs)
            for item in chain.failure_modes
        ],
        *[
            ("control_item", item.control_plan_id, item.evidence_refs)
            for item in chain.controls
        ],
    ]


def _evidence_manual_review_items(report: dict[str, Any]) -> list[AuditItem]:
    items: list[AuditItem] = []
    for value in report["uncovered_items"]:
        items.append(
            AuditItem(value, "evidence_uncovered", "对象缺少 evidence_refs", "blocker")
        )
    for value in report["missing_refs"]:
        items.append(
            AuditItem(
                value,
                "evidence_missing_ref",
                "evidence_refs 引用了不存在的证据",
                "blocker",
            )
        )
    for value in report["ai_inferred_refs"]:
        items.append(
            AuditItem(
                value,
                "evidence_ai_inferred",
                "引用证据为 AI 推断，需要人工确认",
                "blocker",
            )
        )
    for value in report["needs_confirmation_refs"]:
        items.append(
            AuditItem(
                value, "evidence_needs_confirmation", "对象或引用证据标记为待确认", "review"
            )
        )
    return items


def _row_needs_confirmation_items(chain: APQPChain) -> list[str]:
    items: list[str] = []
    for step in chain.process_steps:
        if step.needs_confirmation:
            items.append(f"process_step:{step.process_step_id}")
    for candidate in chain.failure_mode_candidates:
        if candidate.needs_confirmation:
            items.append(f"failure_mode_candidate:{candidate.candidate_id}")
    for failure in chain.failure_modes:
        if failure.needs_confirmation:
            items.append(f"failure_mode:{failure.pfmea_id}")
    for control in chain.controls:
        if control.needs_confirmation:
            items.append(f"control_item:{control.control_plan_id}")
    for link in chain.links:
        if link.needs_confirmation and not _is_mechanical_trace_link(link):
            items.append(_trace_link_label(link))
    items.extend(_pending_field_paths(chain.pending_fields))
    items.extend(_flagged_item_labels(chain.ai_inferred_items, "needs_confirmation"))
    return _dedupe_preserve_order(items)


def _row_needs_confirmation_manual_review_items(items: list[str]) -> list[AuditItem]:
    return [
        AuditItem(
            item,
            "row_needs_confirmation",
            "关键对象标记为待确认，需要人工复核后才能正式放行",
            "review",
        )
        for item in items
    ]


def _is_mechanical_trace_link(link: Any) -> bool:
    """Return True for mechanically generated trace links that do not need
    independent human confirmation (real gating is done by linkage gaps)."""
    link_id = str(getattr(link, "trace_link_id", "")).strip().upper()
    for prefix in ("TL-PFD-PFMEA-", "TL-PFMEA-CP-", "TL-STEP-CAND-"):
        if link_id.startswith(prefix):
            return True
    return False


def _trace_link_label(link: Any) -> str:
    link_id = str(getattr(link, "trace_link_id", "")).strip()
    if link_id:
        return f"trace_link:{link_id}"
    from_id = str(getattr(link, "from_id", "")).strip()
    to_id = str(getattr(link, "to_id", "")).strip()
    if from_id or to_id:
        return f"trace_link:{from_id}->{to_id}"
    return "trace_link"


def _flagged_item_labels(items: Any, flag: str) -> list[str]:
    if isinstance(items, dict):
        iterable = [items]
    elif isinstance(items, list):
        iterable = items
    else:
        return []
    labels: list[str] = []
    for index, item in enumerate(iterable):
        if isinstance(item, str):
            if flag == "needs_confirmation" and item.strip():
                labels.append(item.strip())
            continue
        if not isinstance(item, dict) or not item.get(flag):
            continue
        labels.append(_flagged_item_label(item, index))
    return labels


def _flagged_item_label(item: dict[str, Any], index: int) -> str:
    for field_name in (
        "id",
        "item_id",
        "field",
        "evidence_id",
        "process_step_id",
        "pfmea_id",
        "control_plan_id",
        "candidate_id",
        "link_id",
        "trace_link_id",
    ):
        value = str(item.get(field_name, "")).strip()
        if value:
            return value
    return f"ai_inferred_item[{index}]"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def _confirmed_targets(chain: APQPChain) -> set[str]:
    return {
        str(item.get("target", "")).strip()
        for item in _review_confirmations(chain)
        if isinstance(item, dict) and str(item.get("target", "")).strip()
    }


def _confirmed_field_paths(chain: APQPChain) -> set[str]:
    field_paths: set[str] = set()
    for item in _review_confirmations(chain):
        if not isinstance(item, dict):
            continue
        field_path = str(item.get("field_path", "")).strip()
        if field_path:
            field_paths.add(field_path)
        target = str(item.get("target", "")).strip()
        field = str(item.get("field", "")).strip()
        if target.startswith("pending_field:"):
            field_paths.add(target.split(":", 1)[1].strip())
        if target and field:
            target_id = target.split(":", 1)[1] if ":" in target else target
            field_paths.add(f"{target_id}.{field}")
            field_paths.add(f"{target}.{field}")
    return field_paths


def _review_confirmations(chain: APQPChain) -> list[Any]:
    confirmations = chain.metadata.get(REVIEW_CONFIRMATIONS_KEY, [])
    return confirmations if isinstance(confirmations, list) else []


def _with_safe_ai_batch_confirmations(payload: dict[str, Any]) -> dict[str, Any]:
    targets = _safe_ai_batch_confirmation_targets(payload)
    if not targets:
        return payload
    patched = copy.deepcopy(payload)
    metadata = patched.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        return patched
    confirmations = metadata.setdefault(REVIEW_CONFIRMATIONS_KEY, [])
    if not isinstance(confirmations, list):
        return patched
    existing = {
        str(item.get("target", "")).strip()
        for item in confirmations
        if isinstance(item, dict)
    }
    for target in targets:
        if target in existing:
            continue
        confirmations.append(
            {
                "target": target,
                "confirmation_mode": "ai_recommended_batch",
                "source": "automation_review",
            }
        )
    return patched


def _unsafe_ai_batch_review_issues(payload: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for table, chain_key, id_fields, target_type in (
        ("process_flow", "process_steps", ("process_step_id", "id", "step_no"), "process_step"),
        ("pfmea", "failure_modes", ("pfmea_id", "id"), "failure_mode"),
        ("control_plan", "controls", ("control_plan_id", "id"), "control_item"),
    ):
        rows = payload.get(chain_key, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("confirmation_mode", "")).strip() != "ai_recommended_batch":
                continue
            row_id = _row_mapping_id(row, id_fields)
            if not row_id or _safe_ai_batch_row(payload, table, row):
                continue
            target = f"{target_type}:{row_id}"
            issues.append(
                build_review_issue(
                    category="AI批量确认",
                    message="该项目不满足低风险高置信批量确认条件，需要人工复核后才能正式放行。",
                    severity="blocker",
                    source="automation_review",
                    target=target,
                    automation_level="ai_recommended_batch",
                    can_batch_confirm=False,
                    human_reason_required=True,
                )
            )
    return issues


def _safe_ai_batch_confirmation_targets(payload: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for table, chain_key, id_fields, target_type in (
        ("process_flow", "process_steps", ("process_step_id", "id", "step_no"), "process_step"),
        ("pfmea", "failure_modes", ("pfmea_id", "id"), "failure_mode"),
        ("control_plan", "controls", ("control_plan_id", "id"), "control_item"),
    ):
        rows = payload.get(chain_key, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("confirmation_mode", "")).strip() != "ai_recommended_batch":
                continue
            row_id = _row_mapping_id(row, id_fields)
            if row_id and _safe_ai_batch_row(payload, table, row):
                targets.append(f"{target_type}:{row_id}")
    return _dedupe_preserve_order(targets)


def _safe_ai_batch_row(payload: dict[str, Any], table: str, row: dict[str, Any]) -> bool:
    if row.get("deleted") or row.get("soft_deleted"):
        return False
    refs = [str(ref).strip() for ref in row.get("evidence_refs", []) if str(ref).strip()]
    if not refs:
        return False
    confidence = _float_value(row.get("confidence"))
    if confidence is None or confidence < 0.85:
        return False
    if str(row.get("action_priority", row.get("AP", ""))).strip().upper() == "H":
        return False
    if (
        row.get("classification")
        or row.get("characteristic_refs")
        or row.get("special_characteristics")
        or row.get("source_special_characteristics")
    ):
        return False
    if table != "process_flow":
        step_id = str(row.get("process_step_id", "")).strip()
        for step in payload.get("process_steps", []):
            if (
                isinstance(step, dict)
                and str(step.get("process_step_id", "")).strip() == step_id
                and step.get("special_characteristics")
            ):
                return False
    return True


def _row_mapping_id(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field_name in fields:
        value = str(row.get(field_name, "")).strip()
        if value:
            return value
    return ""


def _without_confirmed(values: list[str], confirmed: set[str]) -> list[str]:
    return [value for value in values if not _is_confirmed(value, confirmed)]


def _is_confirmed(value: str, confirmed: set[str]) -> bool:
    text = str(value).strip()
    if not text:
        return False
    if text in confirmed:
        return True
    for item in confirmed:
        if _confirmation_matches_value(item, text):
            return True
    return False


def _confirmation_matches_value(confirmed: str, value: str) -> bool:
    if confirmed == value:
        return True
    if " -> " in value:
        _, ref = value.rsplit(" -> ", 1)
        if confirmed == ref.strip():
            return True
        if confirmed == f"evidence:{ref.strip()}":
            return True
    if ":" in confirmed:
        confirmed_type, confirmed_id = confirmed.split(":", 1)
        if value.startswith(f"{confirmed} -> "):
            return True
        if value == confirmed_id:
            return True
        if value.endswith(f":{confirmed_id}"):
            return True
        if value.startswith(f"{confirmed_id}."):
            return True
        if value.startswith(f"{confirmed}."):
            return True
        if value.endswith(f" -> {confirmed_id}"):
            return True
        if confirmed_type == "evidence" and value.endswith(f" -> {confirmed_id}"):
            return True
    return False


def _pending_fields(chain: APQPChain) -> list[str]:
    pending: list[str] = []
    for failure in chain.failure_modes:
        if not failure.failure_mode:
            pending.append(f"{failure.pfmea_id}.failure_mode")
        if not failure.failure_cause:
            pending.append(f"{failure.pfmea_id}.failure_cause")
    for control in chain.controls:
        if not control.specification:
            pending.append(f"{control.control_plan_id}.specification")
        if not control.reaction_plan:
            pending.append(f"{control.control_plan_id}.reaction_plan")
    for item in _pending_field_paths(getattr(chain, "pending_fields", [])):
        if item and item not in pending:
            pending.append(item)
    return pending


def _ai_inferred_items(chain: APQPChain) -> list[str]:
    items = [item.evidence_id for item in chain.evidence if item.ai_inferred]
    for item in _flagged_evidence_ids(
        getattr(chain, "ai_inferred_items", []), "ai_inferred"
    ):
        if item and item not in items:
            items.append(item)
    for item in getattr(chain, "ai_inferred_items", []):
        if isinstance(item, dict):
            continue
        value = str(item)
        if value and value not in items:
            items.append(value)
    return items


