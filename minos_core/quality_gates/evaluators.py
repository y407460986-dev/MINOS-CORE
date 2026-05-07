"""Bundle gate evaluators — thin wrappers over report functions."""
from __future__ import annotations

from typing import Any

from ..audit import audit_chain
from ..domain import APQPChain
from ..schemas import validate_bundle_schema
from ..validation import ChainValidationResult

from ._report_analysis import (
    _analysis_bundle_report,
    _analysis_manual_review_items,
    _failure_mode_candidates_manual_review_items,
    _failure_mode_candidates_report,
)
from ._report_pfd import (
    _pfd_bundle_report,
    _pfd_manual_review_items,
)
from ._report_pfmea_cp import (
    _control_plan_bundle_report,
    _control_plan_manual_review_items,
    _pfmea_bundle_report,
    _pfmea_manual_review_items,
)


def _validate_versioned_bundle_schema(
    payload: dict[str, Any], document_type: str
) -> None:
    if isinstance(payload, dict) and "schema_version" not in payload:
        return
    validate_bundle_schema(payload, document_type)


def evaluate_analysis_bundle_gate(
    analysis_bundle: dict[str, Any],
    stage: str = "analyze",
) -> "StageQualityGate":
    from . import StageQualityGate  # late import to avoid circular dependency

    _validate_versioned_bundle_schema(analysis_bundle, "analysis_bundle")
    validation = ChainValidationResult(ok=True, messages=[], chain=APQPChain())
    audit = audit_chain(APQPChain())
    report = _analysis_bundle_report(analysis_bundle)
    manual_review_items = _analysis_manual_review_items(report, analysis_bundle)
    can_continue = bool(report["ok"])
    return StageQualityGate(
        stage=stage,
        can_continue=can_continue,
        allow_user_export=False,
        validation=validation,
        audit=audit,
        evidence_sufficient=bool(report["evidence_sufficient"]),
        pending_fields=list(report["pending_fields"]),
        ai_inferred_items=list(report["ai_inferred_refs"]),
        manual_review_items=manual_review_items,
        evidence_coverage=report,
        missing_evidence_refs=list(report["missing_refs"]),
        uncovered_evidence_items=list(report["uncovered_items"]),
        needs_confirmation_items=list(report["needs_confirmation_refs"]),
    )


def evaluate_pfd_bundle_gate(
    pfd_bundle: dict[str, Any],
    stage: str = "generate_pfd",
) -> "StageQualityGate":
    from . import StageQualityGate  # late import to avoid circular dependency

    _validate_versioned_bundle_schema(pfd_bundle, "process_flow")
    validation = ChainValidationResult(ok=True, messages=[], chain=APQPChain())
    audit = audit_chain(APQPChain())
    report = _pfd_bundle_report(
        pfd_bundle,
        stage_mode="generate_pfd",
        next_stage="brainstorm_failure_modes",
    )
    return StageQualityGate(
        stage=stage,
        can_continue=bool(report["ok"]),
        allow_user_export=False,
        validation=validation,
        audit=audit,
        evidence_sufficient=bool(report["evidence_sufficient"]),
        pending_fields=list(report["pending_fields"]),
        ai_inferred_items=list(report["ai_inferred_refs"]),
        manual_review_items=_pfd_manual_review_items(report),
        evidence_coverage=report,
        missing_evidence_refs=list(report["missing_refs"]),
        uncovered_evidence_items=list(report["uncovered_items"]),
        needs_confirmation_items=list(report["needs_confirmation_refs"]),
    )


def evaluate_brainstorm_failure_modes_input_gate(
    process_flow: dict[str, Any],
    stage: str = "brainstorm_failure_modes",
) -> "StageQualityGate":
    from . import StageQualityGate  # late import to avoid circular dependency

    _validate_versioned_bundle_schema(process_flow, "process_flow")
    validation = ChainValidationResult(ok=True, messages=[], chain=APQPChain())
    audit = audit_chain(APQPChain())
    report = _pfd_bundle_report(
        process_flow,
        stage_mode="brainstorm_failure_modes_preflight",
        next_stage="brainstorm_failure_modes",
        require_operation=False,
    )
    return StageQualityGate(
        stage=stage,
        can_continue=bool(report["ok"]),
        allow_user_export=False,
        validation=validation,
        audit=audit,
        evidence_sufficient=bool(report["evidence_sufficient"]),
        pending_fields=list(report["pending_fields"]),
        ai_inferred_items=list(report["ai_inferred_refs"]),
        manual_review_items=_pfd_manual_review_items(report),
        evidence_coverage=report,
        missing_evidence_refs=list(report["missing_refs"]),
        uncovered_evidence_items=list(report["uncovered_items"]),
        needs_confirmation_items=list(report["needs_confirmation_refs"]),
    )


def evaluate_failure_mode_candidates_gate(
    candidates_bundle: dict[str, Any],
    stage: str = "brainstorm_failure_modes",
) -> "StageQualityGate":
    from . import StageQualityGate  # late import to avoid circular dependency

    _validate_versioned_bundle_schema(candidates_bundle, "failure_mode_candidates")
    validation = ChainValidationResult(ok=True, messages=[], chain=APQPChain())
    audit = audit_chain(APQPChain())
    report = _failure_mode_candidates_report(candidates_bundle)
    return StageQualityGate(
        stage=stage,
        can_continue=bool(report["ok"]),
        allow_user_export=False,
        validation=validation,
        audit=audit,
        evidence_sufficient=bool(report["evidence_sufficient"]),
        pending_fields=list(report["pending_fields"]),
        ai_inferred_items=list(report["ai_inferred_refs"]),
        manual_review_items=_failure_mode_candidates_manual_review_items(report),
        evidence_coverage=report,
        missing_evidence_refs=list(report["missing_refs"]),
        uncovered_evidence_items=list(report["uncovered_items"]),
        needs_confirmation_items=list(report["needs_confirmation_refs"]),
    )


def evaluate_pfmea_bundle_gate(
    pfmea_bundle: dict[str, Any],
    stage: str = "generate_pfmea",
) -> "StageQualityGate":
    from . import StageQualityGate  # late import to avoid circular dependency

    _validate_versioned_bundle_schema(pfmea_bundle, "pfmea")
    validation = ChainValidationResult(ok=True, messages=[], chain=APQPChain())
    audit = audit_chain(APQPChain())
    report = _pfmea_bundle_report(pfmea_bundle)
    return StageQualityGate(
        stage=stage,
        can_continue=bool(report["ok"]),
        allow_user_export=False,
        validation=validation,
        audit=audit,
        evidence_sufficient=bool(report["evidence_sufficient"]),
        pending_fields=list(report["pending_fields"]),
        ai_inferred_items=list(report["ai_inferred_refs"]),
        manual_review_items=_pfmea_manual_review_items(report),
        evidence_coverage=report,
        missing_evidence_refs=list(report["missing_refs"]),
        uncovered_evidence_items=list(report["uncovered_items"]),
        needs_confirmation_items=list(report["needs_confirmation_refs"]),
    )


def evaluate_control_plan_bundle_gate(
    control_plan_bundle: dict[str, Any],
    stage: str = "generate_control_plan",
) -> "StageQualityGate":
    from . import StageQualityGate  # late import to avoid circular dependency

    _validate_versioned_bundle_schema(control_plan_bundle, "control_plan")
    validation = ChainValidationResult(ok=True, messages=[], chain=APQPChain())
    audit = audit_chain(APQPChain())
    report = _control_plan_bundle_report(control_plan_bundle)
    return StageQualityGate(
        stage=stage,
        can_continue=bool(report["ok"]),
        allow_user_export=False,
        validation=validation,
        audit=audit,
        evidence_sufficient=bool(report["evidence_sufficient"]),
        pending_fields=list(report["pending_fields"]),
        ai_inferred_items=list(report["ai_inferred_refs"]),
        manual_review_items=_control_plan_manual_review_items(report),
        evidence_coverage=report,
        missing_evidence_refs=list(report["missing_refs"]),
        uncovered_evidence_items=list(report["uncovered_items"]),
        needs_confirmation_items=list(report["needs_confirmation_refs"]),
    )
