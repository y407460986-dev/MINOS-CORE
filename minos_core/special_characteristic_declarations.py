"""Declared CC/SC count extraction from OCR/MinerU drawing text."""

from __future__ import annotations

import re
from typing import Any

from minos_core._text_utils import string_list, text

_FORMAL_CLASSIFICATIONS = {"CC", "SC"}
_DECLARATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "CC",
        re.compile(
            r"(?:关键特性|critical\s+characteristics?)[^\r\n;；]{0,40}?"
            r"(?<![A-Z0-9])CC(?![A-Z0-9])[^\r\n;；]{0,80}?"
            r"(?<![A-Z0-9])(\d{1,2})(?![A-Z0-9])",
            re.I,
        ),
    ),
    (
        "SC",
        re.compile(
            r"(?:重要特性|special\s+characteristics?)[^\r\n;；]{0,40}?"
            r"(?<![A-Z0-9])SC(?![A-Z0-9])[^\r\n;；]{0,80}?"
            r"(?<![A-Z0-9])(\d{1,2})(?![A-Z0-9])",
            re.I,
        ),
    ),
)


def extract_declared_special_characteristics(
    drawing_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Extract formally declared CC/SC counts from OCR/MinerU text evidence."""

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source in _text_sources(drawing_analysis):
        source_text = text(source.get("text"))
        if not source_text:
            continue
        for classification, expected_count in _declared_counts_from_text(source_text):
            if classification not in _FORMAL_CLASSIFICATIONS:
                continue
            key = (classification, source_text.lower())
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "declaration_id": f"SCD-{classification}-{len(rows) + 1:03d}",
                    "classification": classification,
                    "label": "关键特性" if classification == "CC" else "重要特性",
                    "expected_count": expected_count,
                    "source": text(source.get("source")) or "ocr_text",
                    "source_text": source_text,
                    "evidence_refs": string_list(source.get("evidence_refs", [])),
                    "confidence": _confidence(source.get("confidence")),
                }
            )
    return {"declared_counts": rows, "declared_totals": _totals(rows)}


def attach_declared_special_characteristics(
    drawing_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Attach declared CC/SC counts to an existing drawing analysis bundle."""

    result = extract_declared_special_characteristics(drawing_analysis)
    drawing_analysis["declared_special_characteristics"] = result["declared_counts"]
    drawing_analysis["declared_totals"] = result["declared_totals"]
    return drawing_analysis


def _text_sources(drawing_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for item in drawing_analysis.get("evidence", []):
        if not isinstance(item, dict):
            continue
        value = text(item.get("content"), item.get("text"))
        if value:
            sources.append(
                {
                    "text": value,
                    "source": text(item.get("source")) or "evidence",
                    "evidence_refs": [
                        text(item.get("evidence_id"), item.get("id")),
                    ],
                    "confidence": item.get("confidence"),
                }
            )

    for key in ("text_evidence", "technical_requirements", "inspection_requirements"):
        for item in drawing_analysis.get(key, []):
            if not isinstance(item, dict):
                continue
            value = text(
                item.get("content"),
                item.get("text"),
                item.get("description"),
                item.get("name"),
            )
            if value:
                sources.append(
                    {
                        "text": value,
                        "source": key,
                        "evidence_refs": string_list(item.get("evidence_refs", [])),
                        "confidence": item.get("confidence"),
                    }
                )
    return sources


def _declared_counts_from_text(value: str) -> list[tuple[str, int]]:
    matches: list[tuple[int, str, int]] = []
    for classification, pattern in _DECLARATION_PATTERNS:
        for match in pattern.finditer(value):
            matches.append((match.start(), classification, int(match.group(1))))
    matches.sort(key=lambda item: item[0])
    return [(classification, count) for _, classification, count in matches]


def _totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"CC": 0, "SC": 0}
    for row in rows:
        classification = text(row.get("classification")).upper()
        if classification in totals:
            totals[classification] = max(
                totals[classification],
                _int_value(row.get("expected_count")),
            )
    return totals


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _confidence(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 3)
    except (TypeError, ValueError):
        return 0.7
