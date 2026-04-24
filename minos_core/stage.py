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
    from .domain import Evidence
    from .exporters import export_apqp_workbook
    from .ingest import ingest_evidence_bundle
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


def _dump_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return vars(value)
    return value
