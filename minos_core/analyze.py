"""Analyze Evidence bundles into structured generation clues."""

from __future__ import annotations

import json
import re
from typing import Any

from .adapters.llm import LLMAdapter, LLMMessage
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
        if evidence.ai_inferred:
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


def analyze_evidence_bundle_with_ai(
    source: dict[str, Any],
    llm_adapter: LLMAdapter,
) -> dict[str, Any]:
    """Augment rule-based analysis with structured LLM candidate clues.

    AI output is treated as review-only signal. It must reference existing
    evidence and is always marked as inferred and needing confirmation.
    """

    analysis = analyze_evidence_bundle(source)
    ai_payload = _load_ai_analysis_payload(_call_ai_analyzer(analysis, llm_adapter))
    evidence_ids = {
        str(item.get("evidence_id", ""))
        for item in analysis.get("evidence", [])
        if isinstance(item, dict) and item.get("evidence_id")
    }
    ai_items: list[dict[str, Any]] = []

    for item in ai_payload["drawings"]:
        normalized = _ai_item(item, "drawing", evidence_ids)
        analysis["drawings"].append(normalized)
        ai_items.append(_ai_inferred_item("drawing", normalized))

    characteristic_ids = {
        str(item.get("characteristic_id", ""))
        for item in analysis.get("characteristics", [])
        if isinstance(item, dict)
    }
    for item in ai_payload["characteristics"]:
        normalized = _ai_item(item, "characteristic", evidence_ids)
        characteristic_id = str(normalized.get("characteristic_id", "")).strip()
        if characteristic_id and characteristic_id in characteristic_ids:
            continue
        if characteristic_id:
            characteristic_ids.add(characteristic_id)
        analysis["characteristics"].append(normalized)
        ai_items.append(_ai_inferred_item("characteristic", normalized))

    process_keys = {
        (
            str(item.get("process_step_id", "")),
            str(item.get("operation", "")),
            str(item.get("source_ref", "")),
        )
        for item in analysis.get("process_clues", [])
        if isinstance(item, dict)
    }
    for item in ai_payload["process_clues"]:
        normalized = _ai_item(item, "process_clue", evidence_ids)
        key = (
            str(normalized.get("process_step_id", "")),
            str(normalized.get("operation", "")),
            str(normalized.get("source_ref", "")),
        )
        if key in process_keys:
            continue
        process_keys.add(key)
        analysis["process_clues"].append(normalized)
        ai_items.append(_ai_inferred_item("process_clue", normalized))

    for item in ai_payload["pending_fields"]:
        normalized = _ai_pending_field(item, evidence_ids)
        analysis["pending_fields"].append(normalized)
        ai_items.append(_ai_inferred_item("pending_field", normalized))

    risks = []
    for item in ai_payload["risksAndUncertainties"]:
        normalized = _ai_risk_item(item, evidence_ids)
        risks.append(normalized)
        ai_items.append(_ai_inferred_item("risk", normalized))
    if risks:
        analysis.setdefault("risksAndUncertainties", []).extend(risks)

    analysis["ai_inferred_items"].extend(ai_items)
    analysis["metadata"] = {
        **analysis.get("metadata", {}),
        "analysis_mode": "keyword_rules_plus_ai",
        "llm_used": True,
        "llm_model": _text_value(ai_payload.get("_llm_model", "fake")),
        "llm_metadata": ai_payload.get("_llm_metadata", {}),
    }
    return analysis


def _call_ai_analyzer(
    analysis: dict[str, Any],
    llm_adapter: LLMAdapter,
) -> dict[str, Any]:
    evidence_summary = [
        {
            "evidence_id": item.get("evidence_id", ""),
            "source": item.get("source", ""),
            "content": item.get("content", ""),
        }
        for item in analysis.get("evidence", [])
        if isinstance(item, dict)
    ]
    result = llm_adapter.complete(
        [
            LLMMessage(
                role="system",
                content=(
                    "Return strict JSON with drawings, characteristics, "
                    "process_clues, pending_fields, and risksAndUncertainties only."
                ),
            ),
            LLMMessage(
                role="user",
                content=json.dumps(
                    {"evidence": evidence_summary}, ensure_ascii=False, indent=2
                ),
            ),
        ]
    )
    return {
        "content": result.content,
        "model": result.model,
        "metadata": result.metadata,
    }


def _load_ai_analysis_payload(result: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(str(result.get("content", "")))
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI analysis output must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("AI analysis output must be a JSON object")
    allowed = {
        "drawings",
        "characteristics",
        "process_clues",
        "pending_fields",
        "risksAndUncertainties",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"AI analysis output contains unsupported blocks: {unknown}")
    normalized = {}
    for key in allowed:
        value = payload.get(key, [])
        if not isinstance(value, list):
            raise ValueError(f"AI analysis block must be a list: {key}")
        normalized[key] = value
    normalized["_llm_model"] = result.get("model", "")
    normalized["_llm_metadata"] = result.get("metadata", {})
    return normalized


def _ai_item(
    item: Any,
    item_type: str,
    evidence_ids: set[str],
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"AI {item_type} item must be a JSON object")
    source_ref = _require_source_ref(item, item_type, evidence_ids)
    normalized = dict(item)
    normalized["source_ref"] = source_ref
    normalized["ai_inferred"] = True
    normalized["needs_confirmation"] = True
    normalized.setdefault("matched_terms", ["llm"])
    return normalized


def _ai_pending_field(
    item: Any,
    evidence_ids: set[str],
) -> dict[str, Any]:
    normalized = _ai_item(item, "pending_field", evidence_ids)
    if not str(normalized.get("field", "")).strip():
        raise ValueError("AI pending_field item requires field")
    normalized.setdefault("reason", "AI suggested field requires confirmation")
    return normalized


def _ai_risk_item(
    item: Any,
    evidence_ids: set[str],
) -> dict[str, Any]:
    normalized = _ai_item(item, "risk", evidence_ids)
    if not str(normalized.get("description", "")).strip():
        raise ValueError("AI risk item requires description")
    normalized.setdefault("type", "ai_uncertainty")
    return normalized


def _require_source_ref(
    item: dict[str, Any],
    item_type: str,
    evidence_ids: set[str],
) -> str:
    source_ref = str(item.get("source_ref", "")).strip()
    if not source_ref:
        evidence_refs = item.get("evidence_refs", [])
        if isinstance(evidence_refs, list) and evidence_refs:
            source_ref = str(evidence_refs[0]).strip()
    if not source_ref:
        raise ValueError(f"AI {item_type} item requires source_ref")
    if source_ref not in evidence_ids:
        raise ValueError(
            f"AI {item_type} item source_ref does not exist in evidence: {source_ref}"
        )
    return source_ref


def _ai_inferred_item(item_type: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": str(item.get("source_ref", "")),
        "source": "llm",
        "content": json.dumps(
            {"type": item_type, "item": item}, ensure_ascii=False, sort_keys=True
        ),
        "confidence": item.get("confidence"),
        "needs_confirmation": True,
        "ai_inferred": True,
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
    matched_pxx_operations: set[str] = set()
    matched_pxx_tokens: set[str] = set()
    for step_id, operation in PROCESS_STEP_RULES:
        if step_id.lower() in lower and operation in lower:
            matched_pxx_operations.add(operation)
            matched_pxx_tokens.update(operation.split())
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
        if operation in matched_pxx_operations:
            continue
        if operation in lower and not _phrase_is_covered_by_pxx(operation, matched_pxx_tokens):
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


def _phrase_is_covered_by_pxx(operation: str, matched_tokens: set[str]) -> bool:
    operation_tokens = set(operation.split())
    return bool(operation_tokens and operation_tokens.issubset(matched_tokens))


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


def _text_value(value: Any) -> str:
    return str(value or "").strip()
