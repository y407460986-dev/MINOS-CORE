"""Pipeline entry points for APQP workflow orchestration."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

from .adapters.fixture_json import load_fixture_payload, read_json_object
from .exporters import export_apqp_workbook
from .exporters.three_table_workbooks import (
    export_split_three_table_workbooks,
    export_three_table_workbook,
)
from .quality_gates import evaluate_export_gate, require_export_gate
from .review_patch import REVIEW_CONFIRMATIONS_KEY, apply_review_patch
from .run_manifest import build_run_manifest, write_run_manifest
from ._text_utils import string_list
from .stage import assemble_generated_apqp_chain as _assemble_generated_apqp_chain
from .three_table_result import (
    build_three_table_generation_envelope,
    build_canonical_three_table_bundle,
    dedupe_strings as _dedupe_strings,
    three_table_manual_review as _three_table_manual_review,
    three_table_status_display as _three_table_status_display,
)


PIPELINE_STAGES = (
    "ingest",
    "analyze",
    "generate_pfd",
    "brainstorm_failure_modes",
    "generate_pfmea",
    "generate_control_plan",
    "assemble_generated_apqp_chain",
    "generate_draft",
    "validate",
    "export",
)


DRAFT_WARNING = (
    "当前结果仅为 APQP 工程草案，不是正式导出文件；必须经过质量门检查和人工工程复核后，"
    "才能用于正式放行。"
)

THREE_TABLE_DRAFT_WARNING = (
    "AI 图纸生成的 PFD/PFMEA/CP 仅为工程草案；必须经过质量门和人工复核确认后，"
    "才能作为正式工程文件使用。"
)

HYBRID_OCR_FALLBACK_WARNING = "AI 视觉识别未完成，当前结果基于 OCR，必须人工复核。"
OCR_UNAVAILABLE_WARNING = (
    "OCR 识别未完成：MINOS 预期由 minos_core.drawing_ocr_analysis 提供 "
    "analyze_drawing_with_ocr(...)。"
)
OCR_IDENTITY_LOCK_CONFIDENCE = 0.70
OCR_FAMILY_LOCK_CONFIDENCE = 0.78
OCR_IDENTITY_LOCK_FIELDS = ("part_name", "drawing_number", "revision")
HYBRID_VISION_TIMEOUT_SECONDS = 45.0
HYBRID_VISION_MAX_RETRIES = 0

ANALYSIS_MODES = {"hybrid", "ocr_only", "vision_only"}
OCR_ENGINES = {"auto", "pdf_text", "rapidocr", "mineru"}
DEFAULT_OCR_ENGINE = "mineru"


GENERATED_DRAFT_STAGES = (
    "ingest",
    "analyze",
    "generate_pfd",
    "brainstorm_failure_modes",
    "generate_pfmea",
    "generate_control_plan",
    "assemble_generated_apqp_chain",
)


def generate_draft(
    evidence: str | Path | dict[str, Any],
    output_path: str | Path | None = None,
    manifest_output: str | Path | None = None,
) -> dict[str, Any]:
    """Run generated stages from evidence and return a draft APQPChain envelope.

    The returned draft is intentionally not a formal APQP export. It includes the
    assembled APQPChain payload, the validate-stage quality gate, and manual
    review data so callers can decide what needs engineering review before any
    release workflow.
    """

    from .stage import run_stage

    stage_results = []
    stage_outputs: dict[str, Any] = {}
    current_payload: Any = evidence
    for stage_name in GENERATED_DRAFT_STAGES:
        stage_input = current_payload
        if stage_name == "assemble_generated_apqp_chain":
            stage_input = {
                "generate_pfd": stage_outputs["generate_pfd"],
                "brainstorm_failure_modes": stage_outputs[
                    "brainstorm_failure_modes"
                ],
                "generate_pfmea": stage_outputs["generate_pfmea"],
                "generate_control_plan": stage_outputs["generate_control_plan"],
            }
        result = run_stage(stage_input, stage=stage_name)
        stage_results.append(result)
        if not result.ok:
            envelope = _draft_envelope(
                draft=None,
                status="blocked",
                generated_stage_results=stage_results,
                validation_stage_result=None,
                blocked_stage=stage_name,
            )
            if output_path is not None:
                _write_json_file(output_path, envelope)
            if manifest_output is not None:
                _write_manifest_file(
                    manifest_output,
                    inputs=evidence,
                    outputs=envelope,
                    stage_results=envelope.get("stage_results", []),
                    quality_gates=[envelope.get("quality_gate")],
                    review_confirmations=[],
                    artifacts={"draft_result": envelope},
                    warnings=[DRAFT_WARNING],
                )
            return envelope
        current_payload = result.output
        stage_outputs[stage_name] = result.output

    validation_result = run_stage(current_payload, stage="validate")
    stage_results.append(validation_result)
    envelope = _draft_envelope(
        draft=current_payload,
        status="draft_ready" if validation_result.ok else "blocked",
        generated_stage_results=stage_results[:-1],
        validation_stage_result=validation_result,
        blocked_stage=None if validation_result.ok else "validate",
    )
    if output_path is not None:
        _write_json_file(output_path, envelope)
    if manifest_output is not None:
        _write_manifest_file(
            manifest_output,
            inputs=evidence,
            outputs=envelope,
            stage_results=envelope.get("stage_results", []),
            quality_gates=[envelope.get("quality_gate")],
            review_confirmations=[],
            artifacts={"draft_result": envelope},
            warnings=[DRAFT_WARNING],
        )
    return envelope


def generate_three_tables_from_drawing(
    drawing_path: str | Path,
    output_dir: str | Path,
    context: dict[str, Any] | None = None,
    export_mode: str = "draft",
    analysis_mode: str = "hybrid",
    ocr_engine: str = "auto",
    ocr_adapter: Any | None = None,
    *,
    analyzer: Any | None = None,
) -> dict[str, Any]:
    """Generate drawing-driven PFD/PFMEA/CP drafts and export workbooks.

    The default export mode is draft. A final export is blocked unless the final
    export quality gate allows user export, which normally requires human review
    of AI-inferred drawing content.
    """

    from .drawing_to_pfd import infer_process_flow_from_drawing
    from .generate_control_plan import generate_control_plan_from_pfmea
    from .pfd_to_pfmea_ai import infer_pfmea_from_process_flow
    from .characteristic_registry import build_characteristic_registry, attach_characteristics_to_three_tables
    from .quality_gates import (
        evaluate_control_plan_bundle_gate,
        evaluate_pfmea_bundle_gate,
        evaluate_pfd_bundle_gate,
    )

    if export_mode not in {"draft", "final"}:
        raise ValueError("export_mode must be 'draft' or 'final'")

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    analysis_result = analyze_drawing_for_three_table_chain(
        drawing_path,
        target_dir,
        context=context,
        analysis_mode=analysis_mode,
        ocr_engine=ocr_engine,
        ocr_adapter=ocr_adapter,
        analyzer=analyzer,
    )
    drawing_analysis = analysis_result["drawing_analysis"]
    context_payload = analysis_result["context"]
    active_analysis_mode = analysis_result["analysis_mode"]
    active_ocr_engine = analysis_result["ocr_engine"]
    analysis_warnings = analysis_result["warnings"]
    analysis_source = analysis_result["analysis_source"]
    part_family_classification = analysis_result["part_family_classification"]
    family_context = analysis_result["family_context"]
    drawing_gate = analysis_result["drawing_gate"]
    pipeline_inputs = analysis_result["pipeline_inputs"]

    if not drawing_gate.can_continue:
        return _three_table_generation_envelope(
            status="blocked",
            drawing_analysis=drawing_analysis,
            process_flow=None,
            pfmea=None,
            control_plan=None,
            chain=None,
            quality_gates={"drawing_recognition": drawing_gate.model_dump()},
            exports={},
            output_dir=target_dir,
            inputs=pipeline_inputs,
            blocked_stage="drawing_recognition",
            warnings=_dedupe_strings(
                analysis_warnings + ["图纸识别质量门未通过，已阻止继续推导过程流程图。"]
            ),
            part_family_classification=part_family_classification,
            family_context=family_context,
        )

    registry = build_characteristic_registry(drawing_analysis) if drawing_analysis else {}

    pfd_result = _generate_pfd_stage(
        drawing_analysis, family_context, registry,
        infer_process_flow_from_drawing, attach_characteristics_to_three_tables,
        evaluate_pfd_bundle_gate,
    )
    process_flow, pfd_gate = pfd_result["process_flow"], pfd_result["pfd_gate"]
    if not pfd_gate.can_continue:
        return _three_table_generation_envelope(
            status="blocked",
            drawing_analysis=drawing_analysis,
            process_flow=process_flow,
            pfmea=None, control_plan=None, chain=None,
            quality_gates={
                "drawing_recognition": drawing_gate.model_dump(),
                "process_flow": pfd_gate.model_dump(),
            },
            exports={}, output_dir=target_dir, inputs=pipeline_inputs,
            blocked_stage="process_flow",
            warnings=_dedupe_strings(
                analysis_warnings + ["过程流程图质量门未通过，已阻止继续推导 PFMEA。"]
            ),
            characteristic_registry=registry,
            part_family_classification=part_family_classification,
            family_context=family_context,
        )

    pfmea_result = _generate_pfmea_stage(
        process_flow, registry,
        infer_pfmea_from_process_flow, attach_characteristics_to_three_tables,
        evaluate_pfmea_bundle_gate,
    )
    process_flow = pfmea_result["process_flow"]
    pfmea, pfmea_gate = pfmea_result["pfmea"], pfmea_result["pfmea_gate"]
    if not pfmea_gate.can_continue:
        return _three_table_generation_envelope(
            status="blocked",
            drawing_analysis=drawing_analysis,
            process_flow=process_flow,
            pfmea=pfmea, control_plan=None, chain=None,
            quality_gates={
                "drawing_recognition": drawing_gate.model_dump(),
                "process_flow": pfd_gate.model_dump(),
                "pfmea": pfmea_gate.model_dump(),
            },
            exports={}, output_dir=target_dir, inputs=pipeline_inputs,
            blocked_stage="pfmea",
            warnings=_dedupe_strings(
                analysis_warnings + ["PFMEA 质量门未通过，已阻止继续生成控制计划。"]
            ),
            characteristic_registry=registry,
            part_family_classification=part_family_classification,
            family_context=family_context,
        )

    cp_result = _generate_cp_stage(
        process_flow, pfmea, registry,
        generate_control_plan_from_pfmea, attach_characteristics_to_three_tables,
        evaluate_control_plan_bundle_gate,
    )
    process_flow = cp_result["process_flow"]
    pfmea = cp_result["pfmea"]
    control_plan = cp_result["control_plan"]
    control_plan_gate = cp_result["control_plan_gate"]

    chain = _assemble_three_table_chain(
        drawing_analysis, process_flow, pfmea, control_plan,
        characteristic_registry=registry,
        part_family_classification=part_family_classification,
        family_context=family_context,
    )

    analysis = _build_chain_analysis(chain, registry, part_family_classification, family_context)
    linkage_map = analysis["linkage_map"]
    linkage_gaps = analysis["linkage_gaps"]
    risk_structure = analysis["risk_structure"]
    review_dashboard = analysis["review_dashboard"]
    knowledge_recs = analysis["knowledge_recs"]

    final_gate = evaluate_export_gate(chain)
    quality_gates = {
        "drawing_recognition": drawing_gate.model_dump(),
        "process_flow": pfd_gate.model_dump(),
        "pfmea": pfmea_gate.model_dump(),
        "control_plan": control_plan_gate.model_dump(),
        "final_three_table": final_gate.model_dump(),
    }

    if not control_plan_gate.can_continue:
        return _three_table_generation_envelope(
            status="blocked",
            drawing_analysis=drawing_analysis,
            process_flow=process_flow, pfmea=pfmea,
            control_plan=control_plan, chain=chain,
            quality_gates=quality_gates, exports={},
            output_dir=target_dir, inputs=pipeline_inputs,
            blocked_stage="control_plan",
            warnings=_dedupe_strings(
                analysis_warnings + ["控制计划质量门未通过，已阻止导出工作簿。"]
            ),
            linkage_map=linkage_map, linkage_gaps=linkage_gaps,
            characteristic_registry=registry,
            knowledge_recommendations=knowledge_recs,
            risk_structure=risk_structure, review_dashboard=review_dashboard,
            part_family_classification=part_family_classification,
            family_context=family_context,
        )

    if export_mode == "final" and not final_gate.allow_user_export:
        return _three_table_generation_envelope(
            status="blocked",
            drawing_analysis=drawing_analysis,
            process_flow=process_flow, pfmea=pfmea,
            control_plan=control_plan, chain=chain,
            quality_gates=quality_gates, exports={},
            output_dir=target_dir, inputs=pipeline_inputs,
            blocked_stage="final_three_table",
            warnings=_dedupe_strings(
                analysis_warnings + ["最终三表质量门未通过，已阻止正式导出。"]
            ),
            linkage_map=linkage_map, linkage_gaps=linkage_gaps,
            characteristic_registry=registry,
            knowledge_recommendations=knowledge_recs,
            risk_structure=risk_structure, review_dashboard=review_dashboard,
            part_family_classification=part_family_classification,
            family_context=family_context,
        )

    return _export_and_finalize(
        chain, target_dir, export_mode, final_gate, quality_gates,
        analysis_source, analysis_warnings, drawing_analysis, process_flow,
        pfmea, control_plan, pipeline_inputs, linkage_map, linkage_gaps,
        registry, knowledge_recs, risk_structure, review_dashboard,
        part_family_classification, family_context,
    )


def _generate_pfd_stage(
    drawing_analysis, family_context, registry,
    infer_process_flow_from_drawing, attach_characteristics_to_three_tables,
    evaluate_pfd_bundle_gate,
):
    """Infer PFD from drawing analysis and evaluate quality gate."""
    process_flow = infer_process_flow_from_drawing(
        drawing_analysis,
        family_context=family_context or None,
    )
    if registry and registry.get("items"):
        process_flow = attach_characteristics_to_three_tables(
            {"process_flow": process_flow}, registry
        )["process_flow"]
    pfd_gate = evaluate_pfd_bundle_gate(process_flow, stage="drawing_to_pfd")
    return {"process_flow": process_flow, "pfd_gate": pfd_gate}


def _generate_pfmea_stage(
    process_flow, registry,
    infer_pfmea_from_process_flow, attach_characteristics_to_three_tables,
    evaluate_pfmea_bundle_gate,
):
    """Infer PFMEA from process flow and evaluate quality gate."""
    pfmea = infer_pfmea_from_process_flow(process_flow)
    if registry and registry.get("items"):
        attached = attach_characteristics_to_three_tables(
            {"process_flow": process_flow, "pfmea": pfmea}, registry
        )
        process_flow = attached["process_flow"]
        pfmea = attached["pfmea"]
    pfmea_gate = evaluate_pfmea_bundle_gate(pfmea, stage="pfd_to_pfmea")
    return {"process_flow": process_flow, "pfmea": pfmea, "pfmea_gate": pfmea_gate}


def _generate_cp_stage(
    process_flow, pfmea, registry,
    generate_control_plan_from_pfmea, attach_characteristics_to_three_tables,
    evaluate_control_plan_bundle_gate,
):
    """Generate control plan from PFMEA and evaluate quality gate."""
    control_plan = generate_control_plan_from_pfmea(pfmea)
    if registry and registry.get("items"):
        attached = attach_characteristics_to_three_tables(
            {"process_flow": process_flow, "pfmea": pfmea, "control_plan": control_plan}, registry
        )
        process_flow = attached["process_flow"]
        pfmea = attached["pfmea"]
        control_plan = attached["control_plan"]
    control_plan_gate = evaluate_control_plan_bundle_gate(
        control_plan, stage="pfmea_to_control_plan"
    )
    return {
        "process_flow": process_flow, "pfmea": pfmea,
        "control_plan": control_plan, "control_plan_gate": control_plan_gate,
    }


def _build_chain_analysis(chain, registry, part_family_classification, family_context):
    """Build action items, linkage, risk structure, and review dashboard."""
    from .action_tracking import build_action_items, action_items_summary
    from .three_table_linkage import build_three_table_linkage_map, evaluate_three_table_linkage
    from .risk_structure import build_risk_structure
    from .edit_patch import _build_review_dashboard, evaluate_edit_export_gate

    metadata = chain.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["action_items"] = build_action_items(chain)
        metadata["action_items_summary"] = action_items_summary(metadata["action_items"])

    linkage_map = build_three_table_linkage_map(chain)
    linkage_report = evaluate_three_table_linkage(chain)
    linkage_gaps = linkage_map.get("gaps", [])
    risk_structure = build_risk_structure(chain)
    knowledge_recs = chain.get("metadata", {}).get("knowledge_recommendations", [])
    edit_gate_for_envelope = evaluate_edit_export_gate(chain)
    review_dashboard = _build_review_dashboard(
        chain, edit_gate_for_envelope, risk_structure, linkage_report,
    )
    return {
        "linkage_map": linkage_map,
        "linkage_gaps": linkage_gaps,
        "risk_structure": risk_structure,
        "review_dashboard": review_dashboard,
        "knowledge_recs": knowledge_recs,
    }


def _export_and_finalize(
    chain, target_dir, export_mode, final_gate, quality_gates,
    analysis_source, analysis_warnings, drawing_analysis, process_flow,
    pfmea, control_plan, pipeline_inputs, linkage_map, linkage_gaps,
    registry, knowledge_recs, risk_structure, review_dashboard,
    part_family_classification, family_context,
):
    """Export workbooks and build the final generation envelope."""
    manual_review = _three_table_manual_review(quality_gates)
    unified = export_three_table_workbook(
        chain,
        target_dir / "三表总工作簿.xlsx",
        export_mode=export_mode,
        require_gate=export_mode == "final",
        quality_gate=final_gate,
        manual_review_items=manual_review["items"],
    )
    split = export_split_three_table_workbooks(
        chain,
        target_dir / "三表独立文件",
        export_mode=export_mode,
    )
    exports = {
        "unified_workbook": str(unified),
        "process_flow": str(split["process_flow"]),
        "pfmea": str(split["pfmea"]),
        "control_plan": str(split["control_plan"]),
    }
    status = (
        "draft_ready"
        if final_gate.allow_user_export and not final_gate.needs_human_review
        else "needs_review"
    )
    if analysis_source in {"ocr", "hybrid_ocr_fallback"} or analysis_warnings:
        status = "needs_review"
    result_warnings = (
        list(analysis_warnings)
        if status == "draft_ready"
        else _dedupe_strings(analysis_warnings + [THREE_TABLE_DRAFT_WARNING])
    )
    return _three_table_generation_envelope(
        status=status,
        drawing_analysis=drawing_analysis,
        process_flow=process_flow,
        pfmea=pfmea,
        control_plan=control_plan,
        chain=chain,
        quality_gates=quality_gates,
        exports=exports,
        output_dir=target_dir,
        inputs=pipeline_inputs,
        blocked_stage=None,
        warnings=result_warnings,
        manual_review=manual_review,
        linkage_map=linkage_map,
        linkage_gaps=linkage_gaps,
        characteristic_registry=registry,
        knowledge_recommendations=knowledge_recs,
        risk_structure=risk_structure,
        review_dashboard=review_dashboard,
        part_family_classification=part_family_classification,
        family_context=family_context,
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

    from .adapters.multimodal import OpenAIResponsesMultimodalDrawingAnalyzer
    from .drawing_analysis import analyze_drawing_pages, evaluate_drawing_recognition_gate
    from .drawing_input import load_drawing_source, render_drawing_pages

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
            warnings.append(_readable_ocr_warning(exc))
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


def _positive_float_config(raw_value: Any, default: float, name: str) -> float:
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
    if raw_value in (None, ""):
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _effective_analysis_mode(
    analysis_mode: str,
    context_payload: dict[str, Any],
) -> str:
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
    try:
        module = importlib.import_module(".drawing_ocr_analysis", __package__)
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


def _ocr_summary_for_context(drawing_analysis: dict[str, Any]) -> dict[str, Any]:
    metadata = drawing_analysis.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("ocr_summary"), dict):
        return dict(metadata["ocr_summary"])
    return {
        "drawing_identity": drawing_analysis.get("drawing_identity", {}),
        "materials": _summary_items(drawing_analysis.get("materials", [])),
        "dimensions": _summary_items(drawing_analysis.get("dimensions", [])),
        "special_characteristics": _summary_items(
            drawing_analysis.get("special_characteristics", [])
        ),
        "technical_requirements": _summary_items(
            drawing_analysis.get("technical_requirements", [])
        ),
        "manufacturing_clues": _summary_items(
            drawing_analysis.get("manufacturing_clues", [])
        ),
    }


def _summary_items(value: Any, *, limit: int = 8) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:limit]


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


def _attach_ocr_reference_metadata(
    vision_analysis: dict[str, Any],
    ocr_analysis: dict[str, Any],
) -> None:
    metadata = vision_analysis.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["ocr_analysis_summary"] = _ocr_summary_for_context(ocr_analysis)


def _lock_hybrid_identity_from_ocr(
    vision_analysis: dict[str, Any],
    ocr_analysis: dict[str, Any],
) -> None:
    ocr_identity = _as_dict(ocr_analysis.get("drawing_identity"))
    ocr_part_name = _clean_text(ocr_identity.get("part_name"))
    ocr_confidence = _float_value(ocr_identity.get("confidence"), 0.0)
    if not ocr_part_name or ocr_confidence < OCR_IDENTITY_LOCK_CONFIDENCE:
        return

    vision_identity = vision_analysis.setdefault("drawing_identity", {})
    if not isinstance(vision_identity, dict):
        vision_identity = {}
        vision_analysis["drawing_identity"] = vision_identity
    original_identity = copy.deepcopy(vision_identity)
    locked_fields: list[str] = []
    ocr_field_refs = _as_dict(ocr_identity.get("field_evidence_refs"))
    vision_field_refs = vision_identity.setdefault("field_evidence_refs", {})
    if not isinstance(vision_field_refs, dict):
        vision_field_refs = {}
        vision_identity["field_evidence_refs"] = vision_field_refs

    for field_name in OCR_IDENTITY_LOCK_FIELDS:
        value = _clean_text(ocr_identity.get(field_name))
        if not value:
            continue
        if _clean_text(vision_identity.get(field_name)) != value:
            locked_fields.append(f"drawing_identity.{field_name}")
        vision_identity[field_name] = value
        refs = string_list(ocr_field_refs.get(field_name))
        if refs:
            vision_field_refs[field_name] = refs

    if not locked_fields:
        return

    ocr_refs = string_list(ocr_identity.get("evidence_refs"))
    if ocr_refs:
        vision_identity["evidence_refs"] = _dedupe_strings(
            string_list(vision_identity.get("evidence_refs")) + ocr_refs
        )
    vision_identity["confidence"] = max(
        _float_value(vision_identity.get("confidence"), 0.0),
        ocr_confidence,
    )
    vision_identity["ocr_identity_locked"] = True
    vision_identity["needs_confirmation"] = bool(
        ocr_identity.get("needs_confirmation", vision_identity.get("needs_confirmation", False))
    )

    _merge_ocr_evidence(vision_analysis, ocr_analysis)
    metadata = vision_analysis.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        vision_analysis["metadata"] = metadata

    lock_record: dict[str, Any] = {
        "locked": True,
        "source": "ocr_title_block",
        "reason": "OCR/title-block identity is treated as the whole-part authority in hybrid mode.",
        "confidence": round(ocr_confidence, 3),
        "locked_fields": locked_fields,
        "ocr_identity": copy.deepcopy(ocr_identity),
        "original_vision_identity": original_identity,
    }
    family_lock = _ocr_family_lock_classification(ocr_analysis)
    if family_lock:
        lock_record["part_family_classification"] = family_lock
        metadata["locked_part_family_classification"] = family_lock
    metadata["ocr_identity_lock"] = lock_record


def _merge_ocr_evidence(
    vision_analysis: dict[str, Any],
    ocr_analysis: dict[str, Any],
) -> None:
    evidence = vision_analysis.setdefault("evidence", [])
    if not isinstance(evidence, list):
        evidence = []
        vision_analysis["evidence"] = evidence
    existing_ids = {
        str(item.get("evidence_id", "")).strip()
        for item in evidence
        if isinstance(item, dict)
    }
    for item in ocr_analysis.get("evidence", []):
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id", "")).strip()
        if not evidence_id or evidence_id in existing_ids:
            continue
        evidence.append(copy.deepcopy(item))
        existing_ids.add(evidence_id)


def _ocr_family_lock_classification(
    ocr_analysis: dict[str, Any],
) -> dict[str, Any]:
    try:
        from .part_family_classifier import classify_part_family
    except ImportError:
        return {}

    classification = classify_part_family(ocr_analysis)
    if not isinstance(classification, dict):
        return {}
    family_key = _clean_text(classification.get("family_key"))
    confidence = _float_value(classification.get("confidence"), 0.0)
    if not family_key or family_key == "unknown":
        return {}
    if confidence < OCR_FAMILY_LOCK_CONFIDENCE:
        return {}
    locked = copy.deepcopy(classification)
    locked["locked_by"] = "ocr_title_block"
    locked["needs_confirmation"] = False
    return locked


def _readable_ocr_warning(exc: BaseException) -> str:
    message = _readable_error(exc)
    if OCR_UNAVAILABLE_WARNING in message:
        return OCR_UNAVAILABLE_WARNING
    return f"OCR 识别未完成：{message}"


def _readable_error(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if "stream_read_error" in message:
        return f"AI 视觉识别中断，已保留 OCR 识别结果。详情：{message}"
    return message


def apply_review(
    draft_result_or_chain: str | Path | dict[str, Any],
    review_patch: str | Path | dict[str, Any],
    output_path: str | Path | None = None,
    manifest_output: str | Path | None = None,
) -> dict[str, Any]:
    """Apply a human review patch and return a reviewed APQPChain envelope.

    ``draft_result_or_chain`` may be an ``apqp_chain_draft_result`` envelope, an
    ``apqp_chain_review_result`` envelope, a raw APQPChain JSON file, or a fixture
    directory. ``review_patch`` must be a review patch JSON object accepted by
    :func:`review_patch.apply_review_patch`.
    """

    source_payload = _load_review_source_payload(draft_result_or_chain)
    patch_payload = _load_review_patch_payload(review_patch)
    patched_chain = apply_review_patch(source_payload, patch_payload)
    quality_gate = evaluate_export_gate(patched_chain)
    envelope = {
        "document_type": "apqp_chain_review_result",
        "patched_chain": patched_chain,
        "quality_gate": quality_gate.model_dump(),
        "review_confirmations": list(
            patched_chain.get("metadata", {}).get(REVIEW_CONFIRMATIONS_KEY, [])
        ),
        "manual_review": {
            "required": bool(quality_gate.needs_human_review),
            "items": [_dump_json_value(item) for item in quality_gate.manual_review_items],
        },
        "final_export_allowed": bool(quality_gate.allow_user_export),
    }
    if output_path is not None:
        _write_json_file(output_path, envelope)
    if manifest_output is not None:
        _write_manifest_file(
            manifest_output,
            inputs={"source": draft_result_or_chain, "review_patch": review_patch},
            outputs=envelope,
            stage_results=[],
            quality_gates=[envelope.get("quality_gate")],
            review_confirmations=envelope.get("review_confirmations", []),
            artifacts={"review_result": envelope, "patched_chain": patched_chain},
            warnings=[]
            if quality_gate.allow_user_export
            else ["导出质量门未通过，当前结果不允许正式导出。"],
        )
    return envelope


def apply_edit_patch(source: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply a human edit patch to a three-table result or APQP chain."""

    from .edit_patch import apply_edit_patch as _apply_edit_patch

    return _apply_edit_patch(source, patch)


def evaluate_edit_export_gate(source: dict[str, Any]) -> dict[str, Any]:
    """Evaluate whether an edited three-table payload may be final-exported."""

    from .edit_patch import evaluate_edit_export_gate as _evaluate_edit_export_gate

    return _evaluate_edit_export_gate(source)


def export_edited_three_tables(
    source: dict[str, Any],
    output_dir: str | Path,
    export_mode: str = "draft",
) -> dict[str, Any]:
    """Export edited three-table workbooks after applying edit gate rules."""

    from .edit_patch import export_edited_three_tables as _export_edited_three_tables

    return _export_edited_three_tables(source, output_dir, export_mode)


def _draft_envelope(
    *,
    draft: dict[str, Any] | None,
    status: str,
    generated_stage_results: list[Any],
    validation_stage_result: Any | None,
    blocked_stage: str | None,
) -> dict[str, Any]:
    quality_gate = (
        validation_stage_result.quality_gate
        if validation_stage_result is not None
        else _last_quality_gate(generated_stage_results)
    )
    manual_review_items = (
        quality_gate.manual_review_items if quality_gate is not None else []
    )
    return {
        "document_type": "apqp_chain_draft_result",
        "status": status,
        "draft_notice": DRAFT_WARNING,
        "draft_is_formal_export": False,
        "blocked_stage": blocked_stage,
        "draft": draft,
        "quality_gate": quality_gate.model_dump() if quality_gate is not None else None,
        "manual_review": {
            "required": bool(
                quality_gate.needs_human_review if quality_gate is not None else False
            ),
            "items": [_dump_json_value(item) for item in manual_review_items],
        },
        "stage_results": [result.model_dump() for result in generated_stage_results],
    }


def _last_quality_gate(stage_results: list[Any]) -> Any | None:
    for result in reversed(stage_results):
        if getattr(result, "quality_gate", None) is not None:
            return result.quality_gate
    return None


def _assemble_three_table_chain(
    drawing_analysis: dict[str, Any],
    process_flow: dict[str, Any],
    pfmea: dict[str, Any],
    control_plan: dict[str, Any],
    characteristic_registry: dict[str, Any] | None = None,
    part_family_classification: dict[str, Any] | None = None,
    family_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble an APQP chain from already-attached three-table documents.

    The caller is responsible for building the characteristic registry and
    attaching it to *process_flow*, *pfmea*, and *control_plan* before
    calling this function.  This function only assembles the chain dict and
    records the registry in metadata without performing any internal
    attachment.
    """
    from .knowledge_recommendation import recommend_from_knowledge

    canonical = build_canonical_three_table_bundle(
        process_flow=process_flow,
        pfmea=pfmea,
        control_plan=control_plan,
    )
    process_flow = canonical["process_flow"]
    pfmea = canonical["pfmea"]
    control_plan = canonical["control_plan"]
    chain = {
        "document_type": "apqp_chain",
        "schema_version": "minos-core.generated.v1",
        "process_flow": process_flow,
        "pfmea": pfmea,
        "control_plan": control_plan,
        "product": process_flow.get("product", {}),
        "drawings": process_flow.get("drawings", []),
        "characteristics": process_flow.get("characteristics", []),
        "process_steps": process_flow.get("steps", []),
        "failure_modes": pfmea.get("rows", []),
        "controls": control_plan.get("rows", []),
        "evidence": drawing_analysis.get("evidence", []),
        "links": process_flow.get("links", []),
        "pending_fields": _dedupe_strings(
            list(process_flow.get("pending_fields", []))
            + list(pfmea.get("pending_fields", []))
            + list(control_plan.get("pending_fields", []))
        ),
        "ai_inferred_items": _dedupe_strings(
            list(process_flow.get("ai_inferred_items", []))
            + list(pfmea.get("ai_inferred_items", []))
            + list(control_plan.get("ai_inferred_items", []))
        ),
        "metadata": {
            "generation_mode": "ai_drawing_three_table_generation",
            "source_document_type": "drawing_analysis_bundle",
            "requires_engineering_review": True,
            "strict_aiag_vda_pfmea_gate": True,
        },
    }
    if characteristic_registry:
        chain["metadata"]["characteristic_registry"] = characteristic_registry
    chain["metadata"]["part_family_classification"] = part_family_classification or {}
    chain["metadata"]["family_context"] = family_context or {}
    chain["metadata"]["knowledge_recommendations"] = recommend_from_knowledge(
        chain,
        family_context=family_context or None,
    )
    return chain


def _part_family_context_from_drawing(
    drawing_analysis: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    from .part_family_classifier import classify_part_family
    from .part_family_knowledge import load_part_family_knowledge

    classification = _locked_part_family_classification(drawing_analysis)
    if not classification:
        classification = classify_part_family(drawing_analysis)
    if not isinstance(classification, dict):
        classification = {}

    family_key = str(classification.get("family_key", "")).strip()
    if not family_key or family_key == "unknown":
        return classification, {}

    family_context = dict(classification)
    try:
        knowledge = load_part_family_knowledge(family_key)
    except (FileNotFoundError, KeyError, ValueError, ImportError) as exc:
        family_context["knowledge_load_error"] = str(exc)
        return classification, family_context

    if isinstance(knowledge, dict):
        family_context = _merge_family_context(classification, knowledge)
    return classification, family_context


def _locked_part_family_classification(
    drawing_analysis: dict[str, Any],
) -> dict[str, Any]:
    metadata = _as_dict(drawing_analysis.get("metadata"))
    classification = metadata.get("locked_part_family_classification")
    if not isinstance(classification, dict):
        lock = metadata.get("ocr_identity_lock")
        if isinstance(lock, dict):
            classification = lock.get("part_family_classification")
    if not isinstance(classification, dict):
        return {}
    family_key = _clean_text(classification.get("family_key"))
    confidence = _float_value(classification.get("confidence"), 0.0)
    if not family_key or family_key == "unknown":
        return {}
    if confidence < OCR_FAMILY_LOCK_CONFIDENCE:
        return {}
    locked = copy.deepcopy(classification)
    locked.setdefault("locked_by", "ocr_title_block")
    locked["needs_confirmation"] = False
    return locked


def _merge_family_context(
    classification: dict[str, Any],
    knowledge: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(classification)
    for key, value in knowledge.items():
        if key in {"knowledge_source_refs", "source_refs"}:
            continue
        if value not in ("", None, [], {}):
            merged[key] = value
    merged["knowledge_source_refs"] = _dedupe_strings(
        string_list(classification.get("knowledge_source_refs", []))
        + string_list(knowledge.get("knowledge_source_refs", []))
    )
    source_refs = knowledge.get("source_refs", [])
    if isinstance(source_refs, list):
        merged["source_refs"] = source_refs
    return merged


def _three_table_generation_envelope(
    *,
    status: str,
    drawing_analysis: dict[str, Any] | None,
    process_flow: dict[str, Any] | None,
    pfmea: dict[str, Any] | None,
    control_plan: dict[str, Any] | None,
    chain: dict[str, Any] | None,
    quality_gates: dict[str, Any],
    exports: dict[str, Any],
    output_dir: Path,
    inputs: dict[str, Any],
    blocked_stage: str | None,
    warnings: list[str],
    manual_review: dict[str, Any] | None = None,
    linkage_map: dict[str, Any] | None = None,
    linkage_gaps: list[dict[str, Any]] | None = None,
    characteristic_registry: dict[str, Any] | None = None,
    knowledge_recommendations: list[dict[str, Any]] | None = None,
    risk_structure: dict[str, Any] | None = None,
    review_dashboard: dict[str, Any] | None = None,
    part_family_classification: dict[str, Any] | None = None,
    family_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    canonical = build_canonical_three_table_bundle(
        process_flow=process_flow,
        pfmea=pfmea,
        control_plan=control_plan,
    )
    return build_three_table_generation_envelope(
        status=status,
        drawing_analysis=drawing_analysis,
        process_flow=canonical["process_flow"],
        pfmea=canonical["pfmea"],
        control_plan=canonical["control_plan"],
        chain=chain,
        quality_gates=quality_gates,
        exports=exports,
        output_dir=output_dir,
        inputs=inputs,
        blocked_stage=blocked_stage,
        warnings=warnings,
        manual_review=manual_review,
        linkage_map=linkage_map,
        linkage_gaps=linkage_gaps,
        characteristic_registry=characteristic_registry,
        knowledge_recommendations=knowledge_recommendations,
        risk_structure=risk_structure,
        review_dashboard=review_dashboard,
        part_family_classification=part_family_classification,
        family_context=family_context,
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_review_source_payload(source: str | Path | dict[str, Any]) -> dict[str, Any]:
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
    if isinstance(review_patch, dict):
        return review_patch
    path = Path(review_patch)
    if path.is_dir():
        raise ValueError("review patch must be a JSON file, not a directory")
    return read_json_object(path)


def _write_json_file(output_path: str | Path, payload: dict[str, Any]) -> Path:
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
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return value


def validate_fixture(fixture: str | Path | dict[str, Any]) -> Any:
    """Load an APQP fixture, build the domain chain, and validate it."""

    payload = load_fixture_payload(fixture)
    chain = _build_chain(payload)
    result = _validate_chain(chain)
    if not result:
        raise ValueError("APQP chain validation failed:\n" + "\n".join(result.messages))
    return result


def export_fixture(
    fixture: str | Path | dict[str, Any],
    output_path: str | Path | None = None,
    manifest_output: str | Path | None = None,
) -> Path:
    """Run the shared final export gate and export the fixed Chinese workbook."""

    payload = load_fixture_payload(fixture)
    chain = _build_chain(payload)
    require_export_gate(chain)
    destination = (
        Path(output_path)
        if output_path is not None
        else _default_output_path(fixture, chain)
    )
    exported = export_apqp_workbook(
        chain, destination, require_gate=False, export_mode="final"
    )
    if manifest_output is not None:
        gate = evaluate_export_gate(chain)
        _write_manifest_file(
            manifest_output,
            inputs=fixture,
            outputs={"export_path": exported},
            stage_results=[],
            quality_gates=[gate.model_dump()],
            review_confirmations=list(
                payload.get("metadata", {}).get(REVIEW_CONFIRMATIONS_KEY, [])
            ),
            artifacts={"final_export": exported},
            warnings=[],
        )
    return exported


def export_draft_fixture(
    fixture: str | Path | dict[str, Any],
    output_path: str | Path | None = None,
    manifest_output: str | Path | None = None,
) -> Path:
    """Export a draft-only APQP workbook with review warnings and gate details."""

    payload = load_fixture_payload(fixture)
    chain = _build_chain(payload)
    quality_gate = evaluate_export_gate(chain)
    destination = (
        Path(output_path)
        if output_path is not None
        else _default_output_path(fixture, chain)
    )
    exported = export_apqp_workbook(
        chain,
        destination,
        require_gate=False,
        export_mode="draft",
        quality_gate=quality_gate,
    )
    if manifest_output is not None:
        _write_manifest_file(
            manifest_output,
            inputs=fixture,
            outputs={"export_path": exported},
            stage_results=[],
            quality_gates=[quality_gate.model_dump()],
            review_confirmations=list(
                payload.get("metadata", {}).get(REVIEW_CONFIRMATIONS_KEY, [])
            ),
            artifacts={"draft_export": exported},
            warnings=[DRAFT_WARNING],
        )
    return exported



def assemble_generated_apqp_chain(
    process_flow: dict[str, Any] | None = None,
    failure_mode_candidates: dict[str, Any] | None = None,
    pfmea: dict[str, Any] | None = None,
    control_plan: dict[str, Any] | None = None,
    *,
    pfd: dict[str, Any] | None = None,
    brainstorm: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble generated APQP bundles through the stage implementation."""

    return _assemble_generated_apqp_chain(
        pfd if process_flow is None else process_flow,
        brainstorm if failure_mode_candidates is None else failure_mode_candidates,
        pfmea,
        control_plan,
        metadata=metadata,
    )


def _build_chain(payload: dict[str, Any]) -> Any:
    from .domain import APQPChain

    if hasattr(APQPChain, "model_validate"):
        return APQPChain.model_validate(payload)
    if hasattr(APQPChain, "parse_obj"):
        return APQPChain.parse_obj(payload)
    return APQPChain(**payload)


def _validate_chain(chain: Any) -> Any:
    from .validation import validate_chain

    return validate_chain(chain)


def _default_output_path(fixture: str | Path | dict[str, Any], chain: Any) -> Path:
    if isinstance(fixture, (str, Path)):
        return Path(fixture).with_suffix(".xlsx")
    slug = _chain_value(chain, "slug", "id", default="apqp_chain")
    return Path(f"{slug}.xlsx")


def _chain_value(chain: Any, *names: str, default: str) -> str:
    for name in names:
        if isinstance(chain, dict) and name in chain:
            return str(chain[name])
        if hasattr(chain, name):
            return str(getattr(chain, name))
    return default
