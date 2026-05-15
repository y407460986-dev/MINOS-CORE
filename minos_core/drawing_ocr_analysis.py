"""Build drawing analysis bundles from OCR text evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from minos_core._text_utils import float_or_none

from .adapters.ocr import (
    CompositeOCRAdapter,
    OCRBlock,
    OCRPageText,
    OCRResult,
    PyMuPDFTextLayerOCRAdapter,
    RapidOCRPageAdapter,
)
from .drawing_analysis import DRAWING_ANALYSIS_SCHEMA_VERSION


LOW_CONFIDENCE_THRESHOLD = 0.75


@dataclass(frozen=True)
class _TextUnit:
    evidence_id: str
    page_number: int
    text: str
    confidence: float | None
    bbox: tuple[float, float, float, float] | None
    engine: str


@dataclass(frozen=True)
class _Hit:
    value: str
    evidence_refs: list[str]
    confidence: float | None
    raw_text: str


def analyze_drawing_with_ocr(
    *,
    source: Any,
    pages: list[Any],
    output_dir: str | Path,
    context: dict[str, Any] | None = None,
    ocr_engine: str = "auto",
    ocr_adapter: Any | None = None,
) -> dict[str, Any]:
    """Run OCR over the drawing source and return a drawing_analysis bundle.

    /// 1. Pick the configured OCR adapter: PDF text layer, RapidOCR, or auto.
    /// 2. Extract OCR page/block evidence from the original drawing bytes.
    /// 3. Convert OCR evidence into the same drawing_analysis contract used downstream.
    """

    del output_dir
    source_path = _source_path(source)
    source_ref = str(source_path or _source_ref(source))
    content = _source_bytes(source_path)
    adapter = ocr_adapter or _ocr_adapter_for_engine(ocr_engine)
    result = adapter.extract_text(source_ref, content)
    return build_drawing_analysis_bundle_from_ocr(pages, result, context)


def build_drawing_analysis_bundle_from_ocr(
    pages: list[Any],
    ocr_result: OCRResult,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a drawing_analysis_bundle from OCR pages and blocks.

    /// 1. Turn OCR pages/blocks into stable evidence records.
    /// 2. Extract conservative drawing fields from OCR text only.
    /// 3. Keep every OCR-derived item traceable and marked for confirmation.
    """

    context_payload = dict(context or {})
    evidence, extraction_units = _ocr_evidence_and_units(ocr_result)
    fallback_refs = _fallback_evidence_refs(evidence)
    text_units = extraction_units or _page_units_from_evidence(evidence)
    source_ref = str(ocr_result.source_ref or context_payload.get("source_ref", ""))
    filename_text = _filename_text(source_ref, pages)

    drawing_number = _drawing_number_hit(text_units, source_ref)
    part_name = _part_name_hit(text_units, source_ref, drawing_number.value)
    revision = _revision_hit(text_units, source_ref)

    materials = _material_items(text_units, fallback_refs)
    surface_treatments = _surface_treatment_items(text_units, fallback_refs)
    dimensions = _dimension_items(text_units, fallback_refs)
    tolerances = _tolerance_items(text_units, fallback_refs)
    special_characteristics = _special_characteristic_items(text_units, fallback_refs)
    technical_requirements = _requirement_items(
        text_units,
        fallback_refs,
        _TECHNICAL_REQUIREMENT_PATTERN,
        "technical_requirement",
    )
    inspection_requirements = _requirement_items(
        text_units,
        fallback_refs,
        _INSPECTION_REQUIREMENT_PATTERN,
        "inspection_requirement",
    )
    standard_references = _standard_reference_items(text_units, fallback_refs)
    manufacturing_clues = _manufacturing_clues(
        text_units,
        filename_text,
        fallback_refs,
        materials,
        surface_treatments,
        dimensions,
        inspection_requirements,
    )

    bundle = {
        "document_type": "drawing_analysis_bundle",
        "schema_version": DRAWING_ANALYSIS_SCHEMA_VERSION,
        "drawing_identity": _drawing_identity(
            drawing_number,
            part_name,
            revision,
            fallback_refs,
        ),
        "materials": materials,
        "surface_treatments": surface_treatments,
        "dimensions": dimensions,
        "tolerances": tolerances,
        "special_characteristics": special_characteristics,
        "technical_requirements": technical_requirements,
        "inspection_requirements": inspection_requirements,
        "manufacturing_clues": manufacturing_clues,
        "uncertainties": _uncertainty_items(
            drawing_number,
            part_name,
            revision,
            materials,
            manufacturing_clues,
            fallback_refs,
        ),
        "evidence": evidence,
        "metadata": {
            "ai_inferred": False,
            "source_stage": "drawing_ocr_analysis",
            "ocr": {
                "engine": _metadata_engine(ocr_result),
                "page_count": len(ocr_result.pages),
                "text_length": len(ocr_result.text),
                "source_ref": ocr_result.source_ref,
            },
            "drawing_page_evidence_refs": _drawing_page_refs(pages),
        },
    }
    if standard_references:
        bundle["standard_references"] = standard_references
    return bundle


def _ocr_adapter_for_engine(ocr_engine: str) -> Any:
    engine = str(ocr_engine or "auto").strip().lower()
    if engine == "auto":
        return CompositeOCRAdapter()
    if engine == "pdf_text":
        return PyMuPDFTextLayerOCRAdapter()
    if engine == "rapidocr":
        return RapidOCRPageAdapter()
    raise ValueError("ocr_engine must be one of: auto, pdf_text, rapidocr")


def _source_path(source: Any) -> Path | None:
    path_value = getattr(source, "path", None)
    if path_value is None and isinstance(source, dict):
        path_value = source.get("path")
    if path_value is None:
        return None
    path = Path(str(path_value))
    return path if path.exists() and path.is_file() else None


def _source_ref(source: Any) -> str:
    for attr in ("path", "source_ref", "file_name", "source_id"):
        value = getattr(source, attr, None)
        if value:
            return str(value)
    if isinstance(source, dict):
        for key in ("path", "source_ref", "file_name", "source_id"):
            value = source.get(key)
            if value:
                return str(value)
    return "drawing"


def _source_bytes(source_path: Path | None) -> bytes:
    if source_path is None:
        raise ValueError("OCR drawing analysis requires a readable drawing source path")
    return source_path.read_bytes()


def _ocr_evidence_and_units(ocr_result: OCRResult) -> tuple[list[dict[str, Any]], list[_TextUnit]]:
    evidence: list[dict[str, Any]] = []
    page_units: list[_TextUnit] = []
    block_units: list[_TextUnit] = []
    for page_index, page in enumerate(ocr_result.pages, start=1):
        page_id = f"ocr_page_{page_index:03d}"
        page_text = str(page.text or "").strip()
        page_confidence = page.confidence
        evidence.append(
            _evidence_record(
                evidence_id=page_id,
                source="ocr_page",
                content=page_text,
                page_number=page.page_number or page_index,
                confidence=page_confidence,
                bbox=page.bbox,
                engine=page.engine,
                source_ref=page.source_ref or ocr_result.source_ref,
            )
        )
        if page_text:
            page_units.append(
                _TextUnit(
                    evidence_id=page_id,
                    page_number=page.page_number or page_index,
                    text=page_text,
                    confidence=page_confidence,
                    bbox=page.bbox,
                    engine=page.engine,
                )
            )
        for block_index, block in enumerate(page.blocks, start=1):
            block_text = str(block.text or "").strip()
            if not block_text:
                continue
            block_id = f"{page_id}_block_{block_index:04d}"
            evidence.append(
                _evidence_record(
                    evidence_id=block_id,
                    source="ocr_block",
                    content=block_text,
                    page_number=page.page_number or page_index,
                    confidence=block.confidence,
                    bbox=block.bbox,
                    engine=block.engine or page.engine,
                    source_ref=block.source_ref or page.source_ref or ocr_result.source_ref,
                )
            )
            block_units.append(
                _TextUnit(
                    evidence_id=block_id,
                    page_number=page.page_number or page_index,
                    text=block_text,
                    confidence=block.confidence,
                    bbox=block.bbox,
                    engine=block.engine or page.engine,
                )
            )
    return evidence, _dedupe_text_units(block_units + page_units)


def _evidence_record(
    *,
    evidence_id: str,
    source: str,
    content: str,
    page_number: int,
    confidence: float | None,
    bbox: tuple[float, float, float, float] | None,
    engine: str,
    source_ref: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "evidence_id": evidence_id,
        "source": source,
        "content": content,
        "page_number": page_number,
        "confidence": _confidence_value(confidence),
        "engine": engine,
        "source_ref": source_ref,
        "ai_inferred": False,
        "ocr_inferred": True,
        "needs_confirmation": True,
    }
    if bbox is not None:
        record["bbox"] = list(bbox)
    return record


def _drawing_identity(
    drawing_number: _Hit,
    part_name: _Hit,
    revision: _Hit,
    fallback_refs: list[str],
) -> dict[str, Any]:
    field_refs = {
        "drawing_number": drawing_number.evidence_refs or fallback_refs,
        "part_name": part_name.evidence_refs or fallback_refs,
        "revision": revision.evidence_refs or fallback_refs,
    }
    identity_refs = _unique_strings(
        field_refs["drawing_number"],
        field_refs["part_name"],
        field_refs["revision"],
    )
    confidences = [
        hit.confidence
        for hit in (drawing_number, part_name, revision)
        if hit.confidence is not None
    ]
    return {
        "drawing_number": drawing_number.value,
        "part_name": part_name.value,
        "revision": revision.value,
        "evidence_refs": identity_refs or fallback_refs,
        "field_evidence_refs": field_refs,
        "confidence": min(confidences) if confidences else 0.7,
        "ai_inferred": False,
        "ocr_inferred": True,
        "needs_confirmation": True,
    }


def _drawing_number_hit(units: list[_TextUnit], source_ref: str) -> _Hit:
    hit = _first_regex_hit(
        units,
        (
            r"(?:drawing\s*(?:no\.?|number)|dwg\.?\s*no\.?|part\s*(?:no\.?|number)|图号|图纸编号|零件号|件号)\s*[:：#]?\s*([A-Z0-9][A-Z0-9_.\-/]{2,})",
        ),
    )
    if hit.value:
        return _clean_hit(hit)
    filename_value = _drawing_number_from_filename(source_ref)
    return _Hit(filename_value, _first_unit_ref(units), 0.62 if filename_value else None, source_ref)


def _part_name_hit(units: list[_TextUnit], source_ref: str, drawing_number: str) -> _Hit:
    hit = _first_regex_hit(
        units,
        (
            r"(?:part\s*name|drawing\s*name|名称|图名|零件名称|品名)\s*[:：#]?\s*([^\r\n]+)",
        ),
    )
    if hit.value:
        return _clean_hit(hit)
    title_line_hit = _unlabeled_title_part_name_hit(units, drawing_number)
    if title_line_hit.value:
        return title_line_hit
    filename_value = _part_name_from_filename(source_ref, drawing_number)
    return _Hit(filename_value, _first_unit_ref(units), 0.58 if filename_value else None, source_ref)


def _unlabeled_title_part_name_hit(
    units: list[_TextUnit],
    drawing_number: str,
) -> _Hit:
    for unit in _line_units(units):
        candidate = _part_name_candidate_from_title_line(unit.text, drawing_number)
        if not candidate:
            continue
        confidence = _confidence_value(unit.confidence)
        return _Hit(candidate, [unit.evidence_id], min(0.82, max(0.72, confidence)), unit.text)
    return _Hit("", [], None, "")


def _part_name_candidate_from_title_line(text: str, drawing_number: str) -> str:
    line = " ".join(str(text or "").split()).strip(" ,;，；")
    if not line or len(line) > 90:
        return ""
    if _TITLE_LINE_NOISE_PATTERN.search(line):
        return ""
    if not _PART_FAMILY_NAME_PATTERN.search(line):
        return ""
    candidate = line
    if drawing_number:
        candidate = re.sub(
            re.escape(drawing_number).replace("\\-", "[-_ ]"),
            "",
            candidate,
            flags=re.I,
        )
    candidate = re.sub(r"^[A-Z]{1,8}\d[A-Z0-9_.\-/]{4,}\s*", "", candidate, flags=re.I)
    candidate = re.sub(r"^\d{4,}[A-Z0-9_.\-/]*\s*", "", candidate, flags=re.I)
    candidate = _clean_field_value(candidate)
    if len(candidate) < 2 or not _PART_FAMILY_NAME_PATTERN.search(candidate):
        return ""
    return candidate


def _revision_hit(units: list[_TextUnit], source_ref: str) -> _Hit:
    hit = _first_regex_hit(
        units,
        (
            r"(?:rev(?:ision)?|version|版本|版次|更改标记)\s*[:：#]?\s*([A-Z0-9][A-Z0-9_.\-]{0,7})",
        ),
    )
    if hit.value:
        return _clean_hit(hit)
    filename_match = re.search(r"(?:rev|revision|版本|版次)[_\-\s]*([A-Z0-9]{1,6})", source_ref, re.I)
    value = filename_match.group(1) if filename_match else ""
    return _Hit(value, _first_unit_ref(units), 0.58 if value else None, source_ref)


def _material_items(units: list[_TextUnit], fallback_refs: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    labeled = _first_regex_hit(
        units,
        (r"(?:material|matl|材料)\s*[:：#]?\s*([^\r\n;,，；]+)",),
    )
    if labeled.value:
        items.append(
            _ocr_item(
                {"name": _clean_field_value(labeled.value), "source_text": labeled.raw_text},
                labeled.evidence_refs or fallback_refs,
                labeled.confidence,
            )
        )
    for hit in _regex_hits(units, (_MATERIAL_PATTERN.pattern,)):
        material = _clean_field_value(hit.value)
        if material and not _has_item_value(items, material):
            items.append(
                _ocr_item(
                    {"name": material, "source_text": hit.raw_text},
                    hit.evidence_refs or fallback_refs,
                    hit.confidence,
                )
            )
    return items[:5]


def _surface_treatment_items(
    units: list[_TextUnit], fallback_refs: list[str]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    labeled = _first_regex_hit(
        units,
        (
            r"(?:surface\s*(?:treatment|finish)|finish|coating|表面处理|表面|涂层)\s*[:：#]?\s*([^\r\n;,，；]+)",
        ),
    )
    if labeled.value:
        items.append(
            _ocr_item(
                {"name": _clean_field_value(labeled.value), "source_text": labeled.raw_text},
                labeled.evidence_refs or fallback_refs,
                labeled.confidence,
            )
        )
    for unit in _line_units(units):
        if _SURFACE_PATTERN.search(unit.text) and not _has_item_value(items, unit.text):
            items.append(
                _ocr_item(
                    {"name": _snippet(unit.text), "source_text": unit.text},
                    [unit.evidence_id],
                    unit.confidence,
                )
            )
    return items[:5]


def _dimension_items(units: list[_TextUnit], fallback_refs: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for unit in _line_units(units):
        if not _DIMENSION_PATTERN.search(unit.text):
            continue
        value = _first_match_text(_DIMENSION_VALUE_PATTERN, unit.text) or _snippet(unit.text)
        items.append(
            _ocr_item(
                {
                    "name": "OCR dimension/tolerance text",
                    "value": value,
                    "text": _snippet(unit.text),
                    "dimension_type": "ocr_text",
                },
                [unit.evidence_id] or fallback_refs,
                unit.confidence,
            )
        )
    return _dedupe_items(items, "text")[:20]


def _tolerance_items(units: list[_TextUnit], fallback_refs: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for unit in _line_units(units):
        if not _TOLERANCE_PATTERN.search(unit.text):
            continue
        items.append(
            _ocr_item(
                {"name": "OCR tolerance text", "value": _snippet(unit.text), "text": _snippet(unit.text)},
                [unit.evidence_id] or fallback_refs,
                unit.confidence,
            )
        )
    return _dedupe_items(items, "text")[:20]


def _special_characteristic_items(
    units: list[_TextUnit], fallback_refs: list[str]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, unit in enumerate(_line_units(units), start=1):
        if not _SPECIAL_CHARACTERISTIC_PATTERN.search(unit.text):
            continue
        items.append(
            _ocr_item(
                {
                    "id": f"OCR-SC-{index:03d}",
                    "name": _snippet(unit.text),
                    "classification": _special_classification(unit.text),
                    "specification": _snippet(unit.text),
                },
                [unit.evidence_id] or fallback_refs,
                unit.confidence,
            )
        )
    return _dedupe_items(items, "name")[:10]


def _requirement_items(
    units: list[_TextUnit],
    fallback_refs: list[str],
    pattern: re.Pattern[str],
    requirement_type: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for unit in _line_units(units):
        if not pattern.search(unit.text):
            continue
        items.append(
            _ocr_item(
                {"text": _snippet(unit.text), "requirement_type": requirement_type},
                [unit.evidence_id] or fallback_refs,
                unit.confidence,
            )
        )
    return _dedupe_items(items, "text")[:20]


def _standard_reference_items(
    units: list[_TextUnit], fallback_refs: list[str]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for unit in _line_units(units):
        matches = [match.group(0).strip() for match in _STANDARD_PATTERN.finditer(unit.text)]
        if not matches:
            continue
        for standard in matches:
            items.append(
                _ocr_item(
                    {"standard": standard, "text": _snippet(unit.text)},
                    [unit.evidence_id] or fallback_refs,
                    unit.confidence,
                )
            )
    return _dedupe_items(items, "standard")[:20]


def _manufacturing_clues(
    units: list[_TextUnit],
    filename_text: str,
    fallback_refs: list[str],
    materials: list[dict[str, Any]],
    surface_treatments: list[dict[str, Any]],
    dimensions: list[dict[str, Any]],
    inspection_requirements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    clues: list[dict[str, Any]] = []
    combined_text = " ".join([unit.text for unit in _line_units(units)] + [filename_text])
    for keywords, operation, reason in _MANUFACTURING_KEYWORDS:
        hit_unit = _first_unit_with_any_term(units, keywords)
        if hit_unit is None:
            continue
        clues.append(
            _manufacturing_clue(
                operation=operation,
                reason=reason,
                evidence_refs=[hit_unit.evidence_id],
                confidence=hit_unit.confidence,
                source="ocr_text",
            )
        )

    if clues:
        return _dedupe_items(clues, "operation")[:8]

    family_operation = _family_operation_from_text(combined_text)
    if family_operation:
        clues.append(
            _manufacturing_clue(
                operation=family_operation,
                reason="OCR文本或文件名包含零件族线索，制造路线不足，先给出保守工艺线索供确认",
                evidence_refs=fallback_refs,
                confidence=0.66,
                source="ocr_part_family_hint",
            )
        )
        return clues

    if materials or surface_treatments or dimensions or inspection_requirements:
        clues.append(
            _manufacturing_clue(
                operation="process inspection",
                reason="OCR识别到材料、尺寸或检验要求，但制造工序线索不足，先保守加入检验线索避免流程完全阻断",
                evidence_refs=fallback_refs,
                confidence=0.62,
                source="ocr_conservative_hint",
            )
        )
    return clues


def _manufacturing_clue(
    *,
    operation: str,
    reason: str,
    evidence_refs: list[str],
    confidence: float | None,
    source: str,
) -> dict[str, Any]:
    return _ocr_item(
        {
            "operation": operation,
            "process_function": f"根据OCR线索确认可能需要{operation}相关过程",
            "reasoning": reason,
            "source": source,
        },
        evidence_refs,
        confidence if confidence is not None else 0.66,
    )


def _uncertainty_items(
    drawing_number: _Hit,
    part_name: _Hit,
    revision: _Hit,
    materials: list[dict[str, Any]],
    manufacturing_clues: list[dict[str, Any]],
    fallback_refs: list[str],
) -> list[dict[str, Any]]:
    missing: list[str] = []
    if not drawing_number.value:
        missing.append("图号未能从OCR文本中稳定识别")
    if not part_name.value:
        missing.append("零件名称未能从OCR文本中稳定识别")
    if not revision.value:
        missing.append("版本未能从OCR文本中稳定识别")
    if not materials:
        missing.append("材料未能从OCR文本中稳定识别")
    if not manufacturing_clues:
        missing.append("制造工艺线索不足，需要工程确认")
    return [
        _ocr_item({"text": text, "uncertainty_type": "ocr_missing_or_low_signal"}, fallback_refs, 0.55)
        for text in missing
    ]


def _ocr_item(
    values: dict[str, Any],
    evidence_refs: list[str],
    confidence: float | None,
) -> dict[str, Any]:
    normalized = dict(values)
    normalized["confidence"] = _confidence_value(confidence)
    normalized["evidence_refs"] = _unique_strings(evidence_refs)
    normalized["ai_inferred"] = False
    normalized["ocr_inferred"] = True
    normalized["needs_confirmation"] = True
    return normalized


def _first_regex_hit(units: list[_TextUnit], patterns: tuple[str, ...]) -> _Hit:
    hits = _regex_hits(units, patterns)
    return hits[0] if hits else _Hit("", [], None, "")


def _regex_hits(units: list[_TextUnit], patterns: tuple[str, ...]) -> list[_Hit]:
    hits: list[_Hit] = []
    for unit in _line_units(units):
        for pattern in patterns:
            match = re.search(pattern, unit.text, re.I)
            if not match:
                continue
            value = match.group(1) if match.lastindex else match.group(0)
            cleaned = _clean_field_value(value)
            if cleaned:
                hits.append(_Hit(cleaned, [unit.evidence_id], unit.confidence, unit.text))
    return hits


def _line_units(units: list[_TextUnit]) -> list[_TextUnit]:
    lines: list[_TextUnit] = []
    for unit in units:
        raw_lines = [line.strip() for line in str(unit.text).splitlines() if line.strip()]
        if not raw_lines:
            continue
        for line in raw_lines:
            for segment in _split_semicolon_segments(line):
                if segment:
                    lines.append(
                        _TextUnit(
                            evidence_id=unit.evidence_id,
                            page_number=unit.page_number,
                            text=segment,
                            confidence=unit.confidence,
                            bbox=unit.bbox,
                            engine=unit.engine,
                        )
                    )
    return lines


def _page_units_from_evidence(evidence: list[dict[str, Any]]) -> list[_TextUnit]:
    units: list[_TextUnit] = []
    for item in evidence:
        text = str(item.get("content", "")).strip()
        if not text:
            continue
        units.append(
            _TextUnit(
                evidence_id=str(item.get("evidence_id", "")),
                page_number=int(item.get("page_number", 0) or 0),
                text=text,
                confidence=float_or_none(item.get("confidence")),
                bbox=None,
                engine=str(item.get("engine", "")),
            )
        )
    return units


def _dedupe_text_units(units: list[_TextUnit]) -> list[_TextUnit]:
    result: list[_TextUnit] = []
    seen: set[tuple[str, str]] = set()
    for unit in units:
        key = (unit.evidence_id, unit.text)
        if key in seen:
            continue
        result.append(unit)
        seen.add(key)
    return result


def _clean_hit(hit: _Hit) -> _Hit:
    return _Hit(
        _clean_field_value(hit.value),
        hit.evidence_refs,
        hit.confidence,
        hit.raw_text,
    )


def _clean_field_value(value: str) -> str:
    text = " ".join(str(value or "").strip().strip(":：#-").split())
    text = re.split(
        r"\s+(?=(?:drawing\s*no|dwg|part\s*no|part\s*name|rev|revision|version|material|surface|finish|图号|零件号|名称|版本|材料|表面处理)\s*[:：#]?)",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    return text.strip(" ,;，；")


def _drawing_number_from_filename(source_ref: str) -> str:
    stem = Path(str(source_ref)).stem
    matches = re.findall(r"[A-Z]{1,6}[-_ ]?\d[A-Z0-9_\-]*|\d{4,}[A-Z0-9_\-]*", stem.upper())
    if not matches:
        return ""
    return matches[0].replace("_", "-").replace(" ", "-")


def _part_name_from_filename(source_ref: str, drawing_number: str) -> str:
    stem = Path(str(source_ref)).stem
    if not stem:
        return ""
    value = stem
    if drawing_number:
        value = re.sub(re.escape(drawing_number).replace("\\-", "[-_ ]"), "", value, flags=re.I)
    value = re.sub(r"(?:rev|revision|版本|版次)[_\-\s]*[A-Z0-9]{1,6}", "", value, flags=re.I)
    value = re.sub(r"[_\-]+", " ", value)
    value = " ".join(value.split())
    if not value or re.fullmatch(r"[A-Z0-9_.\- ]+", value) and any(char.isdigit() for char in value):
        return ""
    return value


def _filename_text(source_ref: str, pages: list[Any]) -> str:
    values = [Path(str(source_ref)).stem]
    for page in pages:
        for attr in ("image_path", "source_ref", "file_name"):
            value = str(getattr(page, attr, "") or "")
            if value:
                values.append(Path(value).stem)
    return " ".join(values)


def _metadata_engine(ocr_result: OCRResult) -> str:
    engines: list[str] = []
    for page in ocr_result.pages:
        if page.engine:
            engines.append(page.engine)
        for block in page.blocks:
            if block.engine:
                engines.append(block.engine)
    unique = _unique_strings(engines)
    if not unique:
        return ""
    return unique[0] if len(unique) == 1 else "mixed"


def _drawing_page_refs(pages: list[Any]) -> list[str]:
    refs: list[str] = []
    for page in pages:
        ref = str(getattr(page, "evidence_id", "") or "").strip()
        if ref:
            refs.append(ref)
    return _unique_strings(refs)


def _fallback_evidence_refs(evidence: list[dict[str, Any]]) -> list[str]:
    refs = [
        str(item.get("evidence_id", "")).strip()
        for item in evidence
        if str(item.get("evidence_id", "")).strip()
    ]
    return refs[:1]


def _first_unit_ref(units: list[_TextUnit]) -> list[str]:
    return [units[0].evidence_id] if units else []


def _confidence_value(value: float | None) -> float:
    try:
        if value is None:
            return 0.7
        return round(max(0.0, min(1.0, float(value))), 3)
    except (TypeError, ValueError):
        return 0.7




def _split_semicolon_segments(line: str) -> list[str]:
    parts = re.split(r"[;；]\s*", line)
    return [part.strip() for part in parts if part.strip()]


def _first_match_text(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(0).strip() if match else ""


def _snippet(text: str) -> str:
    return " ".join(str(text).split())[:180]


def _has_item_value(items: list[dict[str, Any]], value: str) -> bool:
    needle = value.lower()
    for item in items:
        for key in ("name", "value", "text", "standard", "operation"):
            if str(item.get(key, "")).strip().lower() == needle:
                return True
    return False


def _dedupe_items(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        value = str(item.get(key, "")).strip().lower()
        if not value or value in seen:
            continue
        result.append(item)
        seen.add(value)
    return result


def _first_unit_with_any_term(
    units: list[_TextUnit], terms: tuple[str, ...]
) -> _TextUnit | None:
    for unit in _line_units(units):
        lowered = unit.text.lower()
        if any(term.lower() in lowered for term in terms):
            return unit
    return None


def _family_operation_from_text(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("hinge", "limiter", "assembly", "bracket assembly", "铰链", "限位器", "总成")):
        return "assembly"
    if any(term in lowered for term in ("bracket", "panel", "sheet", "spcc", "secc", "冲压", "钣金")):
        return "blanking"
    if any(term in lowered for term in ("shaft", "cnc", "machined", "turning", "milling", "轴", "机加工")):
        return "machining"
    if any(term in lowered for term in ("plastic", "resin", "mold", "注塑", "塑料")):
        return "injection molding"
    return ""


def _special_classification(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\bsc\b|特殊特性", lowered, re.I):
        return "SC"
    if re.search(r"\bcc\b|关键特性|critical", lowered, re.I):
        return "CC"
    if re.search(r"\bptc\b", lowered, re.I):
        return "PTC"
    return ""


def _unique_strings(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, (list, tuple, set)):
            candidates = list(value)
        else:
            candidates = []
        for item in candidates:
            text = str(item).strip()
            if text and text not in result:
                result.append(text)
    return result


_MATERIAL_PATTERN = re.compile(
    r"\b(?:SPCC|SECC|SGCC|DC01|SUS\s*\d{3}|SUS\d{3}|ADC12|AISI\s*\d{3,4}|"
    r"6061-T6|7075-T6|AL6061|Q235|45#|PA66|POM|ABS)\b",
    re.I,
)
_SURFACE_PATTERN = re.compile(
    r"(?:zinc|plating|plated|anodiz|coating|paint|powder|phosphate|e-coat|"
    r"镀锌|电镀|阳极|喷粉|喷涂|涂层|磷化|电泳|发黑)",
    re.I,
)
_DIMENSION_PATTERN = re.compile(
    r"(?:[ØΦ⌀]\s*\d|R\s*\d|M\d|\d+(?:\.\d+)?\s*(?:±|\+/-|\+\s*\d|- ?\d)|"
    r"\b\d+(?:\.\d+)?\s*mm\b|公差|tolerance|位置度|平面度|垂直度|同轴度)",
    re.I,
)
_DIMENSION_VALUE_PATTERN = re.compile(
    r"(?:[ØΦ⌀]\s*\d+(?:\.\d+)?|R\s*\d+(?:\.\d+)?|M\d+(?:x\d+(?:\.\d+)?)?|"
    r"\d+(?:\.\d+)?\s*(?:±|\+/-)\s*\d+(?:\.\d+)?)",
    re.I,
)
_TOLERANCE_PATTERN = re.compile(
    r"(?:±|\+/-|tolerance|公差|ISO\s*2768|GB/T\s*1804|未注公差|一般公差)",
    re.I,
)
_TECHNICAL_REQUIREMENT_PATTERN = re.compile(
    r"(?:technical\s*requirements?|notes?|no\s*burr|deburr|clean|sharp\s*edge|"
    r"heat\s*treat|hardness|技术要求|未注|毛刺|锐边|清洗|硬度|倒角|热处理)",
    re.I,
)
_INSPECTION_REQUIREMENT_PATTERN = re.compile(
    r"(?:inspection|inspect|check|gauge|cmm|检验|检测|检查|量具|检具|三坐标|全检|抽检)",
    re.I,
)
_STANDARD_PATTERN = re.compile(
    r"\b(?:ISO|GB/T|GB|DIN|JIS|ASTM|SAE|EN)\s*[A-Z0-9][A-Z0-9 ._/\-]*",
    re.I,
)
_SPECIAL_CHARACTERISTIC_PATTERN = re.compile(
    r"(?:\bSC\b|\bCC\b|\bKPC\b|\bPTC\b|special\s*characteristic|critical|"
    r"key\s*characteristic|特殊特性|关键特性|重要特性|安全特性)",
    re.I,
)
_PART_FAMILY_NAME_PATTERN = re.compile(
    r"(?:门铰链|车门铰链|尾门铰链|尾门较链|背门铰链|背门较链|较链总成|铰链总成|"
    r"door\s*hinge|back\s*door\s*hinge|tailgate\s*hinge|liftgate\s*hinge|"
    r"d[0o]{2}r\s+h[i1]mge|dh\s*assy|"
    r"限位器|限位总成|车门限位|door\s*check|door\s*checker|check\s*strap|"
    r"check\s*arm|limiter|travel\s*limiter|"
    r"冲压件|冲压成形件|钣金件|板金件|stamping|stamped\s*(?:part|component|bracket))",
    re.I,
)
_TITLE_LINE_NOISE_PATTERN = re.compile(
    r"(?:不可|不得|不能|要求|技术|毛刺|材料|检验|检查|尺寸|公差|表面处理|硬度|清洗|露出|"
    r"备注|note|inspection|material|tolerance|requirement)",
    re.I,
)
_MANUFACTURING_KEYWORDS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (
        ("stamping", "sheet metal", "blanking", "piercing", "冲压", "钣金", "落料", "冲孔"),
        "blanking",
        "OCR文本包含冲压/钣金制造线索",
    ),
    (
        ("bending", "forming", "折弯", "成形"),
        "forming",
        "OCR文本包含折弯/成形制造线索",
    ),
    (
        ("machining", "cnc", "turning", "milling", "drilling", "tapping", "机加工", "车削", "铣削", "钻孔", "攻丝"),
        "machining",
        "OCR文本包含机加工制造线索",
    ),
    (
        ("injection", "molded", "plastic", "resin", "注塑", "塑料", "树脂"),
        "injection molding",
        "OCR文本包含注塑制造线索",
    ),
    (
        ("assembly", "riveting", "rivet", "press fit", "welding", "装配", "铆接", "压装", "焊接"),
        "assembly",
        "OCR文本包含装配制造线索",
    ),
    (
        ("deburr", "no burr", "毛刺", "去毛刺"),
        "deburr",
        "OCR文本包含去毛刺要求",
    ),
    (
        ("surface treatment", "plating", "coating", "paint", "镀锌", "电镀", "喷涂", "表面处理"),
        "surface treatment",
        "OCR文本包含表面处理制造线索",
    ),
)
