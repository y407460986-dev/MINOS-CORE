"""Stage-level quality gates for MINOS-CORE pipelines."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from minos_core.observability.logging import get_logger

from ..action_closure import action_closure_issues
from ..audit import AuditReport, audit_chain
from ..change_management import blocking_change_impacts
from ..domain import APQPChain
from ..knowledge_recommendation import unresolved_recommendations
from ..review_issues import unresolved_review_issues
from ..validation import ChainValidationResult
from ._support import (
    _ai_inferred_items,
    _confirmed_field_paths,
    _confirmed_targets,
    _dedupe_preserve_order,
    _dedupe_review_issues,
    _dict_manual_review_items,
    _evidence_coverage_report,
    _evidence_manual_review_items,
    _ingest_evidence_report,
    _is_confirmed,
    _metadata_list,
    _pending_fields,
    _recommendation_manual_review_items,
    _review_issues_from_gate_debts,
    _row_needs_confirmation_items,
    _row_needs_confirmation_manual_review_items,
    _stage_validation,
    _strict_aiag_vda_pfmea_gate_enabled,
    _unsafe_ai_batch_review_issues,
    _with_safe_ai_batch_confirmations,
    _without_confirmed,
)
from .evaluators import (
    evaluate_analysis_bundle_gate,
    evaluate_brainstorm_failure_modes_input_gate,
    evaluate_control_plan_bundle_gate,
    evaluate_failure_mode_candidates_gate,
    evaluate_pfd_bundle_gate,
    evaluate_pfmea_bundle_gate,
)

logger = get_logger(__name__)

__all__ = [
    "StageQualityGate",
    "ExportGateError",
    "evaluate_analysis_bundle_gate",
    "evaluate_brainstorm_failure_modes_input_gate",
    "evaluate_control_plan_bundle_gate",
    "evaluate_failure_mode_candidates_gate",
    "evaluate_pfd_bundle_gate",
    "evaluate_pfmea_bundle_gate",
    "evaluate_export_gate",
    "require_export_gate",
    "evaluate_stage_gate",
]

evaluate_three_table_linkage: Callable[[dict[str, Any]], dict[str, Any]] | None
try:
    from ..three_table_linkage import evaluate_three_table_linkage
except ImportError:
    evaluate_three_table_linkage = None


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
    linkage_gaps: list[dict[str, Any]] = field(default_factory=list)
    linkage_summary: dict[str, Any] = field(default_factory=dict)
    sync_issues: list[dict[str, Any]] = field(default_factory=list)
    live_linkage_issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if the gate allows the pipeline to continue."""
        return self.can_continue

    @property
    def needs_human_review(self) -> bool:
        """Return True if any items require manual human review."""
        return bool(self.manual_review_items or self.needs_confirmation_items)

    @property
    def allow_formal_release(self) -> bool:
        """Return True if the gate permits a formal (non-draft) export."""
        return self.allow_user_export

    @property
    def draft_only(self) -> bool:
        """Return True if the chain can continue but only as a draft (not formally released)."""
        return bool(
            self.can_continue
            and not self.allow_formal_release
            and self.needs_confirmation_items
        )

    def model_dump(self) -> dict[str, Any]:
        """Serialize the gate state to a plain dictionary.

        Returns:
            dict[str, Any]: A dictionary with all gate fields suitable for
                JSON serialization or logging.
        """
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
            "linkage_gaps": self.linkage_gaps,
            "linkage_summary": self.linkage_summary,
            "sync_issues": self.sync_issues,
            "live_linkage_issues": self.live_linkage_issues,
        }


class ExportGateError(ValueError):
    """Raised when a user-facing export is blocked by the export gate."""

    def __init__(self, gate: StageQualityGate) -> None:
        self.gate = gate
        super().__init__(_export_gate_failure_message(gate))


def _unresolved_live_linkage_issues(
    chain: dict[str, Any] | APQPChain,
) -> list[dict[str, Any]]:
    """Check for unresolved live-linkage impacts that block final export.

    Returns blocker issues for rows whose review_status indicates an
    unconfirmed live-linkage sync or a stub that still needs human review.
    """
    issues: list[dict[str, Any]] = []
    for table_key, row_key in [
        ("process_steps", "process_step_id"),
        ("failure_modes", "pfmea_id"),
        ("controls", "control_plan_id"),
    ]:
        rows = chain.get(table_key, []) if isinstance(chain, dict) else getattr(chain, table_key, [])
        for row in rows:
            if isinstance(row, dict):
                deleted = bool(row.get("deleted", False))
                review_status = str(row.get("review_status", ""))
                needs_conf = bool(row.get("needs_confirmation", False))
                row_id = str(row.get(row_key, "?"))
            else:
                deleted = bool(getattr(row, "deleted", False))
                review_status = str(getattr(row, "review_status", ""))
                needs_conf = bool(getattr(row, "needs_confirmation", False))
                row_id = str(getattr(row, row_key, "?"))

            if deleted:
                continue

            if review_status == "待同步确认":
                issues.append({
                    "issue_id": f"LINKAGE-UNRESOLVED-{table_key}-{row_id}",
                    "severity": "blocker",
                    "message": f"行 {row_id} 标记为待同步确认，上游已变更。",
                })

            if review_status == "联动新增" and needs_conf:
                issues.append({
                    "issue_id": f"LINKAGE-STUB-UNCONFIRMED-{table_key}-{row_id}",
                    "severity": "blocker",
                    "message": f"联动新增行 {row_id} 尚未人工确认。",
                })

    return issues


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
    if not gate.validation.ok:
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
    blocker_linkage_gaps = [g for g in gate.linkage_gaps if g.get("severity") == "blocker"]
    if blocker_linkage_gaps:
        lines.append("linkage_blocker_gaps: " + ", ".join(
            str(g.get("gap_id", g.get("message", ""))) for g in blocker_linkage_gaps
        ))
    sync_blockers = [i for i in gate.sync_issues if i.get("severity") == "blocker"]
    if sync_blockers:
        lines.append("sync_blockers: " + ", ".join(
            str(i.get("issue_id", i.get("message", ""))) for i in sync_blockers
        ))
    live_linkage_blockers = [i for i in gate.live_linkage_issues if i.get("severity") == "blocker"]
    if live_linkage_blockers:
        lines.append("live_linkage_blockers: " + ", ".join(
            str(i.get("issue_id", i.get("message", ""))) for i in live_linkage_blockers
        ))
    if gate.validation.messages:
        _append_gate_detail(lines, "validation_messages", gate.validation.messages)
    return "\n".join(lines)


def _append_gate_detail(lines: list[str], label: str, values: list[Any]) -> None:
    """Append a non-empty labelled list line to the gate message."""
    if values:
        lines.append(f"{label}: " + ", ".join(str(value) for value in values))


def _drawing_risk_review_items(chain: APQPChain) -> list[dict[str, Any]]:
    """Collect unconfirmed drawing-analysis risks as manual review items."""
    confirmed = _confirmed_targets(chain)
    risks = _metadata_list(chain, "drawing_analysis_risks") + _metadata_list(
        chain, "ocr_identity_risks"
    )
    items: list[dict[str, Any]] = []
    indexes: dict[str, int] = {}
    for risk in risks:
        risk_id = str(risk.get("risk_id", risk.get("item_id", ""))).strip()
        target = str(risk.get("target", "")).strip()
        if not risk_id:
            continue
        if _is_confirmed(risk_id, confirmed) or (target and _is_confirmed(target, confirmed)):
            continue
        item = dict(risk)
        item["item_id"] = risk_id
        item.setdefault("category", "drawing_analysis")
        item.setdefault("severity", "review")
        item.setdefault("message", "图纸识别风险需要人工复核。")
        if risk_id in indexes:
            existing_index = indexes[risk_id]
            if (
                item.get("severity") == "blocker"
                and items[existing_index].get("severity") != "blocker"
            ):
                items[existing_index] = item
            continue
        indexes[risk_id] = len(items)
        items.append(item)
    return items


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
    audit_blockers = [
        item
        for item in audit.manual_review_items
        if getattr(item, "severity", "") == "blocker"
    ]
    confirmed_targets = _confirmed_targets(chain)
    confirmed_field_paths = _confirmed_field_paths(chain)
    pending_fields = _without_confirmed(_pending_fields(chain), confirmed_field_paths)
    ai_inferred_items = _without_confirmed(
        _ai_inferred_items(chain),
        confirmed_targets | confirmed_field_paths,
    )
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
    drawing_risk_items = _drawing_risk_review_items(chain)
    [
        item for item in drawing_risk_items if item.get("severity") == "blocker"
    ]
    linkage_gaps: list[dict[str, Any]] = []
    linkage_summary: dict[str, Any] = {}
    sync_issues: list[dict[str, Any]] = []
    if evaluate_three_table_linkage is not None:
        try:
            linkage_report = evaluate_three_table_linkage(
                chain if isinstance(chain, dict) else chain.model_dump()
            )
            linkage_map = linkage_report.get("linkage_map", {})
            linkage_gaps = linkage_map.get("gaps", [])
            linkage_summary = linkage_map.get("summary", {})
            sync_issues = linkage_report.get("sync_issues", [])
        except Exception as exc:
            # Log full stack trace for debugging
            logger.exception("三表联动检查执行失败，链接报告数据可能不完整")
            linkage_gaps = [{
                "gap_id": "GAP-LINKAGE-EVALUATION-ERROR",
                "category": "三表联动",
                "category_key": "linkage_evaluation_error",
                "severity": "blocker",
                "source": "three_table_linkage",
                "target": "quality_gate",
                "message": f"三表联动检查执行失败：{type(exc).__name__}: {exc}",
                "recommended_action": "检查三表数据是否完整，或联系开发人员排查联动检查逻辑。",
                "status": "待处理",
                "evidence_refs": [],
            }]
            linkage_summary = {}
    linkage_blockers = [g for g in linkage_gaps if g.get("severity") == "blocker"]
    sync_blockers = [i for i in sync_issues if i.get("severity") == "blocker"]
    live_linkage_issues = _unresolved_live_linkage_issues(chain)
    live_linkage_blockers = [i for i in live_linkage_issues if i.get("severity") == "blocker"]
    linkage_review_items = [
        g for g in linkage_gaps if g.get("severity") in ("warning", "review")
    ]
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
        and not audit_blockers
        and not drawing_risk_items
        and not linkage_blockers
        and not sync_blockers
        and not live_linkage_blockers
    )
    manual_review_items: list[Any] = list(audit.manual_review_items)
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
    manual_review_items.extend(_dict_manual_review_items(drawing_risk_items))
    manual_review_items.extend(_recommendation_manual_review_items(recommendation_blockers))
    # manual_review_items.extend(_dict_manual_review_items(unresolved_action_review_items))
    manual_review_items.extend(linkage_review_items)
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
        linkage_gaps=linkage_gaps,
        linkage_summary=linkage_summary,
        sync_issues=sync_issues,
        live_linkage_issues=live_linkage_issues,
    )
