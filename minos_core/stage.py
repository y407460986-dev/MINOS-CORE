"""Stage context and result envelopes for MINOS-CORE pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .domain import APQPChain
from .quality_gates import StageQualityGate, evaluate_stage_gate


@dataclass(frozen=True)
class StageContext:
    stage: str
    fixture: str | Path | dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    chain: APQPChain | None = None
    output_path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "fixture": str(self.fixture) if self.fixture is not None else None,
            "has_payload": self.payload is not None,
            "has_chain": self.chain is not None,
            "output_path": str(self.output_path)
            if self.output_path is not None
            else None,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class StageResult:
    stage: str
    status: str
    output: Any = None
    evidence: list[Any] = field(default_factory=list)
    pending_fields: list[str] = field(default_factory=list)
    ai_inferred_items: list[str] = field(default_factory=list)
    quality_gate: StageQualityGate | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def model_dump(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "output": _dump_value(self.output),
            "evidence": [_dump_value(item) for item in self.evidence],
            "pending_fields": self.pending_fields,
            "ai_inferred_items": self.ai_inferred_items,
            "quality_gate": self.quality_gate.model_dump()
            if self.quality_gate
            else None,
        }


def build_stage_context(
    fixture: str | Path | dict[str, Any],
    stage: str = "validate",
    output_path: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> StageContext:
    from .adapters.fixture_json import load_fixture_payload
    from .pipeline import PIPELINE_STAGES

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
    from .analyze import analyze_evidence_bundle
    from .brainstorm import brainstorm_failure_modes_from_pfd
    from .domain import Evidence
    from .exporters import export_apqp_workbook
    from .generate_control_plan import generate_control_plan_from_pfmea
    from .generate_pfmea import generate_pfmea_from_candidates
    from .generate_pfd import generate_pfd_from_analysis
    from .ingest import ingest_evidence_bundle
    from .quality_gates import (
        evaluate_analysis_bundle_gate,
        evaluate_brainstorm_failure_modes_input_gate,
        evaluate_control_plan_bundle_gate,
        evaluate_failure_mode_candidates_gate,
        evaluate_pfmea_bundle_gate,
        evaluate_pfd_bundle_gate,
    )
    from .validation import validate_chain

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

    context = build_stage_context(fixture, stage=stage, output_path=output_path)
    if stage == "validate":
        result = validate_chain(context.chain)
        return build_stage_result(
            context, output=result, status="ok" if result else "failed"
        )
    if stage == "export":
        gate = evaluate_stage_gate(context.chain, stage=stage)
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
        exported = export_apqp_workbook(context.chain, context.output_path)
        return build_stage_result(context, output=exported, status="ok")
    return build_stage_result(context)


def assemble_generated_apqp_chain(
    process_flow: dict[str, Any] | None = None,
    failure_mode_candidates: dict[str, Any] | None = None,
    pfmea: dict[str, Any] | None = None,
    control_plan: dict[str, Any] | None = None,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble generated APQP stage bundles into a standard draft payload."""

    if _looks_like_stage_bundle_map(process_flow):
        bundle_map = process_flow or {}
        process_flow = _pick_bundle(bundle_map, "process_flow", "generate_pfd")
        failure_mode_candidates = _pick_bundle(
            bundle_map,
            "failure_mode_candidates",
            "brainstorm_failure_modes",
            "candidates",
        )
        pfmea = _pick_bundle(bundle_map, "pfmea", "generate_pfmea")
        control_plan = _pick_bundle(
            bundle_map, "control_plan", "generate_control_plan", "controls"
        )
    elif _looks_like_combined_stage_payload(process_flow):
        combined_payload = process_flow or {}
        process_flow = combined_payload.get("process_flow")
        failure_mode_candidates = combined_payload.get("failure_mode_candidates")
        pfmea = combined_payload.get("pfmea")
        control_plan = combined_payload.get("control_plan")
        if metadata is None and isinstance(combined_payload.get("metadata"), dict):
            metadata = combined_payload["metadata"]
    elif isinstance(process_flow, dict) and failure_mode_candidates is None and pfmea is None and control_plan is None:
        document_type = str(process_flow.get("document_type", ""))
        if document_type == "failure_mode_candidates":
            failure_mode_candidates = process_flow
            process_flow = None
        elif document_type == "pfmea":
            pfmea = process_flow
            process_flow = None
        elif document_type == "control_plan":
            control_plan = process_flow
            process_flow = None

    if pfmea is None and isinstance(process_flow, dict):
        embedded_pfmea = process_flow.get("pfmea")
        if isinstance(embedded_pfmea, dict):
            pfmea = embedded_pfmea
    if pfmea is None and isinstance(failure_mode_candidates, dict):
        embedded_pfmea = failure_mode_candidates.get("pfmea")
        if isinstance(embedded_pfmea, dict):
            pfmea = embedded_pfmea
    if control_plan is None:
        embedded_control_plan = None
        if isinstance(process_flow, dict):
            embedded_control_plan = process_flow.get("control_plan")
        if embedded_control_plan is None and isinstance(pfmea, dict):
            embedded_control_plan = pfmea.get("control_plan")
        if embedded_control_plan is None and isinstance(failure_mode_candidates, dict):
            embedded_control_plan = failure_mode_candidates.get("control_plan")
        if isinstance(embedded_control_plan, dict):
            control_plan = embedded_control_plan

    bundles = [
        bundle
        for bundle in (process_flow, failure_mode_candidates, pfmea, control_plan)
        if isinstance(bundle, dict)
    ]
    product = _first_mapping_value(
        [process_flow, failure_mode_candidates, pfmea, control_plan], "product"
    )
    schema_version = _first_text_value(
        [process_flow, failure_mode_candidates, pfmea, control_plan], "schema_version"
    )

    process_steps = list(
        (process_flow or {}).get("steps", (process_flow or {}).get("process_steps", []))
    )
    candidate_rows = list(
        (failure_mode_candidates or {}).get(
            "candidates",
            (failure_mode_candidates or {}).get("failure_mode_candidates", []),
        )
    )
    pfmea_rows = list((pfmea or {}).get("rows", (pfmea or {}).get("failure_modes", [])))
    control_rows = list(
        (control_plan or {}).get(
            "rows",
            (control_plan or {}).get(
                "controls", (control_plan or {}).get("control_plan_items", [])
            ),
        )
    )
    links = _dedupe_mappings(
        list((process_flow or {}).get("links", []))
        + list((failure_mode_candidates or {}).get("links", []))
        + list((pfmea or {}).get("links", []))
        + list((control_plan or {}).get("links", []))
        + _generated_pfd_pfmea_links(process_steps, candidate_rows, pfmea_rows)
        + _generated_pfmea_cp_links(pfmea_rows, control_rows)
    )
    assembled_metadata = _merge_metadata(bundles, metadata)
    assembled_metadata["generated"] = True
    assembled_metadata["requires_engineering_review"] = True

    return {
        "document_type": "apqp_chain",
        "schema_version": schema_version or "minos-core.generated.v1",
        "product": product,
        "process_steps": _dedupe_mappings(process_steps),
        "failure_mode_candidates": _dedupe_mappings(candidate_rows),
        "failure_modes": _dedupe_mappings(pfmea_rows),
        "controls": _dedupe_mappings(control_rows),
        "evidence": _merge_evidence(bundles),
        "links": links,
        "pending_fields": _merge_list_field(bundles, "pending_fields"),
        "ai_inferred_items": _merge_list_field(bundles, "ai_inferred_items"),
        "metadata": assembled_metadata,
    }


def _looks_like_stage_bundle_map(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("document_type") in {
        "process_flow",
        "failure_mode_candidates",
        "pfmea",
        "control_plan",
    }:
        return False
    return any(
        isinstance(value.get(key), dict)
        for key in (
            "process_flow",
            "generate_pfd",
            "failure_mode_candidates",
            "brainstorm_failure_modes",
            "pfmea",
            "generate_pfmea",
            "control_plan",
            "generate_control_plan",
        )
    )


def _looks_like_combined_stage_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return any(key in value for key in ("process_flow", "pfmea", "control_plan"))


def _pick_bundle(bundle_map: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        value = bundle_map.get(key)
        if isinstance(value, dict):
            return value
    return None


def _first_mapping_value(
    bundles: list[dict[str, Any] | None], field_name: str
) -> dict[str, Any]:
    for bundle in bundles:
        if isinstance(bundle, dict) and isinstance(bundle.get(field_name), dict):
            return dict(bundle[field_name])
    return {}


def _first_text_value(
    bundles: list[dict[str, Any] | None], field_name: str
) -> str:
    for bundle in bundles:
        if isinstance(bundle, dict):
            value = str(bundle.get(field_name, "")).strip()
            if value:
                return value
    return ""


def _merge_evidence(bundles: list[dict[str, Any]]) -> list[Any]:
    evidence: list[Any] = []
    for bundle in bundles:
        evidence.extend(_list_value(bundle, "evidence"))
    return _dedupe_values(evidence)


def _merge_list_field(bundles: list[dict[str, Any]], field_name: str) -> list[Any]:
    values: list[Any] = []
    for bundle in bundles:
        values.extend(_list_value(bundle, field_name))
    return _dedupe_values(values)


def _merge_metadata(
    bundles: list[dict[str, Any]], extra_metadata: dict[str, Any] | None
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    source_stages: list[str] = []
    generation_modes: list[str] = []
    for bundle in bundles:
        bundle_metadata = bundle.get("metadata", {})
        if not isinstance(bundle_metadata, dict):
            continue
        for key, value in bundle_metadata.items():
            if key == "source_stage" and value:
                source_stages.append(str(value))
            elif key == "generation_mode" and value:
                generation_modes.append(str(value))
            elif key not in merged:
                merged[key] = value
    if generation_modes:
        merged["generation_modes"] = _dedupe_values(generation_modes)
    if source_stages:
        merged["source_stages"] = _dedupe_values(source_stages)
    if extra_metadata:
        merged.update(extra_metadata)
    return merged


def _generated_pfd_pfmea_links(
    process_steps: list[Any], candidate_rows: list[Any], pfmea_rows: list[Any]
) -> list[dict[str, Any]]:
    step_ids = {
        step_id
        for step in process_steps
        if isinstance(step, dict)
        for step_id in [_text_value(step, "process_step_id", "id", "step_no")]
        if step_id
    }
    candidate_refs = {
        _text_value(candidate, "candidate_id", "id"): _list_value(candidate, "evidence_refs")
        for candidate in candidate_rows
        if isinstance(candidate, dict)
    }
    links: list[dict[str, Any]] = []
    for row in pfmea_rows:
        if not isinstance(row, dict):
            continue
        pfmea_id = _text_value(row, "pfmea_id", "id")
        step_id = _text_value(row, "process_step_id", "step_no", "step")
        if not pfmea_id or not step_id or (step_ids and step_id not in step_ids):
            continue
        source_candidate_id = _text_value(row, "source_candidate_id")
        evidence_refs = _list_value(row, "evidence_refs")
        if source_candidate_id and not evidence_refs:
            evidence_refs = candidate_refs.get(source_candidate_id, [])
        links.append(
            {
                "trace_link_id": f"TL-PFD-PFMEA-{step_id}-{pfmea_id}",
                "from": step_id,
                "to": pfmea_id,
                "from_id": step_id,
                "to_id": pfmea_id,
                "from_type": "process_flow_step",
                "to_type": "pfmea_row",
                "link_type": "pfd_to_pfmea",
                "evidence_refs": evidence_refs,
                "created_by_stage": "assemble_generated_apqp_chain",
            }
        )
    return links


def _generated_pfmea_cp_links(
    pfmea_rows: list[Any], control_rows: list[Any]
) -> list[dict[str, Any]]:
    pfmea_by_id = {
        _text_value(row, "pfmea_id", "id"): row
        for row in pfmea_rows
        if isinstance(row, dict) and _text_value(row, "pfmea_id", "id")
    }
    links: list[dict[str, Any]] = []
    for row in control_rows:
        if not isinstance(row, dict):
            continue
        control_plan_id = _text_value(row, "control_plan_id", "id")
        pfmea_id = _text_value(row, "pfmea_id", "source_pfmea_id")
        if not control_plan_id or not pfmea_id:
            continue
        evidence_refs = _list_value(row, "evidence_refs")
        if not evidence_refs and pfmea_id in pfmea_by_id:
            evidence_refs = _list_value(pfmea_by_id[pfmea_id], "evidence_refs")
        links.append(
            {
                "trace_link_id": f"TL-PFMEA-CP-{pfmea_id}-{control_plan_id}",
                "from": pfmea_id,
                "to": control_plan_id,
                "from_id": pfmea_id,
                "to_id": control_plan_id,
                "from_type": "pfmea_row",
                "to_type": "control_plan_row",
                "link_type": "pfmea_to_control_plan",
                "evidence_refs": evidence_refs,
                "created_by_stage": "assemble_generated_apqp_chain",
            }
        )
    return links


def _dedupe_mappings(values: list[Any]) -> list[Any]:
    return _dedupe_values(values)


def _dedupe_values(values: list[Any]) -> list[Any]:
    deduped: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = _dedupe_key(value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _dedupe_key(value: Any) -> str:
    if isinstance(value, dict):
        for key in (
            "evidence_id",
            "trace_link_id",
            "candidate_id",
            "pfmea_id",
            "control_plan_id",
            "process_step_id",
        ):
            text = str(value.get(key, "")).strip()
            if text:
                return f"{key}:{text}"
        from_id = str(value.get("from", value.get("from_id", ""))).strip()
        to_id = str(value.get("to", value.get("to_id", ""))).strip()
        link_type = str(value.get("link_type", "")).strip()
        if from_id or to_id or link_type:
            return f"link:{from_id}:{to_id}:{link_type}"
    return repr(value)


def _text_value(row: dict[str, Any], *field_names: str) -> str:
    for field_name in field_names:
        value = row.get(field_name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _list_value(row: dict[str, Any], field_name: str) -> list[Any]:
    value = row.get(field_name, [])
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    text = str(value).strip()
    return [text] if text else []


def _dump_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return vars(value)
    return value
