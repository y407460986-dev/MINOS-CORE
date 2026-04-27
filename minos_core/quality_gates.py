"""Stage-level quality gates for MINOS-CORE pipelines."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

from .action_closure import action_closure_issues
from .audit import AuditItem, AuditReport, audit_chain
from .change_management import blocking_change_impacts
from .domain import APQPChain
from .knowledge_recommendation import unresolved_recommendations
from .review_patch import REVIEW_CONFIRMATIONS_KEY
from .review_issues import (
    build_review_issue,
    review_issue_from_manual_item,
    unresolved_review_issues,
)
from .schemas import validate_bundle_schema
from .validation import ChainValidationResult, validate_chain


@dataclass(frozen=True)
class StageQualityGate:
    stage: str
    can_continue: bool
    allow_user_export: bool
    validation: ChainValidationResult
    audit: AuditReport
    evidence_sufficient: bool
    pending_fields: list[str] = field(default_factory=list)
    ai_inferred_items: list[str] = field(default_factory=list)
    manual_review_items: list[Any] = field(default_factory=list)
    evidence_coverage: dict[str, Any] = field(default_factory=dict)
    missing_evidence_refs: list[str] = field(default_factory=list)
    uncovered_evidence_items: list[str] = field(default_factory=list)
    needs_confirmation_items: list[str] = field(default_factory=list)
    review_issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.can_continue

    @property
    def needs_human_review(self) -> bool:
        return bool(self.manual_review_items or self.needs_confirmation_items)

    @property
    def allow_formal_release(self) -> bool:
        return self.allow_user_export

    @property
    def draft_only(self) -> bool:
        return bool(
            self.can_continue
            and not self.allow_formal_release
            and self.needs_confirmation_items
        )

    def model_dump(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "can_continue": self.can_continue,
            "allow_user_export": self.allow_user_export,
            "allow_formal_release": self.allow_formal_release,
            "needs_human_review": self.needs_human_review,
            "draft_only": self.draft_only,
            "evidence_sufficient": self.evidence_sufficient,
            "pending_fields": self.pending_fields,
            "ai_inferred_items": self.ai_inferred_items,
            "evidence_coverage": self.evidence_coverage,
            "missing_evidence_refs": self.missing_evidence_refs,
            "uncovered_evidence_items": self.uncovered_evidence_items,
            "needs_confirmation_items": self.needs_confirmation_items,
            "review_issues": self.review_issues,
            "manual_review_items": [
                item.__dict__ if hasattr(item, "__dict__") else item
                for item in self.manual_review_items
            ],
            "validation_messages": self.validation.messages,
            "audit_counts": self.audit.counts,
        }


class ExportGateError(ValueError):
    """Raised when a user-facing export is blocked by the export gate."""

    def __init__(self, gate: StageQualityGate) -> None:
        self.gate = gate
        super().__init__(_export_gate_failure_message(gate))


def evaluate_export_gate(chain: APQPChain | dict[str, Any]) -> StageQualityGate:
    """Evaluate the single quality gate used by every export path."""

    return evaluate_stage_gate(chain, stage="export")


def require_export_gate(chain: APQPChain | dict[str, Any]) -> StageQualityGate:
    """Return the export gate or raise before any workbook is written."""

    gate = evaluate_export_gate(chain)
    if not gate.allow_user_export:
        raise ExportGateError(gate)
    return gate


def _export_gate_failure_message(gate: StageQualityGate) -> str:
    if not gate.validation:
        lines = ["APQP chain validation failed:"]
        lines.extend(gate.validation.messages)
        return "\n".join(lines)

    lines = ["APQP export blocked by export gate."]
    lines.append(f"can_continue: {gate.can_continue}")
    lines.append(f"evidence_sufficient: {gate.evidence_sufficient}")
    _append_gate_detail(lines, "pending_fields", gate.pending_fields)
    _append_gate_detail(lines, "needs_confirmation_items", gate.needs_confirmation_items)
    _append_gate_detail(lines, "ai_inferred_items", gate.ai_inferred_items)
    _append_gate_detail(
        lines,
        "review_issues",
        [item.get("issue_id", item) for item in gate.review_issues],
    )
    _append_gate_detail(lines, "missing_evidence_refs", gate.missing_evidence_refs)
    _append_gate_detail(lines, "uncovered_evidence_items", gate.uncovered_evidence_items)
    if gate.validation.messages:
        _append_gate_detail(lines, "validation_messages", gate.validation.messages)
    return "\n".join(lines)


def _append_gate_detail(lines: list[str], label: str, values: list[Any]) -> None:
    if values:
        lines.append(f"{label}: " + ", ".join(str(value) for value in values))


def evaluate_stage_gate(
    chain: APQPChain | dict[str, Any], stage: str = "validate"
) -> StageQualityGate:
    unsafe_ai_batch_issues: list[dict[str, Any]] = []
    if isinstance(chain, dict):
        unsafe_ai_batch_issues = _unsafe_ai_batch_review_issues(chain)
        chain = _with_safe_ai_batch_confirmations(chain)
        chain = APQPChain(**chain)
    validation = _stage_validation(chain, stage)
    audit = audit_chain(chain)
    confirmed_targets = _confirmed_targets(chain)
    confirmed_field_paths = _confirmed_field_paths(chain)
    pending_fields = _without_confirmed(_pending_fields(chain), confirmed_field_paths)
    ai_inferred_items = _ai_inferred_items(chain)
    evidence_coverage = (
        _ingest_evidence_report(chain)
        if stage in {"ingest", "analyze"}
        else _evidence_coverage_report(chain)
    )
    row_needs_confirmation_items = _row_needs_confirmation_items(chain)
    needs_confirmation_items = _without_confirmed(
        _dedupe_preserve_order(
            list(evidence_coverage["needs_confirmation_refs"])
            + row_needs_confirmation_items
        ),
        confirmed_targets | confirmed_field_paths,
    )
    evidence_coverage["needs_confirmation_refs"] = _without_confirmed(
        list(evidence_coverage["needs_confirmation_refs"]),
        confirmed_targets | confirmed_field_paths,
    )
    evidence_sufficient = bool(evidence_coverage["ok"])
    strict_aiag_vda_gate = _strict_aiag_vda_pfmea_gate_enabled(chain)
    action_issues = (
        action_closure_issues([item.__dict__ for item in chain.failure_modes])
        if strict_aiag_vda_gate
        else []
    )
    action_blockers = [item for item in action_issues if item.get("severity") == "blocker"]
    change_impacts = _metadata_list(chain, "change_impacts") if strict_aiag_vda_gate else []
    change_blockers = blocking_change_impacts(change_impacts)
    recommendation_items = (
        _metadata_list(chain, "knowledge_recommendations") if strict_aiag_vda_gate else []
    )
    recommendation_blockers = unresolved_recommendations(recommendation_items)
    review_issue_blockers = unresolved_review_issues(
        _metadata_list(chain, "review_issues")
    )
    can_continue = (
        evidence_sufficient
        if stage in {"ingest", "analyze"}
        else bool(validation) and evidence_sufficient
    )
    allow_user_export = bool(
        stage not in {"ingest", "analyze"}
        and can_continue
        and not pending_fields
        and not needs_confirmation_items
        and not ai_inferred_items
        and not action_blockers
        and not change_blockers
        and not recommendation_blockers
        and not review_issue_blockers
        and not unsafe_ai_batch_issues
    )
    manual_review_items = list(audit.manual_review_items)
    manual_review_items.extend(_evidence_manual_review_items(evidence_coverage))
    manual_review_items.extend(
        _row_needs_confirmation_manual_review_items(
            _without_confirmed(
                row_needs_confirmation_items, confirmed_targets | confirmed_field_paths
            )
        )
    )
    manual_review_items.extend(_dict_manual_review_items(action_issues))
    manual_review_items.extend(_dict_manual_review_items(change_blockers))
    manual_review_items.extend(_recommendation_manual_review_items(recommendation_blockers))
    review_issues = _review_issues_from_gate_debts(
        manual_review_items=manual_review_items,
        needs_confirmation_items=needs_confirmation_items,
        recommendation_blockers=recommendation_blockers,
        change_blockers=change_blockers,
        existing_review_issues=review_issue_blockers,
    )
    review_issues = _dedupe_review_issues(review_issues + unsafe_ai_batch_issues)
    return StageQualityGate(
        stage=stage,
        can_continue=can_continue,
        allow_user_export=allow_user_export,
        validation=validation,
        audit=audit,
        evidence_sufficient=evidence_sufficient,
        pending_fields=pending_fields,
        ai_inferred_items=ai_inferred_items,
        manual_review_items=manual_review_items,
        evidence_coverage=evidence_coverage,
        missing_evidence_refs=list(evidence_coverage["missing_refs"]),
        uncovered_evidence_items=list(evidence_coverage["uncovered_items"]),
        needs_confirmation_items=needs_confirmation_items,
        review_issues=review_issues,
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
) -> StageQualityGate:
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
) -> StageQualityGate:
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
) -> StageQualityGate:
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
) -> StageQualityGate:
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
) -> StageQualityGate:
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
) -> StageQualityGate:
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


def _pfmea_bundle_report(pfmea_bundle: dict[str, Any]) -> dict[str, Any]:
    rows = pfmea_bundle.get("rows", pfmea_bundle.get("failure_modes", []))
    report = _document_rows_report(
        rows=rows,
        evidence=pfmea_bundle.get("evidence", []),
        pending_fields=pfmea_bundle.get("pending_fields", []),
        ai_inferred_items=pfmea_bundle.get("ai_inferred_items", []),
        stage_mode="generate_pfmea",
        next_stage="generate_control_plan",
        row_label="pfmea_row",
        id_field="pfmea_id",
        required_fields=(
            "pfmea_id",
            "process_step_id",
            "failure_mode",
            "failure_effect",
            "failure_cause",
            "evidence_refs",
        ),
        review_fields=("severity", "occurrence", "detection"),
    )
    _extend_pfmea_pfd_linkage_report(report, pfmea_bundle, rows)
    return report


def _metadata_list(chain: APQPChain, key: str) -> list[dict[str, Any]]:
    value = chain.metadata.get(key, []) if isinstance(chain.metadata, dict) else []
    return value if isinstance(value, list) else []


def _strict_aiag_vda_pfmea_gate_enabled(chain: APQPChain) -> bool:
    metadata = chain.metadata if isinstance(chain.metadata, dict) else {}
    if metadata.get("strict_aiag_vda_pfmea_gate") is True:
        return True
    generation_mode = str(metadata.get("generation_mode", "")).strip()
    if generation_mode in {
        "ai_drawing_three_table_generation",
        "human_edited_three_table_generation",
    }:
        return True
    return False


def _dict_manual_review_items(items: list[dict[str, Any]]) -> list[AuditItem]:
    return [
        AuditItem(
            str(item.get("item_id", "")),
            str(item.get("category", "人工复核")),
            str(item.get("message", "")),
            str(item.get("severity", "review")),
        )
        for item in items
    ]


def _recommendation_manual_review_items(items: list[dict[str, Any]]) -> list[AuditItem]:
    return [
        AuditItem(
            str(item.get("recommendation_id", item.get("item_id", ""))),
            "知识库推荐",
            str(item.get("reason", "知识库推荐需要人工采纳或填写忽略原因。")),
            "review",
        )
        for item in items
    ]


def _review_issues_from_gate_debts(
    *,
    manual_review_items: list[Any],
    needs_confirmation_items: list[str],
    recommendation_blockers: list[dict[str, Any]],
    change_blockers: list[dict[str, Any]],
    existing_review_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in manual_review_items:
        issues.append(review_issue_from_manual_item(item))
    for item in needs_confirmation_items:
        issues.append(
            build_review_issue(
                category="人工确认",
                message="关键对象标记为待确认，需要人工确认后才能正式放行。",
                severity="review",
                source="quality_gate",
                target=item,
            )
        )
    for item in recommendation_blockers:
        issues.append(
            build_review_issue(
                category="知识库推荐",
                message=str(item.get("reason", "知识库推荐需要人工采纳或填写忽略原因。")),
                severity="blocker",
                source="knowledge_recommendation",
                target=str(item.get("target_id", "")),
                recommendation_id=str(item.get("recommendation_id", "")),
                confidence=item.get("confidence"),
            )
        )
    for item in change_blockers:
        issues.append(
            build_review_issue(
                category="变更影响",
                message=str(item.get("message", "变更影响需要处理后才能正式放行。")),
                severity=str(item.get("severity", "blocker")),
                source="change_management",
                target=str(item.get("target", "")),
                change_impact_id=str(item.get("item_id", "")),
            )
        )
    issues.extend(dict(item) for item in existing_review_issues)
    return _dedupe_review_issues(issues)


def _dedupe_review_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        issue_id = str(item.get("issue_id", "")).strip()
        if not issue_id:
            continue
        if issue_id in seen:
            continue
        result.append(item)
        seen.add(issue_id)
    return result


def _control_plan_bundle_report(control_plan_bundle: dict[str, Any]) -> dict[str, Any]:
    rows = control_plan_bundle.get(
        "rows", control_plan_bundle.get("control_plan_items", control_plan_bundle.get("controls", []))
    )
    report = _document_rows_report(
        rows=rows,
        evidence=control_plan_bundle.get("evidence", []),
        pending_fields=control_plan_bundle.get("pending_fields", []),
        ai_inferred_items=control_plan_bundle.get("ai_inferred_items", []),
        stage_mode="generate_control_plan",
        next_stage="validate",
        row_label="control_plan_row",
        id_field="control_plan_id",
        required_fields=(
            "control_plan_id",
            "process_step_id",
            "pfmea_id",
            "product_process_characteristic",
            "specification",
            "measurement_method",
            "control_method",
            "reaction_plan",
            "evidence_refs",
        ),
        review_fields=("sample_size", "sample_frequency"),
    )
    _extend_control_plan_linkage_report(report, control_plan_bundle, rows)
    return report


def _extend_pfmea_pfd_linkage_report(
    report: dict[str, Any], pfmea_bundle: dict[str, Any], rows: Any
) -> None:
    process_steps = pfmea_bundle.get("process_steps", pfmea_bundle.get("steps", []))
    if not isinstance(process_steps, list) or not isinstance(rows, list):
        return
    step_ids = {
        str(step.get("process_step_id", step.get("id", ""))).strip()
        for step in process_steps
        if isinstance(step, dict) and str(step.get("process_step_id", step.get("id", ""))).strip()
    }
    row_step_ids = {
        str(row.get("process_step_id", "")).strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("process_step_id", "")).strip()
    }
    for step_id in sorted(step_ids - row_step_ids):
        report["uncovered_items"].append(f"process_step:{step_id}.pfmea_risk")
    for step_id in sorted(row_step_ids - step_ids):
        report["uncovered_items"].append(f"pfmea_row.process_step_missing:{step_id}")
    report["ok"] = bool(report["ok"] and not any(
        item.endswith(".pfmea_risk") or "process_step_missing" in item
        for item in report["uncovered_items"]
    ))


def _extend_control_plan_linkage_report(
    report: dict[str, Any], control_plan_bundle: dict[str, Any], rows: Any
) -> None:
    pfmea_rows = control_plan_bundle.get("pfmea_rows", control_plan_bundle.get("failure_modes", []))
    process_steps = control_plan_bundle.get("process_steps", [])
    if not isinstance(rows, list):
        return
    if isinstance(process_steps, list) and process_steps:
        step_ids = {
            str(step.get("process_step_id", step.get("id", ""))).strip()
            for step in process_steps
            if isinstance(step, dict) and str(step.get("process_step_id", step.get("id", ""))).strip()
        }
        for row in rows:
            if not isinstance(row, dict):
                continue
            step_id = str(row.get("process_step_id", "")).strip()
            control_id = str(row.get("control_plan_id", "")).strip()
            if step_id and step_id not in step_ids:
                report["uncovered_items"].append(
                    f"control_plan_row:{control_id}.process_step_missing:{step_id}"
                )
    if isinstance(pfmea_rows, list) and pfmea_rows:
        controlled_pfmea_ids = {
            str(row.get("pfmea_id", "")).strip()
            for row in rows
            if isinstance(row, dict) and str(row.get("pfmea_id", "")).strip()
        }
        for pfmea_row in pfmea_rows:
            if not isinstance(pfmea_row, dict) or not _pfmea_row_requires_control(pfmea_row):
                continue
            pfmea_id = str(pfmea_row.get("pfmea_id", "")).strip()
            if pfmea_id and pfmea_id not in controlled_pfmea_ids:
                report["uncovered_items"].append(
                    f"pfmea_row:{pfmea_id}.control_plan_control"
                )
    report["ok"] = bool(report["ok"] and not any(
        "process_step_missing" in item or item.endswith(".control_plan_control")
        for item in report["uncovered_items"]
    ))


def _pfmea_row_requires_control(row: dict[str, Any]) -> bool:
    action_priority = str(row.get("action_priority", row.get("AP", ""))).strip().upper()
    classification = str(row.get("classification", "")).strip()
    try:
        severity = int(row.get("severity", row.get("S", 0)) or 0)
    except (TypeError, ValueError):
        severity = 0
    return bool(action_priority in {"H", "M"} or severity >= 9 or classification)


def _document_rows_report(
    *,
    rows: Any,
    evidence: Any,
    pending_fields: Any,
    ai_inferred_items: Any,
    stage_mode: str,
    next_stage: str,
    row_label: str,
    id_field: str,
    required_fields: tuple[str, ...],
    review_fields: tuple[str, ...],
) -> dict[str, Any]:
    document_rows = rows if isinstance(rows, list) else []
    evidence_rows = evidence if isinstance(evidence, list) else []
    evidence_by_id = {
        str(item.get("evidence_id", "")): item
        for item in evidence_rows
        if isinstance(item, dict) and item.get("evidence_id")
    }
    upstream_pending = _pending_field_paths(pending_fields)
    blocking_pending: list[str] = []
    uncovered_items: list[str] = []
    missing_refs: list[str] = []
    needs_confirmation_refs: list[str] = []
    review_items: list[str] = []
    referenced_evidence_ids: set[str] = set()
    referenced_non_ai_evidence_ids: set[str] = set()
    ai_inferred_refs = set(_flagged_evidence_ids(ai_inferred_items, "ai_inferred"))
    row_ids: set[str] = set()

    if not document_rows:
        uncovered_items.append(f"{row_label}:min_count")

    for index, row in enumerate(document_rows):
        if not isinstance(row, dict):
            blocking_pending.append(f"{row_label}[{index}]")
            continue
        row_id = str(row.get(id_field, "")).strip()
        label = f"{row_label}:{row_id}" if row_id else f"{row_label}[{index}]"
        if row_id:
            row_ids.add(row_id)
        if row.get("ai_inferred") and row_id:
            ai_inferred_refs.add(row_id)
        for field_name in required_fields:
            if field_name == "evidence_refs":
                _check_document_evidence_refs(
                    label,
                    row.get("evidence_refs", []),
                    evidence_by_id,
                    blocking_pending,
                    missing_refs,
                    uncovered_items,
                    ai_inferred_refs,
                    needs_confirmation_refs,
                    referenced_evidence_ids,
                    referenced_non_ai_evidence_ids,
                )
                continue
            if not str(row.get(field_name, "")).strip():
                blocking_pending.append(f"{label}.{field_name}")
        for field_name in review_fields:
            if not str(row.get(field_name, "")).strip() or row.get(field_name) in {0, "0"}:
                review_items.append(f"{label}.{field_name}")
        if _document_row_needs_confirmation(row):
            needs_confirmation_refs.append(row_id or label)

    all_referenced_evidence_ai = (
        bool(referenced_evidence_ids) and not referenced_non_ai_evidence_ids
    )
    if all_referenced_evidence_ai:
        uncovered_items.append("all_referenced_evidence_ai_inferred")

    required_count = max(len(document_rows), 1)
    covered_count = (
        required_count
        - len(uncovered_items)
        - len(blocking_pending)
        - len(missing_refs)
    )
    evidence_sufficient = bool(
        referenced_evidence_ids
        and referenced_non_ai_evidence_ids
        and not missing_refs
        and not all_referenced_evidence_ai
    )
    ok = bool(
        document_rows
        and not blocking_pending
        and not uncovered_items
        and not missing_refs
        and evidence_sufficient
    )
    pending = upstream_pending + blocking_pending
    return {
        "stage_mode": stage_mode,
        "next_stage": next_stage,
        "required_items": required_count,
        "covered_items": max(covered_count, 0),
        "coverage_ratio": max(covered_count, 0) / required_count
        if required_count
        else 0.0,
        "row_count": len(document_rows),
        "row_ids": sorted(row_ids),
        "pending_fields": pending,
        "blocking_pending_fields": blocking_pending,
        "uncovered_items": uncovered_items,
        "missing_refs": missing_refs,
        "ai_inferred_refs": sorted(ai_inferred_refs),
        "needs_confirmation_refs": sorted(set(needs_confirmation_refs)),
        "review_items": sorted(set(review_items)),
        "referenced_evidence_ids": sorted(referenced_evidence_ids),
        "referenced_non_ai_evidence_ids": sorted(referenced_non_ai_evidence_ids),
        "evidence_sufficient": evidence_sufficient,
        "legacy_mode": False,
        "ok": ok,
    }


def _check_document_evidence_refs(
    label: str,
    refs: Any,
    evidence_by_id: dict[str, dict[str, Any]],
    pending_fields: list[str],
    missing_refs: list[str],
    uncovered_items: list[str],
    ai_inferred_refs: set[str],
    needs_confirmation_refs: list[str],
    referenced_evidence_ids: set[str],
    referenced_non_ai_evidence_ids: set[str],
) -> None:
    evidence_refs = [str(ref).strip() for ref in refs or [] if str(ref).strip()]
    if not evidence_refs:
        pending_fields.append(f"{label}.evidence_refs")
        return
    row_non_ai_refs: set[str] = set()
    row_referenced_refs: set[str] = set()
    for ref in evidence_refs:
        evidence_item = evidence_by_id.get(ref)
        if evidence_item is None:
            missing_refs.append(f"{label} -> {ref}")
            continue
        referenced_evidence_ids.add(ref)
        row_referenced_refs.add(ref)
        if evidence_item.get("ai_inferred"):
            ai_inferred_refs.add(ref)
        else:
            referenced_non_ai_evidence_ids.add(ref)
            row_non_ai_refs.add(ref)
        if evidence_item.get("needs_confirmation"):
            needs_confirmation_refs.append(ref)
        if _refers_to_confirmable_requirement(evidence_item, label):
            needs_confirmation_refs.append(ref)
    if row_referenced_refs and not row_non_ai_refs:
        uncovered_items.append(f"{label}.all_evidence_ai_inferred")


def _refers_to_confirmable_requirement(evidence_item: dict[str, Any], label: str) -> bool:
    if not evidence_item.get("needs_confirmation"):
        return False
    content = str(evidence_item.get("content", "")).lower()
    source = str(evidence_item.get("source", "")).lower()
    target = label.lower()
    return any(term in source or term in content for term in _label_terms(target))


def _label_terms(label: str) -> tuple[str, ...]:
    if any(term in label for term in ("p20", "rivet", "joint")):
        return ("rivet", "push-out", "push out", "force")
    if any(term in label for term in ("p10", "incoming", "material")):
        return ("material", "thickness")
    if any(term in label for term in ("p30", "final", "inspection", "pack")):
        return ("revision", "barcode", "pack", "quantity")
    return ()


def _document_row_needs_confirmation(row: dict[str, Any]) -> bool:
    if row.get("needs_confirmation"):
        return True
    if not row.get("ai_inferred"):
        return False
    risk_level = str(row.get("source_risk_level", row.get("risk_level", ""))).strip().lower()
    classification = str(row.get("classification", "")).strip()
    confidence = _float_value(row.get("confidence"))
    evidence_refs = [str(ref).strip() for ref in row.get("evidence_refs", []) if str(ref).strip()]
    if risk_level == "high" or classification:
        return True
    if confidence is not None and confidence < 0.75:
        return True
    if not evidence_refs:
        return True
    return _row_ai_reasoning_is_uncertain(row)


def _row_ai_reasoning_is_uncertain(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(field_name, "")).strip()
        for field_name in (
            "ai_reasoning",
            "reasoning",
            "uncertainty",
            "uncertainties",
            "recommended_action",
        )
        if row.get(field_name) is not None
    ).lower()
    return any(
        token in text
        for token in (
            "uncertain",
            "not confirmed",
            "requires engineer",
            "requires engineering",
            "requires quality",
            "requires review",
            "pending",
            "待确认",
            "不确定",
            "需复核",
        )
    )


def _float_value(value: Any) -> float | None:
    try:
        return None if value in {None, ""} else float(value)
    except (TypeError, ValueError):
        return None


def _pfmea_manual_review_items(report: dict[str, Any]) -> list[AuditItem]:
    return _document_manual_review_items(
        report,
        incomplete_category="pfmea_incomplete",
        missing_ref_category="pfmea_missing_ref",
        pending_category="pfmea_pending_field",
        needs_confirmation_category="pfmea_needs_confirmation",
        ai_category="pfmea_ai_inferred",
        review_category="pfmea_review_field",
        message_prefix="PFMEA",
    )


def _control_plan_manual_review_items(report: dict[str, Any]) -> list[AuditItem]:
    return _document_manual_review_items(
        report,
        incomplete_category="control_plan_incomplete",
        missing_ref_category="control_plan_missing_ref",
        pending_category="control_plan_pending_field",
        needs_confirmation_category="control_plan_needs_confirmation",
        ai_category="control_plan_ai_inferred",
        review_category="control_plan_review_field",
        message_prefix="控制计划",
    )


def _document_manual_review_items(
    report: dict[str, Any],
    *,
    incomplete_category: str,
    missing_ref_category: str,
    pending_category: str,
    needs_confirmation_category: str,
    ai_category: str,
    review_category: str,
    message_prefix: str,
) -> list[AuditItem]:
    items: list[AuditItem] = []
    for value in report["uncovered_items"]:
        items.append(
            AuditItem(value, incomplete_category, f"{message_prefix} 缺少进入下一阶段的必要内容", "blocker")
        )
    for value in report["missing_refs"]:
        items.append(
            AuditItem(value, missing_ref_category, f"{message_prefix} evidence_refs 引用了不存在的顶层证据", "blocker")
        )
    for value in report["pending_fields"]:
        items.append(
            AuditItem(value, pending_category, f"{message_prefix} 存在必填字段缺失", "blocker")
        )
    for value in report["needs_confirmation_refs"]:
        items.append(
            AuditItem(value, needs_confirmation_category, f"{message_prefix} 引用内容需要人工确认", "review")
        )
    row_ids = {str(value).strip() for value in report.get("row_ids", [])}
    for value in report["ai_inferred_refs"]:
        if str(value).strip() in row_ids:
            continue
        items.append(
            AuditItem(value, ai_category, f"{message_prefix} 引用了 AI 推断证据", "review")
        )
    for value in report.get("review_items", []):
        items.append(
            AuditItem(value, review_category, f"{message_prefix} 字段为空，需要人工复核", "review")
        )
    return items


def _failure_mode_candidates_report(
    candidates_bundle: dict[str, Any],
) -> dict[str, Any]:
    process_steps = candidates_bundle.get(
        "process_steps", candidates_bundle.get("steps", [])
    )
    candidates = candidates_bundle.get(
        "candidates", candidates_bundle.get("failure_mode_candidates", [])
    )
    evidence = candidates_bundle.get("evidence", [])
    evidence_by_id = {
        str(item.get("evidence_id", "")): item
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_id")
    }
    step_ids = {
        str(step.get("process_step_id", step.get("id", ""))).strip()
        for step in process_steps
        if isinstance(step, dict)
        and str(step.get("process_step_id", step.get("id", ""))).strip()
    }
    candidate_count_by_step = {step_id: 0 for step_id in step_ids}
    upstream_pending_fields = _pending_field_paths(
        candidates_bundle.get("pending_fields", [])
    )
    blocking_pending_fields: list[str] = []
    uncovered_items: list[str] = []
    missing_refs: list[str] = []
    ai_inferred_refs: set[str] = set()
    needs_confirmation_refs: list[str] = []
    referenced_evidence_ids: set[str] = set()
    referenced_non_ai_evidence_ids: set[str] = set()
    candidate_ids: set[str] = set()

    if not candidates:
        uncovered_items.append("failure_mode_candidates:min_count")

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            blocking_pending_fields.append(f"failure_mode_candidate[{index}]")
            continue
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        label = (
            f"failure_mode_candidate:{candidate_id}"
            if candidate_id
            else f"failure_mode_candidate[{index}]"
        )
        step_id = str(candidate.get("process_step_id", "")).strip()
        failure_mode = str(
            candidate.get("failure_mode", candidate.get("candidate_failure_mode", ""))
        ).strip()
        evidence_refs = candidate.get("evidence_refs", [])
        if not candidate_id:
            blocking_pending_fields.append(
                f"failure_mode_candidate[{index}].candidate_id"
            )
        else:
            candidate_ids.add(candidate_id)
        if not step_id:
            blocking_pending_fields.append(f"{label}.process_step_id")
        elif step_id not in step_ids:
            uncovered_items.append(f"{label}.process_step_missing:{step_id}")
        else:
            candidate_count_by_step[step_id] = (
                candidate_count_by_step.get(step_id, 0) + 1
            )
        if not failure_mode:
            blocking_pending_fields.append(f"{label}.failure_mode")
        if candidate.get("needs_confirmation"):
            needs_confirmation_refs.append(candidate_id or label)
        _check_candidate_evidence_refs(
            label,
            evidence_refs,
            evidence_by_id,
            blocking_pending_fields,
            missing_refs,
            uncovered_items,
            ai_inferred_refs,
            needs_confirmation_refs,
            referenced_evidence_ids,
            referenced_non_ai_evidence_ids,
        )

    for step_id in sorted(step_ids):
        if candidate_count_by_step.get(step_id, 0) < 1:
            uncovered_items.append(
                f"process_step:{step_id}.failure_mode_candidates:min_count"
            )

    all_referenced_evidence_ai = (
        bool(referenced_evidence_ids) and not referenced_non_ai_evidence_ids
    )
    if all_referenced_evidence_ai:
        uncovered_items.append("all_referenced_evidence_ai_inferred")

    required_count = max(len(process_steps) + len(candidates), 1)
    covered_count = (
        required_count
        - len(uncovered_items)
        - len(blocking_pending_fields)
        - len(missing_refs)
    )
    evidence_sufficient = bool(
        referenced_evidence_ids
        and referenced_non_ai_evidence_ids
        and not missing_refs
        and not all_referenced_evidence_ai
    )
    ok = bool(
        candidates
        and not blocking_pending_fields
        and not uncovered_items
        and not missing_refs
        and evidence_sufficient
    )
    pending_fields = upstream_pending_fields + blocking_pending_fields
    return {
        "stage_mode": "brainstorm_failure_modes",
        "next_stage": "generate_pfmea",
        "required_items": required_count,
        "covered_items": max(covered_count, 0),
        "coverage_ratio": max(covered_count, 0) / required_count
        if required_count
        else 0.0,
        "step_count": len(process_steps),
        "candidate_count": len(candidates),
        "required_candidate_count": 1,
        "step_ids": sorted(step_ids),
        "candidate_ids": sorted(candidate_ids),
        "candidate_count_by_step": candidate_count_by_step,
        "pending_fields": pending_fields,
        "blocking_pending_fields": blocking_pending_fields,
        "uncovered_items": uncovered_items,
        "missing_refs": missing_refs,
        "ai_inferred_refs": sorted(ai_inferred_refs),
        "needs_confirmation_refs": sorted(set(needs_confirmation_refs)),
        "referenced_evidence_ids": sorted(referenced_evidence_ids),
        "referenced_non_ai_evidence_ids": sorted(referenced_non_ai_evidence_ids),
        "evidence_sufficient": evidence_sufficient,
        "legacy_mode": False,
        "ok": ok,
    }


def _check_candidate_evidence_refs(
    label: str,
    refs: Any,
    evidence_by_id: dict[str, dict[str, Any]],
    pending_fields: list[str],
    missing_refs: list[str],
    uncovered_items: list[str],
    ai_inferred_refs: set[str],
    needs_confirmation_refs: list[str],
    referenced_evidence_ids: set[str],
    referenced_non_ai_evidence_ids: set[str],
) -> None:
    evidence_refs = [str(ref).strip() for ref in refs or [] if str(ref).strip()]
    if not evidence_refs:
        pending_fields.append(f"{label}.evidence_refs")
        return
    candidate_non_ai_refs: set[str] = set()
    candidate_referenced_refs: set[str] = set()
    for ref in evidence_refs:
        evidence_item = evidence_by_id.get(ref)
        if evidence_item is None:
            missing_refs.append(f"{label} -> {ref}")
            continue
        referenced_evidence_ids.add(ref)
        candidate_referenced_refs.add(ref)
        if evidence_item.get("ai_inferred"):
            ai_inferred_refs.add(ref)
        else:
            referenced_non_ai_evidence_ids.add(ref)
            candidate_non_ai_refs.add(ref)
        if evidence_item.get("needs_confirmation"):
            needs_confirmation_refs.append(ref)
    if candidate_referenced_refs and not candidate_non_ai_refs:
        uncovered_items.append(f"{label}.all_evidence_ai_inferred")


def _failure_mode_candidates_manual_review_items(
    report: dict[str, Any],
) -> list[AuditItem]:
    items: list[AuditItem] = []
    for value in report["uncovered_items"]:
        items.append(
            AuditItem(
                value,
                "failure_mode_candidate_incomplete",
                "失效模式候选缺少进入 generate_pfmea 的必要内容",
                "blocker",
            )
        )
    for value in report["missing_refs"]:
        items.append(
            AuditItem(
                value,
                "failure_mode_candidate_missing_ref",
                "失效模式候选 evidence_refs 引用了不存在的顶层证据",
                "blocker",
            )
        )
    for value in report["pending_fields"]:
        items.append(
            AuditItem(
                value,
                "failure_mode_candidate_pending_field",
                "失效模式候选存在必填字段缺失",
                "blocker",
            )
        )
    for value in report["needs_confirmation_refs"]:
        items.append(
            AuditItem(
                value,
                "failure_mode_candidate_needs_confirmation",
                "失效模式候选引用内容需要人工确认",
                "review",
            )
        )
    for value in report["ai_inferred_refs"]:
        items.append(
            AuditItem(
                value,
                "failure_mode_candidate_ai_inferred",
                "失效模式候选引用了 AI 推断证据",
                "review",
            )
        )
    return items


def _pfd_bundle_report(
    pfd_bundle: dict[str, Any],
    stage_mode: str = "generate_pfd",
    next_stage: str = "brainstorm_failure_modes",
    require_operation: bool = True,
) -> dict[str, Any]:
    steps = pfd_bundle.get("steps", pfd_bundle.get("process_steps", []))
    links = pfd_bundle.get("links", [])
    pending_fields = _pending_field_paths(pfd_bundle.get("pending_fields", []))
    pfd_blocking_fields: list[str] = []
    ai_inferred_refs = set(
        _flagged_evidence_ids(pfd_bundle.get("ai_inferred_items", []), "ai_inferred")
    )
    evidence = pfd_bundle.get("evidence", [])
    evidence_by_id = {
        str(item.get("evidence_id", "")): item
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_id")
    }
    step_ids: set[str] = set()
    uncovered_items: list[str] = []
    missing_refs: list[str] = []
    needs_confirmation_refs: list[str] = []
    review_items: list[str] = []
    referenced_evidence_ids: set[str] = set()
    referenced_non_ai_evidence_ids: set[str] = set()
    mapped_special_characteristics: set[str] = set()
    if len(steps) < 2:
        uncovered_items.append("process_steps:min_count")
    if len(links) < 1:
        uncovered_items.append("links:min_count")

    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            pfd_blocking_fields.append(f"process_step[{index}]")
            continue
        step_id = str(step.get("process_step_id", step.get("id", ""))).strip()
        operation = str(step.get("operation", step.get("name", ""))).strip()
        if not step_id:
            pfd_blocking_fields.append(f"process_step[{index}].id")
            continue
        step_ids.add(step_id)
        if not operation and require_operation:
            pfd_blocking_fields.append(f"process_step:{step_id}.operation")
        elif not operation:
            review_items.append(f"process_step:{step_id}.operation")
        _check_pfd_evidence_refs(
            f"process_step:{step_id}",
            step.get("evidence_refs", []),
            evidence_by_id,
            pfd_blocking_fields,
            missing_refs,
            ai_inferred_refs,
            needs_confirmation_refs,
            referenced_evidence_ids,
            referenced_non_ai_evidence_ids,
        )
        if not str(step.get("process_function", "")).strip():
            review_items.append(f"process_step:{step_id}.process_function")
        if not step.get("special_characteristics") and step.get("needs_confirmation"):
            review_items.append(f"process_step:{step_id}.special_characteristics")
        mapped_special_characteristics.update(
            _special_characteristic_refs(step.get("special_characteristics"))
        )

    unmapped_special_characteristics = _unmapped_special_characteristics(
        pfd_bundle.get("characteristics", []), mapped_special_characteristics
    )
    if unmapped_special_characteristics:
        review_items.append("process_flow.characteristics.unmapped")

    for index, link in enumerate(links):
        if not isinstance(link, dict):
            pfd_blocking_fields.append(f"trace_link[{index}]")
            continue
        from_id = str(link.get("from", link.get("from_id", ""))).strip()
        to_id = str(link.get("to", link.get("to_id", ""))).strip()
        link_type = str(link.get("link_type", "")).strip()
        if not link_type:
            pfd_blocking_fields.append(f"trace_link[{index}].link_type")
        elif link_type != "sequence":
            uncovered_items.append(f"trace_link[{index}].link_type_invalid:{link_type}")
        if not from_id:
            pfd_blocking_fields.append(f"trace_link[{index}].from")
        elif from_id not in step_ids:
            uncovered_items.append(f"trace_link[{index}].from_missing:{from_id}")
        if not to_id:
            pfd_blocking_fields.append(f"trace_link[{index}].to")
        elif to_id not in step_ids:
            uncovered_items.append(f"trace_link[{index}].to_missing:{to_id}")
        _check_pfd_evidence_refs(
            f"trace_link[{index}]",
            link.get("evidence_refs", []),
            evidence_by_id,
            pfd_blocking_fields,
            missing_refs,
            ai_inferred_refs,
            needs_confirmation_refs,
            referenced_evidence_ids,
            referenced_non_ai_evidence_ids,
        )

    required_count = max(len(steps) + len(links), 1)
    pending_fields.extend(pfd_blocking_fields)
    all_referenced_evidence_ai = (
        bool(referenced_evidence_ids) and not referenced_non_ai_evidence_ids
    )
    if all_referenced_evidence_ai:
        uncovered_items.append("all_referenced_evidence_ai_inferred")
    covered_count = (
        required_count
        - len(uncovered_items)
        - len(pfd_blocking_fields)
        - len(missing_refs)
    )
    evidence_sufficient = bool(
        referenced_evidence_ids
        and referenced_non_ai_evidence_ids
        and not any(item.endswith(".evidence_refs") for item in pfd_blocking_fields)
        and not missing_refs
        and not all_referenced_evidence_ai
    )
    ok = bool(
        len(steps) >= 2
        and len(links) >= 1
        and not pfd_blocking_fields
        and not uncovered_items
        and not missing_refs
        and evidence_sufficient
    )
    return {
        "stage_mode": stage_mode,
        "next_stage": next_stage,
        "required_items": required_count,
        "covered_items": max(covered_count, 0),
        "coverage_ratio": max(covered_count, 0) / required_count
        if required_count
        else 0.0,
        "step_count": len(steps),
        "link_count": len(links),
        "required_step_count": 2,
        "required_link_count": 1,
        "pending_fields": pending_fields,
        "uncovered_items": uncovered_items,
        "missing_refs": missing_refs,
        "ai_inferred_refs": sorted(ai_inferred_refs),
        "needs_confirmation_refs": sorted(set(needs_confirmation_refs)),
        "review_items": sorted(set(review_items)),
        "unmapped_special_characteristics": unmapped_special_characteristics,
        "step_ids": sorted(step_ids),
        "evidence_sufficient": evidence_sufficient,
        "legacy_mode": False,
        "ok": ok,
    }


def _special_characteristic_refs(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.strip()} if value.strip() else set()
    if not isinstance(value, list):
        return set()
    refs: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            ref = str(
                item.get("characteristic_id")
                or item.get("id")
                or item.get("name")
                or ""
            ).strip()
        else:
            ref = str(item).strip()
        if ref:
            refs.add(ref)
    return refs


def _unmapped_special_characteristics(
    characteristics: Any, mapped_refs: set[str]
) -> list[str]:
    if not isinstance(characteristics, list):
        return []
    characteristic_refs: list[str] = []
    for index, item in enumerate(characteristics, start=1):
        if isinstance(item, dict):
            ref = str(
                item.get("characteristic_id")
                or item.get("id")
                or item.get("name")
                or f"characteristics[{index - 1}]"
            ).strip()
        else:
            ref = str(item).strip()
        if ref:
            characteristic_refs.append(ref)
    if not characteristic_refs:
        return []
    return [ref for ref in characteristic_refs if ref not in mapped_refs]


def _check_pfd_evidence_refs(
    label: str,
    refs: Any,
    evidence_by_id: dict[str, dict[str, Any]],
    pfd_blocking_fields: list[str],
    missing_refs: list[str],
    ai_inferred_refs: set[str],
    needs_confirmation_refs: list[str],
    referenced_evidence_ids: set[str],
    referenced_non_ai_evidence_ids: set[str],
) -> None:
    evidence_refs = [str(ref).strip() for ref in refs or [] if str(ref).strip()]
    if not evidence_refs:
        pfd_blocking_fields.append(f"{label}.evidence_refs")
        return
    for ref in evidence_refs:
        evidence_item = evidence_by_id.get(ref)
        if evidence_item is None:
            missing_refs.append(f"{label} -> {ref}")
            continue
        referenced_evidence_ids.add(ref)
        if evidence_item.get("ai_inferred"):
            ai_inferred_refs.add(ref)
        else:
            referenced_non_ai_evidence_ids.add(ref)
        if evidence_item.get("needs_confirmation"):
            needs_confirmation_refs.append(ref)


def _evidence_ids(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [
        str(item.get("evidence_id"))
        for item in items
        if isinstance(item, dict) and item.get("evidence_id")
    ]


def _flagged_evidence_ids(items: Any, flag: str) -> list[str]:
    if isinstance(items, dict):
        iterable = [items]
    elif isinstance(items, list):
        iterable = items
    else:
        return []
    return [
        str(item.get("evidence_id") or item.get("item_id"))
        for item in iterable
        if isinstance(item, dict)
        and (item.get("evidence_id") or item.get("item_id"))
        and item.get(flag)
    ]


def _pfd_manual_review_items(report: dict[str, Any]) -> list[AuditItem]:
    items: list[AuditItem] = []
    for value in report["uncovered_items"]:
        items.append(
            AuditItem(
                value,
                "pfd_incomplete",
                "PFD 缺少进入 brainstorm_failure_modes 的必要内容",
                "blocker",
            )
        )
    for value in report["missing_refs"]:
        items.append(
            AuditItem(
                value,
                "pfd_missing_ref",
                "PFD evidence_refs 引用了不存在的顶层证据",
                "blocker",
            )
        )
    for value in report["pending_fields"]:
        items.append(
            AuditItem(value, "pfd_pending_field", "PFD 存在待补字段", "blocker")
        )
    for value in report["needs_confirmation_refs"]:
        items.append(
            AuditItem(
                value, "pfd_needs_confirmation", "PFD 引用内容需要人工确认", "review"
            )
        )
    for value in report["ai_inferred_refs"]:
        items.append(
            AuditItem(value, "pfd_ai_inferred", "PFD 输入包含 AI 推断证据", "review")
        )
    for value in report.get("review_items", []):
        items.append(
            AuditItem(value, "pfd_review_field", "PFD 字段为空，需要人工复核", "review")
        )
    return items


def _analysis_bundle_report(analysis_bundle: dict[str, Any]) -> dict[str, Any]:
    required_blocks = [
        "evidence",
        "drawings",
        "characteristics",
        "process_clues",
        "pending_fields",
        "ai_inferred_items",
    ]
    missing_blocks = [name for name in required_blocks if name not in analysis_bundle]
    evidence = analysis_bundle.get("evidence", [])
    drawings = analysis_bundle.get("drawings", [])
    characteristics = analysis_bundle.get("characteristics", [])
    process_clues = analysis_bundle.get("process_clues", [])
    pending_fields = _pending_field_paths(analysis_bundle.get("pending_fields", []))
    uncovered_items: list[str] = []
    if missing_blocks:
        uncovered_items.extend(f"missing_block:{name}" for name in missing_blocks)
    if not drawings:
        uncovered_items.append("drawings")
    if not characteristics:
        uncovered_items.append("characteristics")
    if not process_clues:
        uncovered_items.append("process_clues")

    evidence_ids = [
        str(item.get("evidence_id", "")) for item in evidence if isinstance(item, dict)
    ]
    evidence_id_set = {item for item in evidence_ids if item}
    ai_evidence_ids = {
        str(item.get("evidence_id"))
        for item in evidence
        if isinstance(item, dict)
        and item.get("evidence_id")
        and item.get("ai_inferred")
    }
    missing_refs: list[str] = []
    valid_route_clues: list[dict[str, Any]] = []
    for index, clue in enumerate(process_clues):
        if not isinstance(clue, dict):
            continue
        step_id = str(clue.get("process_step_id", "")).strip().upper()
        operation = str(clue.get("operation", "")).strip()
        source_ref = str(clue.get("source_ref", "")).strip()
        if source_ref and source_ref not in evidence_id_set:
            missing_refs.append(f"process_clues[{index}].source_ref -> {source_ref}")
            continue
        if (
            re.match(r"^P\d+$", step_id)
            and operation
            and source_ref
            and source_ref not in ai_evidence_ids
            and not clue.get("ai_inferred")
        ):
            valid_route_clues.append(clue)
    if len(valid_route_clues) < 2:
        uncovered_items.append("process_clues:min_valid_pxx_count")
    non_ai_evidence = [
        item
        for item in evidence
        if isinstance(item, dict)
        and item.get("evidence_id")
        and item.get("content")
        and not item.get("ai_inferred", False)
    ]
    needs_confirmation_refs = [
        str(item.get("evidence_id"))
        for item in evidence
        if isinstance(item, dict)
        and item.get("needs_confirmation")
        and item.get("evidence_id")
    ]
    ai_inferred_refs = sorted(ai_evidence_ids)
    all_ai = bool(evidence) and not non_ai_evidence
    if all_ai:
        uncovered_items.append("all_evidence_ai_inferred")

    required_count = len(required_blocks)
    covered_count = required_count - len(missing_blocks)
    evidence_sufficient = bool(evidence and non_ai_evidence)
    ok = bool(
        not missing_blocks
        and drawings
        and characteristics
        and len(valid_route_clues) >= 2
        and evidence_sufficient
        and not all_ai
        and not missing_refs
    )
    return {
        "stage_mode": "analyze",
        "next_stage": "generate_pfd",
        "required_items": required_count,
        "covered_items": covered_count,
        "coverage_ratio": covered_count / required_count if required_count else 0.0,
        "required_blocks": required_blocks,
        "missing_blocks": missing_blocks,
        "route_candidate_count": len(process_clues),
        "usable_route_candidate_count": len(valid_route_clues),
        "drawing_count": len(drawings),
        "characteristic_count": len(characteristics),
        "evidence_count": len(evidence),
        "non_inferred_evidence_count": len(non_ai_evidence),
        "pending_fields": pending_fields,
        "uncovered_items": uncovered_items,
        "missing_refs": missing_refs,
        "ai_inferred_refs": ai_inferred_refs,
        "needs_confirmation_refs": needs_confirmation_refs,
        "evidence_ids": evidence_ids,
        "legacy_mode": False,
        "evidence_sufficient": evidence_sufficient,
        "ok": ok,
    }


def _pending_field_paths(items: Any) -> list[str]:
    if items is None:
        return []
    if isinstance(items, str):
        value = items.strip()
        return [value] if value else []
    if not isinstance(items, list):
        return ["pending_fields"]
    paths: list[str] = []
    for item in items:
        if isinstance(item, str):
            value = item.strip()
            if value:
                paths.append(value)
            continue
        if isinstance(item, dict) and item.get("field"):
            paths.append(
                f"{item.get('source_ref', '')}.{item.get('field', '')}".strip(".")
            )
    return paths


def _analysis_manual_review_items(
    report: dict[str, Any], analysis_bundle: dict[str, Any]
) -> list[AuditItem]:
    items: list[AuditItem] = []
    for value in report["uncovered_items"]:
        items.append(
            AuditItem(
                value,
                "analysis_incomplete",
                "分析结果缺少进入 generate_pfd 的必要内容",
                "blocker",
            )
        )
    for value in report["pending_fields"]:
        items.append(
            AuditItem(
                value, "analysis_pending_field", "分析结果存在待确认字段", "review"
            )
        )
    for value in report["ai_inferred_refs"]:
        items.append(
            AuditItem(
                value, "analysis_ai_inferred", "分析输入包含 AI 推断证据", "review"
            )
        )
    for value in report["needs_confirmation_refs"]:
        items.append(
            AuditItem(
                value, "analysis_needs_confirmation", "分析输入包含待确认证据", "review"
            )
        )
    for index, item in enumerate(analysis_bundle.get("risksAndUncertainties", [])):
        if isinstance(item, dict):
            items.append(
                AuditItem(
                    f"risksAndUncertainties[{index}]",
                    str(item.get("type", "risk")),
                    str(item.get("description", item)),
                    "review",
                )
            )
    return items


def _evidence_sufficient(chain: APQPChain) -> bool:
    return bool(_evidence_coverage_report(chain)["ok"])


def _stage_validation(chain: APQPChain, stage: str) -> ChainValidationResult:
    if stage in {"ingest", "analyze"}:
        return ChainValidationResult(ok=True, messages=[], chain=chain)
    return validate_chain(chain)


def _ingest_evidence_report(chain: APQPChain) -> dict[str, Any]:
    missing_fields: list[str] = []
    duplicate_ids: list[str] = []
    seen_ids: set[str] = set()
    usable_non_ai = 0
    usable_count = 0
    ai_inferred_refs: list[str] = []
    needs_confirmation_refs: list[str] = []

    for index, evidence in enumerate(chain.evidence, start=1):
        label = evidence.evidence_id or f"evidence[{index}]"
        if not evidence.evidence_id:
            missing_fields.append(f"{label}.evidence_id")
        elif evidence.evidence_id in seen_ids:
            duplicate_ids.append(evidence.evidence_id)
        else:
            seen_ids.add(evidence.evidence_id)
        if not evidence.source.strip():
            missing_fields.append(f"{label}.source")
        if not evidence.content.strip():
            missing_fields.append(f"{label}.content")
        usable = bool(
            evidence.evidence_id
            and evidence.source.strip()
            and evidence.content.strip()
        )
        if usable:
            usable_count += 1
            if not evidence.ai_inferred:
                usable_non_ai += 1
        if evidence.ai_inferred:
            ai_inferred_refs.append(label)
        if evidence.needs_confirmation:
            needs_confirmation_refs.append(label)

    all_ai = bool(chain.evidence) and usable_count > 0 and usable_non_ai == 0
    uncovered_items = missing_fields + [f"duplicate:{item}" for item in duplicate_ids]
    if all_ai:
        uncovered_items.append("all_evidence_ai_inferred")

    required_count = max(len(chain.evidence), 1)
    ok = (
        bool(chain.evidence)
        and usable_count > 0
        and usable_non_ai > 0
        and not missing_fields
        and not duplicate_ids
    )
    return {
        "required_items": required_count,
        "covered_items": usable_count,
        "coverage_ratio": usable_count / required_count if required_count else 0.0,
        "uncovered_items": uncovered_items,
        "missing_refs": [],
        "ai_inferred_refs": ai_inferred_refs,
        "needs_confirmation_refs": needs_confirmation_refs,
        "legacy_mode": False,
        "stage_mode": "ingest",
        "ok": ok,
    }


def _evidence_coverage_report(chain: APQPChain) -> dict[str, Any]:
    if not chain.evidence:
        structurally_present = bool(
            chain.process_steps and chain.failure_modes and chain.controls
        )
        required_count = (
            len(chain.process_steps) + len(chain.failure_modes) + len(chain.controls)
        )
        return {
            "required_items": required_count,
            "covered_items": 0,
            "coverage_ratio": 0.0,
            "uncovered_items": [],
            "missing_refs": [],
            "ai_inferred_refs": [],
            "needs_confirmation_refs": [],
            "legacy_mode": True,
            "ok": structurally_present,
        }

    evidence_by_id = {
        item.evidence_id: item for item in chain.evidence if item.evidence_id
    }
    required_items = _iter_evidence_required_items(chain)
    uncovered_items: list[str] = []
    missing_refs: list[str] = []
    ai_inferred_refs: list[str] = []
    needs_confirmation_refs: list[str] = []

    for item_type, item_id, refs in required_items:
        label = f"{item_type}:{item_id}"
        normalized_refs = [str(ref).strip() for ref in refs if str(ref).strip()]
        if not normalized_refs:
            uncovered_items.append(label)
            continue
        for ref in normalized_refs:
            evidence = evidence_by_id.get(ref)
            if evidence is None:
                missing_refs.append(f"{label} -> {ref}")
                continue
            if evidence.ai_inferred:
                ai_inferred_refs.append(f"{label} -> {ref}")
            if evidence.needs_confirmation:
                needs_confirmation_refs.append(f"{label} -> {ref}")

    required_count = len(required_items)
    covered_count = required_count - len(uncovered_items)
    return {
        "required_items": required_count,
        "covered_items": covered_count,
        "coverage_ratio": covered_count / required_count if required_count else 0.0,
        "uncovered_items": uncovered_items,
        "missing_refs": missing_refs,
        "ai_inferred_refs": ai_inferred_refs,
        "needs_confirmation_refs": needs_confirmation_refs,
        "legacy_mode": False,
        "ok": bool(required_count)
        and not uncovered_items
        and not missing_refs
        and not ai_inferred_refs,
    }


def _iter_evidence_required_items(chain: APQPChain) -> list[tuple[str, str, list[str]]]:
    return [
        *[
            ("process_step", item.process_step_id, item.evidence_refs)
            for item in chain.process_steps
        ],
        *[
            ("failure_mode", item.pfmea_id, item.evidence_refs)
            for item in chain.failure_modes
        ],
        *[
            ("control_item", item.control_plan_id, item.evidence_refs)
            for item in chain.controls
        ],
    ]


def _evidence_manual_review_items(report: dict[str, Any]) -> list[AuditItem]:
    items: list[AuditItem] = []
    for value in report["uncovered_items"]:
        items.append(
            AuditItem(value, "evidence_uncovered", "对象缺少 evidence_refs", "blocker")
        )
    for value in report["missing_refs"]:
        items.append(
            AuditItem(
                value,
                "evidence_missing_ref",
                "evidence_refs 引用了不存在的证据",
                "blocker",
            )
        )
    for value in report["ai_inferred_refs"]:
        items.append(
            AuditItem(
                value,
                "evidence_ai_inferred",
                "引用证据为 AI 推断，需要人工确认",
                "blocker",
            )
        )
    for value in report["needs_confirmation_refs"]:
        items.append(
            AuditItem(
                value, "evidence_needs_confirmation", "对象或引用证据标记为待确认", "review"
            )
        )
    return items


def _row_needs_confirmation_items(chain: APQPChain) -> list[str]:
    items: list[str] = []
    for step in chain.process_steps:
        if step.needs_confirmation:
            items.append(f"process_step:{step.process_step_id}")
    for candidate in chain.failure_mode_candidates:
        if candidate.needs_confirmation:
            items.append(f"failure_mode_candidate:{candidate.candidate_id}")
    for failure in chain.failure_modes:
        if failure.needs_confirmation:
            items.append(f"failure_mode:{failure.pfmea_id}")
    for control in chain.controls:
        if control.needs_confirmation:
            items.append(f"control_item:{control.control_plan_id}")
    for link in chain.links:
        if link.needs_confirmation:
            items.append(_trace_link_label(link))
    items.extend(_pending_field_paths(chain.pending_fields))
    items.extend(_flagged_item_labels(chain.ai_inferred_items, "needs_confirmation"))
    return _dedupe_preserve_order(items)


def _row_needs_confirmation_manual_review_items(items: list[str]) -> list[AuditItem]:
    return [
        AuditItem(
            item,
            "row_needs_confirmation",
            "关键对象标记为待确认，需要人工复核后才能正式放行",
            "review",
        )
        for item in items
    ]


def _trace_link_label(link: Any) -> str:
    link_id = str(getattr(link, "trace_link_id", "")).strip()
    if link_id:
        return f"trace_link:{link_id}"
    from_id = str(getattr(link, "from_id", "")).strip()
    to_id = str(getattr(link, "to_id", "")).strip()
    if from_id or to_id:
        return f"trace_link:{from_id}->{to_id}"
    return "trace_link"


def _flagged_item_labels(items: Any, flag: str) -> list[str]:
    if isinstance(items, dict):
        iterable = [items]
    elif isinstance(items, list):
        iterable = items
    else:
        return []
    labels: list[str] = []
    for index, item in enumerate(iterable):
        if isinstance(item, str):
            if flag == "needs_confirmation" and item.strip():
                labels.append(item.strip())
            continue
        if not isinstance(item, dict) or not item.get(flag):
            continue
        labels.append(_flagged_item_label(item, index))
    return labels


def _flagged_item_label(item: dict[str, Any], index: int) -> str:
    for field_name in (
        "id",
        "item_id",
        "field",
        "evidence_id",
        "process_step_id",
        "pfmea_id",
        "control_plan_id",
        "candidate_id",
        "link_id",
        "trace_link_id",
    ):
        value = str(item.get(field_name, "")).strip()
        if value:
            return value
    return f"ai_inferred_item[{index}]"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def _confirmed_targets(chain: APQPChain) -> set[str]:
    return {
        str(item.get("target", "")).strip()
        for item in _review_confirmations(chain)
        if isinstance(item, dict) and str(item.get("target", "")).strip()
    }


def _confirmed_field_paths(chain: APQPChain) -> set[str]:
    field_paths: set[str] = set()
    for item in _review_confirmations(chain):
        if not isinstance(item, dict):
            continue
        field_path = str(item.get("field_path", "")).strip()
        if field_path:
            field_paths.add(field_path)
        target = str(item.get("target", "")).strip()
        field = str(item.get("field", "")).strip()
        if target.startswith("pending_field:"):
            field_paths.add(target.split(":", 1)[1].strip())
        if target and field:
            target_id = target.split(":", 1)[1] if ":" in target else target
            field_paths.add(f"{target_id}.{field}")
            field_paths.add(f"{target}.{field}")
    return field_paths


def _review_confirmations(chain: APQPChain) -> list[Any]:
    confirmations = chain.metadata.get(REVIEW_CONFIRMATIONS_KEY, [])
    return confirmations if isinstance(confirmations, list) else []


def _with_safe_ai_batch_confirmations(payload: dict[str, Any]) -> dict[str, Any]:
    targets = _safe_ai_batch_confirmation_targets(payload)
    if not targets:
        return payload
    patched = copy.deepcopy(payload)
    metadata = patched.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        return patched
    confirmations = metadata.setdefault(REVIEW_CONFIRMATIONS_KEY, [])
    if not isinstance(confirmations, list):
        return patched
    existing = {
        str(item.get("target", "")).strip()
        for item in confirmations
        if isinstance(item, dict)
    }
    for target in targets:
        if target in existing:
            continue
        confirmations.append(
            {
                "target": target,
                "confirmation_mode": "ai_recommended_batch",
                "source": "automation_review",
            }
        )
    return patched


def _unsafe_ai_batch_review_issues(payload: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for table, chain_key, id_fields, target_type in (
        ("process_flow", "process_steps", ("process_step_id", "id", "step_no"), "process_step"),
        ("pfmea", "failure_modes", ("pfmea_id", "id"), "failure_mode"),
        ("control_plan", "controls", ("control_plan_id", "id"), "control_item"),
    ):
        rows = payload.get(chain_key, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("confirmation_mode", "")).strip() != "ai_recommended_batch":
                continue
            row_id = _row_mapping_id(row, id_fields)
            if not row_id or _safe_ai_batch_row(payload, table, row):
                continue
            target = f"{target_type}:{row_id}"
            issues.append(
                build_review_issue(
                    category="AI批量确认",
                    message="该项目不满足低风险高置信批量确认条件，需要人工复核后才能正式放行。",
                    severity="blocker",
                    source="automation_review",
                    target=target,
                    automation_level="ai_recommended_batch",
                    can_batch_confirm=False,
                    human_reason_required=True,
                )
            )
    return issues


def _safe_ai_batch_confirmation_targets(payload: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for table, chain_key, id_fields, target_type in (
        ("process_flow", "process_steps", ("process_step_id", "id", "step_no"), "process_step"),
        ("pfmea", "failure_modes", ("pfmea_id", "id"), "failure_mode"),
        ("control_plan", "controls", ("control_plan_id", "id"), "control_item"),
    ):
        rows = payload.get(chain_key, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("confirmation_mode", "")).strip() != "ai_recommended_batch":
                continue
            row_id = _row_mapping_id(row, id_fields)
            if row_id and _safe_ai_batch_row(payload, table, row):
                targets.append(f"{target_type}:{row_id}")
    return _dedupe_preserve_order(targets)


def _safe_ai_batch_row(payload: dict[str, Any], table: str, row: dict[str, Any]) -> bool:
    if row.get("deleted") or row.get("soft_deleted"):
        return False
    refs = [str(ref).strip() for ref in row.get("evidence_refs", []) if str(ref).strip()]
    if not refs:
        return False
    confidence = _float_value(row.get("confidence"))
    if confidence is None or confidence < 0.85:
        return False
    if str(row.get("action_priority", row.get("AP", ""))).strip().upper() == "H":
        return False
    if (
        row.get("classification")
        or row.get("characteristic_refs")
        or row.get("special_characteristics")
        or row.get("source_special_characteristics")
    ):
        return False
    if table != "process_flow":
        step_id = str(row.get("process_step_id", "")).strip()
        for step in payload.get("process_steps", []):
            if (
                isinstance(step, dict)
                and str(step.get("process_step_id", "")).strip() == step_id
                and step.get("special_characteristics")
            ):
                return False
    return True


def _row_mapping_id(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field_name in fields:
        value = str(row.get(field_name, "")).strip()
        if value:
            return value
    return ""


def _without_confirmed(values: list[str], confirmed: set[str]) -> list[str]:
    return [value for value in values if not _is_confirmed(value, confirmed)]


def _is_confirmed(value: str, confirmed: set[str]) -> bool:
    text = str(value).strip()
    if not text:
        return False
    if text in confirmed:
        return True
    for item in confirmed:
        if _confirmation_matches_value(item, text):
            return True
    return False


def _confirmation_matches_value(confirmed: str, value: str) -> bool:
    if confirmed == value:
        return True
    if " -> " in value:
        _, ref = value.rsplit(" -> ", 1)
        if confirmed == ref.strip():
            return True
        if confirmed == f"evidence:{ref.strip()}":
            return True
    if ":" in confirmed:
        confirmed_type, confirmed_id = confirmed.split(":", 1)
        if value.startswith(f"{confirmed} -> "):
            return True
        if value == confirmed_id:
            return True
        if value.endswith(f":{confirmed_id}"):
            return True
        if value.startswith(f"{confirmed_id}."):
            return True
        if value.startswith(f"{confirmed}."):
            return True
        if value.endswith(f" -> {confirmed_id}"):
            return True
        if confirmed_type == "evidence" and value.endswith(f" -> {confirmed_id}"):
            return True
    return False


def _pending_fields(chain: APQPChain) -> list[str]:
    pending: list[str] = []
    for failure in chain.failure_modes:
        if not failure.failure_mode:
            pending.append(f"{failure.pfmea_id}.failure_mode")
        if not failure.failure_cause:
            pending.append(f"{failure.pfmea_id}.failure_cause")
    for control in chain.controls:
        if not control.specification:
            pending.append(f"{control.control_plan_id}.specification")
        if not control.reaction_plan:
            pending.append(f"{control.control_plan_id}.reaction_plan")
    for item in _pending_field_paths(getattr(chain, "pending_fields", [])):
        if item and item not in pending:
            pending.append(item)
    return pending


def _ai_inferred_items(chain: APQPChain) -> list[str]:
    items = [item.evidence_id for item in chain.evidence if item.ai_inferred]
    for item in _flagged_evidence_ids(
        getattr(chain, "ai_inferred_items", []), "ai_inferred"
    ):
        if item and item not in items:
            items.append(item)
    for item in getattr(chain, "ai_inferred_items", []):
        if isinstance(item, dict):
            continue
        value = str(item)
        if value and value not in items:
            items.append(value)
    return items
