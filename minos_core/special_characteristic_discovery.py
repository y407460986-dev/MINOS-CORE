"""Count-bound special-characteristic visual discovery helpers."""

from __future__ import annotations

from typing import Any

from minos_core._text_utils import string_list, text


def normalize_special_characteristic_locations(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            continue
        classification = text(raw.get("classification")).upper()
        if classification not in {"CC", "SC"}:
            classification = "unknown"
        normalized.append(
            {
                "location_id": text(raw.get("location_id")) or f"SCL-{index:03d}",
                "classification": classification,
                "linked_feature": text(raw.get("linked_feature"), raw.get("name")),
                "symbol_text_or_shape": text(
                    raw.get("symbol_text_or_shape"), raw.get("symbol")
                ),
                "bbox": _bbox(raw.get("bbox", raw.get("symbol_bbox"))),
                "evidence_refs": string_list(raw.get("evidence_refs", [])),
                "confidence": _confidence(raw.get("confidence")),
                "reasoning": text(raw.get("reasoning"), raw.get("reasoning_summary")),
            }
        )
    return normalized


def build_special_characteristic_discovery_report(
    declared_totals: dict[str, Any],
    locations: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = {
        "CC": _count(declared_totals.get("CC")),
        "SC": _count(declared_totals.get("SC")),
    }
    found = {"CC": 0, "SC": 0}
    for item in locations:
        classification = text(item.get("classification")).upper()
        if classification in found and _has_real_location(item):
            found[classification] += 1
    missing = {
        classification: max(0, expected[classification] - found[classification])
        for classification in ("CC", "SC")
    }
    extra = {
        classification: max(0, found[classification] - expected[classification])
        for classification in ("CC", "SC")
    }
    return {
        "declared_totals": expected,
        "found_counts": found,
        "missing_counts": missing,
        "extra_counts": extra,
        "search_coverage": {
            classification: _coverage(found[classification], expected[classification])
            for classification in ("CC", "SC")
        },
        "risks": _risks(expected, found, missing, extra),
    }


def _risks(
    expected: dict[str, int],
    found: dict[str, int],
    missing: dict[str, int],
    extra: dict[str, int],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for classification in ("CC", "SC"):
        if missing[classification] > 0:
            risks.append(
                {
                    "risk_id": f"SC-DISCOVERY-MISSING-{classification}",
                    "item_id": f"SC-DISCOVERY-MISSING-{classification}",
                    "category": "special_characteristic_discovery",
                    "severity": "review",
                    "target": f"declared_totals.{classification}",
                    "message": (
                        f"图纸声明 {classification} 有 {expected[classification]} 个，"
                        f"当前只定位到 {found[classification]} 个。"
                    ),
                    "classification": classification,
                    "expected_count": expected[classification],
                    "found_count": found[classification],
                    "missing_count": missing[classification],
                }
            )
        if extra[classification] > 0:
            risks.append(
                {
                    "risk_id": f"SC-DISCOVERY-EXTRA-{classification}",
                    "item_id": f"SC-DISCOVERY-EXTRA-{classification}",
                    "category": "special_characteristic_discovery",
                    "severity": "review",
                    "target": f"special_characteristic_locations.{classification}",
                    "message": (
                        f"图纸声明 {classification} 有 {expected[classification]} 个，"
                        f"当前定位到 {found[classification]} 个，多出的候选需要复核。"
                    ),
                    "classification": classification,
                    "expected_count": expected[classification],
                    "found_count": found[classification],
                    "extra_count": extra[classification],
                }
            )
    return risks


def _bbox(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        return []
    result: list[float] = []
    for item in value:
        try:
            result.append(round(float(item), 4))
        except (TypeError, ValueError):
            return []
    return result


def _confidence(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 3)
    except (TypeError, ValueError):
        return 0.0


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _coverage(found: int, expected: int) -> float:
    if expected <= 0:
        return 1.0
    return round(min(1.0, found / expected), 3)


def _has_real_location(item: dict[str, Any]) -> bool:
    bbox = item.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    if not any(abs(_float_value(value)) > 0.0001 for value in bbox):
        return False
    combined = " ".join(
        text(item.get(key)).lower()
        for key in ("linked_feature", "symbol_text_or_shape", "reasoning")
    )
    negative_markers = (
        "未找到",
        "未发现",
        "无法定位",
        "没有找到",
        "not found",
        "not located",
    )
    return not any(marker in combined for marker in negative_markers)


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
