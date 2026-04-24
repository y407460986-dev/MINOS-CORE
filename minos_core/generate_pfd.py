"""Generate process flow diagrams from analysis bundles."""

from __future__ import annotations

import re
from typing import Any


def generate_pfd_from_analysis(analysis_bundle: dict[str, Any]) -> dict[str, Any]:
    pending_fields = list(analysis_bundle.get("pending_fields", []))
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
                "process_function": "",
                "owner": "",
                "input_refs": [],
                "output_refs": [],
                "special_characteristics": [],
                "evidence_refs": [],
            },
        )
        if not step["operation"] and operation:
            step["operation"] = operation
        if source_ref and source_ref not in step["evidence_refs"]:
            step["evidence_refs"].append(source_ref)

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
