"""Special characteristic candidate normalization and confirmation rules."""

from __future__ import annotations

from typing import Any

from minos_core._text_utils import string_list, text

CONFIRMABLE_TYPES = {"SC", "CC"}
CONFIRMABLE_SOURCES = {"ocr_text"}
CONFIRMATION_CONFIDENCE = 0.85
EXPLICIT_CONFIRMATION_STATUSES = {"judge_confirmed", "human_confirmed"}


def normalize_special_characteristic_candidates(value: Any) -> list[dict[str, Any]]:
    """Normalize raw special characteristic candidates into a uniform structured format.

    Filters out non-dict items and assigns auto-generated IDs to candidates
    that lack one.

    Args:
        value: Raw candidates from AI output; may be a list of dicts or any type.

    Returns:
        A list of normalized candidate dicts, each with consistent key names and
        rule-based confirmation status resolved.
    """
    raw_items = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            continue
        normalized.append(_normalize_candidate(raw, index))
    return normalized


def confirmed_special_characteristics_from_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter candidates to those that are confirmed and build final characteristic entries.

    Only candidates passing the confirmation check are included. Each entry
    is enriched with resolved IDs, symbol info, and evidence references for
    downstream PFD/PFMEA integration.

    Args:
        candidates: Normalized candidate dicts from
            :func:`normalize_special_characteristic_candidates`.

    Returns:
        A list of confirmed characteristic dicts ready for the three-table output.
    """
    confirmed: list[dict[str, Any]] = []
    for candidate in candidates:
        if not _is_confirmed(candidate):
            continue
        candidate_type = text(candidate.get("candidate_type")).upper()
        candidate_id = text(candidate.get("candidate_id"))
        confirmed.append(
            {
                "id": _confirmed_characteristic_id(candidate_id, candidate_type),
                "name": text(candidate.get("linked_feature")),
                "classification": candidate_type,
                "symbol": text(candidate.get("symbol_text_or_shape")),
                "source_ref": ",".join(string_list(candidate.get("evidence_refs", []))),
                "evidence_refs": string_list(candidate.get("evidence_refs", [])),
                "evidence_regions": candidate.get("evidence_regions", []),
                "confidence": candidate.get("confidence", 0.0),
                "ai_inferred": True,
                "needs_confirmation": False,
                "confirmation_status": text(candidate.get("confirmation_status")),
                "source_candidate_id": candidate_id,
            }
        )
    return confirmed


def risks_from_special_characteristic_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate review-risk entries for unconfirmed special characteristic candidates.

    Unconfirmed candidates require human review before final output. These risk
    entries surface in quality-gate reports to flag items needing attention.

    Args:
        candidates: Normalized candidate dicts.

    Returns:
        A list of risk dicts, one per unconfirmed candidate with a valid ID.
    """
    risks: list[dict[str, Any]] = []
    for candidate in candidates:
        if _is_confirmed(candidate):
            continue
        candidate_id = text(candidate.get("candidate_id"))
        if not candidate_id:
            continue
        risks.append(
            {
                "risk_id": f"SC-CANDIDATE-{candidate_id}",
                "item_id": f"SC-CANDIDATE-{candidate_id}",
                "category": "special_characteristic_candidate",
                "severity": "review",
                "target": f"special_characteristic_candidates.{candidate_id}",
                "message": "图纸存在未确认的特殊特性候选，正式输出前必须人工确认。",
                "candidate": dict(candidate),
            }
        )
    return risks


def confirmed_special_characteristic_ids(registry: dict[str, Any]) -> set[str]:
    """Extract the set of confirmed special characteristic IDs from a registry.

    Scans the registry's items looking for entries classified as
    ``"special_characteristic"`` and collects their ``characteristic_id`` values.

    Args:
        registry: A dict with an ``"items"`` list of characteristic entries.

    Returns:
        A set of confirmed characteristic ID strings.
    """
    ids: set[str] = set()
    for item in registry.get("items", []):
        if not isinstance(item, dict):
            continue
        if text(item.get("classification")) == "special_characteristic":
            characteristic_id = text(item.get("characteristic_id"))
            if characteristic_id:
                ids.add(characteristic_id)
    return ids


def strip_unconfirmed_special_characteristic_refs(
    payload: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    """Remove references to unconfirmed special characteristics from process rows.

    Mutually compares the ``special_characteristics`` and
    ``source_special_characteristics`` fields in each process row against the
    confirmed IDs from the registry; any reference not in the confirmed set is
    dropped.

    Args:
        payload: A process-flow or PFMEA payload containing rows with
            characteristic reference fields.
        registry: Registry dict returned by the special characteristic store.

    Returns:
        The same payload dict (mutated in place) with unconfirmed refs stripped.
    """
    allowed = confirmed_special_characteristic_ids(registry)
    for row in _rows(payload):
        for field in ("special_characteristics", "source_special_characteristics"):
            if field not in row:
                continue
            refs = [ref for ref in string_list(row.get(field)) if ref in allowed]
            row[field] = refs
    return payload


def _normalize_candidate(raw: dict[str, Any], index: int) -> dict[str, Any]:
    """Normalize a single raw candidate dict into a standardised shape with resolved confirmation status."""
    candidate_type = _candidate_type(raw)
    candidate_id = text(raw.get("candidate_id"), raw.get("id")) or f"MSC-{index:03d}"
    evidence_refs = string_list(raw.get("evidence_refs", []))
    symbol_bbox = _bbox(raw.get("symbol_bbox", raw.get("bbox")))
    linked_feature_bbox = _bbox(raw.get("linked_feature_bbox"))
    confidence = _confidence(raw.get("confidence"))
    candidate = {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "source": text(raw.get("source")) or "unknown",
        "symbol_text_or_shape": text(
            raw.get("symbol_text_or_shape"),
            raw.get("symbol"),
            raw.get("marker"),
        ),
        "linked_feature": text(
            raw.get("linked_feature"),
            raw.get("feature"),
            raw.get("characteristic"),
        ),
        "symbol_bbox": symbol_bbox,
        "linked_feature_bbox": linked_feature_bbox,
        "evidence_refs": evidence_refs,
        "evidence_regions": _evidence_regions(raw, evidence_refs, symbol_bbox),
        "confidence": confidence,
        "needs_confirmation": bool(raw.get("needs_confirmation", False)),
        "reasoning": text(raw.get("reasoning"), raw.get("rationale")),
    }
    explicit_status = text(raw.get("confirmation_status"))
    if explicit_status in EXPLICIT_CONFIRMATION_STATUSES:
        candidate["confirmation_status"] = explicit_status
        candidate["needs_confirmation"] = False
    elif _can_rule_confirm(candidate):
        candidate["confirmation_status"] = "rule_confirmed"
        candidate["needs_confirmation"] = False
    else:
        candidate["confirmation_status"] = explicit_status or "needs_human_review"
        candidate["needs_confirmation"] = True
    return candidate


def _candidate_type(raw: dict[str, Any]) -> str:
    """Resolve SC/CC type from candidate keys and fallback inference."""
    candidate_type = text(
        raw.get("candidate_type"),
        raw.get("classification"),
        raw.get("type"),
        raw.get("special_characteristic_type"),
        raw.get("characteristic_type"),
    ).upper()
    if candidate_type in CONFIRMABLE_TYPES:
        return candidate_type
    inferred = _infer_candidate_type_from_text(raw)
    if inferred:
        return inferred
    if candidate_type == "UNKNOWN":
        return "unknown"
    return "unknown"


def _infer_candidate_type_from_text(raw: dict[str, Any]) -> str:
    """Infer SC/CC type from textual clues in symbol markers or reasoning fields."""
    value = " ".join(
        text(
            raw.get(key),
        )
        for key in (
            "symbol_text_or_shape",
            "symbol",
            "marker",
            "reasoning",
            "rationale",
        )
    ).upper()
    compact = value.replace(" ", "")
    if not compact:
        return ""
    if "SC" in compact or "安全特性" in compact:
        return "SC"
    if "CC" in compact or ("关键特性" in compact and "产品关键特性" not in compact):
        return "CC"
    return ""


def _can_rule_confirm(candidate: dict[str, Any]) -> bool:
    """Check if a candidate qualifies for automatic rule-based confirmation."""
    if candidate["candidate_type"] not in CONFIRMABLE_TYPES:
        return False
    if candidate["source"] not in CONFIRMABLE_SOURCES:
        return False
    if not candidate["evidence_refs"]:
        return False
    if not candidate["linked_feature"]:
        return False
    if candidate["confidence"] < CONFIRMATION_CONFIDENCE:
        return False
    return not (candidate["source"] != "ocr_text" and not _has_nonzero_bbox(candidate["symbol_bbox"]))


def _is_confirmed(candidate: dict[str, Any]) -> bool:
    """Return True if a candidate has a confirmable type and a finalised confirmation status."""
    if text(candidate.get("candidate_type")).upper() not in CONFIRMABLE_TYPES:
        return False
    if bool(candidate.get("needs_confirmation", False)):
        return False
    status = text(candidate.get("confirmation_status"))
    if status in EXPLICIT_CONFIRMATION_STATUSES:
        return True
    return status == "rule_confirmed" and text(candidate.get("source")) == "ocr_text"


def _confirmed_characteristic_id(candidate_id: str, candidate_type: str) -> str:
    """Build a final characteristic ID by replacing the auto-generated MSC- prefix with the type prefix."""
    if candidate_id.startswith("MSC-"):
        return candidate_id.replace("MSC-", f"{candidate_type}-", 1)
    return candidate_id or f"{candidate_type}-001"


def _bbox(value: Any) -> list[float]:
    """Normalise a bounding box value to a 4-element float list, defaulting to zeros."""
    if not isinstance(value, list) or len(value) < 4:
        return [0.0, 0.0, 0.0, 0.0]
    result: list[float] = []
    for item in value[:4]:
        try:
            result.append(max(0.0, float(item)))
        except (TypeError, ValueError):
            result.append(0.0)
    return result


def _has_nonzero_bbox(value: list[float]) -> bool:
    """Return True if the bounding box has positive width and height."""
    return len(value) >= 4 and value[2] > 0.0 and value[3] > 0.0


def _confidence(value: Any) -> float:
    """Clamp a confidence value to the [0.0, 1.0] range, defaulting to 0.0 on failure."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _evidence_regions(
    raw: dict[str, Any],
    evidence_refs: list[str],
    symbol_bbox: list[float],
) -> list[dict[str, Any]]:
    """Extract or synthesise evidence regions from the raw candidate."""
    regions = raw.get("evidence_regions")
    if isinstance(regions, list) and regions:
        return [region for region in regions if isinstance(region, dict)]
    if not evidence_refs:
        return []
    return [
        {
            "evidence_ref": evidence_refs[0],
            "bbox": symbol_bbox,
            "text": text(raw.get("symbol_text_or_shape"), raw.get("symbol")),
            "confidence": _confidence(raw.get("confidence")),
        }
    ]


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect all dict-valued rows from known list keys in a process payload."""
    rows: list[dict[str, Any]] = []
    for key in ("steps", "process_steps", "rows", "failure_modes", "controls"):
        values = payload.get(key, [])
        if isinstance(values, list):
            rows.extend(item for item in values if isinstance(item, dict))
    return rows
