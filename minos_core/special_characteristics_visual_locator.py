"""GPT5.5 special characteristic visual locator helpers."""

from __future__ import annotations

from typing import Any

from minos_core.special_characteristic_candidates import normalize_special_characteristic_candidates


class FakeGPT55VisualLocator:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def locate(self, evidence_packet: dict[str, Any]) -> dict[str, Any]:
        return dict(self.payload)


def normalize_visual_locator_result(payload: Any) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    missing = raw.get("missing_counts")
    missing_counts = missing if isinstance(missing, dict) else {}
    review_requests = raw.get("focused_review_requests")

    return {
        "located_occurrences": normalize_special_characteristic_candidates(
            raw.get("located_occurrences", [])
        ),
        "missing_counts": {
            "CC": _count(missing_counts.get("CC")),
            "SC": _count(missing_counts.get("SC")),
        },
        "focused_review_requests": [
            item for item in review_requests if isinstance(item, dict)
        ]
        if isinstance(review_requests, list)
        else [],
    }


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
