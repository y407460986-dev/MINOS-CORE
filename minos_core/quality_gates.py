"""Stage-level quality gates for MINOS-CORE pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .audit import AuditItem, AuditReport, audit_chain
from .domain import APQPChain
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

    @property
    def ok(self) -> bool:
        return self.can_continue

    def model_dump(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "can_continue": self.can_continue,
            "allow_user_export": self.allow_user_export,
            "evidence_sufficient": self.evidence_sufficient,
            "pending_fields": self.pending_fields,
            "ai_inferred_items": self.ai_inferred_items,
            "evidence_coverage": self.evidence_coverage,
            "missing_evidence_refs": self.missing_evidence_refs,
            "uncovered_evidence_items": self.uncovered_evidence_items,
            "needs_confirmation_items": self.needs_confirmation_items,
            "manual_review_items": [
                item.__dict__ if hasattr(item, "__dict__") else item
                for item in self.manual_review_items
            ],
            "validation_messages": self.validation.messages,
            "audit_counts": self.audit.counts,
        }


def evaluate_stage_gate(
    chain: APQPChain | dict[str, Any], stage: str = "validate"
) -> StageQualityGate:
    if isinstance(chain, dict):
        chain = APQPChain(**chain)
    validation = validate_chain(chain)
    audit = audit_chain(chain)
    pending_fields = _pending_fields(chain)
    ai_inferred_items = _ai_inferred_items(chain)
    evidence_coverage = _evidence_coverage_report(chain)
    evidence_sufficient = bool(evidence_coverage["ok"])
    can_continue = bool(validation) and evidence_sufficient
    allow_user_export = can_continue and not pending_fields
    manual_review_items = list(audit.manual_review_items)
    manual_review_items.extend(_evidence_manual_review_items(evidence_coverage))
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
        needs_confirmation_items=list(evidence_coverage["needs_confirmation_refs"]),
    )


def _evidence_sufficient(chain: APQPChain) -> bool:
    return bool(_evidence_coverage_report(chain)["ok"])


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
        and not ai_inferred_refs
        and not needs_confirmation_refs,
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
                value, "evidence_needs_confirmation", "引用证据标记为待确认", "blocker"
            )
        )
    return items


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
    return pending


def _ai_inferred_items(chain: APQPChain) -> list[str]:
    return [item.evidence_id for item in chain.evidence if item.ai_inferred]
