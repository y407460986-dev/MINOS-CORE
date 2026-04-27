"""Validation rules for APQP chains."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from .domain import APQPChain


MOJIBAKE_MARKERS = ("�", "Ã", "Â", "å", "æ", "ä¸", "é", "ï¿½")


@dataclass(frozen=True)
class ChainValidationResult:
    ok: bool
    messages: list[str]
    chain: APQPChain

    @property
    def valid(self) -> bool:
        return self.ok

    def __bool__(self) -> bool:
        return self.ok

    def __str__(self) -> str:
        return "OK" if self.ok else "\n".join(self.messages)


def validate_chain(chain: APQPChain | dict[str, Any]) -> ChainValidationResult:
    """Validate text integrity and PFD/PFMEA/CP linkage rules."""

    if isinstance(chain, dict):
        chain = APQPChain(**chain)
    issues: list[str] = []
    issues.extend(_mojibake_issues(chain))
    issues.extend(_pfd_pfmea_issues(chain))
    issues.extend(_mandatory_cp_issues(chain))
    if _strict_three_table_linkage_enabled(chain):
        issues.extend(_three_table_linkage_issues(chain))
    return ChainValidationResult(ok=not issues, messages=issues, chain=chain)


def _strict_three_table_linkage_enabled(chain: APQPChain) -> bool:
    metadata = chain.metadata if isinstance(chain.metadata, dict) else {}
    if metadata.get("strict_three_table_linkage"):
        return True
    if metadata.get("generated") is True:
        return True
    if metadata.get("edit_history"):
        return True
    generation_mode = str(metadata.get("generation_mode", "")).strip()
    if generation_mode in {
        "ai_drawing_three_table_generation",
        "human_edited_three_table_generation",
    }:
        return True
    generation_modes = metadata.get("generation_modes", [])
    if isinstance(generation_modes, list):
        return any(
            str(mode).strip()
            in {
                "drawing_analysis_process_flow_inference",
                "process_flow_pfmea_ai_draft",
                "pfmea_control_plan_rules",
            }
            for mode in generation_modes
        )
    return False


def _mojibake_issues(value: Any, path: str = "chain") -> list[str]:
    issues: list[str] = []
    if isinstance(value, str):
        if any(marker in value for marker in MOJIBAKE_MARKERS):
            issues.append(f"{path} contains possible mojibake: {value!r}")
        return issues
    if is_dataclass(value):
        for item in fields(value):
            issues.extend(_mojibake_issues(getattr(value, item.name), f"{path}.{item.name}"))
        return issues
    if isinstance(value, dict):
        for key, item in value.items():
            issues.extend(_mojibake_issues(item, f"{path}.{key}"))
        return issues
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            issues.extend(_mojibake_issues(item, f"{path}[{index}]"))
    return issues


def _pfd_pfmea_issues(chain: APQPChain) -> list[str]:
    issues: list[str] = []
    step_ids = {step.process_step_id for step in chain.process_steps}
    pfmea_step_ids = {item.process_step_id for item in chain.failure_modes}

    for step_id in sorted(step_ids - pfmea_step_ids):
        issues.append(f"process step {step_id!r} has no PFMEA row")
    for step_id in sorted(pfmea_step_ids - step_ids):
        issues.append(f"PFMEA references missing process step {step_id!r}")
    return issues


def _mandatory_cp_issues(chain: APQPChain) -> list[str]:
    issues: list[str] = []
    control_ids = {item.control_plan_id for item in chain.controls}
    controlled_pfmea_ids = {item.pfmea_id for item in chain.controls if item.pfmea_id}

    for failure in chain.failure_modes:
        if not failure.is_mandatory_control:
            continue
        has_linked_control = bool(failure.linked_control_plan_id and failure.linked_control_plan_id in control_ids)
        has_pfmea_control = failure.pfmea_id in controlled_pfmea_ids
        if not (has_linked_control or has_pfmea_control):
            issues.append(
                f"mandatory/high-risk PFMEA {failure.pfmea_id!r} is not covered by control plan"
            )
    return issues


def _three_table_linkage_issues(chain: APQPChain) -> list[str]:
    issues: list[str] = []
    steps_by_id = {step.process_step_id: step for step in chain.process_steps}
    failures_by_id = {failure.pfmea_id: failure for failure in chain.failure_modes}
    controls_by_pfmea: dict[str, list[Any]] = {}
    for control in chain.controls:
        if control.process_step_id and control.process_step_id not in steps_by_id:
            issues.append(
                f"control plan {control.control_plan_id!r} references missing process step {control.process_step_id!r}"
            )
        if control.pfmea_id:
            controls_by_pfmea.setdefault(control.pfmea_id, []).append(control)

    for step_id, step in sorted(steps_by_id.items()):
        step_failures = [
            failure for failure in chain.failure_modes if failure.process_step_id == step_id
        ]
        if step_failures:
            continue
        if _has_step_characteristics(step):
            issues.append(
                f"process step {step_id!r} has characteristics but no PFMEA risk row"
            )

    for failure in chain.failure_modes:
        step = steps_by_id.get(failure.process_step_id)
        if step is None:
            continue
        if not _text_matches_any(
            failure.process_function,
            [step.process_function, step.process_purpose, step.operation],
        ):
            issues.append(
                f"PFMEA {failure.pfmea_id!r} does not inherit function from PFD step {failure.process_step_id!r}"
            )
        if _special_refs(failure) and not _special_refs(failure).issubset(
            _special_refs(step)
        ):
            issues.append(
                f"PFMEA {failure.pfmea_id!r} special characteristics are not carried from PFD step {failure.process_step_id!r}"
            )
        if not failure.is_mandatory_control:
            continue
        controls = controls_by_pfmea.get(failure.pfmea_id, [])
        if not controls:
            continue
        if not any(_control_covers_failure(control, failure) for control in controls):
            issues.append(
                f"high-risk PFMEA {failure.pfmea_id!r} has CP rows but no effective control content"
            )

    for step in chain.process_steps:
        step_specials = _special_refs(step)
        if not step_specials:
            continue
        pfmea_specials = {
            ref
            for failure in chain.failure_modes
            if failure.process_step_id == step.process_step_id
            for ref in _special_refs(failure)
        }
        cp_specials = {
            ref
            for control in chain.controls
            if control.process_step_id == step.process_step_id
            for ref in _special_refs(control)
        }
        missing_pfmea = sorted(step_specials - pfmea_specials)
        missing_cp = sorted(step_specials - cp_specials)
        if missing_pfmea:
            issues.append(
                f"special characteristics on PFD step {step.process_step_id!r} missing from PFMEA: {', '.join(missing_pfmea)}"
            )
        if missing_cp:
            issues.append(
                f"special characteristics on PFD step {step.process_step_id!r} missing from control plan: {', '.join(missing_cp)}"
            )

    for control in chain.controls:
        for field_name, value in (
            ("measurement_method", control.measurement_method),
            ("sample_frequency", control.sample_frequency),
            ("reaction_plan", control.reaction_plan),
        ):
            if not str(value).strip():
                issues.append(
                    f"control plan {control.control_plan_id!r} is missing {field_name}"
                )
    return issues


def _has_step_characteristics(step: Any) -> bool:
    return bool(
        _string_values(getattr(step, "special_characteristics", []))
        or _string_values(getattr(step, "product_characteristics", []))
        or _string_values(getattr(step, "process_characteristics", []))
    )


def _special_refs(item: Any) -> set[str]:
    refs: set[str] = set()
    for field_name in (
        "special_characteristics",
        "characteristic_refs",
        "product_characteristics",
        "process_characteristics",
        "source_special_characteristics",
    ):
        refs.update(_string_values(getattr(item, field_name, [])))
    classification = str(getattr(item, "classification", "")).strip()
    if classification:
        refs.update(_string_values(classification.split(",")))
    return refs


def _control_covers_failure(control: Any, failure: Any) -> bool:
    control_text = " ".join(
        str(value)
        for value in (
            control.control_method,
            control.measurement_method,
            control.product_process_characteristic,
            control.specification,
            control.source_failure_cause,
            control.source_prevention_control,
            control.source_detection_control,
        )
        if str(value).strip()
    ).lower()
    required = [
        failure.failure_cause,
        failure.prevention_control,
        failure.detection_control,
    ]
    return any(_text_matches_any(value, [control_text]) for value in required) or bool(
        str(control.control_method).strip()
        and str(control.measurement_method).strip()
        and str(control.reaction_plan).strip()
    )


def _text_matches_any(value: str, candidates: list[str]) -> bool:
    text = " ".join(str(value or "").lower().split())
    if not text:
        return False
    return any(text in " ".join(str(candidate or "").lower().split()) for candidate in candidates)


def _string_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = [value]
    return {str(item).strip() for item in values if str(item).strip()}
