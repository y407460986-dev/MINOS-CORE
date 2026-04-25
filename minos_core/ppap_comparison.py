"""Compare generated APQP chains against an approved PPAP three-table baseline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .adapters.fixture_json import load_fixture_payload
from .domain import APQPChain, ControlItem, FailureMode, ProcessStep
from .quality_matching import overlap_score, quality_tokens

MATCHED = "matched"
MISSING_PROCESS_STEP = "missing_process_step"
MISSING_PFMEA_ITEM = "missing_pfmea_item"
MISSING_CONTROL_ITEM = "missing_control_item"
EXTRA_GENERATED_ITEM = "extra_generated_item"
UNEXPLAINED_DIFFERENCE = "unexplained_difference"


@dataclass(frozen=True)
class ComparisonDifference:
    category: str
    item_type: str
    baseline_id: str = ""
    generated_id: str = ""
    message: str = ""
    evidence: list[str] = field(default_factory=list)
    review: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "item_type": self.item_type,
            "baseline_id": self.baseline_id,
            "generated_id": self.generated_id,
            "message": self.message,
            "evidence": list(self.evidence),
            "review": dict(self.review),
        }


@dataclass(frozen=True)
class PPAPComparisonReport:
    counts: dict[str, int]
    differences: list[ComparisonDifference]
    baseline_metadata: dict[str, Any] = field(default_factory=dict)
    generated_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(item.category == MATCHED for item in self.differences)

    @property
    def unexplained_differences(self) -> list[ComparisonDifference]:
        return [
            item
            for item in self.differences
            if item.category not in {MATCHED, EXTRA_GENERATED_ITEM}
        ]

    def model_dump(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "counts": dict(self.counts),
            "differences": [item.model_dump() for item in self.differences],
            "baseline_metadata": dict(self.baseline_metadata),
            "generated_metadata": dict(self.generated_metadata),
        }


def compare_to_approved_ppap(
    generated: APQPChain | dict[str, Any] | str | Path,
    approved_baseline: APQPChain | dict[str, Any] | str | Path,
) -> PPAPComparisonReport:
    """Return a structured, reviewable comparison against an approved baseline."""

    generated_chain = _as_chain(generated)
    baseline_chain = _as_chain(approved_baseline)
    differences: list[ComparisonDifference] = []

    _compare_collection(
        differences,
        baseline_items=baseline_chain.process_steps,
        generated_items=generated_chain.process_steps,
        item_type="process_step",
        id_getter=lambda item: item.process_step_id,
        signature_getter=_process_step_signature,
        missing_category=MISSING_PROCESS_STEP,
        baseline_text_getter=_process_step_text,
        generated_text_getter=_process_step_text,
        evidence_getter=lambda item: item.evidence_refs,
    )
    _compare_collection(
        differences,
        baseline_items=baseline_chain.failure_modes,
        generated_items=generated_chain.failure_modes,
        item_type="pfmea_item",
        id_getter=lambda item: item.pfmea_id,
        signature_getter=_pfmea_signature,
        missing_category=MISSING_PFMEA_ITEM,
        baseline_text_getter=_pfmea_text,
        generated_text_getter=_pfmea_text,
        evidence_getter=lambda item: item.evidence_refs,
    )
    _compare_collection(
        differences,
        baseline_items=baseline_chain.controls,
        generated_items=generated_chain.controls,
        item_type="control_item",
        id_getter=lambda item: item.control_plan_id,
        signature_getter=_control_signature,
        missing_category=MISSING_CONTROL_ITEM,
        baseline_text_getter=_control_text,
        generated_text_getter=_control_text,
        evidence_getter=lambda item: item.evidence_refs,
    )

    counts = {category: 0 for category in _categories()}
    for item in differences:
        counts[item.category] = counts.get(item.category, 0) + 1
    counts.update(
        {
            "baseline_process_steps": len(baseline_chain.process_steps),
            "generated_process_steps": len(generated_chain.process_steps),
            "baseline_pfmea_items": len(baseline_chain.failure_modes),
            "generated_pfmea_items": len(generated_chain.failure_modes),
            "baseline_control_items": len(baseline_chain.controls),
            "generated_control_items": len(generated_chain.controls),
        }
    )
    return PPAPComparisonReport(
        counts=counts,
        differences=differences,
        baseline_metadata=baseline_chain.metadata,
        generated_metadata=generated_chain.metadata,
    )


def compare_ppap_to_approved_baseline(
    generated: APQPChain | dict[str, Any] | str | Path,
    approved_baseline: APQPChain | dict[str, Any] | str | Path,
) -> PPAPComparisonReport:
    return compare_to_approved_ppap(generated, approved_baseline)


def _compare_collection(
    differences: list[ComparisonDifference],
    *,
    baseline_items: list[Any],
    generated_items: list[Any],
    item_type: str,
    id_getter: Any,
    signature_getter: Any,
    missing_category: str,
    baseline_text_getter: Any,
    generated_text_getter: Any,
    evidence_getter: Any,
) -> None:
    generated_by_id = {id_getter(item): item for item in generated_items}
    baseline_by_id = {id_getter(item): item for item in baseline_items}
    matched_generated_ids: set[str] = set()

    for baseline_item in baseline_items:
        baseline_id = id_getter(baseline_item)
        generated_item = generated_by_id.get(baseline_id)
        if generated_item is None:
            differences.append(
                _difference(
                    category=missing_category,
                    item_type=item_type,
                    baseline_id=baseline_id,
                    message=f"Approved baseline {item_type} {baseline_id} is missing from generated draft.",
                    evidence=evidence_getter(baseline_item),
                    review={
                        "required": True,
                        "reason": "approved baseline item is not covered by generated draft",
                        "suggested_action": "confirm whether this approved PPAP item should be added or intentionally excluded",
                    },
                )
            )
            continue

        matched_generated_ids.add(baseline_id)
        if signature_getter(baseline_item) == signature_getter(generated_item):
            differences.append(
                _difference(
                    category=MATCHED,
                    item_type=item_type,
                    baseline_id=baseline_id,
                    generated_id=baseline_id,
                    message=f"Generated {item_type} {baseline_id} matches approved baseline structure.",
                    evidence=_merged_evidence(
                        evidence_getter(baseline_item), evidence_getter(generated_item)
                    ),
                    review={"required": False, "reason": "baseline and generated signatures match"},
                )
            )
            continue

        differences.append(
            _difference(
                category=UNEXPLAINED_DIFFERENCE,
                item_type=item_type,
                baseline_id=baseline_id,
                generated_id=baseline_id,
                message=f"Generated {item_type} {baseline_id} differs from approved baseline.",
                evidence=_merged_evidence(
                    evidence_getter(baseline_item), evidence_getter(generated_item)
                ),
                review={
                    "required": True,
                    "reason": "same identifier has different normalized content",
                    "baseline_signature": signature_getter(baseline_item),
                    "generated_signature": signature_getter(generated_item),
                    "text_overlap_score": overlap_score(
                        quality_tokens(baseline_text_getter(baseline_item)),
                        quality_tokens(generated_text_getter(generated_item)),
                    ),
                },
            )
        )

    for generated_item in generated_items:
        generated_id = id_getter(generated_item)
        if generated_id in baseline_by_id or generated_id in matched_generated_ids:
            continue
        differences.append(
            _difference(
                category=EXTRA_GENERATED_ITEM,
                item_type=item_type,
                generated_id=generated_id,
                message=f"Generated {item_type} {generated_id} is not present in approved baseline.",
                evidence=evidence_getter(generated_item),
                review={
                    "required": True,
                    "reason": "generated draft includes an item outside approved baseline",
                    "suggested_action": "review source evidence and decide whether it is a justified update",
                },
            )
        )


def _as_chain(value: APQPChain | dict[str, Any] | str | Path) -> APQPChain:
    if isinstance(value, APQPChain):
        return value
    if isinstance(value, (str, Path)):
        return APQPChain(**load_fixture_payload(value))
    return APQPChain(**value)


def _difference(**kwargs: Any) -> ComparisonDifference:
    return ComparisonDifference(**kwargs)


def _categories() -> tuple[str, ...]:
    return (
        MISSING_PROCESS_STEP,
        MISSING_PFMEA_ITEM,
        MISSING_CONTROL_ITEM,
        EXTRA_GENERATED_ITEM,
        MATCHED,
        UNEXPLAINED_DIFFERENCE,
    )


def _process_step_signature(item: ProcessStep) -> tuple[Any, ...]:
    return (
        item.process_step_id,
        item.sequence,
        _normalized(item.operation),
        _normalized(item.process_function),
        tuple(sorted(item.special_characteristics)),
    )


def _pfmea_signature(item: FailureMode) -> tuple[Any, ...]:
    return (
        item.pfmea_id,
        item.process_step_id,
        _normalized(item.process_function),
        _normalized(item.failure_mode),
        _normalized(item.failure_effect),
        int(item.severity or 0),
        _normalized(item.failure_cause),
        int(item.occurrence or 0),
        _normalized(item.prevention_control),
        _normalized(item.detection_control),
        int(item.detection or 0),
        _normalized(item.action_priority),
        _normalized(item.classification),
        _normalized(item.linked_control_plan_id),
    )


def _control_signature(item: ControlItem) -> tuple[Any, ...]:
    return (
        item.control_plan_id,
        item.process_step_id,
        item.pfmea_id,
        _normalized(item.product_process_characteristic),
        _normalized(item.specification),
        _normalized(item.classification),
        _normalized(item.measurement_method),
        _normalized(item.sample_size),
        _normalized(item.sample_frequency),
        _normalized(item.control_method),
        _normalized(item.reaction_plan),
    )


def _process_step_text(item: ProcessStep) -> str:
    return " ".join([item.operation, item.process_function, " ".join(item.special_characteristics)])


def _pfmea_text(item: FailureMode) -> str:
    return " ".join(
        [
            item.process_function,
            item.failure_mode,
            item.failure_effect,
            item.failure_cause,
            item.prevention_control,
            item.detection_control,
            item.classification,
        ]
    )


def _control_text(item: ControlItem) -> str:
    return " ".join(
        [
            item.product_process_characteristic,
            item.specification,
            item.classification,
            item.measurement_method,
            item.control_method,
            item.reaction_plan,
        ]
    )


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _merged_evidence(left: list[str], right: list[str]) -> list[str]:
    return sorted(set(left).union(right))
