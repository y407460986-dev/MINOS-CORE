"""Bundle assembly: merge PFD/PFMEA/CP into APQP chain."""
from __future__ import annotations

from typing import Any

from ._utils import _dedupe_mappings, _dedupe_values, _list_value
from .links import _generated_pfd_pfmea_links, _generated_pfmea_cp_links, _generated_step_candidate_links


def assemble_generated_apqp_chain(
    process_flow: dict[str, Any] | None = None,
    failure_mode_candidates: dict[str, Any] | None = None,
    pfmea: dict[str, Any] | None = None,
    control_plan: dict[str, Any] | None = None,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble generated APQP stage bundles into a standard draft payload."""

    if _looks_like_stage_bundle_map(process_flow):
        bundle_map = process_flow or {}
        process_flow = _pick_bundle(bundle_map, "process_flow", "generate_pfd")
        failure_mode_candidates = _pick_bundle(
            bundle_map,
            "failure_mode_candidates",
            "brainstorm_failure_modes",
            "candidates",
        )
        pfmea = _pick_bundle(bundle_map, "pfmea", "generate_pfmea")
        control_plan = _pick_bundle(
            bundle_map, "control_plan", "generate_control_plan", "controls"
        )
    elif _looks_like_combined_stage_payload(process_flow):
        combined_payload = process_flow or {}
        process_flow = combined_payload.get("process_flow")
        failure_mode_candidates = combined_payload.get("failure_mode_candidates")
        pfmea = combined_payload.get("pfmea")
        control_plan = combined_payload.get("control_plan")
        if metadata is None and isinstance(combined_payload.get("metadata"), dict):
            metadata = combined_payload["metadata"]
    elif isinstance(process_flow, dict) and failure_mode_candidates is None and pfmea is None and control_plan is None:
        document_type = str(process_flow.get("document_type", ""))
        if document_type == "failure_mode_candidates":
            failure_mode_candidates = process_flow
            process_flow = None
        elif document_type == "pfmea":
            pfmea = process_flow
            process_flow = None
        elif document_type == "control_plan":
            control_plan = process_flow
            process_flow = None

    if pfmea is None and isinstance(process_flow, dict):
        embedded_pfmea = process_flow.get("pfmea")
        if isinstance(embedded_pfmea, dict):
            pfmea = embedded_pfmea
    if pfmea is None and isinstance(failure_mode_candidates, dict):
        embedded_pfmea = failure_mode_candidates.get("pfmea")
        if isinstance(embedded_pfmea, dict):
            pfmea = embedded_pfmea
    if control_plan is None:
        embedded_control_plan = None
        if isinstance(process_flow, dict):
            embedded_control_plan = process_flow.get("control_plan")
        if embedded_control_plan is None and isinstance(pfmea, dict):
            embedded_control_plan = pfmea.get("control_plan")
        if embedded_control_plan is None and isinstance(failure_mode_candidates, dict):
            embedded_control_plan = failure_mode_candidates.get("control_plan")
        if isinstance(embedded_control_plan, dict):
            control_plan = embedded_control_plan

    bundles = [
        bundle
        for bundle in (process_flow, failure_mode_candidates, pfmea, control_plan)
        if isinstance(bundle, dict)
    ]
    product = _first_mapping_value(
        [process_flow, failure_mode_candidates, pfmea, control_plan], "product"
    )
    schema_version = _first_text_value(
        [process_flow, failure_mode_candidates, pfmea, control_plan], "schema_version"
    )

    process_steps = list(
        (process_flow or {}).get("steps", (process_flow or {}).get("process_steps", []))
    )
    candidate_rows = list(
        (failure_mode_candidates or {}).get(
            "candidates",
            (failure_mode_candidates or {}).get("failure_mode_candidates", []),
        )
    )
    pfmea_rows = list((pfmea or {}).get("rows", (pfmea or {}).get("failure_modes", [])))
    control_rows = _list_value(
        {
            "rows": (control_plan or {}).get(
                "rows",
                (control_plan or {}).get(
                    "controls", (control_plan or {}).get("control_plan_items", [])
                ),
            )
        },
        "rows",
    )
    evidence_rows = _merge_evidence(bundles)
    links = _dedupe_mappings(
        list((process_flow or {}).get("links", []))
        + list((failure_mode_candidates or {}).get("links", []))
        + list((pfmea or {}).get("links", []))
        + list((control_plan or {}).get("links", []))
        + _generated_pfd_pfmea_links(process_steps, candidate_rows, pfmea_rows, evidence_rows)
        + _generated_pfmea_cp_links(pfmea_rows, control_rows, evidence_rows)
        + _generated_step_candidate_links(process_steps, candidate_rows)
    )
    assembled_metadata = _merge_metadata(bundles, metadata)
    assembled_metadata["generated"] = True
    assembled_metadata["requires_engineering_review"] = True

    return {
        "document_type": "apqp_chain",
        "schema_version": schema_version or "minos-core.generated.v1",
        "product": product,
        "process_steps": _dedupe_mappings(process_steps),
        "failure_mode_candidates": _dedupe_mappings(candidate_rows),
        "failure_modes": _dedupe_mappings(pfmea_rows),
        "controls": _dedupe_mappings(control_rows),
        "evidence": _merge_evidence(bundles),
        "links": links,
        "pending_fields": _merge_list_field(bundles, "pending_fields"),
        "ai_inferred_items": _merge_list_field(bundles, "ai_inferred_items"),
        "metadata": assembled_metadata,
    }


def _looks_like_stage_bundle_map(value: Any) -> bool:
    """Check if the value is a bundle dict keyed by stage name (not a single bundle)."""
    if not isinstance(value, dict):
        return False
    if value.get("document_type") in {
        "process_flow",
        "failure_mode_candidates",
        "pfmea",
        "control_plan",
    }:
        return False
    return any(
        isinstance(value.get(key), dict)
        for key in (
            "process_flow",
            "generate_pfd",
            "failure_mode_candidates",
            "brainstorm_failure_modes",
            "pfmea",
            "generate_pfmea",
            "control_plan",
            "generate_control_plan",
        )
    )


def _looks_like_combined_stage_payload(value: Any) -> bool:
    """Check if the value is a combined payload containing multiple stage bundles."""
    if not isinstance(value, dict):
        return False
    return any(key in value for key in ("process_flow", "pfmea", "control_plan"))


def _pick_bundle(bundle_map: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    """Return the first dict value from bundle_map matching any of the given keys."""
    for key in keys:
        value = bundle_map.get(key)
        if isinstance(value, dict):
            return value
    return None


def _first_mapping_value(
    bundles: list[dict[str, Any] | None], field_name: str
) -> dict[str, Any]:
    """Return the first non-empty dict value for field_name across bundles."""
    for bundle in bundles:
        if isinstance(bundle, dict) and isinstance(bundle.get(field_name), dict):
            return dict(bundle[field_name])
    return {}


def _first_text_value(
    bundles: list[dict[str, Any] | None], field_name: str
) -> str:
    """Return the first non-empty text value for field_name across bundles."""
    for bundle in bundles:
        if isinstance(bundle, dict):
            value = str(bundle.get(field_name, "")).strip()
            if value:
                return value
    return ""


def _merge_evidence(bundles: list[dict[str, Any]]) -> list[Any]:
    """Merge and deduplicate evidence entries from multiple bundles."""
    evidence: list[Any] = []
    for bundle in bundles:
        evidence.extend(_list_value(bundle, "evidence"))
    return _dedupe_values(evidence)


def _merge_list_field(bundles: list[dict[str, Any]], field_name: str) -> list[Any]:
    """Merge and deduplicate a list-valued field across multiple bundles."""
    values: list[Any] = []
    for bundle in bundles:
        values.extend(_list_value(bundle, field_name))
    return _dedupe_values(values)


def _merge_metadata(
    bundles: list[dict[str, Any]], extra_metadata: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge metadata dicts from multiple bundles with optional extras."""
    merged: dict[str, Any] = {}
    source_stages: list[str] = []
    generation_modes: list[str] = []
    for bundle in bundles:
        bundle_metadata = bundle.get("metadata", {})
        if not isinstance(bundle_metadata, dict):
            continue
        for key, value in bundle_metadata.items():
            if key == "source_stage" and value:
                source_stages.append(str(value))
            elif key == "generation_mode" and value:
                generation_modes.append(str(value))
            elif key not in merged:
                merged[key] = value
    if generation_modes:
        merged["generation_modes"] = _dedupe_values(generation_modes)
    if source_stages:
        merged["source_stages"] = _dedupe_values(source_stages)
    if extra_metadata:
        merged.update(extra_metadata)
    return merged
