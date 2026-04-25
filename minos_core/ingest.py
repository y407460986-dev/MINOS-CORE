"""Ingest raw inputs into Evidence bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters.fixture_json import load_fixture_payload, read_json_object
from .adapters.ocr import OCRAdapter
from .domain import Evidence


def ingest_evidence_bundle(
    source: str | Path | dict[str, Any],
    *,
    ocr_adapter: OCRAdapter | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    payload = _load_ingest_payload(source)
    if _looks_like_ocr_text(payload):
        return _bundle_from_ocr_text(payload)
    if ocr_adapter is not None and "content" in payload:
        return _bundle_from_ocr_adapter(payload, ocr_adapter, source_ref=source_ref)
    if "evidence" in payload:
        return _evidence_bundle(
            _normalize_evidence_rows(payload["evidence"]),
            ingest_mode=_detect_mode(payload),
            source_ref=str(source_ref or payload.get("source_ref", "")),
            metadata=payload.get("metadata")
            if isinstance(payload.get("metadata"), dict)
            else None,
        )
    if "content" in payload or "text" in payload:
        return _evidence_bundle(
            _normalize_evidence_rows([payload], default_source="manual"),
            ingest_mode="manual",
            source_ref=str(source_ref or payload.get("source_ref", "")),
        )
    raise ValueError("ingest input must contain evidence, content, text, or ocr_text")


def _load_ingest_payload(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(source, dict):
        payload = load_fixture_payload(source)
        return _input_package_ingest_payload(payload)
    path = Path(source)
    if path.is_dir() and (path / "input_package.json").exists():
        return _input_package_ingest_payload(load_fixture_payload(path))
    if (
        path.is_dir()
        and (path / "evidence.json").exists()
        and not (path / "process_flow.json").exists()
    ):
        payload = read_json_object(path / "evidence.json")
        return {"evidence": payload.get("evidence", []), "source_ref": str(path)}
    payload = load_fixture_payload(source)
    return _input_package_ingest_payload(payload)


def _input_package_ingest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("document_type") != "evidence_bundle":
        return payload
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict) or metadata.get("ingest_mode") != "input_package":
        return payload
    return {
        **payload,
        "source_ref": str(metadata.get("source_ref", "input_package")),
    }


def _looks_like_ocr_text(payload: dict[str, Any]) -> bool:
    return bool(payload.get("ocr_text"))


def _bundle_from_ocr_text(payload: dict[str, Any]) -> dict[str, Any]:
    source_ref = str(payload.get("source_ref", "ocr"))
    row = {
        "evidence_id": str(payload.get("evidence_id", "EV-OCR-001")),
        "source": f"ocr:{source_ref}",
        "content": str(payload.get("ocr_text", "")),
        "confidence": float(payload.get("confidence", 1.0) or 1.0),
        "ai_inferred": False,
        "needs_confirmation": bool(payload.get("needs_confirmation", False)),
    }
    return _evidence_bundle([row], ingest_mode="ocr_text", source_ref=source_ref)


def _bundle_from_ocr_adapter(
    payload: dict[str, Any],
    ocr_adapter: OCRAdapter,
    *,
    source_ref: str | None = None,
) -> dict[str, Any]:
    resolved_source_ref = str(source_ref or payload.get("source_ref", "ocr"))
    raw_content = payload.get("content", b"")
    if isinstance(raw_content, str):
        raw_content = raw_content.encode("utf-8")
    result = ocr_adapter.extract_text(resolved_source_ref, raw_content)
    rows = [
        {
            "evidence_id": f"EV-OCR-{page.page_number:03d}",
            "source": f"ocr:{result.source_ref}",
            "content": page.text,
            "confidence": page.confidence,
            "ai_inferred": False,
            "needs_confirmation": False,
        }
        for page in result.pages
    ]
    return _evidence_bundle(
        rows, ingest_mode="ocr_adapter", source_ref=result.source_ref
    )


def _normalize_evidence_rows(
    rows: Any,
    *,
    default_source: str = "",
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError("evidence must be a JSON array")
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError("evidence item must be a JSON object")
        evidence = Evidence.from_mapping(row)
        if not evidence.evidence_id:
            prefix = "EV-MANUAL" if default_source == "manual" else "EV-INGEST"
            evidence.evidence_id = f"{prefix}-{index:03d}"
        if not evidence.source:
            evidence.source = default_source
        normalized.append(evidence.__dict__)
    return normalized


def _evidence_bundle(
    evidence: list[dict[str, Any]],
    *,
    ingest_mode: str,
    source_ref: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bundle_metadata = {
        "ingest_mode": ingest_mode,
        "source_ref": source_ref,
    }
    if metadata:
        bundle_metadata.update(metadata)
    return {
        "document_type": "evidence_bundle",
        "schema_version": "0.1",
        "evidence": evidence,
        "metadata": bundle_metadata,
    }


def _detect_mode(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata", {})
    if isinstance(metadata, dict) and metadata.get("ingest_mode") == "input_package":
        return "input_package"
    if payload.get("document_type") == "evidence_bundle":
        return "evidence"
    if "process_flow" in payload or "pfmea" in payload or "control_plan" in payload:
        return "fixture"
    return "evidence"
