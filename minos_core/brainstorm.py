"""Brainstorm candidate failure modes from generated process flows."""

from __future__ import annotations

import json
import re
from typing import Any

from .evidence_relevance import filter_relevant_evidence_refs
from minos_core._text_utils import string_list


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
    available_evidence: list[dict[str, Any]] = process_flow.get("evidence", [])
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
        for source_rule, failure_mode, matched_terms in step_candidates:
            key = (step_id, _normalized_text(failure_mode))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(_candidate(step, index, source_rule, failure_mode, matched_terms, available_evidence))
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


def _candidate_specs_for_step(step: dict[str, Any]) -> list[tuple[str, str, list[str]]]:
    operation = str(step.get("operation", step.get("name", ""))).strip()
    process_function = str(step.get("process_function", "")).strip()
    text = f"{operation} {process_function}".lower()
    specs: list[tuple[str, str, list[str]]] = []
    for terms, source_rule, failure_mode in OPERATION_RULES:
        matched = [term for term in terms if term in text]
        if matched:
            specs.append((source_rule, failure_mode, matched))
            break
    if process_function:
        specs.append(
            (
                "process_function:not_achieved",
                f"Process function not achieved: {process_function}",
                [],
            )
        )
    elif operation:
        specs.append(
            (
                "operation:not_completed",
                f"Operation not completed as intended: {operation}",
                [],
            )
        )
    for characteristic in step.get("special_characteristics", []) or []:
        characteristic_id = str(characteristic).strip()
        if characteristic_id:
            specs.append(
                (
                    "special_characteristic:not_met",
                    f"Special characteristic not met: {characteristic_id}",
                    [],
                )
            )
    return specs


def _candidate(
    step: dict[str, Any],
    index: int,
    source_rule: str,
    failure_mode: str,
    matched_terms: list[str],
    available_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    step_id = str(step.get("process_step_id", step.get("id", ""))).strip()
    raw_refs = [
        str(ref).strip()
        for ref in step.get("evidence_refs", [])
        if str(ref).strip()
    ]
    # Build entity text combining the distinguishing fields so relevance
    # scoring can match evidence content against this specific candidate.
    operation = str(step.get("operation", step.get("name", ""))).strip()
    process_function = str(step.get("process_function", "")).strip()
    entity_text = f"{operation} {process_function} {failure_mode}"

    # Compute confidence from step and evidence
    filtered_refs = filter_relevant_evidence_refs(
        evidence_refs=raw_refs,
        entity_text=entity_text,
        available_evidence=available_evidence or [],
    )
    step_confidence = step.get("confidence")
    evidence_confidences = [
        ev.get("confidence") for ev in (available_evidence or [])
        if isinstance(ev, dict) and ev.get("evidence_id") in filtered_refs
        and ev.get("confidence") is not None
    ]
    avg_confidence = (
        sum(evidence_confidences) / len(evidence_confidences)
        if evidence_confidences else (step_confidence if step_confidence is not None else 0.5)
    )

    # Build reasoning explaining why this failure mode was selected
    reasoning_data = {
        "method": "keyword_rule_match",
        "source_rule": source_rule,
        "matched_operation_terms": matched_terms,
        "matched_operation_text": operation,
        "confidence": 0.6,
    }
    reasoning = json.dumps(reasoning_data, ensure_ascii=False)

    # Human-readable ai_reasoning
    if matched_terms:
        ai_reasoning = (
            f"根据关键词规则匹配: 工序「{operation}」包含 '{'、'.join(matched_terms)}'"
            f" → 推断失效模式「{failure_mode}」"
        )
    elif source_rule.startswith("process_function:"):
        ai_reasoning = (
            f"根据工序功能规则: 工序「{operation}」功能未达成"
            f" → 推断失效模式「{failure_mode}」"
        )
    elif source_rule.startswith("special_characteristic:"):
        ai_reasoning = (
            f"根据特殊特性规则: 特殊特性未满足"
            f" → 推断失效模式「{failure_mode}」"
        )
    else:
        ai_reasoning = (
            f"根据工序规则: 工序「{operation}」未按预期完成"
            f" → 推断失效模式「{failure_mode}」"
        )

    return {
        "candidate_id": f"FMC-{step_id}-{index:03d}",
        "process_step_id": step_id,
        "sequence": step.get("sequence", _sequence_from_step_id(step_id)),
        "operation": operation,
        "process_function": process_function,
        "process_step_name": operation,
        "product_characteristics": string_list(step.get("product_characteristics", [])),
        "process_characteristics": string_list(step.get("process_characteristics", [])),
        "special_characteristics": string_list(step.get("special_characteristics", [])),
        "failure_mode": failure_mode,
        "source_rule": source_rule,
        "evidence_refs": filtered_refs,
        "confidence": avg_confidence,
        "needs_confirmation": avg_confidence < 0.85,
        "reasoning": reasoning,
        "ai_reasoning": ai_reasoning,
    }


def _sequence_from_step_id(step_id: str) -> int:
    match = re.match(r"^P(\d+)$", step_id)
    return int(match.group(1)) if match else 0


def _normalized_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


generate_failure_mode_candidates = brainstorm_failure_modes_from_pfd
