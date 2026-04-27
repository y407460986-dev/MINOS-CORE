"""Generate process flow diagrams from analysis bundles."""

from __future__ import annotations

import re
from typing import Any


_STEP_CHARACTERISTIC_RULES = {
    "P10": ("material", "thickness"),
    "P20": ("rivet", "height", "push-out", "push out", "force"),
    "P30": ("revision", "barcode", "pack", "quantity"),
}


def generate_pfd_from_analysis(analysis_bundle: dict[str, Any]) -> dict[str, Any]:
    pending_fields = list(analysis_bundle.get("pending_fields", []))
    characteristics = _characteristics_by_ref(analysis_bundle.get("characteristics", []))
    steps_by_id: dict[str, dict[str, Any]] = {}
    for clue in analysis_bundle.get("process_clues", []):
        if not isinstance(clue, dict):
            continue
        step_id = str(clue.get("process_step_id", "")).strip().upper()
        operation = str(clue.get("operation", "")).strip()
        source_ref = str(clue.get("source_ref", "")).strip()
        match = re.match(r"^P(\d+)$", step_id)
        if not step_id:
            pending_fields.append(
                {
                    "field": "process_step_id",
                    "reason": "process clue has operation but no process_step_id",
                    "source_ref": source_ref,
                    "operation": operation,
                }
            )
            continue
        if not match:
            pending_fields.append(
                {
                    "field": "process_step_id",
                    "reason": "process_step_id is not in Pxx format",
                    "source_ref": source_ref,
                    "operation": operation,
                    "process_step_id": step_id,
                }
            )
            continue
        normalized_step_id = f"P{int(match.group(1))}"
        step = steps_by_id.setdefault(
            normalized_step_id,
            {
                "process_step_id": normalized_step_id,
                "sequence": int(match.group(1)),
                "operation": operation,
                "process_function": _text(
                    clue.get("process_function"),
                    clue.get("function"),
                    clue.get("process_purpose"),
                    clue.get("purpose"),
                    default="",
                ),
                "process_purpose": _text(
                    clue.get("process_purpose"),
                    clue.get("purpose"),
                    default="",
                ),
                "product_characteristics": _string_list(
                    clue.get(
                        "product_characteristics",
                        clue.get("product_characteristic_refs", []),
                    )
                ),
                "process_characteristics": _string_list(
                    clue.get(
                        "process_characteristics",
                        clue.get("process_characteristic_refs", []),
                    )
                ),
                "equipment": _text(clue.get("equipment"), default=""),
                "tooling": _text(clue.get("tooling"), clue.get("fixture"), default=""),
                "gauges": _string_list(
                    clue.get(
                        "gauges",
                        clue.get("inspection_gauges", clue.get("measurement_devices", [])),
                    )
                ),
                "documents": _string_list(
                    clue.get("documents", clue.get("document_refs", clue.get("files", [])))
                ),
                "flow_type": _text(
                    clue.get("flow_type"), clue.get("process_type"), default=""
                ),
                "owner": "",
                "input_refs": [],
                "output_refs": [],
                "special_characteristics": [],
                "evidence_refs": [],
            },
        )
        if not step["operation"] and operation:
            step["operation"] = operation
        _fill_step_fields(step, clue)
        if source_ref and source_ref not in step["evidence_refs"]:
            step["evidence_refs"].append(source_ref)
        _apply_characteristics(step, source_ref, characteristics)

    steps = sorted(steps_by_id.values(), key=lambda item: item["sequence"])
    links = _sequence_links(steps)
    return {
        "document_type": "process_flow",
        "schema_version": "minos-core.generated.v1",
        "source_document_type": analysis_bundle.get("document_type", "analysis_bundle"),
        "product": analysis_bundle.get("product", {}),
        "evidence": analysis_bundle.get("evidence", []),
        "drawings": analysis_bundle.get("drawings", []),
        "characteristics": analysis_bundle.get("characteristics", []),
        "steps": steps,
        "links": links,
        "pending_fields": pending_fields,
        "ai_inferred_items": analysis_bundle.get("ai_inferred_items", []),
        "metadata": {
            "generation_mode": "analysis_process_clues_rules",
            "llm_used": False,
            "source_stage": "analyze",
        },
    }


def _characteristics_by_ref(characteristics: Any) -> dict[str, list[dict[str, Any]]]:
    by_ref: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(characteristics, list):
        return by_ref
    for characteristic in characteristics:
        if not isinstance(characteristic, dict):
            continue
        source_ref = str(characteristic.get("source_ref", "")).strip()
        if not source_ref:
            continue
        by_ref.setdefault("*", []).append(characteristic)
        by_ref.setdefault(source_ref, []).append(characteristic)
    return by_ref


def _fill_step_fields(step: dict[str, Any], clue: dict[str, Any]) -> None:
    for field_name, values in (
        (
            "process_function",
            (
                clue.get("process_function"),
                clue.get("function"),
                clue.get("process_purpose"),
                clue.get("purpose"),
            ),
        ),
        ("process_purpose", (clue.get("process_purpose"), clue.get("purpose"))),
        ("equipment", (clue.get("equipment"),)),
        ("tooling", (clue.get("tooling"), clue.get("fixture"))),
        ("flow_type", (clue.get("flow_type"), clue.get("process_type"))),
    ):
        if not step.get(field_name):
            step[field_name] = _text(*values, default="")
    for field_name, value in (
        (
            "product_characteristics",
            clue.get(
                "product_characteristics",
                clue.get("product_characteristic_refs", []),
            ),
        ),
        (
            "process_characteristics",
            clue.get(
                "process_characteristics",
                clue.get("process_characteristic_refs", []),
            ),
        ),
        (
            "gauges",
            clue.get(
                "gauges",
                clue.get("inspection_gauges", clue.get("measurement_devices", [])),
            ),
        ),
        ("documents", clue.get("documents", clue.get("document_refs", clue.get("files", [])))),
    ):
        existing = set(_string_list(step.get(field_name, [])))
        for item in _string_list(value):
            if item not in existing:
                step.setdefault(field_name, []).append(item)
                existing.add(item)


def _apply_characteristics(
    step: dict[str, Any],
    source_ref: str,
    characteristics_by_ref: dict[str, list[dict[str, Any]]],
) -> None:
    existing = set(step.get("special_characteristics", []))
    step_id = str(step.get("process_step_id", "")).strip().upper()
    for characteristic in characteristics_by_ref.get("*", []):
        if not _characteristic_applies_to_step(characteristic, step_id):
            continue
        characteristic_id = str(characteristic.get("characteristic_id", "")).strip()
        if characteristic_id and characteristic_id not in existing:
            step["special_characteristics"].append(characteristic_id)
            existing.add(characteristic_id)
            characteristic_ref = str(characteristic.get("source_ref", "")).strip()
            if characteristic_ref and characteristic_ref not in step["evidence_refs"]:
                step["evidence_refs"].append(characteristic_ref)


def _characteristic_applies_to_step(
    characteristic: dict[str, Any], step_id: str
) -> bool:
    terms = _STEP_CHARACTERISTIC_RULES.get(step_id, ())
    if not terms:
        return False
    characteristic_text = " ".join(
        str(characteristic.get(field_name, ""))
        for field_name in ("characteristic_id", "name", "matched_terms")
    ).lower()
    return any(term in characteristic_text for term in terms)


def _sequence_links(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for current_step, next_step in zip(steps, steps[1:]):
        evidence_refs: list[str] = []
        for ref in current_step.get("evidence_refs", []) + next_step.get(
            "evidence_refs", []
        ):
            if ref not in evidence_refs:
                evidence_refs.append(ref)
        links.append(
            {
                "from": current_step["process_step_id"],
                "to": next_step["process_step_id"],
                "link_type": "sequence",
                "evidence_refs": evidence_refs,
            }
        )
    return links


def _text(*values: Any, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [str(item).strip() for item in values if str(item).strip()]
