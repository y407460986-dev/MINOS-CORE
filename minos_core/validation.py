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
    return ChainValidationResult(ok=not issues, messages=issues, chain=chain)


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
