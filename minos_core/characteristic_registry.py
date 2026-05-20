"""Characteristic registry — extracts characteristics from drawing analysis
and attaches them to PFD/PFMEA/CP three-table documents."""

from __future__ import annotations

import copy
from typing import Any

from minos_core._text_utils import string_list, text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_characteristic_registry(drawing_analysis: dict[str, Any]) -> dict[str, Any]:
    """从图纸分析结果构建特性注册表。

    Extracts characteristics from four source blocks in the drawing analysis
    bundle and returns a unified registry with stable IDs, deduplication,
    and traceability metadata.
    """
    blocks: list[tuple[str, str, str]] = [
        ("dimensions", "dimension", "dimensions"),
        ("special_characteristics", "special_characteristic", "special_characteristics"),
        ("technical_requirements", "technical_requirement", "technical_requirements"),
        ("inspection_requirements", "inspection_requirement", "inspection_requirements"),
    ]

    chr_counter = 0
    sc_counter = 0
    items: list[dict[str, Any]] = []

    for block_key, classification, source_block in blocks:
        raw_items = _list(drawing_analysis.get(block_key))
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue

            name = _extract_name(raw, block_key)
            if not name:
                continue

            spec = _extract_specification(raw, block_key)

            # --- ID generation ---
            if block_key == "special_characteristics":
                symbol = text(raw.get("symbol"))
                if symbol:
                    characteristic_id = symbol
                else:
                    sc_counter += 1
                    characteristic_id = f"SC-{sc_counter:03d}"
            else:
                chr_counter += 1
                characteristic_id = f"CHR-{chr_counter:03d}"

            item: dict[str, Any] = {
                "characteristic_id": characteristic_id,
                "name": name,
                "classification": classification,
                "specification": spec,
                "source_block": source_block,
                "source_ref": text(raw.get("source_ref", "")),
                "evidence_refs": string_list(raw.get("evidence_refs", [])),
                "confidence": _confidence(raw),
                "ai_inferred": bool(raw.get("ai_inferred", True)),
                "needs_confirmation": bool(raw.get("needs_confirmation", False)),
            }
            items.append(item)

    # Deduplicate: same name + same specification + overlapping evidence_refs
    items = _deduplicate_by_name_spec_evidence(items)

    return {
        "document_type": "characteristic_registry",
        "schema_version": "minos-core.characteristic_registry.v1",
        "items": items,
    }


def attach_characteristics_to_three_tables(
    source: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    """将特性注册表挂接到三表（PFD/PFMEA/CP）的 characteristic_refs。

    Returns a modified **copy** of *source*; the original dict is never mutated.
    """
    result = copy.deepcopy(source)
    items = _list(registry.get("items", []))

    _attach_to_pfd(result, items)
    _attach_to_pfmea(result, items)
    _attach_to_cp(result, items)

    return result


def characteristics_for_step(
    registry: dict[str, Any],
    step: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return registry items relevant to a specific PFD step.

    Matches based on substring overlap between the characteristic name
    and the step's operation/process_function fields.
    """
    items = _list(registry.get("items", []))
    combined = (
        text(step.get("operation"), step.get("name", ""))
        + " "
        + text(step.get("process_function"), step.get("description", ""))
    ).strip()
    if not combined:
        return []
    matched = []
    for item in items:
        name = text(item.get("name"))
        if not name:
            continue
        if name in combined or _keyword_overlap(name, combined):
            matched.append(item)
    return matched


def _keyword_overlap(name: str, combined: str) -> bool:
    """Check if key terms from the characteristic name appear in the step text."""
    keywords = [w for w in name.replace("≥", " ").replace("≤", " ").split() if len(w) >= 2]
    if not keywords:
        return False
    return sum(1 for kw in keywords if kw in combined) >= max(1, len(keywords) // 2)


# ---------------------------------------------------------------------------
# Internal: name / specification extraction
# ---------------------------------------------------------------------------


def _extract_name(raw: dict[str, Any], block_key: str) -> str:
    """Extract a human-readable name from an analysis item."""
    name = text(raw.get("name"), raw.get("designation"), raw.get("characteristic"))
    if name:
        return name
    if block_key == "technical_requirements":
        return text(raw.get("description"), raw.get("requirement_desc"))
    if block_key == "inspection_requirements":
        return text(raw.get("item"), raw.get("inspection_item"))
    return ""


def _extract_specification(raw: dict[str, Any], block_key: str) -> str:
    """Extract a specification/tolerance string from an analysis item."""
    spec = text(
        raw.get("specification"),
        raw.get("dimension_value"),
        raw.get("value"),
        raw.get("tolerance"),
    )
    if spec:
        return spec
    if block_key == "technical_requirements":
        return text(raw.get("description"), raw.get("requirement_desc"))
    if block_key == "inspection_requirements":
        return text(raw.get("requirement"), raw.get("item"), raw.get("inspection_item"))
    return ""


# ---------------------------------------------------------------------------
# Internal: deduplication
# ---------------------------------------------------------------------------


def _deduplicate_by_name_spec_evidence(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate items that share the same name, specification, and at least
    one evidence_ref. The first occurrence is kept; confidence takes the higher
    of the two values."""
    deduped: list[dict[str, Any]] = []
    for candidate in items:
        merged = False
        for existing in deduped:
            if _is_same_characteristic(existing, candidate):
                # Keep the higher confidence
                existing["confidence"] = max(
                    existing.get("confidence", 0.0),
                    candidate.get("confidence", 0.0),
                )
                merged = True
                break
        if not merged:
            deduped.append(candidate)
    return deduped


def _is_same_characteristic(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Two characteristics are the same when name, specification, source_block,
    and at least one evidence_ref overlap."""
    if text(a.get("source_block")) != text(b.get("source_block")):
        return False
    if text(a.get("name")) != text(b.get("name")):
        return False
    if text(a.get("specification")) != text(b.get("specification")):
        return False
    a_refs = set(string_list(a.get("evidence_refs", [])))
    b_refs = set(string_list(b.get("evidence_refs", [])))
    if not a_refs or not b_refs:
        return False
    return bool(a_refs & b_refs)


# ---------------------------------------------------------------------------
# Internal: three-table attachment
# ---------------------------------------------------------------------------


def _attach_to_pfd(source: dict[str, Any], items: list[dict[str, Any]]) -> None:
    """Attach characteristic refs to PFD steps."""
    for step in _pfd_steps(source):
        _attach_to_step(step, items)


def _attach_to_step(step: dict[str, Any], items: list[dict[str, Any]]) -> None:
    """Attach characteristic refs to a single PFD step based on substring
    matches in operation and process_function."""
    combined = text(step.get("operation"), step.get("name", "")) + " " + text(
        step.get("process_function"), step.get("description", "")
    )
    if not combined.strip():
        return

    characteristic_refs = _ensure_list(step, "characteristic_refs")
    special_characteristics = _ensure_list(step, "special_characteristics")

    for item in items:
        name = text(item.get("name"))
        if not name:
            continue
        if name in combined:
            cid = text(item.get("characteristic_id"))
            if cid and cid not in characteristic_refs:
                characteristic_refs.append(cid)
            if (
                text(item.get("classification")) == "special_characteristic"
                and cid
                and cid not in special_characteristics
            ):
                special_characteristics.append(cid)


def _attach_to_pfmea(source: dict[str, Any], items: list[dict[str, Any]]) -> None:
    """Attach characteristic refs to PFMEA rows."""
    for row in _pfmea_rows(source):
        combined = text(
            row.get("failure_mode"), row.get("failure_mode_description", "")
        ) + " " + text(row.get("function_requirement"), row.get("requirement", ""))
        if not combined.strip():
            continue

        characteristic_refs = _ensure_list(row, "characteristic_refs")
        for item in items:
            name = text(item.get("name"))
            if not name:
                continue
            if name in combined:
                cid = text(item.get("characteristic_id"))
                if cid and cid not in characteristic_refs:
                    characteristic_refs.append(cid)


def _attach_to_cp(source: dict[str, Any], items: list[dict[str, Any]]) -> None:
    """Attach characteristic refs to CP rows."""
    for row in _cp_rows(source):
        combined = text(
            row.get("product_process_characteristic"), row.get("characteristic", "")
        ) + " " + text(row.get("specification", ""))
        if not combined.strip():
            continue

        characteristic_refs = _ensure_list(row, "characteristic_refs")
        source_special_characteristics = _ensure_list(row, "source_special_characteristics")

        for item in items:
            name = text(item.get("name"))
            if not name:
                continue
            if name in combined:
                cid = text(item.get("characteristic_id"))
                if cid and cid not in characteristic_refs:
                    characteristic_refs.append(cid)
                if (
                    text(item.get("classification")) == "special_characteristic"
                    and cid
                    and cid not in source_special_characteristics
                ):
                    source_special_characteristics.append(cid)


# ---------------------------------------------------------------------------
# Internal: row extraction (mirrors change_management._rows pattern)
# ---------------------------------------------------------------------------


def _pfd_steps(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract PFD steps from a source dict that may be a three-table payload
    or an APQP chain dict."""
    rows = _rows(source, "process_flow", "process_steps", "steps")
    return [r for r in rows if isinstance(r, dict)]


def _pfmea_rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _rows(source, "pfmea", "failure_modes", "rows")
    return [r for r in rows if isinstance(r, dict)]


def _cp_rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _rows(source, "control_plan", "controls", "rows")
    return [r for r in rows if isinstance(r, dict)]


def _rows(
    source: dict[str, Any],
    table: str,
    chain_key: str,
    table_key: str,
) -> list[Any]:
    """Follow the same lookup convention as change_management._rows."""
    if table in source and isinstance(source.get(table), dict):
        rows = source[table].get(table_key)
        if isinstance(rows, list):
            return rows
    rows = source.get(chain_key)
    return rows if isinstance(rows, list) else []


# ---------------------------------------------------------------------------
# Internal: generic helpers
# ---------------------------------------------------------------------------


def _list(value: Any) -> list[Any]:
    """Coerce *value* to a list, or return an empty list."""
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return []


def _confidence(item: dict[str, Any]) -> float:
    """Extract a 0.0-1.0 confidence value from an analysis item."""
    try:
        return float(item.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _ensure_list(parent: dict[str, Any], key: str) -> list[Any]:
    """Ensure *parent[key]* is a list, creating it if necessary."""
    value = parent.get(key)
    if not isinstance(value, list):
        value = []
        parent[key] = value
    return value
