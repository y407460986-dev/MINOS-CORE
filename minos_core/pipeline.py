"""Pipeline entry points for APQP workflow orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .adapters.fixture_json import load_fixture_payload, read_json_object
from .exporters import export_apqp_workbook
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
    "Generated APQPChain draft only. It is not a formal export and requires "
    "quality-gate review plus manual engineering approval before release."
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
            else ["Final export is not allowed by the export quality gate."],
        )
    return envelope


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
