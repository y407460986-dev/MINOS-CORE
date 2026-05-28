"""Hybrid mode fusion logic for OCR and vision analysis."""

from __future__ import annotations

import copy
from typing import Any

from .._text_utils import string_list
from ..three_table_result import dedupe_strings as _dedupe_strings
from .utilities import _as_dict, _clean_text, _float_value, _summary_items
from .family_context import _ocr_family_lock_classification


# OCR identity lock thresholds and fields
OCR_IDENTITY_LOCK_CONFIDENCE = 0.70
OCR_IDENTITY_LOCK_FIELDS = ("part_name", "drawing_number", "revision")


def _attach_ocr_reference_metadata(
    vision_analysis: dict[str, Any],
    ocr_analysis: dict[str, Any],
) -> None:
    """Attach OCR analysis summary to vision analysis metadata."""
    metadata = vision_analysis.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["ocr_analysis_summary"] = _ocr_summary_for_context(ocr_analysis)


def _lock_hybrid_identity_from_ocr(
    vision_analysis: dict[str, Any],
    ocr_analysis: dict[str, Any],
) -> None:
    """Lock high-confidence OCR identity fields into vision analysis in hybrid mode."""
    ocr_identity = _as_dict(ocr_analysis.get("drawing_identity"))
    ocr_part_name = _clean_text(ocr_identity.get("part_name"))
    ocr_confidence = _float_value(ocr_identity.get("confidence"), 0.0)
    if not ocr_part_name or ocr_confidence < OCR_IDENTITY_LOCK_CONFIDENCE:
        return

    vision_identity = vision_analysis.setdefault("drawing_identity", {})
    if not isinstance(vision_identity, dict):
        vision_identity = {}
        vision_analysis["drawing_identity"] = vision_identity
    original_identity = copy.deepcopy(vision_identity)
    locked_fields: list[str] = []
    ocr_field_refs = _as_dict(ocr_identity.get("field_evidence_refs"))
    vision_field_refs = vision_identity.setdefault("field_evidence_refs", {})
    if not isinstance(vision_field_refs, dict):
        vision_field_refs = {}
        vision_identity["field_evidence_refs"] = vision_field_refs

    for field_name in OCR_IDENTITY_LOCK_FIELDS:
        value = _clean_text(ocr_identity.get(field_name))
        if not value:
            continue
        if _clean_text(vision_identity.get(field_name)) != value:
            locked_fields.append(f"drawing_identity.{field_name}")
        vision_identity[field_name] = value
        refs = string_list(ocr_field_refs.get(field_name))
        if refs:
            vision_field_refs[field_name] = refs

    if not locked_fields:
        return

    ocr_refs = string_list(ocr_identity.get("evidence_refs"))
    if ocr_refs:
        vision_identity["evidence_refs"] = _dedupe_strings(
            string_list(vision_identity.get("evidence_refs")) + ocr_refs
        )
    vision_identity["confidence"] = max(
        _float_value(vision_identity.get("confidence"), 0.0),
        ocr_confidence,
    )
    vision_identity["ocr_identity_locked"] = True
    vision_identity["needs_confirmation"] = bool(
        ocr_identity.get("needs_confirmation", vision_identity.get("needs_confirmation", False))
    )

    _merge_ocr_evidence(vision_analysis, ocr_analysis)
    metadata = vision_analysis.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        vision_analysis["metadata"] = metadata

    lock_record: dict[str, Any] = {
        "locked": True,
        "source": "ocr_title_block",
        "reason": "OCR/title-block identity is treated as the whole-part authority in hybrid mode.",
        "confidence": round(ocr_confidence, 3),
        "locked_fields": locked_fields,
        "ocr_identity": copy.deepcopy(ocr_identity),
        "original_vision_identity": original_identity,
    }
    family_lock = _ocr_family_lock_classification(ocr_analysis)
    if family_lock:
        lock_record["part_family_classification"] = family_lock
        metadata["locked_part_family_classification"] = family_lock
    metadata["ocr_identity_lock"] = lock_record


def _merge_ocr_evidence(
    vision_analysis: dict[str, Any],
    ocr_analysis: dict[str, Any],
) -> None:
    """Merge OCR evidence items into vision analysis evidence list."""
    evidence = vision_analysis.setdefault("evidence", [])
    if not isinstance(evidence, list):
        evidence = []
        vision_analysis["evidence"] = evidence
    existing_ids = {
        str(item.get("evidence_id", "")).strip()
        for item in evidence
        if isinstance(item, dict)
    }
    for item in ocr_analysis.get("evidence", []):
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id", "")).strip()
        if not evidence_id or evidence_id in existing_ids:
            continue
        evidence.append(copy.deepcopy(item))
        existing_ids.add(evidence_id)


def _ocr_summary_for_context(drawing_analysis: dict[str, Any]) -> dict[str, Any]:
    """Build OCR summary for context payload."""
    metadata = drawing_analysis.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("ocr_summary"), dict):
        return dict(metadata["ocr_summary"])
    return {
        "drawing_identity": drawing_analysis.get("drawing_identity", {}),
        "materials": _summary_items(drawing_analysis.get("materials", [])),
        "dimensions": _summary_items(drawing_analysis.get("dimensions", [])),
        "special_characteristics": _summary_items(
            drawing_analysis.get("special_characteristics", [])
        ),
        "technical_requirements": _summary_items(
            drawing_analysis.get("technical_requirements", [])
        ),
        "manufacturing_clues": _summary_items(
            drawing_analysis.get("manufacturing_clues", [])
        ),
    }
