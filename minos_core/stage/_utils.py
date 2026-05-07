"""Collection utilities: deduplication, text/list value extraction."""
from __future__ import annotations
from typing import Any


def _dedupe_mappings(values: list[Any]) -> list[Any]:
    return _dedupe_values(values)


def _dedupe_values(values: list[Any]) -> list[Any]:
    deduped: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = _dedupe_key(value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _dedupe_key(value: Any) -> str:
    if isinstance(value, dict):
        for key in (
            "evidence_id",
            "trace_link_id",
            "candidate_id",
            "pfmea_id",
            "control_plan_id",
            "process_step_id",
        ):
            text = str(value.get(key, "")).strip()
            if text:
                return f"{key}:{text}"
        from_id = str(value.get("from", value.get("from_id", ""))).strip()
        to_id = str(value.get("to", value.get("to_id", ""))).strip()
        link_type = str(value.get("link_type", "")).strip()
        if from_id or to_id or link_type:
            return f"link:{from_id}:{to_id}:{link_type}"
    return repr(value)


def _text_value(row: dict[str, Any], *field_names: str) -> str:
    for field_name in field_names:
        value = row.get(field_name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _list_value(row: dict[str, Any], field_name: str) -> list[Any]:
    value = row.get(field_name, [])
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    text = str(value).strip()
    return [text] if text else []
