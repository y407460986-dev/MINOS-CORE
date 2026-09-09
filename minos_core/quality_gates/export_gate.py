"""Export gate: AI batch confirmation safety checks."""
from __future__ import annotations

import copy
from typing import Any

from ..review_issues import build_review_issue
from ..review_patch import REVIEW_CONFIRMATIONS_KEY
from .core_evaluators import _dedupe_preserve_order, _float_value, _row_mapping_id

__all__ = [
    "_safe_ai_batch_confirmation_targets",
    "_safe_ai_batch_row",
    "_unsafe_ai_batch_review_issues",
    "_with_safe_ai_batch_confirmations",
]


def _with_safe_ai_batch_confirmations(payload: dict[str, Any]) -> dict[str, Any]:
    """Auto-confirm low-risk AI-batch rows by injecting review confirmations into metadata."""
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
    """Find AI-batch rows that do not meet low-risk criteria and create blocker issues."""
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
    """Collect target identifiers of all AI-batch rows that pass the safety check."""
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
    """Return True if the AI-batch row meets low-risk, high-confidence auto-confirm criteria."""
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
