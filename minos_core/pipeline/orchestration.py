"""Core pipeline orchestration for APQP workflow."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..exporters.three_table_workbooks import (
    export_split_three_table_workbooks,
    export_three_table_workbook,
)
from ..quality_gates import StageQualityGate, evaluate_export_gate
from ..special_characteristic_candidates import strip_unconfirmed_special_characteristic_refs
from ..stage import assemble_generated_apqp_chain as _assemble_generated_apqp_chain
from ..three_table_result import (
    build_three_table_generation_envelope,
)
from ..three_table_result import (
    dedupe_strings as _dedupe_strings,
)
from ..three_table_result import (
    three_table_manual_review as _three_table_manual_review,
)
from .drawing_analysis import analyze_drawing_for_three_table_chain
from .utilities import (
    _dump_json_value,
    _last_quality_gate,
    _write_json_file,
    _write_manifest_file,
)

# Pipeline stage definitions
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

GENERATED_DRAFT_STAGES = (
    "ingest",
    "analyze",
    "generate_pfd",
    "brainstorm_failure_modes",
    "generate_pfmea",
    "generate_control_plan",
    "assemble_generated_apqp_chain",
)

# Warning messages
DRAFT_WARNING = (
    "当前结果仅为 APQP 工程草案，不是正式导出文件；必须经过质量门检查和人工工程复核后，"
    "才能用于正式放行。"
)

THREE_TABLE_DRAFT_WARNING = (
    "AI 图纸生成的 PFD/PFMEA/CP 仅为工程草案；必须经过质量门和人工复核确认后，"
    "才能作为正式工程文件使用。"
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

    from ..stage import run_stage

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

    # Load external plugins once (idempotent — logs failures, never crashes)
    from ..plugins import load_entry_point_plugins

    load_entry_point_plugins()

    from ..characteristic_registry import attach_characteristics_to_three_tables, build_characteristic_registry
    from ..drawing_to_pfd import infer_process_flow_from_drawing
    from ..generate_control_plan import generate_control_plan_from_pfmea
    from ..pfd_to_pfmea_ai import infer_pfmea_from_process_flow
    from ..quality_gates import (
        evaluate_control_plan_bundle_gate,
        evaluate_pfd_bundle_gate,
        evaluate_pfmea_bundle_gate,
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
    analysis_result["context"]
    analysis_result["analysis_mode"]
    analysis_result["ocr_engine"]
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


def _generate_pfd_stage(
    drawing_analysis: dict[str, Any],
    family_context: dict[str, Any],
    registry: dict[str, Any],
    infer_process_flow_from_drawing: Callable[..., dict[str, Any]],
    attach_characteristics_to_three_tables: Callable[..., dict[str, Any]],
    evaluate_pfd_bundle_gate: Callable[..., StageQualityGate],
) -> dict[str, Any]:
    """Infer PFD from drawing analysis and evaluate quality gate."""
    process_flow = infer_process_flow_from_drawing(
        drawing_analysis,
        family_context=family_context or None,
    )
    if registry and registry.get("items"):
        process_flow = attach_characteristics_to_three_tables(
            {"process_flow": process_flow}, registry
        )["process_flow"]
    strip_unconfirmed_special_characteristic_refs(process_flow, registry)
    pfd_gate = evaluate_pfd_bundle_gate(process_flow, stage="drawing_to_pfd")
    return {"process_flow": process_flow, "pfd_gate": pfd_gate}


def _generate_pfmea_stage(
    process_flow: dict[str, Any],
    registry: dict[str, Any],
    infer_pfmea_from_process_flow: Callable[..., dict[str, Any]],
    attach_characteristics_to_three_tables: Callable[..., dict[str, Any]],
    evaluate_pfmea_bundle_gate: Callable[..., StageQualityGate],
) -> dict[str, Any]:
    """Infer PFMEA from process flow and evaluate quality gate."""
    pfmea = infer_pfmea_from_process_flow(process_flow)
    if registry and registry.get("items"):
        attached = attach_characteristics_to_three_tables(
            {"process_flow": process_flow, "pfmea": pfmea}, registry
        )
        process_flow = attached["process_flow"]
        pfmea = attached["pfmea"]
    strip_unconfirmed_special_characteristic_refs(process_flow, registry)
    strip_unconfirmed_special_characteristic_refs(pfmea, registry)
    pfmea_gate = evaluate_pfmea_bundle_gate(pfmea, stage="pfd_to_pfmea")
    return {"process_flow": process_flow, "pfmea": pfmea, "pfmea_gate": pfmea_gate}


def _generate_cp_stage(
    process_flow: dict[str, Any],
    pfmea: dict[str, Any],
    registry: dict[str, Any],
    generate_control_plan_from_pfmea: Callable[..., dict[str, Any]],
    attach_characteristics_to_three_tables: Callable[..., dict[str, Any]],
    evaluate_control_plan_bundle_gate: Callable[..., StageQualityGate],
) -> dict[str, Any]:
    """Generate control plan from PFMEA and evaluate quality gate."""
    control_plan = generate_control_plan_from_pfmea(pfmea)
    if registry and registry.get("items"):
        attached = attach_characteristics_to_three_tables(
            {"process_flow": process_flow, "pfmea": pfmea, "control_plan": control_plan}, registry
        )
        process_flow = attached["process_flow"]
        pfmea = attached["pfmea"]
        control_plan = attached["control_plan"]
    strip_unconfirmed_special_characteristic_refs(process_flow, registry)
    strip_unconfirmed_special_characteristic_refs(pfmea, registry)
    strip_unconfirmed_special_characteristic_refs(control_plan, registry)
    control_plan_gate = evaluate_control_plan_bundle_gate(
        control_plan, stage="pfmea_to_control_plan"
    )
    return {
        "process_flow": process_flow, "pfmea": pfmea,
        "control_plan": control_plan, "control_plan_gate": control_plan_gate,
    }


def _build_chain_analysis(
    chain: dict[str, Any],
    registry: dict[str, Any],
    part_family_classification: dict[str, Any] | None,
    family_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build action items, linkage, risk structure, and review dashboard."""
    from ..action_tracking import action_items_summary, build_action_items
    from ..edit_patch import evaluate_edit_export_gate
    from ..edit_patch_reports import build_review_dashboard
    from ..risk_structure import build_risk_structure
    from ..three_table_linkage import build_three_table_linkage_map, evaluate_three_table_linkage

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
    review_dashboard = build_review_dashboard(
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
    chain: dict[str, Any],
    target_dir: Path,
    export_mode: str,
    final_gate: StageQualityGate,
    quality_gates: dict[str, Any],
    analysis_source: str,
    analysis_warnings: list[str],
    drawing_analysis: dict[str, Any],
    process_flow: dict[str, Any],
    pfmea: dict[str, Any],
    control_plan: dict[str, Any],
    pipeline_inputs: dict[str, Any],
    linkage_map: dict[str, Any],
    linkage_gaps: list[dict[str, Any]],
    registry: dict[str, Any],
    knowledge_recs: list[dict[str, Any]],
    risk_structure: dict[str, Any],
    review_dashboard: dict[str, Any],
    part_family_classification: dict[str, Any] | None,
    family_context: dict[str, Any] | None,
) -> dict[str, Any]:
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
    from ..knowledge_recommendation import recommend_from_knowledge

    chain = {
        "document_type": "apqp_chain",
        "schema_version": "minos-core.generated.v1",
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
    drawing_risks = _drawing_analysis_risks(drawing_analysis)
    if drawing_risks:
        chain["metadata"]["drawing_analysis_risks"] = drawing_risks
    chain["metadata"]["part_family_classification"] = part_family_classification or {}
    chain["metadata"]["family_context"] = family_context or {}
    chain["metadata"]["knowledge_recommendations"] = recommend_from_knowledge(
        chain,
        family_context=family_context or None,
    )
    return chain


def _drawing_analysis_risks(drawing_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = drawing_analysis.get("metadata", {})
    if not isinstance(metadata, dict):
        return []
    risks: list[dict[str, Any]] = []
    indexes: dict[str, int] = {}
    for key in ("drawing_analysis_risks", "ocr_identity_risks"):
        values = metadata.get(key, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            risk_id = str(item.get("risk_id", item.get("item_id", ""))).strip()
            if not risk_id:
                continue
            risk = dict(item)
            if risk_id in indexes:
                existing_index = indexes[risk_id]
                if (
                    risk.get("severity") == "blocker"
                    and risks[existing_index].get("severity") != "blocker"
                ):
                    risks[existing_index] = risk
                continue
            indexes[risk_id] = len(risks)
            risks.append(risk)
    return risks


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
    """Build three-table generation envelope."""
    return build_three_table_generation_envelope(
        status=status,
        drawing_analysis=drawing_analysis,
        process_flow=process_flow,
        pfmea=pfmea,
        control_plan=control_plan,
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


def _draft_envelope(
    *,
    draft: dict[str, Any] | None,
    status: str,
    generated_stage_results: list[Any],
    validation_stage_result: Any | None,
    blocked_stage: str | None,
) -> dict[str, Any]:
    """Build draft generation envelope."""
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
