"""Pipeline entry points for APQP workflow orchestration."""

from __future__ import annotations

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
from .stage import assemble_generated_apqp_chain as _assemble_generated_apqp_chain


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
    *,
    analyzer: Any | None = None,
) -> dict[str, Any]:
    """Generate drawing-driven PFD/PFMEA/CP drafts and export workbooks.

    The default export mode is draft. A final export is blocked unless the final
    export quality gate allows user export, which normally requires human review
    of AI-inferred drawing content.
    """

    from .adapters.multimodal import OpenAIResponsesMultimodalDrawingAnalyzer
    from .drawing_analysis import analyze_drawing_pages, evaluate_drawing_recognition_gate
    from .drawing_input import load_drawing_source, render_drawing_pages
    from .drawing_to_pfd import infer_process_flow_from_drawing
    from .generate_control_plan import generate_control_plan_from_pfmea
    from .pfd_to_pfmea_ai import infer_pfmea_from_process_flow
    from .quality_gates import (
        evaluate_control_plan_bundle_gate,
        evaluate_pfmea_bundle_gate,
        evaluate_pfd_bundle_gate,
    )

    if export_mode not in {"draft", "final"}:
        raise ValueError("export_mode must be 'draft' or 'final'")

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    context_payload = dict(context or {})

    source = load_drawing_source(drawing_path)
    pages = render_drawing_pages(source, target_dir / "pages")
    active_analyzer = analyzer if analyzer is not None else OpenAIResponsesMultimodalDrawingAnalyzer()
    drawing_analysis = analyze_drawing_pages(pages, active_analyzer, context_payload)
    drawing_gate = evaluate_drawing_recognition_gate(drawing_analysis)
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
            inputs={"drawing_path": str(drawing_path), "context": context_payload},
            blocked_stage="drawing_recognition",
            warnings=["图纸识别质量门未通过，已阻止继续推导过程流程图。"],
        )

    process_flow = infer_process_flow_from_drawing(drawing_analysis)
    pfd_gate = evaluate_pfd_bundle_gate(process_flow, stage="drawing_to_pfd")
    if not pfd_gate.can_continue:
        return _three_table_generation_envelope(
            status="blocked",
            drawing_analysis=drawing_analysis,
            process_flow=process_flow,
            pfmea=None,
            control_plan=None,
            chain=None,
            quality_gates={
                "drawing_recognition": drawing_gate.model_dump(),
                "process_flow": pfd_gate.model_dump(),
            },
            exports={},
            output_dir=target_dir,
            inputs={"drawing_path": str(drawing_path), "context": context_payload},
            blocked_stage="process_flow",
            warnings=["过程流程图质量门未通过，已阻止继续推导 PFMEA。"],
        )

    pfmea = infer_pfmea_from_process_flow(process_flow)
    pfmea_gate = evaluate_pfmea_bundle_gate(pfmea, stage="pfd_to_pfmea")
    if not pfmea_gate.can_continue:
        return _three_table_generation_envelope(
            status="blocked",
            drawing_analysis=drawing_analysis,
            process_flow=process_flow,
            pfmea=pfmea,
            control_plan=None,
            chain=None,
            quality_gates={
                "drawing_recognition": drawing_gate.model_dump(),
                "process_flow": pfd_gate.model_dump(),
                "pfmea": pfmea_gate.model_dump(),
            },
            exports={},
            output_dir=target_dir,
            inputs={"drawing_path": str(drawing_path), "context": context_payload},
            blocked_stage="pfmea",
            warnings=["PFMEA 质量门未通过，已阻止继续生成控制计划。"],
        )

    control_plan = generate_control_plan_from_pfmea(pfmea)
    control_plan_gate = evaluate_control_plan_bundle_gate(
        control_plan, stage="pfmea_to_control_plan"
    )
    chain = _assemble_three_table_chain(drawing_analysis, process_flow, pfmea, control_plan)
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
            process_flow=process_flow,
            pfmea=pfmea,
            control_plan=control_plan,
            chain=chain,
            quality_gates=quality_gates,
            exports={},
            output_dir=target_dir,
            inputs={"drawing_path": str(drawing_path), "context": context_payload},
            blocked_stage="control_plan",
            warnings=["控制计划质量门未通过，已阻止导出工作簿。"],
        )

    if export_mode == "final" and not final_gate.allow_user_export:
        return _three_table_generation_envelope(
            status="blocked",
            drawing_analysis=drawing_analysis,
            process_flow=process_flow,
            pfmea=pfmea,
            control_plan=control_plan,
            chain=chain,
            quality_gates=quality_gates,
            exports={},
            output_dir=target_dir,
            inputs={"drawing_path": str(drawing_path), "context": context_payload},
            blocked_stage="final_three_table",
            warnings=["最终三表质量门未通过，已阻止正式导出。"],
        )

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
        inputs={"drawing_path": str(drawing_path), "context": context_payload},
        blocked_stage=None,
        warnings=[] if status == "draft_ready" else [THREE_TABLE_DRAFT_WARNING],
        manual_review=manual_review,
    )


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
) -> dict[str, Any]:
    from .knowledge_recommendation import recommend_from_knowledge

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
    chain["metadata"]["knowledge_recommendations"] = recommend_from_knowledge(chain)
    return chain


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
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "document_type": "three_table_generation_result",
        "schema_version": "minos-core.three_table_generation_result.v1",
        "status": status,
        "status_display": _three_table_status_display(status),
        "blocked_stage": blocked_stage,
        "drawing_analysis": drawing_analysis,
        "process_flow": process_flow,
        "pfmea": pfmea,
        "control_plan": control_plan,
        "chain": chain,
        "quality_gate": quality_gates.get("final_three_table")
        or _last_mapping_value(quality_gates),
        "quality_gates": quality_gates,
        "exports": exports,
        "manifest": {},
        "manual_review": manual_review or _three_table_manual_review(quality_gates),
        "warnings": warnings,
    }
    manifest = build_run_manifest(
        inputs=inputs,
        outputs={"status": status, "exports": exports},
        stage_results=_three_table_stage_results(quality_gates),
        quality_gates=list(quality_gates.values()),
        review_confirmations=[],
        artifacts=_three_table_artifacts(
            drawing_analysis=drawing_analysis,
            process_flow=process_flow,
            pfmea=pfmea,
            control_plan=control_plan,
            chain=chain,
            exports=exports,
        ),
        warnings=warnings,
    )
    manifest_path = write_run_manifest(output_dir / "run_manifest.json", manifest)
    envelope["manifest"] = {
        "path": str(manifest_path),
        "run_id": manifest.get("run_id", ""),
        "artifact_hashes": manifest.get("artifact_hashes", {}),
    }
    return envelope


def _three_table_stage_results(quality_gates: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "stage": stage,
            "status": "ok" if gate.get("can_continue") else "blocked",
            "quality_gate": gate,
        }
        for stage, gate in quality_gates.items()
        if isinstance(gate, dict)
    ]


def _three_table_manual_review(quality_gates: dict[str, Any]) -> dict[str, Any]:
    items: list[Any] = []
    for gate in quality_gates.values():
        if not isinstance(gate, dict):
            continue
        items.extend(gate.get("manual_review_items", []))
        items.extend(gate.get("needs_confirmation_items", []))
    raw_items = _dedupe_manual_review_items(items)
    grouped_items = _group_three_table_manual_review_items(raw_items)
    return {
        "required": bool(raw_items),
        "items": grouped_items,
        "raw_items": raw_items,
        "raw_count": len(raw_items),
        "summary": _manual_review_summary(grouped_items, len(raw_items)),
    }


def _group_three_table_manual_review_items(items: list[Any]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for item in items:
        normalized = _manual_review_record(item)
        bucket_key = _manual_review_bucket_key(normalized)
        bucket = buckets.setdefault(
            bucket_key,
            {
                "item_id": bucket_key,
                "category": _manual_review_bucket_category(bucket_key),
                "message": _manual_review_bucket_message(bucket_key),
                "severity": _manual_review_bucket_severity(normalized),
                "severity_display": _manual_review_severity_display(
                    _manual_review_bucket_severity(normalized)
                ),
                "count": 0,
                "examples": [],
            },
        )
        bucket["count"] += 1
        if normalized["target"] and len(bucket["examples"]) < 8:
            bucket["examples"].append(normalized["target"])
        if normalized["severity"] == "blocker":
            bucket["severity"] = "blocker"
            bucket["severity_display"] = _manual_review_severity_display("blocker")
    return list(buckets.values())


def _manual_review_record(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        target = ""
        for field_name in ("item_id", "id", "field", "target"):
            value = str(item.get(field_name, "")).strip()
            if value:
                target = value
                break
        return {
            "target": target,
            "category": str(item.get("category", "")).strip(),
            "message": str(item.get("message", "")).strip(),
            "severity": str(item.get("severity", "review")).strip() or "review",
        }
    if hasattr(item, "__dict__"):
        return _manual_review_record(dict(item.__dict__))
    text = str(item).strip()
    return {
        "target": text,
        "category": "",
        "message": "",
        "severity": "review",
    }


def _manual_review_bucket_key(item: dict[str, str]) -> str:
    category = item.get("category", "")
    target = item.get("target", "")
    if category.startswith("drawing_recognition"):
        return "drawing_recognition"
    if category.startswith("pfd") or target.startswith(("process_step:", "trace_link:")):
        return "process_flow_review"
    if category.startswith("pfmea") or target.startswith(("PFMEA-", "failure_mode:")):
        return "pfmea_review"
    if category == "知识库推荐":
        return "pfmea_review"
    if category.startswith("control_plan") or target.startswith(("CP-", "control_item:")):
        return "control_plan_review"
    if category.startswith("evidence"):
        return "evidence_review"
    if category.startswith("row_needs_confirmation"):
        if target.startswith("failure_mode:"):
            return "pfmea_review"
        if target.startswith("control_item:"):
            return "control_plan_review"
        if target.startswith(("process_step:", "trace_link:")):
            return "process_flow_review"
        return "row_confirmation_review"
    return category or "manual_review"


def _manual_review_bucket_category(key: str) -> str:
    return {
        "drawing_recognition": "图纸识别复核",
        "process_flow_review": "过程流程图复核",
        "pfmea_review": "PFMEA 复核",
        "control_plan_review": "控制计划复核",
        "evidence_review": "证据链复核",
        "row_confirmation_review": "草案确认复核",
        "manual_review": "人工复核",
    }.get(key, "人工复核")


def _manual_review_bucket_message(key: str) -> str:
    return {
        "drawing_recognition": "图纸识别存在低置信度或待补字段，需要工程人员确认。",
        "process_flow_review": "过程流程图存在 AI 推断、空字段或顺序关系待确认。",
        "pfmea_review": "PFMEA 风险行为 AI 草案，需要确认高风险和不确定项。",
        "control_plan_review": "控制计划由 PFMEA 草案推导，需要确认规格、方法、频次和反应计划。",
        "evidence_review": "部分对象的证据引用需要确认，正式放行前不能忽略。",
        "row_confirmation_review": "部分草案对象标记为待确认，需要人工复核。",
        "manual_review": "存在需要人工确认的草案项。",
    }.get(key, "存在需要人工确认的草案项。")


def _manual_review_bucket_severity(item: dict[str, str]) -> str:
    return "blocker" if item.get("severity") == "blocker" else "review"


def _manual_review_severity_display(severity: str) -> str:
    return {"blocker": "阻断", "review": "需复核"}.get(severity, "需复核")


def _manual_review_summary(items: list[dict[str, Any]], raw_count: int) -> dict[str, Any]:
    return {
        "display_count": len(items),
        "raw_count": raw_count,
        "message": f"已将 {raw_count} 条明细复核项合并为 {len(items)} 类中文复核摘要。",
    }


def _three_table_status_display(status: str) -> str:
    return {
        "draft_ready": "草案已就绪",
        "needs_review": "待人工复核",
        "blocked": "已阻断",
    }.get(status, status)


def _dedupe_manual_review_items(items: list[Any]) -> list[Any]:
    """Collapse duplicate review entries from gate summaries without hiding risk."""

    result: list[Any] = []
    seen: set[str] = set()
    deferred_strings: list[str] = []
    for item in items:
        key = _manual_review_key(item)
        if not key:
            continue
        if isinstance(item, str):
            deferred_strings.append(item)
            continue
        if key in seen:
            continue
        result.append(item)
        seen.add(key)
    for item in deferred_strings:
        key = _manual_review_key(item)
        if key and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _manual_review_key(item: Any) -> str:
    if isinstance(item, str):
        return _canonical_manual_review_target(item.strip())
    if isinstance(item, dict):
        for field_name in ("item_id", "id", "field", "target"):
            value = str(item.get(field_name, "")).strip()
            if value:
                return _canonical_manual_review_target(value)
        return json.dumps(item, ensure_ascii=False, sort_keys=True)
    if hasattr(item, "__dict__"):
        return _manual_review_key(dict(item.__dict__))
    return _canonical_manual_review_target(str(item).strip())


def _canonical_manual_review_target(value: str) -> str:
    text = str(value).strip()
    if text.startswith("failure_mode:"):
        return "pfmea:" + text.split(":", 1)[1].strip()
    if text.startswith("control_item:"):
        return "control_plan:" + text.split(":", 1)[1].strip()
    if text.startswith("process_step:"):
        return "pfd:" + text.split(":", 1)[1].strip()
    if text.startswith("PFMEA-"):
        return "pfmea:" + text
    if text.startswith("CP-"):
        return "control_plan:" + text
    if re_match := _process_step_review_pattern(text):
        return "pfd:" + re_match
    return text


def _process_step_review_pattern(value: str) -> str:
    if value.startswith("P") and value[1:].isdigit():
        return value
    return ""


def _three_table_artifacts(
    *,
    drawing_analysis: dict[str, Any] | None,
    process_flow: dict[str, Any] | None,
    pfmea: dict[str, Any] | None,
    control_plan: dict[str, Any] | None,
    chain: dict[str, Any] | None,
    exports: dict[str, Any],
) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for name, payload in (
        ("drawing_analysis", drawing_analysis),
        ("process_flow", process_flow),
        ("pfmea", pfmea),
        ("control_plan", control_plan),
        ("chain", chain),
    ):
        if payload is not None:
            artifacts[name] = payload
    for name, path in exports.items():
        if path:
            artifacts[name] = path
    return artifacts


def _last_mapping_value(values: dict[str, Any]) -> Any:
    for value in reversed(list(values.values())):
        return value
    return None


def _dedupe_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


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
