"""Evidence relevance scoring and filtering for traceability."""

from __future__ import annotations

from typing import Any


def filter_relevant_evidence_refs(
    evidence_refs: list[str],
    entity_text: str,
    available_evidence: list[dict[str, Any]],
    min_overlap: float = 0.1,
) -> list[str]:
    """Filter evidence refs to only those with minimum text overlap relevance.

    Tokenizes entity_text into character bigrams (works for Chinese and
    English) and computes token overlap with each referenced evidence item's
    content. Refs whose evidence text has overlap below *min_overlap* are
    dropped.

    Args:
        evidence_refs: Evidence IDs to filter (e.g. ``["EV-001", "EV-002"]``).
        entity_text: The text of the entity (failure mode, PFMEA row, etc.)
            whose relevance we are checking against.
        available_evidence: List of evidence dicts, each expected to contain
            at least ``evidence_id`` and ``content`` keys.
        min_overlap: Minimum Jaccard coefficient (0.0‑1.0) required to keep
            a reference. Default 0.1 is deliberately low — we only want to
            drop obviously irrelevant evidence.

    Returns:
        Filtered list of evidence reference strings. If every reference would
        be dropped, at least the first one is kept as a safety net.
    """
    if not evidence_refs:
        return []

    trimmed = entity_text.strip()
    if not trimmed:
        # No entity text to compare — keep everything conservatively.
        return list(evidence_refs)

    # Build O(1) lookup by evidence_id.
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for ev in available_evidence:
        ev_id = str(ev.get("evidence_id", "")).strip()
        if ev_id:
            evidence_by_id[ev_id] = ev

    entity_tokens = _tokenize(trimmed)
    if not entity_tokens:
        return list(evidence_refs)

    relevant: list[str] = []
    for ref in evidence_refs:
        evidence_item = evidence_by_id.get(ref)
        if evidence_item is None:
            # Reference not found in available evidence — keep (conservative).
            relevant.append(ref)
            continue

        content = str(evidence_item.get("content", "")).strip()
        if not content:
            # Evidence has no text content — keep (conservative).
            relevant.append(ref)
            continue

        content_tokens = _tokenize(content)
        if not content_tokens:
            relevant.append(ref)
            continue

        # Jaccard similarity: |intersection| / |union|
        overlap = len(entity_tokens & content_tokens) / max(
            len(entity_tokens | content_tokens), 1
        )
        if overlap >= min_overlap:
            relevant.append(ref)

    # Safety net: never return an empty list if the caller provided refs.
    if not relevant and evidence_refs:
        relevant.append(evidence_refs[0])

    return relevant


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Tokenize *text* into a set of character bigrams and single characters.

    Character bigrams work well for Chinese text (where words are not
    whitespace-separated) *and* for short English/technical text. Single
    characters provide an additional signal for very short content.
    """
    text = text.strip().lower()
    if not text:
        return set()

    tokens: set[str] = set()
    # Character bigrams
    for i in range(len(text) - 1):
        tokens.add(text[i : i + 2])
    # Single characters
    tokens.update(text)

    return tokens
