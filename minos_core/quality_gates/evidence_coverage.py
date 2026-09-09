"""Evidence coverage checking and reporting."""
from __future__ import annotations

from typing import Any

from ..audit import AuditItem
from ..domain import APQPChain
from ..validation import ChainValidationResult, validate_chain

__all__ = [
    "_evidence_coverage_report",
    "_evidence_manual_review_items",
    "_evidence_sufficient",
    "_ingest_evidence_report",
    "_iter_evidence_required_items",
    "_stage_validation",
]


def _evidence_sufficient(chain: APQPChain) -> bool:
    """Return True if the chain has sufficient evidence coverage."""
    return bool(_evidence_coverage_report(chain)["ok"])


def _stage_validation(chain: APQPChain, stage: str) -> ChainValidationResult:
    """Return validation result; ingest/analyze stages skip full chain validation."""
    if stage in {"ingest", "analyze"}:
        return ChainValidationResult(ok=True, messages=[], chain=chain)
    return validate_chain(chain)


def _ingest_evidence_report(chain: APQPChain) -> dict[str, Any]:
    """Compute an evidence-coverage report for the ingest stage.

    Validates that each evidence item has an ID, source, and content, then
    categorises items as AI-inferred or needing confirmation.
    """
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
    """Produce an evidence-coverage report after chain assembly.

    Maps each required item (process step, failure mode, control) to its
    evidence references and reports any missing or AI-inferred refs.
    """
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
    """Yield required evidence items from process steps, failure modes, and controls."""
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
    """Convert an evidence-coverage report into a list of AuditItems for manual review."""
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
