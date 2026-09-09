"""Core gate evaluation utilities: confirmations, pending fields, AI inference."""
from __future__ import annotations

from typing import Any

from ..domain import APQPChain
from ..review_patch import REVIEW_CONFIRMATIONS_KEY

__all__ = [
    "_ai_inferred_items",
    "_confirmation_matches_value",
    "_confirmed_field_paths",
    "_confirmed_targets",
    "_dedupe_preserve_order",
    "_flagged_evidence_ids",
    "_flagged_item_label",
    "_flagged_item_labels",
    "_float_value",
    "_is_confirmed",
    "_is_mechanical_trace_link",
    "_metadata_list",
    "_pending_field_paths",
    "_pending_fields",
    "_review_confirmations",
    "_row_mapping_id",
    "_row_needs_confirmation_items",
    "_strict_aiag_vda_pfmea_gate_enabled",
    "_trace_link_label",
    "_without_confirmed",
]


def _metadata_list(chain: APQPChain, key: str) -> list[dict[str, Any]]:
    """Retrieve the metadata list for the given key from the chain metadata."""
    value = chain.metadata.get(key, []) if isinstance(chain.metadata, dict) else []
    return value if isinstance(value, list) else []


def _strict_aiag_vda_pfmea_gate_enabled(chain: APQPChain) -> bool:
    """Check whether the strict AIAG/VDA PFMEA gate is enabled for the given chain."""
    metadata = chain.metadata if isinstance(chain.metadata, dict) else {}
    if metadata.get("skip_strict_gate") is True:
        return False
    if metadata.get("strict_aiag_vda_pfmea_gate") is True:
        return True
    generation_mode = str(metadata.get("generation_mode", "")).strip()
    return generation_mode in {"ai_drawing_three_table_generation", "human_edited_three_table_generation"}


def _float_value(value: Any) -> float | None:
    """Convert a value to float, returning None on failure."""
    try:
        return None if value in {None, ""} else float(value)
    except (TypeError, ValueError):
        return None


def _flagged_evidence_ids(items: Any, flag: str) -> list[str]:
    """Return evidence IDs for items that have the given flag set."""
    if isinstance(items, dict):
        iterable = [items]
    elif isinstance(items, list):
        iterable = items
    else:
        return []
    return [
        str(item.get("evidence_id") or item.get("item_id"))
        for item in iterable
        if isinstance(item, dict)
        and (item.get("evidence_id") or item.get("item_id"))
        and item.get(flag)
    ]


def _pending_field_paths(items: Any) -> list[str]:
    """Extract pending field path strings from items."""
    if items is None:
        return []
    if isinstance(items, str):
        value = items.strip()
        return [value] if value else []
    if not isinstance(items, list):
        return ["pending_fields"]
    paths: list[str] = []
    for item in items:
        if isinstance(item, str):
            value = item.strip()
            if value:
                paths.append(value)
            continue
        if isinstance(item, dict) and item.get("field"):
            paths.append(
                f"{item.get('source_ref', '')}.{item.get('field', '')}".strip(".")
            )
    return paths


def _row_needs_confirmation_items(chain: APQPChain) -> list[str]:
    """Collect all items in the chain that still need human confirmation."""
    items: list[str] = []
    for step in chain.process_steps:
        if step.needs_confirmation:
            items.append(f"process_step:{step.process_step_id}")
    for candidate in chain.failure_mode_candidates:
        if candidate.needs_confirmation:
            items.append(f"failure_mode_candidate:{candidate.candidate_id}")
    for failure in chain.failure_modes:
        if failure.needs_confirmation:
            items.append(f"failure_mode:{failure.pfmea_id}")
    for control in chain.controls:
        if control.needs_confirmation:
            items.append(f"control_item:{control.control_plan_id}")
    for link in chain.links:
        if link.needs_confirmation and not _is_mechanical_trace_link(link):
            items.append(_trace_link_label(link))
    items.extend(_pending_field_paths(chain.pending_fields))
    items.extend(_flagged_item_labels(chain.ai_inferred_items, "needs_confirmation"))
    return _dedupe_preserve_order(items)


def _is_mechanical_trace_link(link: Any) -> bool:
    """Return True for mechanically generated trace links that do not need
    independent human confirmation (real gating is done by linkage gaps)."""
    link_id = str(getattr(link, "trace_link_id", "")).strip().upper()
    return any(link_id.startswith(prefix) for prefix in ("TL-PFD-PFMEA-", "TL-PFMEA-CP-", "TL-STEP-CAND-"))


def _trace_link_label(link: Any) -> str:
    """Build a human-readable label string for a trace link."""
    link_id = str(getattr(link, "trace_link_id", "")).strip()
    if link_id:
        return f"trace_link:{link_id}"
    from_id = str(getattr(link, "from_id", "")).strip()
    to_id = str(getattr(link, "to_id", "")).strip()
    if from_id or to_id:
        return f"trace_link:{from_id}->{to_id}"
    return "trace_link"


def _flagged_item_labels(items: Any, flag: str) -> list[str]:
    """Extract labels for items that have the given flag set."""
    if isinstance(items, dict):
        iterable = [items]
    elif isinstance(items, list):
        iterable = items
    else:
        return []
    labels: list[str] = []
    for index, item in enumerate(iterable):
        if isinstance(item, str):
            if flag == "needs_confirmation" and item.strip():
                labels.append(item.strip())
            continue
        if not isinstance(item, dict) or not item.get(flag):
            continue
        labels.append(_flagged_item_label(item, index))
    return labels


def _flagged_item_label(item: dict[str, Any], index: int) -> str:
    """Generate a single label for a flagged item, falling back to a positional index."""
    for field_name in (
        "id",
        "item_id",
        "field",
        "evidence_id",
        "process_step_id",
        "pfmea_id",
        "control_plan_id",
        "candidate_id",
        "link_id",
        "trace_link_id",
    ):
        value = str(item.get(field_name, "")).strip()
        if value:
            return value
    return f"ai_inferred_item[{index}]"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    """Deduplicate a list while preserving the original order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def _confirmed_targets(chain: APQPChain) -> set[str]:
    """Return the set of confirmed target identifiers from the chain metadata."""
    return {
        str(item.get("target", "")).strip()
        for item in _review_confirmations(chain)
        if isinstance(item, dict) and str(item.get("target", "")).strip()
    }


def _confirmed_field_paths(chain: APQPChain) -> set[str]:
    """Return the set of confirmed field paths from review confirmations."""
    field_paths: set[str] = set()
    for item in _review_confirmations(chain):
        if not isinstance(item, dict):
            continue
        field_path = str(item.get("field_path", "")).strip()
        if field_path:
            field_paths.add(field_path)
        target = str(item.get("target", "")).strip()
        field = str(item.get("field", "")).strip()
        if target.startswith("pending_field:"):
            field_paths.add(target.split(":", 1)[1].strip())
        if target and field:
            target_id = target.split(":", 1)[1] if ":" in target else target
            field_paths.add(f"{target_id}.{field}")
            field_paths.add(f"{target}.{field}")
    return field_paths


def _review_confirmations(chain: APQPChain) -> list[Any]:
    """Retrieve the review confirmations list from the chain metadata."""
    confirmations = chain.metadata.get(REVIEW_CONFIRMATIONS_KEY, [])
    return confirmations if isinstance(confirmations, list) else []


def _row_mapping_id(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    """Return the first non-empty field value from the row for the given fields."""
    for field_name in fields:
        value = str(row.get(field_name, "")).strip()
        if value:
            return value
    return ""


def _without_confirmed(values: list[str], confirmed: set[str]) -> list[str]:
    """Filter out values that are already confirmed."""
    return [value for value in values if not _is_confirmed(value, confirmed)]


def _is_confirmed(value: str, confirmed: set[str]) -> bool:
    """Check whether a value has been confirmed, considering aliases."""
    text = str(value).strip()
    if not text:
        return False
    if text in confirmed:
        return True
    return any(_confirmation_matches_value(item, text) for item in confirmed)


def _confirmation_matches_value(confirmed: str, value: str) -> bool:
    """Check whether a confirmed string matches a value using flexible comparisons."""
    if confirmed == value:
        return True
    if " -> " in value:
        _, ref = value.rsplit(" -> ", 1)
        if confirmed == ref.strip():
            return True
        if confirmed == f"evidence:{ref.strip()}":
            return True
    if ":" in confirmed:
        confirmed_type, confirmed_id = confirmed.split(":", 1)
        if value.startswith(f"{confirmed} -> "):
            return True
        if value == confirmed_id:
            return True
        if value.endswith(f":{confirmed_id}"):
            return True
        if value.startswith(f"{confirmed_id}."):
            return True
        if value.startswith(f"{confirmed}."):
            return True
        if value.endswith(f" -> {confirmed_id}"):
            return True
        if confirmed_type == "evidence" and value.endswith(f" -> {confirmed_id}"):
            return True
    return False


def _pending_fields(chain: APQPChain) -> list[str]:
    """Identify fields in the chain that still have empty/missing values."""
    pending: list[str] = []
    for failure in chain.failure_modes:
        if not failure.failure_mode:
            pending.append(f"{failure.pfmea_id}.failure_mode")
        if not failure.failure_cause:
            pending.append(f"{failure.pfmea_id}.failure_cause")
    for control in chain.controls:
        if not control.specification:
            pending.append(f"{control.control_plan_id}.specification")
        if not control.reaction_plan:
            pending.append(f"{control.control_plan_id}.reaction_plan")
    for item in _pending_field_paths(getattr(chain, "pending_fields", [])):
        if item and item not in pending:
            pending.append(item)
    return pending


def _ai_inferred_items(chain: APQPChain) -> list[str]:
    """Collect evidence IDs and items that were AI-inferred in the chain."""
    items = [item.evidence_id for item in chain.evidence if item.ai_inferred]
    for item in _flagged_evidence_ids(
        getattr(chain, "ai_inferred_items", []), "ai_inferred"
    ):
        if item and item not in items:
            items.append(item)
    for item in getattr(chain, "ai_inferred_items", []):
        if isinstance(item, dict):
            continue
        value = str(item)
        if value and value not in items:
            items.append(value)
    return items
