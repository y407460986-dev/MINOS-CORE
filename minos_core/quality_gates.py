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
    validation = _stage_validation(chain, stage)
    audit = audit_chain(chain)
    pending_fields = _pending_fields(chain)
    ai_inferred_items = _ai_inferred_items(chain)
    evidence_coverage = (
        _ingest_evidence_report(chain)
        if stage in {"ingest", "analyze"}
        else _evidence_coverage_report(chain)
    )
    evidence_sufficient = bool(evidence_coverage["ok"])
    can_continue = (
        evidence_sufficient
        if stage in {"ingest", "analyze"}
        else bool(validation) and evidence_sufficient
    )
    allow_user_export = (
        False if stage in {"ingest", "analyze"} else can_continue and not pending_fields
    )
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


def evaluate_analysis_bundle_gate(
    analysis_bundle: dict[str, Any],
    stage: str = "analyze",
) -> StageQualityGate:
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
    ai_inferred = analysis_bundle.get("ai_inferred_items", [])
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
    ai_inferred_refs = [
        str(item.get("evidence_id"))
        for item in ai_inferred
        if isinstance(item, dict) and item.get("evidence_id")
    ]
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
        and process_clues
        and evidence_sufficient
        and not all_ai
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
        "usable_route_candidate_count": len(process_clues),
        "drawing_count": len(drawings),
        "characteristic_count": len(characteristics),
        "evidence_count": len(evidence),
        "non_inferred_evidence_count": len(non_ai_evidence),
        "pending_fields": pending_fields,
        "uncovered_items": uncovered_items,
        "missing_refs": [],
        "ai_inferred_refs": ai_inferred_refs,
        "needs_confirmation_refs": needs_confirmation_refs,
        "evidence_ids": evidence_ids,
        "legacy_mode": False,
        "evidence_sufficient": evidence_sufficient,
        "ok": ok,
    }


def _pending_field_paths(items: Any) -> list[str]:
    if not isinstance(items, list):
        return ["pending_fields"]
    return [
        f"{item.get('source_ref', '')}.{item.get('field', '')}".strip(".")
        for item in items
        if isinstance(item, dict) and item.get("field")
    ]


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
