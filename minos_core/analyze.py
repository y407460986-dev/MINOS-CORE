"""Analyze Evidence bundles into structured generation clues."""

from __future__ import annotations

import re
from typing import Any

from .domain import Evidence
from .ingest import ingest_evidence_bundle


DRAWING_TERMS = (
    "drawing",
    "engineering requirements",
    "drawing revision",
    "revision check",
    "released revision",
)


CHARACTERISTIC_RULES = (
    {
        "characteristic_id": "CHR-MATERIAL-THICKNESS",
        "name": "material thickness",
        "terms": ("material thickness", "thickness"),
        "spec_patterns": (
            r"(?:material\s+)?thickness\s+([0-9.]+\s*\+/-\s*[0-9.]+\s*mm)",
        ),
    },
    {
        "characteristic_id": "CHR-RIVET-HEIGHT",
        "name": "rivet height",
        "terms": ("rivet height",),
        "spec_patterns": (r"rivet\s+height\s+([0-9.]+\s*\+[0-9.]+/-[0-9.]+\s*mm)",),
    },
    {
        "characteristic_id": "CHR-PUSH-OUT-FORCE",
        "name": "push-out force",
        "terms": ("push-out force", "push out force"),
        "spec_patterns": (r"push[- ]out\s+force\s*(>=\s*[0-9.]+\s*kN)",),
    },
    {
        "characteristic_id": "CHR-TRACEABILITY-BARCODE",
        "name": "traceability barcode",
        "terms": ("traceability barcode", "barcode"),
        "spec_patterns": (),
    },
    {
        "characteristic_id": "CHR-PACK-QUANTITY",
        "name": "pack quantity",
        "terms": ("pack quantity",),
        "spec_patterns": (),
    },
    {
        "characteristic_id": "CHR-RELEASED-REVISION",
        "name": "released revision",
        "terms": ("released revision", "drawing revision"),
        "spec_patterns": (),
    },
)


PROCESS_STEP_RULES = (
    ("P10", "incoming material verification"),
    ("P20", "rivet assembly"),
    ("P30", "final inspection and pack"),
)

PROCESS_PHRASE_RULES = (
    "incoming inspection",
    "incoming material verification",
    "rivet assembly",
    "final inspection",
    "final inspection and pack",
    "press setup verification",
    "first-off approval",
    "digital thickness gauge measurement",
    "destructive push-out test",
    "barcode scan",
)


def analyze_evidence_bundle(source: dict[str, Any]) -> dict[str, Any]:
    bundle = (
        source
        if source.get("document_type") == "evidence_bundle"
        else ingest_evidence_bundle(source)
    )
    evidence_items = [
        Evidence.from_mapping(item) for item in bundle.get("evidence", [])
    ]
    drawings: list[dict[str, Any]] = []
    characteristics: dict[str, dict[str, Any]] = {}
    process_clues: dict[tuple[str, str, str], dict[str, Any]] = {}
    pending_fields: list[dict[str, str]] = []
    ai_inferred_items: list[dict[str, Any]] = []

    for evidence in evidence_items:
        source_ref = evidence.evidence_id
        content = evidence.content or ""
        text = f"{evidence.source} {content}"
        lower = text.lower()
        drawings.extend(_drawing_clues(evidence, lower, pending_fields))
        for characteristic in _characteristics(evidence, lower, content):
            characteristics.setdefault(
                characteristic["characteristic_id"], characteristic
            )
        for clue in _process_clues(evidence, lower):
            process_clues.setdefault(
                (clue["process_step_id"], clue["operation"], source_ref), clue
            )
        if evidence.ai_inferred or evidence.needs_confirmation:
            ai_inferred_items.append(
                {
                    "evidence_id": evidence.evidence_id,
                    "source": evidence.source,
                    "content": evidence.content,
                    "confidence": evidence.confidence,
                    "needs_confirmation": evidence.needs_confirmation,
                    "ai_inferred": evidence.ai_inferred,
                }
            )

    return {
        "document_type": "analysis_bundle",
        "schema_version": "0.1",
        "source_document_type": bundle.get("document_type", "evidence_bundle"),
        "evidence": [item.__dict__ for item in evidence_items],
        "drawings": drawings,
        "characteristics": list(characteristics.values()),
        "process_clues": list(process_clues.values()),
        "pending_fields": pending_fields,
        "ai_inferred_items": ai_inferred_items,
        "metadata": {
            "analysis_mode": "keyword_rules",
            "llm_used": False,
            "evidence_count": len(evidence_items),
        },
    }


def _drawing_clues(
    evidence: Evidence,
    lower: str,
    pending_fields: list[dict[str, str]],
) -> list[dict[str, Any]]:
    matched = [term for term in DRAWING_TERMS if term in lower]
    if not matched:
        return []
    drawing_id = _extract_drawing_id(evidence.content)
    revision = _extract_revision(evidence.content)
    if not drawing_id:
        pending_fields.append(
            {
                "field": "drawing_id",
                "reason": "drawing keyword found but no drawing number pattern was present",
                "source_ref": evidence.evidence_id,
            }
        )
    if any("revision" in term for term in matched) and not revision:
        pending_fields.append(
            {
                "field": "revision",
                "reason": "revision keyword found but no explicit revision value was present",
                "source_ref": evidence.evidence_id,
            }
        )
    return [
        {
            "drawing_id": drawing_id,
            "title": matched[0],
            "revision": revision,
            "source_ref": evidence.evidence_id,
            "matched_terms": matched,
        }
    ]


def _characteristics(
    evidence: Evidence, lower: str, content: str
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for rule in CHARACTERISTIC_RULES:
        matched_terms = [term for term in rule["terms"] if term in lower]
        if not matched_terms:
            continue
        results.append(
            {
                "characteristic_id": rule["characteristic_id"],
                "name": rule["name"],
                "classification": "",
                "specification": _extract_specification(content, rule["spec_patterns"]),
                "source_ref": evidence.evidence_id,
                "matched_terms": matched_terms,
            }
        )
    return results


def _process_clues(evidence: Evidence, lower: str) -> list[dict[str, Any]]:
    clues: list[dict[str, Any]] = []
    for step_id, operation in PROCESS_STEP_RULES:
        if step_id.lower() in lower and operation in lower:
            clues.append(
                {
                    "process_step_id": step_id,
                    "operation": operation,
                    "source_ref": evidence.evidence_id,
                    "matched_terms": [step_id, operation],
                    "confidence": evidence.confidence
                    if evidence.confidence is not None
                    else 1.0,
                }
            )
    for operation in PROCESS_PHRASE_RULES:
        if operation in lower:
            clues.append(
                {
                    "process_step_id": "",
                    "operation": operation,
                    "source_ref": evidence.evidence_id,
                    "matched_terms": [operation],
                    "confidence": evidence.confidence
                    if evidence.confidence is not None
                    else 1.0,
                }
            )
    return clues


def _extract_specification(content: str, patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        match = re.search(pattern, content, flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(1).split())
    return ""


def _extract_drawing_id(content: str) -> str:
    match = re.search(r"\b(DRW[-_ ]?[A-Z0-9-]+)\b", content, flags=re.IGNORECASE)
    return match.group(1).replace(" ", "-").upper() if match else ""


def _extract_revision(content: str) -> str:
    match = re.search(
        r"\b(?:rev|revision)\.?\s+([A-Z0-9]+)\b", content, flags=re.IGNORECASE
    )
    return match.group(1).upper() if match else ""
