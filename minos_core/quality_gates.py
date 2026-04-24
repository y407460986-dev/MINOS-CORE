"""Stage-level quality gates for MINOS-CORE pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .audit import AuditReport, audit_chain
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
    evidence_sufficient = _evidence_sufficient(chain)
    can_continue = bool(validation) and evidence_sufficient
    allow_user_export = can_continue and not pending_fields
    return StageQualityGate(
        stage=stage,
        can_continue=can_continue,
        allow_user_export=allow_user_export,
        validation=validation,
        audit=audit,
        evidence_sufficient=evidence_sufficient,
        pending_fields=pending_fields,
        ai_inferred_items=ai_inferred_items,
        manual_review_items=list(audit.manual_review_items),
    )


def _evidence_sufficient(chain: APQPChain) -> bool:
    return bool(chain.process_steps and chain.failure_modes and chain.controls)


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
