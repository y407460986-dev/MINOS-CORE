"""Generate thin PFMEA rows from failure mode candidates."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .aiag_vda_pfmea import calculate_rpn, normalize_pfmea_row
from minos_core._text_utils import integer, string_list, text
from minos_core.three_table_result import canonical_three_table_bundle


def generate_pfmea_from_candidates(
    candidates_bundle: dict[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    counters: dict[str, int] = defaultdict(int)
    steps_by_id = _steps_by_id(candidates_bundle)

    for candidate in candidates_bundle.get(
        "candidates", candidates_bundle.get("failure_mode_candidates", [])
    ):
        if not isinstance(candidate, dict):
            continue
        step_id = str(candidate.get("process_step_id", "")).strip()
        if step_id and step_id not in steps_by_id:
            continue
        inherited_step = steps_by_id.get(step_id, {})
        counters[step_id] += 1
        rows.append(_pfmea_row(candidate, counters[step_id], inherited_step))

    return canonical_three_table_bundle({
        "document_type": "pfmea",
        "schema_version": "minos-core.generated.v1",
        "source_document_type": candidates_bundle.get(
            "document_type", "failure_mode_candidates"
        ),
        "product": candidates_bundle.get("product", {}),
        "evidence": candidates_bundle.get("evidence", []),
        "process_steps": candidates_bundle.get("process_steps", candidates_bundle.get("steps", [])),
        "rows": rows,
        "pending_fields": candidates_bundle.get("pending_fields", []),
        "ai_inferred_items": candidates_bundle.get("ai_inferred_items", []),
        "metadata": {
            "generation_mode": "failure_mode_candidates_pfmea_rules",
            "llm_used": False,
            "source_stage": "brainstorm_failure_modes",
            "requires_engineering_review": True,
            "source_process_step_ids": sorted(steps_by_id),
        },
    }, document_type="pfmea", row_key="rows")


def _steps_by_id(candidates_bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = candidates_bundle.get("process_steps", candidates_bundle.get("steps", []))
    if not isinstance(rows, list):
        return {}
    return {
        step_id: step
        for step in rows
        if isinstance(step, dict)
        for step_id in [str(step.get("process_step_id", step.get("id", ""))).strip()]
        if step_id
    }


def _pfmea_row(candidate: dict[str, Any], index: int, step: dict[str, Any]) -> dict[str, Any]:
    step_id = str(candidate.get("process_step_id", "")).strip()
    failure_mode = str(candidate.get("failure_mode", "")).strip()
    operation = text(
        candidate.get("operation"),
        candidate.get("process_step_name"),
        step.get("operation"),
        step.get("name"),
        default="",
    )
    process_function = text(
        candidate.get("process_function"),
        step.get("process_function"),
        step.get("process_purpose"),
        operation,
        default="",
    )
    severity = integer(candidate.get("severity"), default=5)
    occurrence = integer(candidate.get("occurrence"), default=3)
    detection = integer(candidate.get("detection"), default=6)
    special_characteristics = _merged_string_list(
        candidate.get("special_characteristics", []),
        step.get("special_characteristics", []),
    )

    return normalize_pfmea_row({
        "pfmea_id": _pfmea_id(step_id, index),
        "process_step_id": step_id,
        "process_step_name": operation,
        "process_step_operation": operation,
        "process_function": process_function,
        "product_characteristics": _merged_string_list(
            candidate.get("product_characteristics", []),
            step.get("product_characteristics", []),
        ),
        "process_characteristics": _merged_string_list(
            candidate.get("process_characteristics", []),
            step.get("process_characteristics", []),
        ),
        "failure_mode": failure_mode,
        "failure_effect": text(
            candidate.get("failure_effect"),
            "Process output may not meet requirements",
        ),
        "severity": severity,
        "failure_cause": text(
            candidate.get("failure_cause"),
            "Cause requires engineering confirmation",
        ),
        "occurrence": occurrence,
        "prevention_control": text(
            candidate.get("prevention_control"),
            "Prevention control requires engineering confirmation",
        ),
        "detection_control": text(
            candidate.get("detection_control"),
            "Detection control requires engineering confirmation",
        ),
        "detection": detection,
        "action_priority": text(
            candidate.get("action_priority"),
            _action_priority(severity, occurrence, detection),
        ),
        "rpn": calculate_rpn(severity, occurrence, detection),
        "recommended_action": text(
            candidate.get("recommended_action"),
            "由工程确认推荐措施、责任人和完成日期",
        ),
        "responsibility": text(candidate.get("responsibility"), candidate.get("owner")),
        "target_date": text(candidate.get("target_date"), candidate.get("completion_due_date")),
        "action_status": text(candidate.get("action_status"), "未制定"),
        "classification": text(
            candidate.get("classification"),
            ",".join(special_characteristics),
            default="",
        ),
        "linked_control_plan_id": str(
            candidate.get("linked_control_plan_id", "")
        ).strip(),
        "evidence_refs": string_list(candidate.get("evidence_refs", [])),
        "needs_confirmation": bool(candidate.get("needs_confirmation", True)),
        "source_candidate_id": str(candidate.get("candidate_id", "")).strip(),
        "source_process_step_id": step_id,
        "source_rule": str(candidate.get("source_rule", "")).strip(),
        "characteristic_refs": special_characteristics,
    }, step)


def _pfmea_id(step_id: str, index: int) -> str:
    normalized_step_id = step_id or "P00"
    return f"PFMEA-{normalized_step_id}-{index:03d}"


def _action_priority(severity: int, occurrence: int, detection: int) -> str:
    if severity >= 9 or (severity >= 7 and occurrence >= 5):
        return "H"
    if severity >= 7 or occurrence >= 6 or detection >= 8:
        return "M"
    return "L"


def _merged_string_list(*values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in string_list(value):
            if item not in seen:
                result.append(item)
                seen.add(item)
    return result
