"""AI drawing recognition contract and quality gate."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, cast

from minos_core._text_utils import dedupe, float_or_none, string_list
from minos_core._types import DrawingAnalysisResult
from minos_core.special_characteristic_candidates import (
    confirmed_special_characteristics_from_candidates,
    normalize_special_characteristic_candidates,
    risks_from_special_characteristic_candidates,
)
from minos_core.special_characteristic_discovery import (
    build_special_characteristic_discovery_report,
    normalize_special_characteristic_locations,
)

from .audit import AuditItem, AuditReport
from .domain import APQPChain
from .drawing_input import DrawingPageEvidence
from .quality_gates import StageQualityGate
from .review_issues import review_issue_from_manual_item
from .validation import ChainValidationResult

DRAWING_ANALYSIS_SCHEMA_VERSION = "minos-core.drawing_analysis.v1"
MIN_REVIEW_CONFIDENCE = 0.75
DRAWING_PAGE_REF_PATTERN = re.compile(r"^drawing_page_\d{3}$")


class DrawingAnalysisError(ValueError):
    """Raised when drawing analysis output violates the contract.

    Indicates that the AI-generated or OCR-derived drawing analysis bundle
    failed validation checks, such as missing required fields, invalid JSON,
    or unrecognized evidence references.
    """


@dataclass(frozen=True)
class DrawingRecognitionGate:
    gate: StageQualityGate

    @property
    def can_continue(self) -> bool:
        """Whether the pipeline may proceed past this gate without human review.

        Returns:
            True if no blocking issues exist.
        """
        return self.gate.can_continue

    @property
    def needs_human_review(self) -> bool:
        """Whether this gate identified items requiring human review.

        Returns:
            True if any review-grade issue was flagged.
        """
        return self.gate.needs_human_review

    def model_dump(self) -> dict[str, Any]:
        """Serialize the gate to a dictionary.

        Returns:
            Dictionary representation of the underlying stage quality gate.
        """
        return self.gate.model_dump()


@dataclass(frozen=True)
class DrawingAnalysisBundle:
    payload: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        """Return the underlying payload dictionary.

        Returns:
            The raw analysis bundle dictionary.
        """
        return dict(self.payload)


def analyze_drawing_pages(
    pages: list[DrawingPageEvidence],
    analyzer: Any,
    context: dict[str, Any] | None = None,
) -> DrawingAnalysisResult:
    """Run a multimodal analyzer and return a validated drawing bundle.

    Args:
        pages: One or more drawing page evidence objects.
        analyzer: An object with an ``analyze_drawing_pages`` method that
            accepts pages and context, returning a result with ``content``.
        context: Optional dictionary of contextual parameters forwarded to the
            analyzer.

    Returns:
        A validated drawing analysis result dictionary.

    Raises:
        DrawingAnalysisError: If no pages are provided, the analyzer returns
            invalid JSON, or the JSON payload is not a dictionary.
    """

    if not pages:
        raise DrawingAnalysisError("drawing analysis requires at least one drawing page")
    result = analyzer.analyze_drawing_pages(pages, context or {})
    try:
        payload = _loads_model_json_object(result.content)
    except json.JSONDecodeError as exc:
        raise DrawingAnalysisError(f"AI drawing analysis returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DrawingAnalysisError("AI drawing analysis JSON must be an object")

    bundle = _normalize_drawing_analysis_payload(payload, pages, result)
    evaluate_drawing_recognition_gate(dict(bundle))
    return bundle


def _loads_model_json_object(content: str) -> Any:
    """Parse a JSON object from model output, retrying with bracket extraction on failure."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        extracted = _extract_json_object_text(content)
        if not extracted or extracted == content:
            raise
        return json.loads(extracted)


def _extract_json_object_text(content: str) -> str:
    """Extract the outermost JSON object from content, handling fences and leading text."""
    text = str(content or "").strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
            if depth < 0:
                return ""
    return ""


def evaluate_drawing_recognition_gate(
    bundle: dict[str, Any],
    stage: str = "drawing_analysis",
) -> StageQualityGate:
    """Evaluate whether drawing recognition can feed process-flow inference.

    Analyzes the drawing analysis bundle and produces a quality gate result
    that determines whether the pipeline may proceed.

    Args:
        bundle: The drawing analysis bundle dictionary.
        stage: Name of the pipeline stage (default "drawing_analysis").

    Returns:
        A StageQualityGate with validation results, audit items, coverage
        information and manual review items.
    """

    report = _drawing_analysis_report(bundle)
    validation = ChainValidationResult(
        ok=not report["blocking_items"],
        messages=list(report["blocking_items"]),
        chain=APQPChain(),
    )
    audit = AuditReport(counts={}, manual_review_items=[])
    manual_review_items = _drawing_manual_review_items(report)
    review_issues = [
        review_issue_from_manual_item(item, source="drawing_analysis")
        for item in manual_review_items
    ]
    return StageQualityGate(
        stage=stage,
        can_continue=bool(report["ok"]),
        allow_user_export=False,
        validation=validation,
        audit=audit,
        evidence_sufficient=not report["missing_refs"],
        pending_fields=list(report["pending_fields"]),
        ai_inferred_items=list(report["ai_inferred_items"]),
        manual_review_items=manual_review_items,
        evidence_coverage=report,
        missing_evidence_refs=list(report["missing_refs"]),
        uncovered_evidence_items=list(report["blocking_items"]),
        needs_confirmation_items=list(report["needs_confirmation_items"]),
        review_issues=review_issues,
    )


def _normalize_drawing_analysis_payload(
    payload: dict[str, Any],
    pages: list[DrawingPageEvidence],
    result: Any,
) -> DrawingAnalysisResult:
    """Normalize a raw AI drawing analysis payload into a validated bundle."""
    adapter_metadata = getattr(result, "metadata", {})
    evidence = [page.model_dump() for page in pages] + _visual_evidence_region_items(
        adapter_metadata
    )
    source_ids = {
        str(item.get("evidence_id", "")).strip()
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_id")
    }
    located_occurrences = normalize_special_characteristic_candidates(
        payload.get("located_occurrences", [])
    )
    special_characteristic_candidates = _dedupe_candidate_rows(
        normalize_special_characteristic_candidates(
            _list(payload.get("special_characteristic_candidates"))
            + _list(payload.get("located_occurrences"))
        )
    )
    special_characteristic_locations = normalize_special_characteristic_locations(
        _list(payload.get("special_characteristic_locations"))
        + _locations_from_located_occurrences(located_occurrences)
    )
    declared_totals = dict(_dict(payload.get("declared_totals")))
    discovery_report = build_special_characteristic_discovery_report(
        declared_totals=declared_totals,
        locations=special_characteristic_locations,
    )
    confirmed_specials = confirmed_special_characteristics_from_candidates(
        _directly_confirmable_special_characteristic_candidates(
            special_characteristic_candidates
        )
    )
    raw_special_characteristics = _normalize_analysis_items(payload.get("special_characteristics"))
    if _strict_candidate_special_characteristics(
        adapter_metadata,
        special_characteristic_candidates,
    ):
        raw_special_characteristics = [
            item
            for item in raw_special_characteristics
            if _confirmed_raw_special_characteristic(item)
        ]
    normalized: dict[str, Any] = {
        "document_type": "drawing_analysis_bundle",
        "schema_version": DRAWING_ANALYSIS_SCHEMA_VERSION,
        "drawing_identity": _dict(payload.get("drawing_identity")),
        "materials": _normalize_analysis_items(payload.get("materials")),
        "surface_treatments": _normalize_analysis_items(payload.get("surface_treatments")),
        "dimensions": _normalize_analysis_items(payload.get("dimensions")),
        "tolerances": _normalize_analysis_items(payload.get("tolerances")),
        "special_characteristics": raw_special_characteristics + confirmed_specials,
        "special_characteristic_candidates": special_characteristic_candidates,
        "located_occurrences": located_occurrences,
        "special_characteristic_judgments": _normalize_judgment_items(
            payload.get("special_characteristic_judgments")
        ),
        "declared_special_characteristics": _normalize_analysis_items(
            payload.get("declared_special_characteristics")
        ),
        "declared_totals": declared_totals,
        "special_characteristic_locations": special_characteristic_locations,
        "special_characteristic_discovery": {
            key: value
            for key, value in discovery_report.items()
            if key != "risks"
        },
        "technical_requirements": _normalize_analysis_items(payload.get("technical_requirements")),
        "inspection_requirements": _normalize_analysis_items(payload.get("inspection_requirements")),
        "manufacturing_clues": _normalize_analysis_items(payload.get("manufacturing_clues")),
        "uncertainties": _normalize_analysis_items(payload.get("uncertainties")),
        "focused_review_requests": _normalize_judgment_items(
            payload.get("focused_review_requests")
        ),
        "evidence": evidence,
        "metadata": {
            "model": getattr(result, "model", ""),
            "adapter_metadata": adapter_metadata,
            "ai_inferred": True,
            "source_stage": "drawing_analysis",
        },
    }
    candidate_risks = risks_from_special_characteristic_candidates(
        special_characteristic_candidates
    )
    if candidate_risks:
        normalized["metadata"]["drawing_analysis_risks"] = candidate_risks
    discovery_risks = [
        item for item in discovery_report.get("risks", []) if isinstance(item, dict)
    ]
    if discovery_risks:
        normalized["metadata"]["drawing_analysis_risks"] = _merge_drawing_risks(
            _list(normalized["metadata"].get("drawing_analysis_risks")),
            discovery_risks,
        )
    evidence_packet = _dict(payload.get("special_characteristic_evidence_packet"))
    if evidence_packet:
        normalized["special_characteristic_evidence_packet"] = evidence_packet
    evidence_ref_repairs = _repair_page_evidence_refs(normalized, source_ids)
    if evidence_ref_repairs:
        normalized["metadata"]["evidence_ref_repairs"] = evidence_ref_repairs
    _validate_all_refs_exist(normalized, source_ids)
    return cast(DrawingAnalysisResult, normalized)


def _visual_evidence_region_items(adapter_metadata: Any) -> list[dict[str, Any]]:
    """Convert adapter visual evidence regions into standard evidence items."""
    metadata = adapter_metadata if isinstance(adapter_metadata, dict) else {}
    regions = _list(metadata.get("visual_evidence_regions"))
    evidence_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for region in regions:
        if not isinstance(region, dict):
            continue
        region_id = str(region.get("region_id", "")).strip()
        if not region_id or region_id in seen:
            continue
        seen.add(region_id)
        evidence_items.append(
            {
                "evidence_id": region_id,
                "source": "visual_evidence_crop",
                "page_evidence_id": str(region.get("page_evidence_id", "")).strip(),
                "label": str(region.get("label", "")).strip(),
                "bbox": list(region.get("bbox", []))
                if isinstance(region.get("bbox"), list)
                else [],
                "image_path": str(region.get("image_path", "")).strip(),
                "evidence_refs": string_list(region.get("evidence_refs", [])),
            }
        )
    return evidence_items


def _drawing_analysis_report(bundle: dict[str, Any]) -> dict[str, Any]:
    """Build a structured quality report from the drawing analysis bundle."""
    evidence_ids = {
        str(item.get("evidence_id", "")).strip()
        for item in bundle.get("evidence", [])
        if isinstance(item, dict) and item.get("evidence_id")
    }
    missing_refs: list[str] = []
    pending_fields: list[str] = []
    needs_confirmation_items: list[str] = []
    ai_inferred_items: list[str] = []
    blocking_items: list[str] = []
    evidence_ref_repair_items: list[dict[str, Any]] = []
    confidence_parse_error_items: list[dict[str, Any]] = []
    drawing_risk_items = _drawing_risk_items(bundle)
    candidate_risks = risks_from_special_characteristic_candidates(
        normalize_special_characteristic_candidates(
            _list(bundle.get("special_characteristic_candidates"))
        )
    )
    if candidate_risks:
        drawing_risk_items = _merge_drawing_risks(drawing_risk_items, candidate_risks)

    identity = _dict(bundle.get("drawing_identity"))
    for field_name in ("part_name", "drawing_number", "revision"):
        if not str(identity.get(field_name, "")).strip():
            pending_fields.append(f"drawing_identity.{field_name}")

    for block_name in (
        "materials",
        "dimensions",
        "special_characteristics",
        "special_characteristic_candidates",
        "technical_requirements",
        "manufacturing_clues",
    ):
        items = _list(bundle.get(block_name))
        if not items and block_name in {"materials", "manufacturing_clues"}:
            pending_fields.append(block_name)
        for index, item in enumerate(items):
            label = _item_label(block_name, index, item)
            refs = string_list(item.get("evidence_refs") if isinstance(item, dict) else [])
            if not refs:
                missing_refs.append(f"{label}.evidence_refs")
            for ref in refs:
                if ref not in evidence_ids:
                    missing_refs.append(f"{label}.evidence_refs -> {ref}")
            confidence = _confidence(item)
            if confidence < MIN_REVIEW_CONFIDENCE:
                needs_confirmation_items.append(label)
            if isinstance(item, dict) and item.get("needs_confirmation"):
                needs_confirmation_items.append(label)
            if isinstance(item, dict):
                for error in _list(item.get("confidence_parse_errors")):
                    if isinstance(error, dict):
                        error_item = dict(error)
                        error_item.setdefault("label", label)
                        error_item.setdefault("block", block_name)
                        confidence_parse_error_items.append(error_item)
                for repair in _list(item.get("evidence_ref_repairs")):
                    if isinstance(repair, dict):
                        repair_item = dict(repair)
                        repair_item.setdefault("label", label)
                        evidence_ref_repair_items.append(repair_item)
            if isinstance(item, dict) and item.get("ai_inferred", True):
                ai_inferred_items.append(label)

    blocker_drawing_risks = [
        item for item in drawing_risk_items if item.get("severity") == "blocker"
    ]
    if missing_refs:
        blocking_items.extend(missing_refs)
    blocking_items.extend(
        str(item.get("item_id", ""))
        for item in blocker_drawing_risks
    )

    ok = bool(evidence_ids and not missing_refs and not blocker_drawing_risks and bundle.get("manufacturing_clues"))
    return {
        "stage_mode": "drawing_analysis",
        "next_stage": "infer_process_flow_from_drawing",
        "evidence_count": len(evidence_ids),
        "pending_fields": dedupe(pending_fields),
        "missing_refs": dedupe(missing_refs),
        "needs_confirmation_items": dedupe(needs_confirmation_items),
        "ai_inferred_items": dedupe(ai_inferred_items),
        "evidence_ref_repair_items": evidence_ref_repair_items,
        "confidence_parse_error_items": confidence_parse_error_items,
        "drawing_risk_items": drawing_risk_items,
        "blocking_items": dedupe(blocking_items),
        "ok": ok,
    }


def _validate_all_refs_exist(bundle: dict[str, Any], evidence_ids: set[str]) -> None:
    """Raise DrawingAnalysisError if any item references an unknown evidence ID."""
    for block_name in (
        "materials",
        "surface_treatments",
        "dimensions",
        "tolerances",
        "special_characteristics",
        "special_characteristic_candidates",
        "technical_requirements",
        "inspection_requirements",
        "manufacturing_clues",
        "uncertainties",
    ):
        for index, item in enumerate(bundle.get(block_name, [])):
            if not isinstance(item, dict):
                continue
            for ref in string_list(item.get("evidence_refs", [])):
                if ref not in evidence_ids:
                    if DRAWING_PAGE_REF_PATTERN.match(ref):
                        continue
                    raise DrawingAnalysisError(
                        f"{block_name}[{index}].evidence_refs references unknown evidence: {ref}"
                    )


def _drawing_manual_review_items(report: dict[str, Any]) -> list[AuditItem]:
    """Convert report risk and repair items into audit items for manual review."""
    items: list[AuditItem] = []
    for risk in report.get("drawing_risk_items", []):
        if not isinstance(risk, dict):
            continue
        items.append(
            AuditItem(
                str(risk.get("item_id", "")),
                str(risk.get("category", "drawing_analysis")),
                str(risk.get("message", "图纸识别风险需要人工复核。")),
                str(risk.get("severity", "review")),
            )
        )
    for repair in report.get("evidence_ref_repair_items", []):
        if not isinstance(repair, dict):
            continue
        items.append(
            AuditItem(
                str(repair.get("label", repair.get("block", "drawing_analysis"))),
                "drawing_evidence_ref_repaired",
                str(
                    repair.get(
                        "message",
                        "AI 引用了不存在的图纸页面证据，已标记为需要人工复核。",
                    )
                ),
                "review",
            )
        )
    for error in report.get("confidence_parse_error_items", []):
        if not isinstance(error, dict):
            continue
        items.append(
            AuditItem(
                str(error.get("label", error.get("path", "drawing_analysis"))),
                "drawing_confidence_parse_error",
                str(error.get("message", "图纸识别置信度无法解析，需要人工复核。")),
                "review",
            )
        )
    for value in report["blocking_items"]:
        if any(
            isinstance(risk, dict) and risk.get("item_id") == value
            for risk in report.get("drawing_risk_items", [])
        ):
            continue
        items.append(AuditItem(value, "drawing_recognition_blocker", "图纸识别缺少可追溯证据", "blocker"))
    for value in report["pending_fields"]:
        items.append(AuditItem(value, "drawing_recognition_pending", "图纸识别存在待补字段", "review"))
    for value in report["needs_confirmation_items"]:
        items.append(
            AuditItem(value, "drawing_recognition_low_confidence", "图纸识别置信度不足，需要人工复核", "review")
        )
    return items


def _dict(value: Any) -> dict[str, Any]:
    """Coerce a value to dict, returning an empty dict for non-dict values."""
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    """Coerce a value to list, returning an empty list for non-list values."""
    return value if isinstance(value, list) else []


def _drawing_risk_items(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect and deduplicate drawing analysis risk items from bundle metadata."""
    metadata = _dict(bundle.get("metadata"))
    risks = _list(metadata.get("drawing_analysis_risks")) + _list(
        metadata.get("ocr_identity_risks")
    )
    items: list[dict[str, Any]] = []
    indexes: dict[str, int] = {}
    for risk in risks:
        if not isinstance(risk, dict):
            continue
        risk_id = str(risk.get("risk_id", risk.get("item_id", ""))).strip()
        if not risk_id:
            continue
        item = dict(risk)
        item["item_id"] = risk_id
        item.setdefault("category", "drawing_analysis")
        item.setdefault("severity", "review")
        item.setdefault("message", "图纸识别风险需要人工复核。")
        if risk_id in indexes:
            existing_index = indexes[risk_id]
            if (
                item.get("severity") == "blocker"
                and items[existing_index].get("severity") != "blocker"
            ):
                items[existing_index] = item
            continue
        indexes[risk_id] = len(items)
        items.append(item)
    return items


def _merge_drawing_risks(
    existing: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge candidate risk items into existing, upgrading severity when applicable."""
    merged = list(existing)
    indexes = {
        str(item.get("risk_id", item.get("item_id", ""))).strip(): index
        for index, item in enumerate(merged)
        if isinstance(item, dict)
        and str(item.get("risk_id", item.get("item_id", ""))).strip()
    }
    for risk in candidates:
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


def _strict_candidate_special_characteristics(
    adapter_metadata: Any,
    candidates: list[dict[str, Any]],
) -> bool:
    """Determine whether to apply strict filtering based on visual source evidence."""
    metadata = adapter_metadata if isinstance(adapter_metadata, dict) else {}
    if _visual_candidate_source(metadata.get("source")):
        return True
    return any(
        _visual_candidate_source(candidate.get("source"))
        for candidate in candidates
        if isinstance(candidate, dict)
    )


def _visual_candidate_source(value: Any) -> bool:
    """Check whether a source string originates from a visual detection pipeline."""
    source = str(value or "").strip().lower()
    return source.startswith("gpt55_visual") or source in {
        "generic_visual",
        "visual",
        "visual_symbol",
        "visual_locator",
        "symbol_table_on_drawing",
    }


def _directly_confirmable_special_characteristic_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter candidates that can be confirmed directly (OCR text sourced)."""
    return [
        candidate
        for candidate in candidates
        if str(candidate.get("source", "")).strip() == "ocr_text"
    ]


def _dedupe_candidate_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate candidate rows by candidate_id or full item representation."""
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        key = candidate_id or repr(sorted(candidate.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _locations_from_located_occurrences(
    occurrences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert located occurrences with CC/SC classification into location items."""
    locations: list[dict[str, Any]] = []
    for item in occurrences:
        classification = str(item.get("candidate_type", "")).strip().upper()
        if classification not in {"CC", "SC"}:
            continue
        candidate_id = str(item.get("candidate_id", "")).strip()
        locations.append(
            {
                "location_id": candidate_id or "",
                "classification": classification,
                "linked_feature": item.get("linked_feature", ""),
                "symbol_text_or_shape": item.get("symbol_text_or_shape", ""),
                "bbox": item.get("symbol_bbox", []),
                "evidence_refs": string_list(item.get("evidence_refs", [])),
                "confidence": item.get("confidence", 0.0),
                "reasoning": item.get("reasoning", ""),
            }
        )
    return locations


def _confirmed_raw_special_characteristic(item: Any) -> bool:
    """Check whether a raw special characteristic item has a confirmed status."""
    if not isinstance(item, dict):
        return False
    return str(item.get("confirmation_status", "")).strip() in {
        "judge_confirmed",
        "rule_confirmed",
        "human_confirmed",
    }


def _normalize_judgment_items(value: Any) -> list[dict[str, Any]]:
    """Coerce a value into a list of dictionaries (judgment items)."""
    return [dict(item) for item in _list(value) if isinstance(item, dict)]


def _normalize_analysis_items(value: Any) -> list[Any]:
    """Normalize every item in a list through the single-item normalizer."""
    items = _list(value)
    return [_normalize_analysis_item(item) for item in items]


def _normalize_analysis_item(item: Any) -> Any:
    """Normalize a single analysis item: add evidence_regions, refs, confidence and confirmation."""
    if not isinstance(item, dict):
        return item
    normalized = dict(item)
    normalized["evidence_regions"] = _normalize_evidence_regions(
        normalized.get("evidence_regions", normalized.get("evidence_region"))
    )
    if "evidence_refs" not in normalized:
        refs = _collect_nested_refs(normalized)
        if refs:
            normalized["evidence_refs"] = refs
    if "confidence" not in normalized:
        confidence = _collect_nested_confidence(normalized)
        if confidence is not None:
            normalized["confidence"] = confidence
    confidence_errors = _collect_confidence_parse_errors(normalized)
    if confidence_errors:
        normalized["confidence_parse_errors"] = confidence_errors
        normalized["needs_confirmation"] = True
    if "needs_confirmation" not in normalized:
        normalized["needs_confirmation"] = _collect_nested_confirmation(normalized)
    return normalized


def _normalize_evidence_regions(value: Any) -> list[dict[str, Any]]:
    """Normalize a list of evidence region dicts into a consistent format."""
    regions = _list(value)
    normalized: list[dict[str, Any]] = []
    for index, region in enumerate(regions):
        if not isinstance(region, dict):
            continue
        evidence_ref = _optional_text(
            region.get("evidence_ref", region.get("evidence_id", region.get("source_ref", "")))
        )
        page_ref = _optional_text(region.get("page_ref", region.get("page", "")))
        if not evidence_ref and page_ref:
            evidence_ref = page_ref
        box = _normalize_region_box(
            region.get("bbox", region.get("bounding_box", region.get("boundingBox", region.get("region"))))
        )
        normalized.append(
            {
                "region_id": _optional_text(region.get("region_id", region.get("id", "")))
                or f"region_{index + 1:03d}",
                "evidence_ref": evidence_ref,
                "page_number": _positive_int(region.get("page_number", region.get("pageNumber"))),
                "box": box,
                "text": _optional_text(region.get("text", region.get("rawText", ""))),
                "confidence": float_or_none(region.get("confidence")),
            }
        )
    return normalized


def _normalize_region_box(value: Any) -> dict[str, float]:
    """Normalize a bounding box value (dict or list) into a standard {x, y, width, height} dict."""
    if isinstance(value, dict):
        left = float_or_none(value.get("x", value.get("left")))
        top = float_or_none(value.get("y", value.get("top")))
        width = float_or_none(value.get("width", value.get("w")))
        height = float_or_none(value.get("height", value.get("h")))
        if width is None and float_or_none(value.get("right")) is not None and left is not None:
            width = float(float_or_none(value.get("right")) or 0.0) - left
        if height is None and float_or_none(value.get("bottom")) is not None and top is not None:
            height = float(float_or_none(value.get("bottom")) or 0.0) - top
        return {
            "x": max(0.0, left or 0.0),
            "y": max(0.0, top or 0.0),
            "width": max(0.0, width or 0.0),
            "height": max(0.0, height or 0.0),
        }
    if isinstance(value, list) and len(value) >= 4:
        left = float_or_none(value[0]) or 0.0
        top = float_or_none(value[1]) or 0.0
        right_or_width = float_or_none(value[2]) or 0.0
        bottom_or_height = float_or_none(value[3]) or 0.0
        width = right_or_width - left if right_or_width > left else right_or_width
        height = bottom_or_height - top if bottom_or_height > top else bottom_or_height
        return {"x": max(0.0, left), "y": max(0.0, top), "width": max(0.0, width), "height": max(0.0, height)}
    return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}


def _repair_page_evidence_refs(
    bundle: dict[str, Any],
    evidence_ids: set[str],
) -> list[dict[str, Any]]:
    """Repair evidence refs that reference non-existent page evidence by substituting fallback IDs."""
    if not evidence_ids:
        return []
    repairs: list[dict[str, Any]] = []
    fallback_ref = sorted(evidence_ids)[0] if len(evidence_ids) == 1 else ""
    for block_name in (
        "materials",
        "surface_treatments",
        "dimensions",
        "tolerances",
        "special_characteristics",
        "special_characteristic_candidates",
        "technical_requirements",
        "inspection_requirements",
        "manufacturing_clues",
        "uncertainties",
    ):
        for index, item in enumerate(bundle.get(block_name, [])):
            if not isinstance(item, dict):
                continue
            refs = string_list(item.get("evidence_refs", []))
            unknown_refs = [ref for ref in refs if ref not in evidence_ids]
            repairable_refs = (
                unknown_refs
                if fallback_ref
                else [ref for ref in unknown_refs if DRAWING_PAGE_REF_PATTERN.match(ref)]
            )
            if not repairable_refs:
                continue
            repair = {
                "block": block_name,
                "index": index,
                "original_refs": list(refs),
                "unknown_refs": list(repairable_refs),
                "message": (
                    "AI 引用了不存在的图纸证据 "
                    + ", ".join(repairable_refs)
                    + "，需要人工确认。"
                ),
            }
            if fallback_ref:
                repaired_refs: list[str] = []
                for ref in refs:
                    normalized_ref = fallback_ref if ref in repairable_refs else ref
                    if normalized_ref and normalized_ref not in repaired_refs:
                        repaired_refs.append(normalized_ref)
                item["original_evidence_refs"] = list(refs)
                item["evidence_refs"] = repaired_refs
                repair["repaired_refs"] = list(repaired_refs)
                repair["message"] = (
                    "AI 引用了不存在的图纸证据 "
                    + ", ".join(repairable_refs)
                    + f"，当前输入只有一页，已临时归并到 {fallback_ref}，需要人工确认。"
                )
            item["needs_confirmation"] = True
            existing_repairs = item.get("evidence_ref_repairs")
            item["evidence_ref_repairs"] = (
                list(existing_repairs) if isinstance(existing_repairs, list) else []
            )
            item["evidence_ref_repairs"].append(repair)
            repairs.append(repair)
    return repairs


def _confidence(item: Any) -> float:
    """Extract the confidence value from an item dict, defaulting to 0.0."""
    if not isinstance(item, dict):
        return 0.0
    try:
        return float(item.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _collect_nested_refs(value: Any) -> list[str]:
    """Recursively collect all evidence_refs from a nested dict/list structure."""
    refs: list[str] = []
    if isinstance(value, dict):
        direct = value.get("evidence_refs")
        if direct is not None:
            for ref in string_list(direct):
                if ref not in refs:
                    refs.append(ref)
        for nested in value.values():
            for ref in _collect_nested_refs(nested):
                if ref not in refs:
                    refs.append(ref)
    elif isinstance(value, list):
        for item in value:
            for ref in _collect_nested_refs(item):
                if ref not in refs:
                    refs.append(ref)
    return refs


def _collect_nested_confidence(value: Any) -> float | None:
    """Recursively find the minimum confidence value in a nested structure."""
    confidences: list[float] = []
    if isinstance(value, dict):
        direct = value.get("confidence")
        try:
            if direct is not None:
                confidences.append(float(direct))
        except (TypeError, ValueError):
            pass
        for nested in value.values():
            nested_confidence = _collect_nested_confidence(nested)
            if nested_confidence is not None:
                confidences.append(nested_confidence)
    elif isinstance(value, list):
        for item in value:
            nested_confidence = _collect_nested_confidence(item)
            if nested_confidence is not None:
                confidences.append(nested_confidence)
    if not confidences:
        return None
    return min(confidences)


def _collect_confidence_parse_errors(value: Any, path: str = "") -> list[dict[str, str]]:
    """Recursively collect confidence values that failed to parse as floats."""
    errors: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            next_path = f"{path}.{key}" if path else str(key)
            if key == "confidence" and nested not in {None, ""}:
                try:
                    float(nested)
                except (TypeError, ValueError):
                    errors.append(
                        {
                            "path": next_path,
                            "raw_value": repr(nested),
                            "message": f"图纸识别置信度无法解析: {next_path}={nested!r}",
                        }
                    )
            else:
                errors.extend(_collect_confidence_parse_errors(nested, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            next_path = f"{path}[{index}]" if path else f"[{index}]"
            errors.extend(_collect_confidence_parse_errors(item, next_path))
    return errors


def _collect_nested_confirmation(value: Any) -> bool:
    """Recursively check whether any nested item has needs_confirmation set to True."""
    if isinstance(value, dict):
        if bool(value.get("needs_confirmation")):
            return True
        return any(_collect_nested_confirmation(nested) for nested in value.values())
    if isinstance(value, list):
        return any(_collect_nested_confirmation(item) for item in value)
    return False


def _item_label(block_name: str, index: int, item: Any) -> str:
    """Build a human-readable label for an item within a block, using id/name if available."""
    if isinstance(item, dict):
        for key in ("id", "name", "characteristic_id", "clue_id", "requirement_id", "designation"):
            value = str(item.get(key, "")).strip()
            if value:
                return f"{block_name}:{value}"
    return f"{block_name}[{index}]"


def _optional_text(value: Any) -> str:
    """Return stripped text or empty string for None values."""
    if value is None:
        return ""
    return str(value).strip()


def _positive_int(value: Any) -> int:
    """Coerce a value to a non-negative integer, defaulting to 0."""
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


