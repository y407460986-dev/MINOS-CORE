"""Edit patch helpers with no dependency on run services."""

from __future__ import annotations

from typing import Any

from ..app_state import ChainStageStates
from ..table_editor import EDIT_PATCH_VERSION


def _merge_edit_patch(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged_items: list[dict[str, Any]] = []
    for source in (existing, patch):
        items = source.get("items", []) if isinstance(source, dict) else []
        if isinstance(items, list):
            merged_items.extend(item for item in items if isinstance(item, dict))
    return {"edit_patch_version": EDIT_PATCH_VERSION, "items": merged_items}


def _apply_confirm_edit_patch(
    current: dict[str, Any],
    existing_patch: dict[str, Any],
    patch: dict[str, Any] | None,
    chain_stages: ChainStageStates | None = None,
) -> tuple[dict[str, Any], dict[str, Any], ChainStageStates | None]:
    if not patch:
        return current, existing_patch, chain_stages
    edit_patch = _normalize_edit_patch(patch)
    from .run_shared import _apply_edit_patch, _invalidate_chain_after_patch

    updated = _apply_edit_patch(current, edit_patch)
    updated, updated_stages = _invalidate_chain_after_patch(updated, edit_patch, chain_stages)
    return updated, _merge_edit_patch(existing_patch, edit_patch), updated_stages


def _normalize_three_table_result(result: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(result or {})
    if any(key in normalized for key in ("process_flow", "pfmea", "control_plan")):
        normalized.setdefault("document_type", "three_table_generation_result")
        normalized.setdefault("schema_version", "minos-core.three_table_generation_result.v1")
        normalized.setdefault("status", "needs_review")
        normalized.setdefault("blocked_stage", None)
        normalized.setdefault("drawing_analysis", {"evidence": []})
        normalized.setdefault("process_flow", {"steps": []})
        normalized.setdefault("pfmea", {"rows": []})
        normalized.setdefault("control_plan", {"rows": []})
        normalized.setdefault("quality_gate", {})
        normalized.setdefault("quality_gates", {})
        normalized.setdefault("exports", {})
        normalized.setdefault("manifest", {})
        normalized.setdefault("manual_review", {"required": False, "items": []})
        normalized.setdefault("warnings", [])
    return normalized


def _normalize_edit_patch(patch: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(patch)
    normalized.setdefault("edit_patch_version", EDIT_PATCH_VERSION)
    items = normalized.get("items", [])
    if not isinstance(items, list):
        normalized["items"] = []
        return normalized
    normalized_items: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            normalized_items.append(item)
            continue
        normalized_item = dict(item)
        if not normalized_item.get("target_id"):
            from .run_shared import _target_id

            normalized_item["target_id"] = str(
                normalized_item.get("row_id") or _target_id(str(normalized_item.get("target") or ""))
            ).strip()
        normalized_items.append(normalized_item)
    normalized["items"] = normalized_items
    return normalized


def _evaluate_edit_export_gate(result: dict[str, Any]) -> dict[str, Any]:
    try:
        from minos_core.edit_patch import evaluate_edit_export_gate
    except ModuleNotFoundError as exc:
        if exc.name not in {"minos_core.edit_patch", "edit_patch"}:
            raise
        from .run_shared import _evaluate_edit_export_gate_locally

        return _evaluate_edit_export_gate_locally(result)
    gate = evaluate_edit_export_gate(result)
    if isinstance(gate, dict):
        return gate
    if hasattr(gate, "model_dump"):
        return gate.model_dump()
    if hasattr(gate, "__dict__"):
        return dict(gate.__dict__)
    return {"allow_final_export": bool(gate)}
