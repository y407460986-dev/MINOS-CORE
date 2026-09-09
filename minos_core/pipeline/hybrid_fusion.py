"""Hybrid mode fusion logic for OCR and vision analysis."""

from __future__ import annotations

import copy
import os
from typing import Any

from .._text_utils import string_list
from ..three_table_result import dedupe_strings as _dedupe_strings
from .family_context import _ocr_family_lock_classification
from .utilities import _as_dict, _clean_text, _float_value, _summary_items

# OCR identity lock thresholds and fields
OCR_IDENTITY_LOCK_CONFIDENCE = 0.70
OCR_IDENTITY_LOCK_FIELDS = ("part_name", "drawing_number", "revision")
SUSPECT_OCR_TOKENS = ("D00R", "HIMGE")


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
        if ocr_part_name:
            _append_ocr_identity_risk(vision_analysis, ocr_identity, ocr_confidence)
        return
    if _has_suspect_ocr_token(ocr_identity):
        _append_ocr_identity_risk(vision_analysis, ocr_identity, ocr_confidence)

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


def _merge_special_characteristic_candidates(
    vision_analysis: dict[str, Any],
    ocr_analysis: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    special_characteristic_judge: Any | None = None,
) -> None:
    """Merge special characteristic candidates from vision, OCR, and judge."""
    from minos_core.special_characteristic_candidates import (
        confirmed_special_characteristics_from_candidates,
        normalize_special_characteristic_candidates,
        risks_from_special_characteristic_candidates,
    )

    _merge_declared_special_characteristics(vision_analysis, ocr_analysis, context)
    _merge_special_characteristic_discovery(vision_analysis)

    raw_candidates = list(vision_analysis.get("special_characteristic_candidates", []))
    located_occurrences = vision_analysis.get("located_occurrences")
    if isinstance(located_occurrences, list):
        raw_candidates.extend(
            copy.deepcopy(item)
            for item in located_occurrences
            if isinstance(item, dict)
        )
    for item in ocr_analysis.get("special_characteristics", []):
        if not isinstance(item, dict):
            continue
        classification = _clean_text(item.get("classification")).upper()
        if classification not in {"SC", "CC"}:
            continue
        raw_candidates.append(
            {
                "candidate_type": classification,
                "source": "ocr_text",
                "symbol_text_or_shape": classification,
                "linked_feature": _clean_text(
                    item.get("name")
                    or item.get("characteristic")
                    or item.get("description")
                ),
                "evidence_refs": string_list(item.get("evidence_refs", [])),
                "confidence": _float_value(item.get("confidence"), 0.0),
                "reasoning": "OCR 文本明确包含 SC/CC 标识。",
            }
        )
    candidates = _dedupe_special_characteristic_candidates(
        normalize_special_characteristic_candidates(raw_candidates)
    )
    vision_analysis["special_characteristic_candidates"] = candidates
    confirmed = confirmed_special_characteristics_from_candidates(
        _directly_confirmable_candidates(candidates)
    )
    if confirmed:
        existing = vision_analysis.setdefault("special_characteristics", [])
        if not isinstance(existing, list):
            existing = []
            vision_analysis["special_characteristics"] = existing
        seen = {
            str(item.get("source_candidate_id", item.get("id", ""))).strip()
            for item in existing
            if isinstance(item, dict)
        }
        for item in confirmed:
            candidate_id = str(item.get("source_candidate_id", "")).strip()
            if candidate_id and candidate_id not in seen:
                existing.append(item)
                seen.add(candidate_id)
    judge_confirmed_candidate_ids: set[str] = set()
    judge_payload = _special_characteristic_judge_payload(vision_analysis)
    if judge_payload:
        judge_confirmed_candidate_ids = _apply_special_characteristic_judgments(
            vision_analysis,
            judge_payload,
        )
    elif special_characteristic_judge is not None:
        judge_confirmed_candidate_ids = _run_special_characteristic_judge(
            vision_analysis,
            special_characteristic_judge,
        )
    elif _special_characteristic_judge_enabled(context):
        judge = _create_special_characteristic_judge(context)
        if judge is not None:
            judge_confirmed_candidate_ids = _run_special_characteristic_judge(
                vision_analysis,
                judge,
            )
    risks = risks_from_special_characteristic_candidates(candidates)
    if judge_confirmed_candidate_ids:
        risks = [
            risk
            for risk in risks
            if _risk_candidate_id(risk) not in judge_confirmed_candidate_ids
        ]
    if risks:
        metadata = vision_analysis.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["drawing_analysis_risks"] = _merge_risks(
                metadata.get("drawing_analysis_risks", []),
                risks,
            )


def _dedupe_special_characteristic_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove duplicate special characteristic candidates by ID or content."""
    seen: set[tuple[str, str] | tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = _clean_text(candidate.get("candidate_id"))
        if candidate_id:
            key: tuple[str, str] | tuple[str, str, str] = ("candidate_id", candidate_id)
        else:
            key = (
                "candidate_content",
                _clean_text(candidate.get("candidate_type")).upper(),
                _clean_text(candidate.get("linked_feature")),
            )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _merge_declared_special_characteristics(
    vision_analysis: dict[str, Any],
    ocr_analysis: dict[str, Any],
    context: dict[str, Any] | None,
) -> None:
    """Merge declared special characteristics from OCR and context into vision."""
    request = _special_characteristic_discovery_request(context)
    declared_totals = _best_declared_totals(
        ocr_analysis.get("declared_totals"),
        request.get("declared_totals"),
        vision_analysis.get("declared_totals"),
    )
    if declared_totals:
        vision_analysis["declared_totals"] = declared_totals
    declared_rows = _first_dict_list(
        ocr_analysis.get("declared_special_characteristics"),
        request.get("declared_special_characteristics"),
        vision_analysis.get("declared_special_characteristics"),
    )
    if declared_rows:
        vision_analysis["declared_special_characteristics"] = declared_rows


def _merge_special_characteristic_discovery(
    vision_analysis: dict[str, Any],
) -> None:
    """Build and merge the special characteristic discovery report into vision."""
    from minos_core.special_characteristic_discovery import (
        build_special_characteristic_discovery_report,
        normalize_special_characteristic_locations,
    )

    raw_locations = vision_analysis.get("special_characteristic_locations")
    locations = normalize_special_characteristic_locations(
        (raw_locations if isinstance(raw_locations, list) else [])
        + _locations_from_located_occurrences(vision_analysis.get("located_occurrences"))
    )
    locations = _dedupe_special_characteristic_locations(locations)
    vision_analysis["special_characteristic_locations"] = locations
    declared_totals = _as_dict(vision_analysis.get("declared_totals"))
    discovery_report = build_special_characteristic_discovery_report(
        declared_totals=dict(declared_totals),
        locations=locations,
    )
    vision_analysis["special_characteristic_discovery"] = {
        key: value
        for key, value in discovery_report.items()
        if key != "risks"
    }
    if not _has_declared_special_count(declared_totals):
        return
    discovery_risks = [
        dict(item) for item in discovery_report.get("risks", []) if isinstance(item, dict)
    ]
    if discovery_risks:
        metadata = vision_analysis.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["drawing_analysis_risks"] = _merge_risks(
                metadata.get("drawing_analysis_risks", []),
                discovery_risks,
            )


def _dedupe_special_characteristic_locations(
    locations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove duplicate locations, keeping the highest-quality entry per identity."""
    by_key: dict[tuple[Any, ...], int] = {}
    deduped: list[dict[str, Any]] = []
    for location in locations:
        key = _location_identity(location)
        existing_index = by_key.get(key)
        if existing_index is None:
            by_key[key] = len(deduped)
            deduped.append(location)
            continue
        if _location_quality(location) > _location_quality(deduped[existing_index]):
            deduped[existing_index] = location
    return deduped


def _location_identity(location: dict[str, Any]) -> tuple[Any, ...]:
    """Derive a unique identity key for a special characteristic location."""
    bbox = location.get("bbox")
    if isinstance(bbox, list) and bbox:
        return ("bbox", tuple(round(_float_value(value, 0.0), 4) for value in bbox))
    location_id = _clean_text(location.get("location_id"))
    if location_id:
        return ("location_id", location_id)
    return (
        "content",
        _clean_text(location.get("classification")).upper(),
        _clean_text(location.get("linked_feature")),
    )


def _location_quality(location: dict[str, Any]) -> tuple[int, int, float]:
    """Score a location by classification, linked feature, and confidence."""
    classification = _clean_text(location.get("classification")).upper()
    has_classification = 1 if classification in {"CC", "SC"} else 0
    has_linked_feature = 1 if _clean_text(location.get("linked_feature")) else 0
    return (
        has_classification,
        has_linked_feature,
        _float_value(location.get("confidence"), 0.0),
    )


def _special_characteristic_discovery_request(
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Extract the special characteristic discovery request from context."""
    if not isinstance(context, dict):
        return {}
    request = context.get("special_characteristic_discovery_request")
    return copy.deepcopy(request) if isinstance(request, dict) else {}


def _locations_from_located_occurrences(value: Any) -> list[dict[str, Any]]:
    """Convert located occurrences into special characteristic location entries."""
    rows = value if isinstance(value, list) else []
    locations: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        classification = _clean_text(item.get("candidate_type")).upper()
        if classification not in {"CC", "SC"}:
            continue
        candidate_id = _clean_text(item.get("candidate_id"))
        locations.append(
            {
                "location_id": candidate_id,
                "classification": classification,
                "linked_feature": _clean_text(item.get("linked_feature")),
                "symbol_text_or_shape": _clean_text(item.get("symbol_text_or_shape")),
                "bbox": item.get("symbol_bbox", []),
                "evidence_refs": string_list(item.get("evidence_refs", [])),
                "confidence": _float_value(item.get("confidence"), 0.0),
                "reasoning": _clean_text(item.get("reasoning")),
            }
        )
    return locations


def _first_dict(*values: Any) -> dict[str, Any]:
    """Return a deep copy of the first non-empty dict from a sequence."""
    for value in values:
        if isinstance(value, dict) and value:
            return copy.deepcopy(value)
    return {}


def _best_declared_totals(*values: Any) -> dict[str, Any]:
    """Select the best declared totals from multiple sources by taking maximums."""
    candidates = [copy.deepcopy(value) for value in values if isinstance(value, dict) and value]
    positive = [item for item in candidates if _has_declared_special_count(item)]
    if not positive:
        return candidates[0] if candidates else {}
    totals = {"CC": 0, "SC": 0}
    for item in positive:
        for classification in ("CC", "SC"):
            totals[classification] = max(
                totals[classification],
                _non_negative_count(item.get(classification)),
            )
    return totals


def _first_dict_list(*values: Any) -> list[dict[str, Any]]:
    """Return a deep-copied list of dicts from the first non-empty list source."""
    for value in values:
        if isinstance(value, list):
            rows = [copy.deepcopy(item) for item in value if isinstance(item, dict)]
            if rows:
                return rows
    return []


def _has_declared_special_count(declared_totals: dict[str, Any]) -> bool:
    """Check whether declared totals contain any positive SC/CC counts."""
    return any(_non_negative_count(declared_totals.get(key)) > 0 for key in ("CC", "SC"))


def _non_negative_count(value: Any) -> int:
    """Parse an integer count, clamping negative values to zero."""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _apply_special_characteristic_judgments(
    vision_analysis: dict[str, Any],
    judge_payload: dict[str, Any],
) -> set[str]:
    """Apply pre-computed judge payload to confirm or reject special characteristics."""
    from minos_core.special_characteristics_evidence import (
        build_special_characteristic_evidence_packet,
    )
    from minos_core.special_characteristics_judge import (
        normalize_special_characteristic_judgments,
        verify_special_characteristic_judgments,
    )

    packet = build_special_characteristic_evidence_packet(vision_analysis)
    normalized = normalize_special_characteristic_judgments(judge_payload)
    judgments = [dict(item) for item in normalized if isinstance(item, dict)]
    report = verify_special_characteristic_judgments(judgments, packet)
    vision_analysis["special_characteristic_judgments"] = judgments

    confirmed_candidate_ids: set[str] = set()
    existing = vision_analysis.setdefault("special_characteristics", [])
    if not isinstance(existing, list):
        existing = []
        vision_analysis["special_characteristics"] = existing
    seen_judgments = {
        _clean_text(item.get("source_judgment_id"))
        for item in existing
        if isinstance(item, dict)
    }
    seen_ids = {
        _clean_text(item.get("id"))
        for item in existing
        if isinstance(item, dict)
    }
    for item in report.get("confirmed", []):
        if not isinstance(item, dict):
            continue
        classification = _clean_text(item.get("classification")).upper()
        if classification not in {"SC", "CC"}:
            continue
        candidate_id = _clean_text(item.get("candidate_id"))
        judgment_id = _clean_text(item.get("judgment_id"))
        if judgment_id and judgment_id in seen_judgments:
            if candidate_id:
                confirmed_candidate_ids.add(candidate_id)
            continue
        characteristic_id = _judge_special_characteristic_id(
            candidate_id,
            classification,
            len(existing) + 1,
        )
        if characteristic_id in seen_ids:
            if candidate_id:
                confirmed_candidate_ids.add(candidate_id)
            continue
        existing.append(
            {
                "id": characteristic_id,
                "name": _clean_text(item.get("linked_feature")) or candidate_id,
                "classification": classification,
                "confidence": _float_value(item.get("confidence"), 0.0),
                "source_ref": ",".join(string_list(item.get("page_evidence_refs", []))),
                "evidence_refs": string_list(item.get("page_evidence_refs", [])),
                "confirmation_status": "judge_confirmed",
                "needs_confirmation": False,
                "source_candidate_id": candidate_id,
                "source_judgment_id": judgment_id,
                "reasoning": _clean_text(item.get("reasoning_summary")),
                "ai_inferred": True,
            }
        )
        seen_ids.add(characteristic_id)
        if judgment_id:
            seen_judgments.add(judgment_id)
        if candidate_id:
            confirmed_candidate_ids.add(candidate_id)

    risks = [dict(item) for item in report.get("risks", []) if isinstance(item, dict)]
    if risks:
        metadata = vision_analysis.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["drawing_analysis_risks"] = _merge_risks(
                metadata.get("drawing_analysis_risks", []),
                risks,
            )
    return confirmed_candidate_ids


def _run_special_characteristic_judge(
    vision_analysis: dict[str, Any],
    judge: Any,
) -> set[str]:
    """Run the special characteristic judge and apply its verdicts."""
    from minos_core.special_characteristics_evidence import (
        build_special_characteristic_evidence_packet,
    )

    packet = build_special_characteristic_evidence_packet(vision_analysis)
    vision_analysis["special_characteristic_evidence_packet"] = copy.deepcopy(packet)
    try:
        judge_payload = judge.judge(packet)
    except Exception as exc:  # noqa: BLE001 - keep drawing analysis usable for review.
        _append_special_characteristic_judge_risk(
            vision_analysis,
            f"特殊特性 AI 裁判未完成：{_clean_text(exc)}",
        )
        return set()
    return _apply_special_characteristic_judgments(vision_analysis, judge_payload)


def _directly_confirmable_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter candidates that were directly sourced from OCR text."""
    return [
        candidate
        for candidate in candidates
        if _clean_text(candidate.get("source")) == "ocr_text"
    ]


def _special_characteristic_judge_payload(
    vision_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Extract the special characteristic judge payload from vision analysis."""
    payload = vision_analysis.get("special_characteristic_judge_payload")
    if isinstance(payload, dict):
        return copy.deepcopy(payload)
    metadata = vision_analysis.get("metadata")
    if isinstance(metadata, dict):
        metadata_payload = metadata.get("special_characteristic_judge_payload")
        if isinstance(metadata_payload, dict):
            return copy.deepcopy(metadata_payload)
    judgments = vision_analysis.get("special_characteristic_judgments")
    if isinstance(judgments, list) and judgments:
        return {"special_characteristic_judgments": copy.deepcopy(judgments)}
    return {}


def _special_characteristic_judge_enabled(
    context: dict[str, Any] | None,
) -> bool:
    """Check whether the special characteristic judge is enabled in context or env."""
    raw = None
    if isinstance(context, dict):
        raw = context.get(
            "special_characteristic_judge_enabled",
            context.get("enable_special_characteristic_judge"),
        )
    if raw is not None:
        return _truthy(raw)
    env_value = os.getenv("MINOS_SPECIAL_CHARACTERISTIC_JUDGE")
    return _truthy(env_value) if env_value is not None else False


def _create_special_characteristic_judge(
    context: dict[str, Any] | None,
) -> Any | None:
    """Create a SpecialCharacteristicJudge instance from config and context."""
    from minos_core.ai_config import load_openai_responses_config
    from minos_core.special_characteristics_judge import SpecialCharacteristicJudge

    model = _clean_text(
        context.get("special_characteristic_judge_model") if isinstance(context, dict) else None
    )
    try:
        config = load_openai_responses_config()
    except Exception as exc:  # noqa: BLE001 - expose config issue as review risk.
        return _UnavailableSpecialCharacteristicJudge(
            f"特殊特性 AI 裁判配置不可用：{_clean_text(exc)}"
        )
    if not config.api_key_configured:
        return _UnavailableSpecialCharacteristicJudge(
            "特殊特性 AI 裁判未配置文本模型 API Key。"
        )
    return SpecialCharacteristicJudge(model=model or config.model)


class _UnavailableSpecialCharacteristicJudge:
    def __init__(self, message: str) -> None:
        """Store the error message for the runtime error."""
        self.message = message

    def judge(self, evidence_packet: dict[str, Any]) -> dict[str, Any]:
        """Raise a RuntimeError with the stored message."""
        raise RuntimeError(self.message)


def _truthy(value: Any) -> bool:
    """Coerce a value to boolean, treating \"1\", \"true\", \"yes\", \"on\" as True."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _append_special_characteristic_judge_risk(
    vision_analysis: dict[str, Any],
    message: str,
) -> None:
    """Append a special characteristic judge runtime risk to the analysis metadata."""
    metadata = vision_analysis.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        vision_analysis["metadata"] = metadata
    metadata["drawing_analysis_risks"] = _merge_risks(
        metadata.get("drawing_analysis_risks", []),
        [
            {
                "risk_id": "SC-JUDGE-RUNTIME",
                "item_id": "SC-JUDGE-RUNTIME",
                "category": "special_characteristic_judge",
                "severity": "review",
                "target": "special_characteristic_judgments",
                "message": message,
            }
        ],
    )


def _judge_special_characteristic_id(
    candidate_id: str,
    classification: str,
    index: int,
) -> str:
    """Derive a special characteristic ID from candidate or classification and index."""
    if candidate_id.startswith("MSC-"):
        return candidate_id.replace("MSC-", f"{classification}-", 1)
    return candidate_id or f"{classification}-{index:03d}"


def _risk_candidate_id(risk: dict[str, Any]) -> str:
    """Extract the candidate ID from a risk dictionary."""
    candidate = risk.get("candidate")
    if isinstance(candidate, dict):
        candidate_id = _clean_text(candidate.get("candidate_id"))
        if candidate_id:
            return candidate_id
    risk_id = _clean_text(risk.get("risk_id", risk.get("item_id")))
    prefix = "SC-CANDIDATE-"
    if risk_id.startswith(prefix):
        return risk_id[len(prefix) :]
    return ""


def _merge_ocr_manufacturing_clues_if_needed(
    vision_analysis: dict[str, Any],
    ocr_analysis: dict[str, Any],
) -> None:
    """Copy OCR manufacturing clues into vision analysis if none already present."""
    vision_clues = [
        item for item in vision_analysis.get("manufacturing_clues", [])
        if isinstance(item, dict)
    ] if isinstance(vision_analysis.get("manufacturing_clues"), list) else []
    if vision_clues:
        return
    ocr_clues = [
        copy.deepcopy(item) for item in ocr_analysis.get("manufacturing_clues", [])
        if isinstance(item, dict)
    ] if isinstance(ocr_analysis.get("manufacturing_clues"), list) else []
    if not ocr_clues:
        return
    for clue in ocr_clues:
        clue.setdefault("source", "ocr_text")
        clue["needs_confirmation"] = True
    vision_analysis["manufacturing_clues"] = ocr_clues
    metadata = vision_analysis.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["ocr_manufacturing_clues_used"] = True


def _append_ocr_identity_risk(
    vision_analysis: dict[str, Any],
    ocr_identity: dict[str, Any],
    confidence: float,
) -> None:
    """Append an OCR identity suspect risk to the analysis metadata."""
    metadata = vision_analysis.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        vision_analysis["metadata"] = metadata
    risks = metadata.setdefault("ocr_identity_risks", [])
    if not isinstance(risks, list):
        risks = []
        metadata["ocr_identity_risks"] = risks
    if any(
        isinstance(item, dict)
        and item.get("risk_id") == "DRAWING-IDENTITY-SUSPECT-OCR"
        for item in risks
    ):
        return
    risks.append(
        {
            "risk_id": "DRAWING-IDENTITY-SUSPECT-OCR",
            "category": "drawing_identity",
            "severity": "review",
            "target": "drawing_identity",
            "message": "图纸身份 OCR 疑似错误，正式输出前必须人工复核。",
            "confidence": round(confidence, 3),
            "ocr_identity": copy.deepcopy(ocr_identity),
        }
    )


def _merge_risks(existing: Any, incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge incoming risks into existing list, deduplicating by risk_id, upgrading severity."""
    merged = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
    indexes = {
        str(item.get("risk_id", item.get("item_id", ""))).strip(): index
        for index, item in enumerate(merged)
        if str(item.get("risk_id", item.get("item_id", ""))).strip()
    }
    for risk in incoming:
        risk_id = str(risk.get("risk_id", risk.get("item_id", ""))).strip()
        if not risk_id:
            continue
        if risk_id in indexes:
            index = indexes[risk_id]
            if (
                risk.get("severity") == "blocker"
                and merged[index].get("severity") != "blocker"
            ):
                merged[index] = risk
            continue
        indexes[risk_id] = len(merged)
        merged.append(risk)
    return merged


def _has_suspect_ocr_token(ocr_identity: dict[str, Any]) -> bool:
    """Check whether OCR identity fields contain known suspect tokens."""
    text = " ".join(
        _clean_text(ocr_identity.get(field_name))
        for field_name in OCR_IDENTITY_LOCK_FIELDS
    ).upper()
    return any(token in text for token in SUSPECT_OCR_TOKENS)


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
        summary = dict(metadata["ocr_summary"])
    else:
        summary = {
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
    summary["declared_special_characteristics"] = [
        dict(item)
        for item in drawing_analysis.get("declared_special_characteristics", [])
        if isinstance(item, dict)
    ]
    declared_totals = drawing_analysis.get("declared_totals")
    summary["declared_totals"] = (
        dict(declared_totals) if isinstance(declared_totals, dict) else {}
    )
    return summary
