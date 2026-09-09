"""Evidence packet builder for AI special-characteristic judging."""

from __future__ import annotations

from typing import Any

from minos_core._text_utils import string_list, text


def build_special_characteristic_evidence_packet(
    drawing_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Build the evidence-only input consumed by the special-characteristic judge."""
    symbol_occurrences = _symbol_occurrences(drawing_analysis)
    text_evidence = _text_evidence(drawing_analysis)
    legend_evidence = _legend_evidence(drawing_analysis)
    customer_rules = _customer_rules(drawing_analysis)
    visual_evidence = _visual_evidence(drawing_analysis)
    visual_evidence_refs = _visual_evidence_refs(visual_evidence)
    visual_locator_metadata = _visual_locator_metadata(drawing_analysis)
    page_evidence_refs = _page_evidence_refs(
        drawing_analysis,
        symbol_occurrences,
        legend_evidence,
        text_evidence,
        customer_rules,
        visual_evidence,
    )
    return {
        "packet_id": text(drawing_analysis.get("packet_id")) or "SC-EVIDENCE-001",
        "drawing_identity": dict(drawing_analysis.get("drawing_identity", {})),
        "declared_counts": [
            dict(item)
            for item in drawing_analysis.get("declared_special_characteristics", [])
            if isinstance(item, dict)
        ],
        "declared_totals": dict(_dict(drawing_analysis.get("declared_totals"))),
        "located_occurrences": [
            dict(item)
            for item in drawing_analysis.get("special_characteristic_locations", [])
            if isinstance(item, dict)
        ],
        "missing_counts": dict(
            _dict(drawing_analysis.get("special_characteristic_discovery")).get(
                "missing_counts", {}
            )
        ),
        "search_coverage": dict(
            _dict(drawing_analysis.get("special_characteristic_discovery")).get(
                "search_coverage", {}
            )
        ),
        "legend_evidence": legend_evidence,
        "symbol_occurrences": symbol_occurrences,
        "text_evidence": text_evidence,
        "customer_rules": customer_rules,
        "visual_evidence": visual_evidence,
        "visual_evidence_refs": visual_evidence_refs,
        "visual_locator_metadata": visual_locator_metadata,
        "page_evidence_refs": page_evidence_refs,
        "special_characteristics": [],
    }


def _symbol_occurrences(drawing_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    for item in drawing_analysis.get("special_characteristic_candidates", []):
        if not isinstance(item, dict):
            continue
        cleaned = {
            key: value
            for key, value in item.items()
            if key not in {"confirmation_status", "needs_confirmation", "ai_inferred"}
        }
        occurrences.append(cleaned)
    return occurrences


def _legend_evidence(drawing_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    legends: list[dict[str, Any]] = []
    for item in drawing_analysis.get("legend_evidence", []):
        if isinstance(item, dict):
            legends.append(dict(item))
    for item in drawing_analysis.get("special_characteristic_candidates", []):
        if not isinstance(item, dict):
            continue
        if text(item.get("source")) in {"legend", "symbol_table_on_drawing"}:
            legend = {
                key: value
                for key, value in item.items()
                if key not in {"confirmation_status", "needs_confirmation", "ai_inferred"}
            }
            legend.setdefault("legend_id", text(item.get("legend_id"), item.get("candidate_id")))
            legends.append(legend)
    return legends


def _text_evidence(drawing_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in drawing_analysis.get("text_evidence", []):
        if isinstance(item, dict):
            rows.append(dict(item))
    for block in ("technical_requirements", "inspection_requirements"):
        for index, item in enumerate(drawing_analysis.get(block, []), start=1):
            if not isinstance(item, dict):
                continue
            value = text(item.get("text"), item.get("description"), item.get("name"))
            if not value:
                continue
            rows.append(
                {
                    "text_id": text(item.get("text_id"), item.get("id"))
                    or f"{block.upper()}-{index:03d}",
                    "text": value,
                    "evidence_refs": string_list(item.get("evidence_refs", [])),
                    "source": text(item.get("source")) or block,
                }
            )
    return rows


def _customer_rules(drawing_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in drawing_analysis.get("customer_rules", [])
        if isinstance(item, dict)
    ]


def _visual_evidence(drawing_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in drawing_analysis.get("visual_evidence", []):
        if isinstance(item, dict):
            rows.append(dict(item))
    return rows


def _visual_evidence_refs(visual_evidence: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for item in visual_evidence:
        _append_unique(refs, text(item.get("evidence_id"), item.get("id")))
        for ref in string_list(item.get("evidence_refs", [])):
            _append_unique(refs, ref)
    return refs


def _visual_locator_metadata(drawing_analysis: dict[str, Any]) -> dict[str, Any]:
    metadata = _dict(drawing_analysis.get("metadata"))
    locator_metadata = drawing_analysis.get("visual_locator_metadata")
    if isinstance(locator_metadata, dict):
        return dict(locator_metadata)
    for key in (
        "visual_locator",
        "gpt55_visual_locator",
        "special_characteristic_visual_locator",
    ):
        value = metadata.get(key)
        if isinstance(value, dict):
            return dict(value)
    return {}


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _page_evidence_refs(
    drawing_analysis: dict[str, Any],
    *evidence_groups: list[dict[str, Any]],
) -> list[str]:
    refs: list[str] = []
    for item in drawing_analysis.get("evidence", []):
        if isinstance(item, dict):
            _append_unique(refs, text(item.get("evidence_id"), item.get("id")))
    for ref in string_list(drawing_analysis.get("page_evidence_refs", [])):
        _append_unique(refs, ref)
    for group in evidence_groups:
        for item in group:
            _append_unique(refs, text(item.get("evidence_id"), item.get("id")))
            for ref in string_list(item.get("evidence_refs", [])):
                _append_unique(refs, ref)
    return refs


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
