"""Part family classification and knowledge context management."""

from __future__ import annotations

import copy
from typing import Any

from .._text_utils import string_list
from ..three_table_result import dedupe_strings as _dedupe_strings
from .utilities import _as_dict, _clean_text, _float_value


# OCR-based family lock confidence threshold
OCR_FAMILY_LOCK_CONFIDENCE = 0.78


def _part_family_context_from_drawing(
    drawing_analysis: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract part family classification and load knowledge context from drawing."""
    from ..part_family_classifier import classify_part_family
    from ..part_family_knowledge import load_part_family_knowledge

    classification = _locked_part_family_classification(drawing_analysis)
    if not classification:
        classification = classify_part_family(drawing_analysis)
    if not isinstance(classification, dict):
        classification = {}

    family_key = str(classification.get("family_key", "")).strip()
    if not family_key or family_key == "unknown":
        return classification, {}

    family_context = dict(classification)
    try:
        knowledge = load_part_family_knowledge(family_key)
    except (FileNotFoundError, KeyError, ValueError, ImportError) as exc:
        family_context["knowledge_load_error"] = str(exc)
        return classification, family_context

    if isinstance(knowledge, dict):
        family_context = _merge_family_context(classification, knowledge)
    return classification, family_context


def _locked_part_family_classification(
    drawing_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Extract locked part family classification from OCR metadata."""
    metadata = _as_dict(drawing_analysis.get("metadata"))
    classification = metadata.get("locked_part_family_classification")
    if not isinstance(classification, dict):
        lock = metadata.get("ocr_identity_lock")
        if isinstance(lock, dict):
            classification = lock.get("part_family_classification")
    if not isinstance(classification, dict):
        return {}
    family_key = _clean_text(classification.get("family_key"))
    confidence = _float_value(classification.get("confidence"), 0.0)
    if not family_key or family_key == "unknown":
        return {}
    if confidence < OCR_FAMILY_LOCK_CONFIDENCE:
        return {}
    locked = copy.deepcopy(classification)
    locked.setdefault("locked_by", "ocr_title_block")
    locked["needs_confirmation"] = False
    return locked


def _merge_family_context(
    classification: dict[str, Any],
    knowledge: dict[str, Any],
) -> dict[str, Any]:
    """Merge classification with knowledge base data."""
    merged = dict(classification)
    for key, value in knowledge.items():
        if key in {"knowledge_source_refs", "source_refs"}:
            continue
        if value not in ("", None, [], {}):
            merged[key] = value
    merged["knowledge_source_refs"] = _dedupe_strings(
        string_list(classification.get("knowledge_source_refs", []))
        + string_list(knowledge.get("knowledge_source_refs", []))
    )
    source_refs = knowledge.get("source_refs", [])
    if isinstance(source_refs, list):
        merged["source_refs"] = source_refs
    return merged


def _ocr_family_lock_classification(
    ocr_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Determine if OCR analysis provides a high-confidence family lock."""
    try:
        from ..part_family_classifier import classify_part_family
    except ImportError:
        return {}

    classification = classify_part_family(ocr_analysis)
    if not isinstance(classification, dict):
        return {}
    family_key = _clean_text(classification.get("family_key"))
    confidence = _float_value(classification.get("confidence"), 0.0)
    if not family_key or family_key == "unknown":
        return {}
    if confidence < OCR_FAMILY_LOCK_CONFIDENCE:
        return {}
    locked = copy.deepcopy(classification)
    locked["locked_by"] = "ocr_title_block"
    locked["needs_confirmation"] = False
    return locked
