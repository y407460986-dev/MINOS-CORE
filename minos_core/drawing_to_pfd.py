"""Infer process-flow drafts from AI drawing analysis bundles."""
from __future__ import annotations

from typing import Any

from minos_core._text_utils import flow_type_display, row_text, string_list

from .drawing_to_pfd_build import (
    _attach_special_candidate_labels_to_steps,
    _characteristics_from_drawing,
    _confidence,
    _display_operation,
    _drawing_from_identity,
    _enrich_with_process_library,
    _expand_manufacturing_clues,
    _formal_special_characteristic_ids,
    _infer_flow_type,
    _library_equipment,
    _library_process_function,
    _normalize_step_id,
    _product_from_drawing,
    _sequence_links,
    _special_candidate_labels_from_drawing,
    _step_special_characteristics,
    normalize_process_flow_steps,
)


def infer_process_flow_from_drawing(
    analysis_bundle: dict[str, Any],
    family_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a PFD draft from drawing manufacturing clues.

    The first implementation is deliberately conservative: it turns explicit
    manufacturing clues from the drawing-recognition bundle into ordered Pxx
    steps and keeps every step marked for review because the route is AI
    inferred from a drawing, not confirmed process planning.
    """
    family_context = _resolve_family_context(family_context)
    steps, pending_fields = _build_steps_from_clues(analysis_bundle, family_context)
    return _finalize_process_flow(steps, analysis_bundle, family_context, pending_fields)


def _resolve_family_context(
    family_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve family_context templates when only family_key is given."""
    if not family_context or family_context.get("process_route_templates"):
        return family_context

    family_key = family_context.get("family_key")
    if not family_key:
        return family_context

    # Try classifier templates first (operation_key format)
    try:
        from minos_core.part_family_classifier import get_default_family_index
        family_index = get_default_family_index()
        family_data = family_index.get(family_key)
        if family_data:
            family_context = dict(family_context)
            family_context["process_route_templates"] = list(
                family_data.get("process_route_templates", [])
            )
            if not family_context.get("knowledge_source_refs"):
                family_context["knowledge_source_refs"] = list(
                    family_data.get("knowledge_source_refs", [])
                )
    except (KeyError, ImportError):
        pass

    # Fallback: load from knowledge base for process_inference data
    if not family_context.get("process_route_templates") or not family_context.get("process_inference"):
        try:
            from minos_core.part_family_knowledge import load_part_family_knowledge
            knowledge = load_part_family_knowledge(family_key)
            if not family_context.get("process_route_templates"):
                family_context = dict(family_context)
                family_context["process_route_templates"] = knowledge.get(
                    "process_route_templates", []
                )
            if knowledge.get("process_inference"):
                family_context = (
                    dict(family_context)
                    if family_context.get("process_inference") is None
                    else family_context
                )
                family_context["process_inference"] = knowledge["process_inference"]
            if not family_context.get("knowledge_source_refs"):
                family_context["knowledge_source_refs"] = knowledge.get(
                    "knowledge_source_refs", []
                )
        except (KeyError, FileNotFoundError, ImportError):
            pass

    return family_context


def _build_steps_from_clues(
    analysis_bundle: dict[str, Any],
    family_context: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Iterate manufacturing clues and build the steps list."""
    clues = _expand_manufacturing_clues(analysis_bundle.get("manufacturing_clues", []))
    clues = _enrich_with_process_library(analysis_bundle, clues, family_context)
    candidate_labels = _special_candidate_labels_from_drawing(analysis_bundle)
    formal_special_ids = _formal_special_characteristic_ids(analysis_bundle)
    special_block = analysis_bundle.get("special_characteristics", [])
    has_special_block = isinstance(special_block, list) and any(
        isinstance(item, dict) for item in special_block
    )
    family_knowledge_refs: list[str] = []
    if family_context:
        family_knowledge_refs = string_list(family_context.get("knowledge_source_refs", []))
    steps: list[dict[str, Any]] = []
    pending_fields = list(analysis_bundle.get("pending_fields", []))
    for index, clue in enumerate(clues, start=1):
        preserve_name = bool(clue.get("preserve_operation_name", False))
        operation = _display_operation(
            row_text(clue, "operation", "process_step", "name", "process", default=""),
            preserve=preserve_name,
        )
        refs = string_list(clue.get("evidence_refs", []))
        if not operation:
            pending_fields.append(f"manufacturing_clues[{index - 1}].operation")
            continue
        step_id = row_text(clue, "process_step_id", "step_id", default=f"P{index * 10}")
        clue_knowledge_refs = string_list(clue.get("knowledge_source_refs", []))
        all_knowledge_refs: list[str] = []
        for ref in clue_knowledge_refs + family_knowledge_refs:
            if ref not in all_knowledge_refs:
                all_knowledge_refs.append(ref)
        flow_type = row_text(clue, "flow_type", "process_type", default="")
        if not flow_type:
            flow_type = _infer_flow_type(operation)
        steps.append(
            {
                "process_step_id": _normalize_step_id(step_id, index),
                "sequence": index * 10,
                "operation": operation,
                "process_function": row_text(
                    clue,
                    "process_function",
                    "purpose",
                    default=_library_process_function(operation),
                ),
                "process_purpose": row_text(
                    clue,
                    "process_purpose",
                    "purpose",
                    default=_library_process_function(operation),
                ),
                "product_characteristics": string_list(
                    clue.get("product_characteristics", [])
                ),
                "process_characteristics": string_list(
                    clue.get("process_characteristics", [])
                ),
                "owner": row_text(clue, "owner", default=""),
                "input_refs": string_list(clue.get("input_refs", [])),
                "output_refs": string_list(clue.get("output_refs", [])),
                "equipment": row_text(
                    clue,
                    "equipment",
                    "tooling",
                    default=_library_equipment(operation),
                ),
                "tooling": row_text(clue, "tooling", "fixture", default=""),
                "gauges": string_list(
                    clue.get(
                        "gauges",
                        clue.get("inspection_gauges", clue.get("measurement_devices", [])),
                    )
                ),
                "documents": string_list(
                    clue.get("documents", clue.get("document_refs", clue.get("files", [])))
                ),
                "flow_type": flow_type,
                "flow_symbol": flow_type,
                "operation_type": flow_type_display(flow_type),
                "input_material": "",
                "output_result": operation,
                "special_characteristics": _step_special_characteristics(
                    clue.get(
                        "special_characteristics",
                        clue.get("special_characteristic_refs", []),
                    ),
                    formal_special_ids=formal_special_ids,
                    has_special_block=has_special_block,
                ),
                "special_characteristic_candidates": string_list(
                    clue.get("special_characteristic_candidates", [])
                ),
                "evidence_refs": refs,
                "knowledge_source_refs": all_knowledge_refs,
                "ai_reasoning": row_text(
                    clue,
                    "reasoning",
                    "ai_reasoning",
                    default="根据图纸识别结果和工艺库推断",
                ),
                "confidence": _confidence(clue),
                "ai_inferred": True,
                "needs_confirmation": bool(clue.get("needs_confirmation", _confidence(clue) < 0.85)),
                "source": row_text(clue, "source", default="drawing_recognition"),
            }
        )
    _attach_special_candidate_labels_to_steps(steps, candidate_labels)
    return steps, pending_fields


def _finalize_process_flow(
    steps: list[dict[str, Any]],
    analysis_bundle: dict[str, Any],
    family_context: dict[str, Any] | None,
    pending_fields: list[str],
) -> dict[str, Any]:
    """Build metadata and assemble the final process_flow dict."""
    metadata: dict[str, Any] = {
        "generation_mode": "drawing_analysis_process_flow_inference",
        "llm_used": True,
        "source_stage": "drawing_analysis",
    }
    if family_context:
        metadata["family_context"] = {
            "family_key": family_context.get("family_key", ""),
            "family_name": family_context.get("family_name", ""),
            "confidence": family_context.get("confidence", 0.0),
        }

    normalize_process_flow_steps(steps)

    return {
        "document_type": "process_flow",
        "schema_version": "minos-core.generated.v1",
        "source_document_type": "drawing_analysis_bundle",
        "product": _product_from_drawing(analysis_bundle),
        "evidence": analysis_bundle.get("evidence", []),
        "drawings": [_drawing_from_identity(analysis_bundle.get("drawing_identity", {}))],
        "characteristics": _characteristics_from_drawing(analysis_bundle),
        "steps": steps,
        "links": _sequence_links(steps),
        "pending_fields": pending_fields,
        "ai_inferred_items": [step["process_step_id"] for step in steps],
        "metadata": metadata,
    }
