"""Drawing analysis orchestration and mode selection."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from ..three_table_result import dedupe_strings as _dedupe_strings
from .utilities import (
    _positive_float_config,
    _non_negative_int_config,
    _readable_error,
    _readable_ocr_warning,
)
from .hybrid_fusion import (
    _attach_ocr_reference_metadata,
    _lock_hybrid_identity_from_ocr,
    _ocr_summary_for_context,
)
from .family_context import _part_family_context_from_drawing


# Analysis mode and OCR engine configuration
ANALYSIS_MODES = {"hybrid", "ocr_only", "vision_only"}
OCR_ENGINES = {"auto", "pdf_text", "rapidocr", "mineru"}
DEFAULT_OCR_ENGINE = "mineru"

# Hybrid vision runtime limits
HYBRID_VISION_TIMEOUT_SECONDS = 45.0
HYBRID_VISION_MAX_RETRIES = 0

# Warning messages
HYBRID_OCR_FALLBACK_WARNING = "AI 视觉识别未完成，当前结果基于 OCR，必须人工复核。"
OCR_UNAVAILABLE_WARNING = (
    "OCR 识别未完成：MINOS 预期由 minos_core.drawing_ocr_analysis 提供 "
    "analyze_drawing_with_ocr(...)。"
)


def analyze_drawing_for_three_table_chain(
    drawing_path: str | Path,
    output_dir: str | Path,
    context: dict[str, Any] | None = None,
    analysis_mode: str = "hybrid",
    ocr_engine: str = "auto",
    ocr_adapter: Any | None = None,
    *,
    analyzer: Any | None = None,
) -> dict[str, Any]:
    """Run only the drawing-recognition stage used by the staged chain."""

    from ..adapters.multimodal import OpenAIResponsesMultimodalDrawingAnalyzer
    from ..drawing_analysis import analyze_drawing_pages, evaluate_drawing_recognition_gate
    from ..drawing_input import load_drawing_source, render_drawing_pages

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    context_payload = dict(context or {})
    requested_ocr_engine = str(ocr_engine).strip().lower()
    active_analysis_mode = _effective_analysis_mode(analysis_mode, context_payload)
    active_ocr_engine = _effective_ocr_engine(ocr_engine, context_payload)
    context_payload["analysis_mode"] = active_analysis_mode
    context_payload["ocr_engine"] = active_ocr_engine
    pipeline_inputs = {
        "drawing_path": str(drawing_path),
        "context": context_payload,
        "analysis_mode": active_analysis_mode,
        "ocr_engine": active_ocr_engine,
    }

    source = load_drawing_source(drawing_path)
    pages = render_drawing_pages(source, target_dir / "pages")
    (
        drawing_analysis,
        analysis_warnings,
        analysis_source,
        analysis_errors,
    ) = _analyze_drawing_pages_for_mode(
        source,
        pages,
        target_dir,
        context_payload,
        analysis_mode=active_analysis_mode,
        ocr_engine=active_ocr_engine,
        ocr_adapter=ocr_adapter,
        analyzer=analyzer,
        default_analyzer_factory=OpenAIResponsesMultimodalDrawingAnalyzer,
        analyze_drawing_pages=analyze_drawing_pages,
    )
    _attach_analysis_metadata(
        drawing_analysis,
        analysis_mode=active_analysis_mode,
        requested_ocr_engine=requested_ocr_engine,
        ocr_engine=active_ocr_engine,
        analysis_source=analysis_source,
        warnings=analysis_warnings,
        errors=analysis_errors,
    )
    part_family_classification, family_context = _part_family_context_from_drawing(
        drawing_analysis
    )
    drawing_gate = evaluate_drawing_recognition_gate(drawing_analysis)
    return {
        "drawing_analysis": drawing_analysis,
        "context": context_payload,
        "analysis_mode": active_analysis_mode,
        "ocr_engine": active_ocr_engine,
        "warnings": analysis_warnings,
        "analysis_source": analysis_source,
        "analysis_errors": analysis_errors,
        "part_family_classification": part_family_classification,
        "family_context": family_context,
        "drawing_gate": drawing_gate,
        "pipeline_inputs": pipeline_inputs,
    }


def _analyze_drawing_pages_for_mode(
    source: Any,
    pages: list[Any],
    target_dir: Path,
    context_payload: dict[str, Any],
    *,
    analysis_mode: str,
    ocr_engine: str,
    ocr_adapter: Any | None,
    analyzer: Any | None,
    default_analyzer_factory: Any,
    analyze_drawing_pages: Any,
) -> tuple[dict[str, Any], list[str], str, list[dict[str, str]]]:
    """Analyze drawing pages using the specified mode (ocr_only, vision_only, or hybrid)."""
    warnings: list[str] = []
    errors: list[dict[str, str]] = []
    ocr_analysis: dict[str, Any] | None = None
    ocr_error: BaseException | None = None

    if analysis_mode in {"ocr_only", "hybrid"}:
        try:
            ocr_analysis = _run_ocr_drawing_analysis(
                source,
                pages,
                target_dir,
                context_payload,
                ocr_engine=ocr_engine,
                ocr_adapter=ocr_adapter,
            )
        except Exception as exc:  # noqa: BLE001 - OCR availability is mode-dependent.
            ocr_error = exc
            errors.append({"stage": "ocr", "message": _readable_error(exc)})
            if analysis_mode == "ocr_only":
                raise
            warnings.append(_readable_ocr_warning(exc, OCR_UNAVAILABLE_WARNING))
        else:
            context_payload["ocr_analysis_summary"] = _ocr_summary_for_context(
                ocr_analysis
            )

    if analysis_mode == "ocr_only":
        if ocr_analysis is None:
            raise RuntimeError("ocr_only 模式未得到 OCR 图纸分析结果。")
        return ocr_analysis, warnings, "ocr", errors

    active_analyzer = (
        analyzer if analyzer is not None else default_analyzer_factory()
    )
    if analysis_mode == "hybrid" and analyzer is None:
        _apply_hybrid_vision_runtime_limits(active_analyzer, context_payload)
    try:
        vision_analysis = analyze_drawing_pages(pages, active_analyzer, context_payload)
    except Exception as exc:  # noqa: BLE001 - hybrid must preserve a successful OCR draft.
        errors.append({"stage": "vision", "message": _readable_error(exc)})
        if analysis_mode == "hybrid" and ocr_analysis is not None:
            warnings = _dedupe_strings(
                warnings
                + [
                    HYBRID_OCR_FALLBACK_WARNING,
                    f"AI 视觉识别错误：{_readable_error(exc)}",
                ]
            )
            return ocr_analysis, warnings, "hybrid_ocr_fallback", errors
        raise

    if analysis_mode == "hybrid" and ocr_analysis is not None:
        _attach_ocr_reference_metadata(vision_analysis, ocr_analysis)
        _lock_hybrid_identity_from_ocr(vision_analysis, ocr_analysis)
        return vision_analysis, warnings, "hybrid_vision", errors
    return vision_analysis, warnings, "vision", errors


def _apply_hybrid_vision_runtime_limits(
    analyzer: Any,
    context_payload: dict[str, Any],
) -> None:
    """Keep hybrid vision bounded so a usable OCR draft can return."""

    timeout_seconds = _positive_float_config(
        context_payload.get(
            "hybrid_vision_timeout_seconds",
            context_payload.get("vision_timeout_seconds"),
        ),
        HYBRID_VISION_TIMEOUT_SECONDS,
        "hybrid_vision_timeout_seconds",
    )
    max_retries = _non_negative_int_config(
        context_payload.get(
            "hybrid_vision_max_retries",
            context_payload.get("vision_max_retries"),
        ),
        HYBRID_VISION_MAX_RETRIES,
        "hybrid_vision_max_retries",
    )
    if hasattr(analyzer, "timeout"):
        setattr(analyzer, "timeout", timeout_seconds)
    if hasattr(analyzer, "max_retries"):
        setattr(analyzer, "max_retries", max_retries)


def _effective_analysis_mode(
    analysis_mode: str,
    context_payload: dict[str, Any],
) -> str:
    """Determine effective analysis mode from input and context."""
    raw_value = (
        context_payload.get("analysis_mode")
        if analysis_mode == "hybrid"
        else analysis_mode
    )
    value = str(raw_value or analysis_mode).strip().lower()
    if value not in ANALYSIS_MODES:
        raise ValueError(
            "analysis_mode must be one of: hybrid, ocr_only, vision_only"
        )
    return value


def _effective_ocr_engine(
    ocr_engine: str,
    context_payload: dict[str, Any],
) -> str:
    """Determine effective OCR engine from input and context."""
    raw_value = ocr_engine if ocr_engine != "auto" else DEFAULT_OCR_ENGINE
    value = str(raw_value or DEFAULT_OCR_ENGINE).strip().lower()
    if value not in OCR_ENGINES:
        raise ValueError("ocr_engine must be one of: auto, pdf_text, rapidocr, mineru")
    if value == "auto":
        return DEFAULT_OCR_ENGINE
    return value


def _run_ocr_drawing_analysis(
    source: Any,
    pages: list[Any],
    target_dir: Path,
    context_payload: dict[str, Any],
    *,
    ocr_engine: str,
    ocr_adapter: Any | None,
) -> dict[str, Any]:
    """Run OCR-based drawing analysis."""
    try:
        module = importlib.import_module("minos_core.drawing_ocr_analysis")
    except ModuleNotFoundError as exc:
        if exc.name not in {"minos_core.drawing_ocr_analysis", "drawing_ocr_analysis"}:
            raise
        raise RuntimeError(OCR_UNAVAILABLE_WARNING) from exc

    analyzer = getattr(module, "analyze_drawing_with_ocr", None)
    if analyzer is None:
        raise RuntimeError(
            "OCR 接口未就绪：MINOS 预期 minos_core.drawing_ocr_analysis "
            "提供 analyze_drawing_with_ocr(source, pages, output_dir, context, "
            "ocr_engine, ocr_adapter)。"
        )

    result = analyzer(
        source=source,
        pages=pages,
        output_dir=target_dir / "ocr",
        context=context_payload,
        ocr_engine=ocr_engine,
        ocr_adapter=ocr_adapter,
    )
    if isinstance(result, tuple) and result:
        result = result[0]
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    if not isinstance(result, dict):
        raise RuntimeError("OCR 图纸分析结果必须是 dict。")
    return result


def _attach_analysis_metadata(
    drawing_analysis: dict[str, Any],
    *,
    analysis_mode: str,
    requested_ocr_engine: str,
    ocr_engine: str,
    analysis_source: str,
    warnings: list[str],
    errors: list[dict[str, str]],
) -> None:
    """Attach analysis metadata to drawing analysis result."""
    metadata = drawing_analysis.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        drawing_analysis["metadata"] = {}
        metadata = drawing_analysis["metadata"]
    metadata["analysis_mode"] = analysis_mode
    metadata["ocr_engine_requested"] = requested_ocr_engine
    metadata["ocr_engine"] = ocr_engine
    metadata["analysis_source"] = analysis_source
    if warnings:
        metadata["analysis_warnings"] = list(warnings)
    if errors:
        metadata["analysis_errors"] = list(errors)
