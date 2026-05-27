"""Utility functions for pipeline operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..adapters.fixture_json import load_fixture_payload, read_json_object
from ..run_manifest import build_run_manifest, write_run_manifest
from .._text_utils import string_list


def _as_dict(value: Any) -> dict[str, Any]:
    """Convert value to dict if it is one, otherwise return empty dict."""
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    """Clean and strip text value."""
    return str(value).strip() if value is not None else ""


def _float_value(value: Any, default: float = 0.0) -> float:
    """Convert value to float with fallback default."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _summary_items(value: Any, *, limit: int = 8) -> list[Any]:
    """Extract summary items from a list with limit."""
    if not isinstance(value, list):
        return []
    return value[:limit]


def _positive_float_config(raw_value: Any, default: float, name: str) -> float:
    """Parse and validate positive float configuration value."""
    if raw_value in (None, ""):
        return default
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _non_negative_int_config(raw_value: Any, default: int, name: str) -> int:
    """Parse and validate non-negative integer configuration value."""
    if raw_value in (None, ""):
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _readable_error(exc: BaseException) -> str:
    """Convert exception to readable error message."""
    message = str(exc).strip() or exc.__class__.__name__
    if "stream_read_error" in message:
        return f"AI 视觉识别中断，已保留 OCR 识别结果。详情：{message}"
    return message


def _readable_ocr_warning(exc: BaseException, ocr_unavailable_warning: str) -> str:
    """Convert OCR exception to readable warning message."""
    message = _readable_error(exc)
    if ocr_unavailable_warning in message:
        return ocr_unavailable_warning
    return f"OCR 识别未完成：{message}"


def _load_review_source_payload(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Load review source payload from various input formats."""
    payload = load_fixture_payload(source)
    document_type = payload.get("document_type")
    if document_type == "apqp_chain_draft_result":
        draft = payload.get("draft")
        if not isinstance(draft, dict):
            raise ValueError("apqp_chain_draft_result.draft must be a JSON object")
        return draft
    if document_type == "apqp_chain_review_result":
        patched_chain = payload.get("patched_chain")
        if not isinstance(patched_chain, dict):
            raise ValueError(
                "apqp_chain_review_result.patched_chain must be a JSON object"
            )
        return patched_chain
    return payload


def _load_review_patch_payload(review_patch: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Load review patch payload from file or dict."""
    if isinstance(review_patch, dict):
        return review_patch
    path = Path(review_patch)
    if path.is_dir():
        raise ValueError("review patch must be a JSON file, not a directory")
    return read_json_object(path)


def _write_json_file(output_path: str | Path, payload: dict[str, Any]) -> Path:
    """Write JSON payload to file."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return destination


def _write_manifest_file(
    manifest_output: str | Path,
    *,
    inputs: Any,
    outputs: Any,
    stage_results: Any,
    quality_gates: Any,
    review_confirmations: Any,
    artifacts: dict[str, Any],
    warnings: list[str],
) -> Path:
    """Write run manifest file."""
    manifest = build_run_manifest(
        inputs=inputs,
        outputs=outputs,
        stage_results=stage_results,
        quality_gates=quality_gates,
        review_confirmations=review_confirmations,
        artifacts=artifacts,
        warnings=warnings,
    )
    return write_run_manifest(manifest_output, manifest)


def _dump_json_value(value: Any) -> Any:
    """Dump value to JSON-serializable format."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return value


def _last_quality_gate(stage_results: list[Any]) -> Any | None:
    """Extract the last quality gate from stage results."""
    for result in reversed(stage_results):
        if getattr(result, "quality_gate", None) is not None:
            return result.quality_gate
    return None


def _build_chain(payload: dict[str, Any]) -> Any:
    """Build APQPChain domain object from payload."""
    from ..domain import APQPChain

    if hasattr(APQPChain, "model_validate"):
        return APQPChain.model_validate(payload)
    if hasattr(APQPChain, "parse_obj"):
        return APQPChain.parse_obj(payload)
    return APQPChain(**payload)


def _validate_chain(chain: Any) -> Any:
    """Validate APQPChain domain object."""
    from ..validation import validate_chain

    return validate_chain(chain)


def _default_output_path(fixture: str | Path | dict[str, Any], chain: Any) -> Path:
    """Determine default output path for export."""
    if isinstance(fixture, (str, Path)):
        return Path(fixture).with_suffix(".xlsx")
    slug = _chain_value(chain, "slug", "id", default="apqp_chain")
    return Path(f"{slug}.xlsx")


def _chain_value(chain: Any, *names: str, default: str) -> str:
    """Extract value from chain by trying multiple field names."""
    for name in names:
        if isinstance(chain, dict) and name in chain:
            return str(chain[name])
        if hasattr(chain, name):
            return str(getattr(chain, name))
    return default
