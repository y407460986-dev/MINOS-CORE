"""Drawing analysis orchestration and mode selection."""

from __future__ import annotations

import copy
import importlib
from pathlib import Path
from typing import Any

from ..three_table_result import dedupe_strings as _dedupe_strings
from .family_context import _part_family_context_from_drawing
from .hybrid_fusion import (
    _attach_ocr_reference_metadata,
    _lock_hybrid_identity_from_ocr,
    _merge_ocr_manufacturing_clues_if_needed,
    _merge_special_characteristic_candidates,
    _ocr_summary_for_context,
)
from .utilities import (
    _non_negative_int_config,
    _positive_float_config,
    _readable_error,
    _readable_ocr_warning,
)

# Analysis mode and OCR engine configuration
ANALYSIS_MODES = {"hybrid", "ocr_only", "vision_only"}
OCR_ENGINES = {"auto", "pdf_text", "rapidocr", "mineru"}
DEFAULT_OCR_ENGINE = "mineru"

# Hybrid vision runtime limits
HYBRID_VISION_TIMEOUT_SECONDS = 120.0
HYBRID_VISION_MAX_RETRIES = 0
FOCUSED_SPECIAL_CHARACTERISTIC_TIMEOUT_SECONDS = 300.0
FOCUSED_SPECIAL_CHARACTERISTIC_MAX_RETRIES = 0
FOCUSED_SPECIAL_CHARACTERISTIC_REASONING_EFFORT = "medium"

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
    component_drawings: list[str | Path] | None = None,
    analyzer: Any | None = None,
) -> dict[str, Any]:
    """Run only the drawing-recognition stage used by the staged chain.

    Args:
        drawing_path: 总成图路径（必填）
        output_dir: 输出目录路径
        context: 可选的上下文信息字典
        analysis_mode: 分析模式，可选 "hybrid"、"ocr_only" 或 "vision_only"，默认为 "hybrid"
        ocr_engine: OCR 引擎，可选 "auto"、"pdf_text"、"rapidocr"、"mineru"，默认为 "auto"
        ocr_adapter: 可选的 OCR 适配器实例
        component_drawings: 子零件图纸路径列表（可选）
        analyzer: 可选的视觉分析器实例

    Returns:
        包含图纸分析结果、上下文、警告、错误等信息的字典
    """

    from ..adapters.multimodal import create_default_multimodal_drawing_analyzer
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
        "component_drawings": [str(p) for p in (component_drawings or [])],
        "context": context_payload,
        "analysis_mode": active_analysis_mode,
        "ocr_engine": active_ocr_engine,
    }

    source = load_drawing_source(drawing_path)
    pages = render_drawing_pages(source, target_dir / "pages")

    # Render component drawings and merge pages
    component_pages_label = ""
    if component_drawings:
        component_page_count = 0
        for comp_path in component_drawings:
            try:
                comp_source = load_drawing_source(comp_path)
                comp_rendered = render_drawing_pages(comp_source, target_dir / "pages")
                if comp_rendered:
                    component_page_count += len(comp_rendered)
                    pages.extend(comp_rendered)
            except Exception as exc:
                raise ValueError(f"无法加载子零件图纸 {comp_path}: {exc}") from exc
        if component_page_count > 0:
            component_pages_label = (
                f"第 {len(pages) - component_page_count + 1} 页起为 {len(component_drawings)} "
                f"个子零件的详细图纸（共 {component_page_count} 页）。"
            )
            context_payload["component_pages_label"] = component_pages_label
            context_payload["component_page_count"] = component_page_count
    context_payload["component_drawings"] = [str(p) for p in (component_drawings or [])]
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
        default_analyzer_factory=create_default_multimodal_drawing_analyzer,
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
            errors.append({"stage": "ocr", "message": _readable_error(exc)})
            if analysis_mode == "ocr_only":
                raise
            warnings.append(_readable_ocr_warning(exc, OCR_UNAVAILABLE_WARNING))
        else:
            context_payload["ocr_analysis_summary"] = _ocr_summary_for_context(
                dict(ocr_analysis)
            )
            context_payload["special_characteristic_discovery_request"] = {
                "declared_totals": dict(ocr_analysis.get("declared_totals", {})),
                "declared_special_characteristics": [
                    dict(item)
                    for item in ocr_analysis.get("declared_special_characteristics", [])
                    if isinstance(item, dict)
                ],
            }

    if analysis_mode == "ocr_only":
        if ocr_analysis is None:
            raise RuntimeError("ocr_only 模式未得到 OCR 图纸分析结果。")
        return ocr_analysis, warnings, "ocr", errors

    focused_special_analysis: dict[str, Any] | None = None
    if analysis_mode == "hybrid":
        try:
            focused_special_analysis = _run_focused_special_characteristic_visual_locator(
                pages,
                context_payload,
                analyzer=analyzer,
                default_analyzer_factory=default_analyzer_factory,
                analyze_drawing_pages=analyze_drawing_pages,
            )
        except Exception as exc:  # noqa: BLE001 - focused locator is additive.
            errors.append(
                {
                    "stage": "special_characteristic_locator",
                    "message": _readable_error(exc),
                }
            )
            warnings = _dedupe_strings(
                warnings
                + [
                    "AI 特殊特性定位未完成，继续使用其它识别结果。",
                    f"AI 特殊特性定位错误：{_readable_error(exc)}",
                ]
            )

    active_analyzer = (
        analyzer if analyzer is not None else default_analyzer_factory()
    )
    if analysis_mode == "hybrid" and analyzer is None:
        _apply_hybrid_vision_runtime_limits(active_analyzer, context_payload)
    try:
        vision_result: Any = analyze_drawing_pages(
            pages, active_analyzer, context_payload
        )
        if not isinstance(vision_result, dict):
            raise RuntimeError("drawing analysis must return a mapping")
        vision_analysis: dict[str, Any] = vision_result
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
            if focused_special_analysis is not None:
                _merge_focused_special_characteristic_analysis(
                    ocr_analysis,
                    focused_special_analysis,
                )
            _merge_special_characteristic_candidates(
                ocr_analysis,
                ocr_analysis,
                context=context_payload,
            )
            return ocr_analysis, warnings, "hybrid_ocr_fallback", errors
        if analysis_mode == "hybrid" and focused_special_analysis is not None:
            warnings = _dedupe_strings(
                warnings
                + [
                    HYBRID_OCR_FALLBACK_WARNING,
                    f"AI 视觉识别错误：{_readable_error(exc)}",
                ]
            )
            return focused_special_analysis, warnings, "hybrid_focused_fallback", errors
        raise

    if analysis_mode == "hybrid" and ocr_analysis is not None:
        if focused_special_analysis is not None:
            _merge_focused_special_characteristic_analysis(
                vision_analysis,
                focused_special_analysis,
            )
        _attach_ocr_reference_metadata(vision_analysis, ocr_analysis)
        _lock_hybrid_identity_from_ocr(vision_analysis, ocr_analysis)
        _merge_ocr_manufacturing_clues_if_needed(vision_analysis, ocr_analysis)
        _merge_special_characteristic_candidates(
            vision_analysis,
            ocr_analysis,
            context=context_payload,
        )
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
        analyzer.timeout = timeout_seconds
    if hasattr(analyzer, "max_retries"):
        analyzer.max_retries = max_retries


def _run_focused_special_characteristic_visual_locator(
    pages: list[Any],
    context_payload: dict[str, Any],
    *,
    analyzer: Any | None,
    default_analyzer_factory: Any,
    analyze_drawing_pages: Any,
) -> dict[str, Any] | None:
    """Run focused visual locator pass for special characteristics, returning focused analysis or None."""
    if not _focused_special_characteristic_locator_enabled(context_payload):
        return None
    active_analyzer = analyzer if analyzer is not None else default_analyzer_factory()
    restore_attrs = _focused_special_characteristic_analyzer_state(active_analyzer)
    _apply_focused_special_characteristic_runtime_limits(
        active_analyzer,
        context_payload,
    )
    if "reasoning_effort" in restore_attrs:
        active_analyzer.reasoning_effort = _focused_special_characteristic_reasoning_effort(context_payload)
    focused_context = dict(context_payload)
    focused_context["visual_task"] = "special_characteristic_locator"
    focused_context["focused_special_characteristic_only"] = True
    focused_context.setdefault("special_characteristic_locator_detail", "broad")
    focused_context.setdefault(
        "special_characteristic_locator_scope",
        "title_block,key_product_characteristic_table,technical_requirements",
    )
    try:
        focused_result: Any = analyze_drawing_pages(
            pages, active_analyzer, focused_context
        )
        if not isinstance(focused_result, dict):
            raise RuntimeError("focused drawing analysis must return a mapping")
        focused_analysis: dict[str, Any] = focused_result
        if not _focused_locator_needs_detailed_retry(
            focused_analysis,
            context_payload,
        ):
            return focused_analysis
        detailed_context = dict(focused_context)
        detailed_context["special_characteristic_locator_detail"] = "detailed"
        detailed_result: Any = analyze_drawing_pages(
            pages,
            active_analyzer,
            detailed_context,
        )
        if isinstance(detailed_result, dict):
            _merge_focused_special_characteristic_analysis(
                focused_analysis,
                detailed_result,
            )
        return focused_analysis
    finally:
        _restore_focused_special_characteristic_analyzer_state(
            active_analyzer,
            restore_attrs,
        )


def _focused_special_characteristic_analyzer_state(analyzer: Any) -> dict[str, Any]:
    """Snapshot current timeout/max_retries/reasoning_effort attrs from the analyzer."""
    return {
        attr: getattr(analyzer, attr)
        for attr in ("timeout", "max_retries", "reasoning_effort")
        if hasattr(analyzer, attr)
    }


def _restore_focused_special_characteristic_analyzer_state(
    analyzer: Any,
    values: dict[str, Any],
) -> None:
    """Restore previously-snapshot analyzer attributes."""
    for attr, value in values.items():
        setattr(analyzer, attr, value)


def _focused_locator_needs_detailed_retry(
    result: dict[str, Any] | None,
    context_payload: dict[str, Any] | None = None,
) -> bool:
    """Check whether the focused locator result requires a detailed retry pass."""
    if not isinstance(result, dict):
        return False
    declared = _focused_locator_expected_totals(result, context_payload)
    if not declared:
        return False
    expected_cc = _non_negative_count(declared.get("CC"))
    expected_sc = _non_negative_count(declared.get("SC"))
    if expected_cc <= 0 and expected_sc <= 0:
        return False
    found = {"CC": 0, "SC": 0}
    for item in result.get("located_occurrences", []):
        if not isinstance(item, dict):
            continue
        classification = str(item.get("candidate_type", "")).strip().upper()
        if classification in found:
            found[classification] += 1
    missing = result.get("missing_counts")
    if isinstance(missing, dict):
        if _non_negative_count(missing.get("CC")) > 0:
            return True
        if _non_negative_count(missing.get("SC")) > 0:
            return True
    return found["CC"] < expected_cc or found["SC"] < expected_sc


def _focused_locator_expected_totals(
    result: dict[str, Any],
    context_payload: dict[str, Any] | None,
) -> dict[str, int]:
    """Extract expected CC/SC totals from result and context."""
    totals = {"CC": 0, "SC": 0}
    sources: list[Any] = []
    if isinstance(result.get("declared_totals"), dict):
        sources.append(result.get("declared_totals"))
    if isinstance(context_payload, dict):
        for key in ("special_characteristic_discovery_request", "ocr_analysis_summary"):
            source = context_payload.get(key)
            if isinstance(source, dict) and isinstance(source.get("declared_totals"), dict):
                sources.append(source.get("declared_totals"))
    for source in sources:
        if not isinstance(source, dict):
            continue
        for classification in ("CC", "SC"):
            totals[classification] = max(
                totals[classification],
                _non_negative_count(source.get(classification)),
            )
    return totals if totals["CC"] > 0 or totals["SC"] > 0 else {}


def _focused_special_characteristic_locator_enabled(
    context_payload: dict[str, Any],
) -> bool:
    """Check whether the focused special characteristic locator is enabled in context."""
    explicit_keys = (
        "focused_special_characteristic_locator_enabled",
        "special_characteristic_locator_enabled",
    )
    for key in explicit_keys:
        if key in context_payload:
            return str(context_payload.get(key)).strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
            }
    return _focused_special_characteristic_locator_has_search_target(context_payload)


def _focused_special_characteristic_locator_has_search_target(
    context_payload: dict[str, Any],
) -> bool:
    """Check whether context contains any declared special characteristics to search for."""
    has_locator_context = any(
        key in context_payload
        for key in ("special_characteristic_discovery_request", "ocr_analysis_summary")
    )
    if not has_locator_context:
        return True
    for key in ("special_characteristic_discovery_request", "ocr_analysis_summary"):
        source = context_payload.get(key)
        if not isinstance(source, dict):
            continue
        declared_totals = source.get("declared_totals")
        if isinstance(declared_totals, dict) and declared_totals:
            return True
        declared_rows = source.get("declared_special_characteristics")
        if isinstance(declared_rows, list) and any(
            isinstance(item, dict) for item in declared_rows
        ):
            return True
    return False


def _apply_focused_special_characteristic_runtime_limits(
    analyzer: Any,
    context_payload: dict[str, Any],
) -> None:
    """Apply runtime limits (timeout, max_retries) to the focused locator analyzer."""
    timeout_seconds = _positive_float_config(
        context_payload.get(
            "special_characteristic_locator_timeout_seconds",
            context_payload.get("focused_special_characteristic_timeout_seconds"),
        ),
        FOCUSED_SPECIAL_CHARACTERISTIC_TIMEOUT_SECONDS,
        "special_characteristic_locator_timeout_seconds",
    )
    max_retries = _non_negative_int_config(
        context_payload.get(
            "special_characteristic_locator_max_retries",
            context_payload.get("focused_special_characteristic_max_retries"),
        ),
        FOCUSED_SPECIAL_CHARACTERISTIC_MAX_RETRIES,
        "special_characteristic_locator_max_retries",
    )
    if hasattr(analyzer, "timeout"):
        analyzer.timeout = timeout_seconds
    if hasattr(analyzer, "max_retries"):
        analyzer.max_retries = max_retries


def _focused_special_characteristic_reasoning_effort(
    context_payload: dict[str, Any],
) -> str:
    """Resolve reasoning effort for the focused locator from context or default."""
    value = context_payload.get(
        "special_characteristic_locator_reasoning_effort",
        context_payload.get("focused_special_characteristic_reasoning_effort"),
    )
    if value in (None, ""):
        return FOCUSED_SPECIAL_CHARACTERISTIC_REASONING_EFFORT
    normalized = str(value).strip().lower()
    if normalized not in {"low", "medium", "high", "xhigh"}:
        raise ValueError(
            "special_characteristic_locator_reasoning_effort must be one of "
            "low, medium, high, xhigh"
        )
    return normalized


def _merge_focused_special_characteristic_analysis(
    target: dict[str, Any],
    focused: dict[str, Any],
) -> None:
    """Merge focused locator results (totals, evidence, candidates) into the target analysis."""
    _merge_declared_totals(target, focused)
    for key in (
        "evidence",
        "visual_evidence",
        "declared_special_characteristics",
        "located_occurrences",
        "special_characteristic_candidates",
        "special_characteristic_locations",
        "focused_review_requests",
    ):
        _append_unique_dict_rows(target, key, focused.get(key))
    metadata = target.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["focused_special_characteristic_locator"] = {
            "source_stage": "special_characteristic_locator",
            "declared_totals": copy.deepcopy(focused.get("declared_totals", {})),
            "candidate_count": len(
                focused.get("special_characteristic_candidates", [])
                if isinstance(focused.get("special_characteristic_candidates"), list)
                else []
            )
            + len(
                focused.get("located_occurrences", [])
                if isinstance(focused.get("located_occurrences"), list)
                else []
            ),
        }


def _merge_declared_totals(target: dict[str, Any], focused: dict[str, Any]) -> None:
    """Merge declared CC/SC totals from focused analysis into target, taking the max per classification."""
    focused_totals = focused.get("declared_totals")
    if not isinstance(focused_totals, dict):
        return
    target_totals = target.get("declared_totals")
    if not isinstance(target_totals, dict):
        target_totals = {}
    merged = dict(target_totals)
    for classification in ("CC", "SC"):
        merged[classification] = max(
            _non_negative_count(merged.get(classification)),
            _non_negative_count(focused_totals.get(classification)),
        )
    target["declared_totals"] = merged


def _append_unique_dict_rows(
    target: dict[str, Any],
    key: str,
    rows: Any,
) -> None:
    """Append unique dict rows from a source list to a target list under the given key."""
    if not isinstance(rows, list) or not rows:
        return
    existing = target.get(key)
    if not isinstance(existing, list):
        existing = []
        target[key] = existing
    seen = {_row_identity(item) for item in existing if isinstance(item, dict)}
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity = _row_identity(row)
        if identity in seen:
            continue
        existing.append(copy.deepcopy(row))
        seen.add(identity)


def _row_identity(row: dict[str, Any]) -> str:
    """Build a stable identity string for a dict row to detect duplicates."""
    for key in (
        "evidence_id",
        "id",
        "candidate_id",
        "location_id",
        "declaration_id",
        "review_id",
        "linked_feature",
        "text",
    ):
        value = str(row.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    return repr(sorted(row.items()))


def _non_negative_count(value: Any) -> int:
    """Parse a value as a non-negative integer, defaulting to 0 on failure."""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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
    raw_value = (
        context_payload.get("ocr_engine")
        if ocr_engine == "auto"
        else ocr_engine
    )
    value = str(raw_value or "auto").strip().lower()
    if value not in OCR_ENGINES:
        # Accept OCR engine names registered via plugins
        from ..plugins import iter_ocr_engines

        plugin_names = {e.name for e in iter_ocr_engines()}
        if value not in plugin_names:
            raise ValueError(
                "ocr_engine must be one of: auto, pdf_text, rapidocr, mineru, "
                "or a registered plugin OCR engine"
            )
    if value == "auto":
        from minos_core.ocr_detection import get_default_ocr_engine

        return get_default_ocr_engine()
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
    return dict(result)


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
