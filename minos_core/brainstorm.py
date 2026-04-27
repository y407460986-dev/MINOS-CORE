"""Brainstorm candidate failure modes from generated process flows."""

from __future__ import annotations

import re
from typing import Any


OPERATION_RULES = (
    (
        ("incoming", "material", "verification"),
        "operation_keyword:incoming_verification",
        "Nonconforming incoming material accepted",
    ),
    (
        ("rivet", "assembly", "join"),
        "operation_keyword:rivet_assembly",
        "Riveted joint does not meet assembly requirements",
    ),
    (
        ("inspection", "pack", "final"),
        "operation_keyword:final_inspection_pack",
        "Nonconforming or incorrect product packed for shipment",
    ),
)


def brainstorm_failure_modes_from_pfd(process_flow: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    pending_fields = list(process_flow.get("pending_fields", []))
    seen: set[tuple[str, str]] = set()

    for step in process_flow.get("steps", process_flow.get("process_steps", [])):
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("process_step_id", step.get("id", ""))).strip()
        operation = str(step.get("operation", step.get("name", ""))).strip()
        if not step_id:
            pending_fields.append(
                {"field": "process_step_id", "reason": "PFD step has no id"}
            )
            continue
        step_candidates = _candidate_specs_for_step(step)
        if not step_candidates:
            pending_fields.append(
                {
                    "field": "failure_mode_candidates",
                    "reason": "No brainstorm rule matched this process step",
                    "process_step_id": step_id,
                    "operation": operation,
                }
            )
            continue
        index = 1
        for source_rule, failure_mode in step_candidates:
            key = (step_id, _normalized_text(failure_mode))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(_candidate(step, index, source_rule, failure_mode))
            index += 1

    return {
        "document_type": "failure_mode_candidates",
        "schema_version": "minos-core.generated.v1",
        "source_document_type": process_flow.get("document_type", "process_flow"),
        "product": process_flow.get("product", {}),
        "evidence": process_flow.get("evidence", []),
        "process_steps": process_flow.get(
            "steps", process_flow.get("process_steps", [])
        ),
        "candidates": candidates,
        "pending_fields": pending_fields,
        "ai_inferred_items": process_flow.get("ai_inferred_items", []),
        "metadata": {
            "generation_mode": "pfd_failure_mode_brainstorm_rules",
            "llm_used": False,
            "source_stage": "generate_pfd",
            "not_formal_pfmea": True,
        },
    }


def _candidate_specs_for_step(step: dict[str, Any]) -> list[tuple[str, str]]:
    operation = str(step.get("operation", step.get("name", ""))).strip()
    process_function = str(step.get("process_function", "")).strip()
    text = f"{operation} {process_function}".lower()
    specs: list[tuple[str, str]] = []
    for terms, source_rule, failure_mode in OPERATION_RULES:
        if any(term in text for term in terms):
            specs.append((source_rule, failure_mode))
            break
    if process_function:
        specs.append(
            (
                "process_function:not_achieved",
                f"Process function not achieved: {process_function}",
            )
        )
    elif operation:
        specs.append(
            (
                "operation:not_completed",
                f"Operation not completed as intended: {operation}",
            )
        )
    for characteristic in step.get("special_characteristics", []) or []:
        characteristic_id = str(characteristic).strip()
        if characteristic_id:
            specs.append(
                (
                    "special_characteristic:not_met",
                    f"Special characteristic not met: {characteristic_id}",
                )
            )
    return specs


def _candidate(
    step: dict[str, Any],
    index: int,
    source_rule: str,
    failure_mode: str,
) -> dict[str, Any]:
    step_id = str(step.get("process_step_id", step.get("id", ""))).strip()
    return {
        "candidate_id": f"FMC-{step_id}-{index:03d}",
        "process_step_id": step_id,
        "sequence": step.get("sequence", _sequence_from_step_id(step_id)),
        "operation": str(step.get("operation", step.get("name", ""))).strip(),
        "process_function": str(step.get("process_function", "")).strip(),
        "process_step_name": str(step.get("operation", step.get("name", ""))).strip(),
        "product_characteristics": _string_list(step.get("product_characteristics", [])),
        "process_characteristics": _string_list(step.get("process_characteristics", [])),
        "special_characteristics": _string_list(step.get("special_characteristics", [])),
        "failure_mode": failure_mode,
        "source_rule": source_rule,
        "evidence_refs": [
            str(ref).strip()
            for ref in step.get("evidence_refs", [])
            if str(ref).strip()
        ],
        "needs_confirmation": True,
    }


def _sequence_from_step_id(step_id: str) -> int:
    match = re.match(r"^P(\d+)$", step_id)
    return int(match.group(1)) if match else 0


def _normalized_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [str(item).strip() for item in values if str(item).strip()]
