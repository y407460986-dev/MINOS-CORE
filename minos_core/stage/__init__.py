"""Stage runner for MINOS-CORE pipelines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..domain import APQPChain
from ..quality_gates import evaluate_export_gate, evaluate_stage_gate
from ._utils import _dedupe_values
from .assembler import assemble_generated_apqp_chain
from .envelope import StageContext, StageResult


def build_stage_context(
    fixture: str | Path | dict[str, Any],
    stage: str = "validate",
    output_path: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> StageContext:
    from ..adapters.fixture_json import load_fixture_payload
    from ..pipeline import PIPELINE_STAGES

    if stage not in PIPELINE_STAGES:
        raise ValueError(f"unknown pipeline stage: {stage}")
    payload = load_fixture_payload(fixture)
    return StageContext(
        stage=stage,
        fixture=fixture,
        payload=payload,
        chain=APQPChain(**payload),
        output_path=Path(output_path) if output_path is not None else None,
        metadata=dict(metadata or {}),
    )


def build_stage_result(
    context: StageContext,
    output: Any = None,
    status: str | None = None,
) -> StageResult:
    if context.chain is None:
        raise ValueError("StageContext.chain is required")
    gate = evaluate_stage_gate(context.chain, stage=context.stage)
    resolved_status = status or ("ok" if gate.can_continue else "blocked")
    return StageResult(
        stage=context.stage,
        status=resolved_status,
        output=output,
        evidence=list(context.chain.evidence),
        pending_fields=list(gate.pending_fields),
        ai_inferred_items=list(gate.ai_inferred_items),
        quality_gate=gate,
    )


def run_stage(
    fixture: str | Path | dict[str, Any],
    stage: str,
    output_path: str | Path | None = None,
) -> StageResult:
    from ..analyze import analyze_evidence_bundle
    from ..brainstorm import brainstorm_failure_modes_from_pfd
    from ..domain import Evidence
    from ..exporters import export_apqp_workbook
    from ..generate_control_plan import generate_control_plan_from_pfmea
    from ..generate_pfmea import generate_pfmea_from_candidates
    from ..generate_pfd import generate_pfd_from_analysis
    from ..ingest import ingest_evidence_bundle
    from ..quality_gates import (
        evaluate_analysis_bundle_gate,
        evaluate_brainstorm_failure_modes_input_gate,
        evaluate_control_plan_bundle_gate,
        evaluate_failure_mode_candidates_gate,
        evaluate_pfmea_bundle_gate,
        evaluate_pfd_bundle_gate,
    )
    from ..validation import validate_chain

    if stage == "ingest":
        bundle = ingest_evidence_bundle(fixture)
        evidence = [Evidence.from_mapping(item) for item in bundle.get("evidence", [])]
        gate = evaluate_stage_gate(
            {"evidence": bundle.get("evidence", [])}, stage=stage
        )
        return StageResult(
            stage=stage,
            status="ok" if gate.can_continue else "blocked",
            output=bundle,
            evidence=evidence,
            pending_fields=list(gate.pending_fields),
            ai_inferred_items=list(gate.ai_inferred_items),
            quality_gate=gate,
        )

    if stage == "analyze":
        analysis_bundle = analyze_evidence_bundle(
            fixture if isinstance(fixture, dict) else ingest_evidence_bundle(fixture)
        )
        gate = evaluate_analysis_bundle_gate(analysis_bundle, stage=stage)
        evidence = [
            Evidence.from_mapping(item) for item in analysis_bundle.get("evidence", [])
        ]
        return StageResult(
            stage=stage,
            status="ok" if gate.can_continue else "blocked",
            output=analysis_bundle,
            evidence=evidence,
            pending_fields=list(gate.pending_fields),
            ai_inferred_items=list(gate.ai_inferred_items),
            quality_gate=gate,
        )

    if stage == "generate_pfd":
        pfd_bundle = (
            fixture
            if isinstance(fixture, dict)
            and fixture.get("document_type") == "process_flow"
            else generate_pfd_from_analysis(
                fixture
                if isinstance(fixture, dict)
                and fixture.get("document_type") == "analysis_bundle"
                else analyze_evidence_bundle(
                    fixture
                    if isinstance(fixture, dict)
                    else ingest_evidence_bundle(fixture)
                )
            )
        )
        gate = evaluate_pfd_bundle_gate(pfd_bundle, stage=stage)
        evidence = [
            Evidence.from_mapping(item) for item in pfd_bundle.get("evidence", [])
        ]
        return StageResult(
            stage=stage,
            status="ok" if gate.can_continue else "blocked",
            output=pfd_bundle,
            evidence=evidence,
            pending_fields=list(gate.pending_fields),
            ai_inferred_items=list(gate.ai_inferred_items),
            quality_gate=gate,
        )

    if stage == "brainstorm_failure_modes":
        if not (
            isinstance(fixture, dict) and fixture.get("document_type") == "process_flow"
        ):
            raise ValueError(
                "brainstorm_failure_modes stage requires a process_flow payload"
            )
        gate = evaluate_brainstorm_failure_modes_input_gate(fixture, stage=stage)
        evidence = [Evidence.from_mapping(item) for item in fixture.get("evidence", [])]
        if not gate.can_continue:
            return StageResult(
                stage=stage,
                status="blocked",
                output=fixture,
                evidence=evidence,
                pending_fields=list(gate.pending_fields),
                ai_inferred_items=list(gate.ai_inferred_items),
                quality_gate=gate,
            )
        candidates_bundle = brainstorm_failure_modes_from_pfd(fixture)
        candidates_gate = evaluate_failure_mode_candidates_gate(
            candidates_bundle, stage=stage
        )
        return StageResult(
            stage=stage,
            status="ok" if candidates_gate.can_continue else "blocked",
            output=candidates_bundle,
            evidence=evidence,
            pending_fields=list(candidates_gate.pending_fields),
            ai_inferred_items=list(candidates_gate.ai_inferred_items),
            quality_gate=candidates_gate,
        )

    if stage == "generate_pfmea":
        if isinstance(fixture, dict) and fixture.get("document_type") == "pfmea":
            pfmea_bundle = fixture
        else:
            candidates_bundle = fixture
            if not (
                isinstance(candidates_bundle, dict)
                and candidates_bundle.get("document_type")
                == "failure_mode_candidates"
            ):
                pfd_result = run_stage(fixture, stage="generate_pfd")
                if not pfd_result.ok:
                    return StageResult(
                        stage=stage,
                        status="blocked",
                        output=pfd_result.output,
                        evidence=pfd_result.evidence,
                        pending_fields=list(pfd_result.pending_fields),
                        ai_inferred_items=list(pfd_result.ai_inferred_items),
                        quality_gate=pfd_result.quality_gate,
                    )
                candidates_result = run_stage(
                    pfd_result.output, stage="brainstorm_failure_modes"
                )
                if not candidates_result.ok:
                    return StageResult(
                        stage=stage,
                        status="blocked",
                        output=candidates_result.output,
                        evidence=candidates_result.evidence,
                        pending_fields=list(candidates_result.pending_fields),
                        ai_inferred_items=list(candidates_result.ai_inferred_items),
                        quality_gate=candidates_result.quality_gate,
                    )
                candidates_bundle = candidates_result.output
            pfmea_bundle = generate_pfmea_from_candidates(candidates_bundle)
        gate = evaluate_pfmea_bundle_gate(pfmea_bundle, stage=stage)
        evidence = [
            Evidence.from_mapping(item) for item in pfmea_bundle.get("evidence", [])
        ]
        return StageResult(
            stage=stage,
            status="ok" if gate.can_continue else "blocked",
            output=pfmea_bundle,
            evidence=evidence,
            pending_fields=list(gate.pending_fields),
            ai_inferred_items=list(gate.ai_inferred_items),
            quality_gate=gate,
        )

    if stage == "generate_control_plan":
        if isinstance(fixture, dict) and fixture.get("document_type") == "control_plan":
            control_plan_bundle = fixture
        else:
            pfmea_bundle = fixture
            if not (
                isinstance(pfmea_bundle, dict)
                and pfmea_bundle.get("document_type") == "pfmea"
            ):
                pfmea_result = run_stage(fixture, stage="generate_pfmea")
                if not pfmea_result.ok:
                    return StageResult(
                        stage=stage,
                        status="blocked",
                        output=pfmea_result.output,
                        evidence=pfmea_result.evidence,
                        pending_fields=list(pfmea_result.pending_fields),
                        ai_inferred_items=list(pfmea_result.ai_inferred_items),
                        quality_gate=pfmea_result.quality_gate,
                    )
                pfmea_bundle = pfmea_result.output
            control_plan_bundle = generate_control_plan_from_pfmea(pfmea_bundle)
        gate = evaluate_control_plan_bundle_gate(control_plan_bundle, stage=stage)
        evidence = [
            Evidence.from_mapping(item)
            for item in control_plan_bundle.get("evidence", [])
        ]
        return StageResult(
            stage=stage,
            status="ok" if gate.can_continue else "blocked",
            output=control_plan_bundle,
            evidence=evidence,
            pending_fields=list(gate.pending_fields),
            ai_inferred_items=list(gate.ai_inferred_items),
            quality_gate=gate,
        )

    if stage == "assemble_generated_apqp_chain":
        if isinstance(fixture, dict) and fixture.get("document_type") == "apqp_chain":
            draft_payload = fixture
        elif isinstance(fixture, dict):
            draft_payload = assemble_generated_apqp_chain(fixture)
        else:
            control_plan_result = run_stage(fixture, stage="generate_control_plan")
            if not control_plan_result.ok:
                return StageResult(
                    stage=stage,
                    status="blocked",
                    output=control_plan_result.output,
                    evidence=control_plan_result.evidence,
                    pending_fields=list(control_plan_result.pending_fields),
                    ai_inferred_items=list(control_plan_result.ai_inferred_items),
                    quality_gate=control_plan_result.quality_gate,
                )
            pfmea_result = run_stage(fixture, stage="generate_pfmea")
            if not pfmea_result.ok:
                return StageResult(
                    stage=stage,
                    status="blocked",
                    output=pfmea_result.output,
                    evidence=pfmea_result.evidence,
                    pending_fields=list(pfmea_result.pending_fields),
                    ai_inferred_items=list(pfmea_result.ai_inferred_items),
                    quality_gate=pfmea_result.quality_gate,
                )
            pfd_result = run_stage(fixture, stage="generate_pfd")
            if not pfd_result.ok:
                return StageResult(
                    stage=stage,
                    status="blocked",
                    output=pfd_result.output,
                    evidence=pfd_result.evidence,
                    pending_fields=list(pfd_result.pending_fields),
                    ai_inferred_items=list(pfd_result.ai_inferred_items),
                    quality_gate=pfd_result.quality_gate,
                )
            candidates_result = run_stage(
                pfd_result.output, stage="brainstorm_failure_modes"
            )
            if not candidates_result.ok:
                return StageResult(
                    stage=stage,
                    status="blocked",
                    output=candidates_result.output,
                    evidence=candidates_result.evidence,
                    pending_fields=list(candidates_result.pending_fields),
                    ai_inferred_items=list(candidates_result.ai_inferred_items),
                    quality_gate=candidates_result.quality_gate,
                )
            draft_payload = assemble_generated_apqp_chain(
                pfd_result.output,
                candidates_result.output,
                pfmea_result.output,
                control_plan_result.output,
            )
        gate = evaluate_stage_gate(draft_payload, stage="validate")
        return StageResult(
            stage=stage,
            status="ok" if gate.can_continue else "blocked",
            output=draft_payload,
            evidence=[
                Evidence.from_mapping(item)
                for item in draft_payload.get("evidence", [])
            ],
            pending_fields=_dedupe_values(
                list(draft_payload.get("pending_fields", []))
                + list(gate.pending_fields)
            ),
            ai_inferred_items=_dedupe_values(
                list(draft_payload.get("ai_inferred_items", []))
                + list(gate.ai_inferred_items)
            ),
            quality_gate=gate,
        )

    if stage in {"generate_draft", "run_pipeline"}:
        from ..pipeline import generate_draft

        envelope = generate_draft(fixture, output_path)
        gate_payload = envelope.get("quality_gate")
        gate = _gate_from_dump(gate_payload) if isinstance(gate_payload, dict) else None
        draft = envelope.get("draft")
        evidence = [Evidence.from_mapping(item) for item in (draft or {}).get("evidence", [])]
        return StageResult(
            stage=stage,
            status="ok" if envelope.get("status") == "draft_ready" else "blocked",
            output=envelope,
            evidence=evidence,
            pending_fields=list((gate_payload or {}).get("pending_fields", [])),
            ai_inferred_items=list((gate_payload or {}).get("ai_inferred_items", [])),
            quality_gate=gate,
        )

    context = build_stage_context(fixture, stage=stage, output_path=output_path)
    if stage == "validate":
        result = validate_chain(context.chain)
        return build_stage_result(
            context, output=result, status="ok" if result else "failed"
        )
    if stage == "export":
        gate = evaluate_export_gate(context.chain)
        if not gate.allow_user_export:
            return StageResult(
                stage=stage,
                status="blocked",
                evidence=list(context.chain.evidence),
                pending_fields=list(gate.pending_fields),
                ai_inferred_items=list(gate.ai_inferred_items),
                quality_gate=gate,
            )
        if context.output_path is None:
            raise ValueError("output_path is required for export stage")
        exported = export_apqp_workbook(
            context.chain,
            context.output_path,
            require_gate=False,
            export_mode="final",
            quality_gate=gate,
        )
        return StageResult(
            stage=stage,
            status="ok",
            output=exported,
            evidence=list(context.chain.evidence),
            pending_fields=list(gate.pending_fields),
            ai_inferred_items=list(gate.ai_inferred_items),
            quality_gate=gate,
        )
    return build_stage_result(context)


def _gate_from_dump(payload: dict[str, Any]):
    from ..audit import audit_chain
    from ..quality_gates import StageQualityGate
    from ..validation import ChainValidationResult

    chain = APQPChain()
    validation = ChainValidationResult(
        ok=not bool(payload.get("validation_messages", [])),
        messages=list(payload.get("validation_messages", [])),
        chain=chain,
    )
    audit = audit_chain(chain)
    return StageQualityGate(
        stage=str(payload.get("stage", "validate")),
        can_continue=bool(payload.get("can_continue", False)),
        allow_user_export=bool(payload.get("allow_user_export", False)),
        validation=validation,
        audit=audit,
        evidence_sufficient=bool(payload.get("evidence_sufficient", False)),
        pending_fields=list(payload.get("pending_fields", [])),
        ai_inferred_items=list(payload.get("ai_inferred_items", [])),
        manual_review_items=list(payload.get("manual_review_items", [])),
        evidence_coverage=dict(payload.get("evidence_coverage", {})),
        missing_evidence_refs=list(payload.get("missing_evidence_refs", [])),
        uncovered_evidence_items=list(payload.get("uncovered_evidence_items", [])),
        needs_confirmation_items=list(payload.get("needs_confirmation_items", [])),
        review_issues=list(payload.get("review_issues", [])),
    )
