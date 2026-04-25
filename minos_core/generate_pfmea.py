"""Generate thin PFMEA rows from failure mode candidates."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def generate_pfmea_from_candidates(
    candidates_bundle: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    counters: dict[str, int] = defaultdict(int)

    for candidate in candidates_bundle.get(
        "candidates", candidates_bundle.get("failure_mode_candidates", [])
    ):
        if not isinstance(candidate, dict):
            continue
        step_id = str(candidate.get("process_step_id", "")).strip()
        counters[step_id] += 1
        rows.append(_pfmea_row(candidate, counters[step_id]))

    return {
        "document_type": "pfmea",
        "schema_version": "minos-core.generated.v1",
        "source_document_type": candidates_bundle.get(
            "document_type", "failure_mode_candidates"
        ),
        "product": candidates_bundle.get("product", {}),
        "evidence": candidates_bundle.get("evidence", []),
        "rows": rows,
        "pending_fields": candidates_bundle.get("pending_fields", []),
        "ai_inferred_items": candidates_bundle.get("ai_inferred_items", []),
        "metadata": {
            "generation_mode": "failure_mode_candidates_pfmea_rules",
            "llm_used": False,
            "source_stage": "brainstorm_failure_modes",
            "requires_engineering_review": True,
        },
    }


def _pfmea_row(candidate: dict[str, Any], index: int) -> dict[str, Any]:
    step_id = str(candidate.get("process_step_id", "")).strip()
    failure_mode = str(candidate.get("failure_mode", "")).strip()
    process_function = _text(candidate.get("process_function"), candidate.get("operation", ""))
    severity = _integer(candidate.get("severity"), default=5)
    occurrence = _integer(candidate.get("occurrence"), default=3)
    detection = _integer(candidate.get("detection"), default=6)

    return {
        "pfmea_id": _pfmea_id(step_id, index),
        "process_step_id": step_id,
        "process_function": process_function,
        "failure_mode": failure_mode,
        "failure_effect": _text(
            candidate.get("failure_effect"),
            "Process output may not meet requirements",
        ),
        "severity": severity,
        "failure_cause": _text(
            candidate.get("failure_cause"),
            "Cause requires engineering confirmation",
        ),
        "occurrence": occurrence,
        "prevention_control": _text(
            candidate.get("prevention_control"),
            "Prevention control requires engineering confirmation",
        ),
        "detection_control": _text(
            candidate.get("detection_control"),
            "Detection control requires engineering confirmation",
        ),
        "detection": detection,
        "action_priority": _text(
            candidate.get("action_priority"),
            _action_priority(severity, occurrence, detection),
        ),
        "classification": str(candidate.get("classification", "")).strip(),
        "linked_control_plan_id": str(
            candidate.get("linked_control_plan_id", "")
        ).strip(),
        "evidence_refs": _string_list(candidate.get("evidence_refs", [])),
        "needs_confirmation": bool(candidate.get("needs_confirmation", True)),
        "source_candidate_id": str(candidate.get("candidate_id", "")).strip(),
        "source_rule": str(candidate.get("source_rule", "")).strip(),
    }


def _pfmea_id(step_id: str, index: int) -> str:
    normalized_step_id = step_id or "P00"
    return f"PFMEA-{normalized_step_id}-{index:03d}"


def _action_priority(severity: int, occurrence: int, detection: int) -> str:
    if severity >= 9 or (severity >= 7 and occurrence >= 5):
        return "H"
    if severity >= 7 or occurrence >= 6 or detection >= 8:
        return "M"
    return "L"


def _integer(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _text(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text if text else default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [str(item).strip() for item in values if str(item).strip()]
