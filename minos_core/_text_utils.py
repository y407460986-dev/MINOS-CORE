"""Shared text-coercion helpers used across the entire codebase.

Previously ~15 modules carried their own private copies of these functions
with slightly incompatible signatures and edge-case handling.  This module
provides the canonical implementations.
"""

from __future__ import annotations

from typing import Any, Mapping


def _coerce(value: Any) -> str:
    """Convert *value* to a stripped string, unwrapping ``{"value": ...}`` dicts."""
    if value is None:
        return ""
    if isinstance(value, dict):
        inner = value.get("value")
        if inner is not None:
            return str(inner).strip()
    return str(value).strip()


# ---------------------------------------------------------------------------
# Core text / string helpers
# ---------------------------------------------------------------------------

def text(*values: Any, default: str = "") -> str:
    """Return the first non-empty, non-None value converted to a string."""
    for value in values:
        s = _coerce(value)
        if s:
            return s
    return default


def row_text(row: Mapping[str, Any], *keys: str, default: str = "") -> str:
    """Look up *keys* in *row* in order; return the first non-empty match."""
    if not isinstance(row, Mapping):
        return default
    for key in keys:
        value = row.get(key)
        s = _coerce(value)
        if s:
            return s
    return default


def string_list(value: Any) -> list[str]:
    """Normalise a value into a list of non-empty, stripped strings."""
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    s = str(value).strip()
    return [s] if s else []


def bool_value(value: Any) -> bool:
    """Coerce *value* to ``bool``, treating common human-readable strings."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "是", "需复核"}
    return bool(value)


def integer(value: Any, default: int = 0) -> int:
    """Safely cast *value* to :class:`int`, falling back to *default*."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(value: Any, default: float = 0.0) -> float:
    """Safely cast *value* to :class:`float`, falling back to *default*."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def dedupe(items: list[Any]) -> list[Any]:
    """Return *items* with duplicates removed, preserving insertion order."""
    result: list[Any] = []
    seen: set[int] = set()
    for item in items:
        h = hash(repr(item))
        if h not in seen:
            seen.add(h)
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# Sequence helpers
# ---------------------------------------------------------------------------

def sequence_links(
    steps: list[Mapping[str, Any]],
    step_key: str = "id",
    *,
    link_type: str = "sequence",
    ai_inferred: bool = True,
) -> list[dict[str, Any]]:
    """Build rich ``from -> to`` links between consecutive steps.

    Returns links with ``link_type``, ``evidence_refs`` (merged from both
    neighbouring steps), ``ai_inferred``, and ``needs_confirmation`` so that
    quality-gate evaluators receive the full set of expected fields.
    """
    links: list[dict[str, Any]] = []
    for i in range(len(steps) - 1):
        current = steps[i]
        nxt = steps[i + 1]
        refs: list[str] = []
        for ref in current.get("evidence_refs", []) + nxt.get("evidence_refs", []):
            r = str(ref).strip()
            if r and r not in refs:
                refs.append(r)
        links.append(
            {
                "from": str(current.get(step_key, "")),
                "to": str(nxt.get(step_key, "")),
                "link_type": link_type,
                "evidence_refs": refs,
                "ai_inferred": ai_inferred,
                "needs_confirmation": bool(
                    current.get("needs_confirmation")
                    or nxt.get("needs_confirmation")
                ),
            }
        )
    return links
