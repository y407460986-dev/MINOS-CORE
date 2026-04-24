"""Quality audit for APQP chains.

The audit layer is intentionally softer than validation. Validation answers
"is the chain structurally usable?"; audit answers "where should an engineer
look before trusting the content?".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .domain import APQPChain, ControlItem, FailureMode
from .quality_matching import overlap_score, quality_tokens


@dataclass(frozen=True)
class AuditItem:
    item_id: str
    category: str
    message: str
    severity: str = "review"


@dataclass(frozen=True)
class AuditReport:
    counts: dict[str, int]
    mechanical_links: list[dict[str, str]] = field(default_factory=list)
    weak_links: list[dict[str, str]] = field(default_factory=list)
    manual_review_items: list[AuditItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    step_density: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return True

    @property
    def valid(self) -> bool:
        return True

    def __bool__(self) -> bool:
        return True

    def model_dump(self) -> dict[str, Any]:
        return {
            "counts": self.counts,
            "mechanical_links": self.mechanical_links,
            "weak_links": self.weak_links,
            "manual_review_items": [item.__dict__ for item in self.manual_review_items],
            "warnings": self.warnings,
            "step_density": self.step_density,
        }

    def to_text(self) -> str:
        lines = [
            "MINOS-CORE 质量审计",
            f"- 工序数: {self.counts.get('process_steps', 0)}",
            f"- PFMEA 数: {self.counts.get('failure_modes', 0)}",
            f"- 控制计划数: {self.counts.get('controls', 0)}",
            f"- 机械链接: {len(self.mechanical_links)}",
            f"- 弱链接: {len(self.weak_links)}",
            f"- 人工复核项: {len(self.manual_review_items)}",
        ]
        if self.warnings:
            lines.append("警告:")
            lines.extend(f"  - {item}" for item in self.warnings)
        if self.manual_review_items:
            lines.append("人工复核清单:")
            for item in self.manual_review_items[:20]:
                lines.append(f"  - [{item.category}] {item.item_id}: {item.message}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


def audit_chain(chain: APQPChain | dict[str, Any]) -> AuditReport:
    if isinstance(chain, dict):
        chain = APQPChain(**chain)

    controls_by_id = {item.control_plan_id: item for item in chain.controls}
    controls_by_pfmea = {
        item.pfmea_id: item for item in chain.controls if item.pfmea_id
    }
    manual_review_items: list[AuditItem] = []
    mechanical_links: list[dict[str, str]] = []
    weak_links: list[dict[str, str]] = []
    warnings: list[str] = []

    for failure in chain.failure_modes:
        _audit_failure_fields(failure, manual_review_items)
        control = controls_by_pfmea.get(failure.pfmea_id)
        if control is None and failure.linked_control_plan_id:
            control = controls_by_id.get(failure.linked_control_plan_id)
            if control is not None:
                mechanical_links.append(
                    {
                        "pfmea_id": failure.pfmea_id,
                        "control_plan_id": control.control_plan_id,
                        "reason": "mechanical linked_control_plan_id coverage",
                    }
                )
                manual_review_items.append(
                    AuditItem(
                        failure.pfmea_id,
                        "mechanical_link",
                        f"PFMEA 只通过 linked_control_plan_id 覆盖到 {control.control_plan_id}，控制项未反向记录 pfmea_id",
                    )
                )
        if failure.is_mandatory_control and control is not None:
            score = _overlap_score(_failure_text(failure), _control_text(control))
            if score == 0:
                weak_links.append(
                    {
                        "pfmea_id": failure.pfmea_id,
                        "control_plan_id": control.control_plan_id,
                        "reason": "weak text overlap",
                    }
                )
                manual_review_items.append(
                    AuditItem(
                        failure.pfmea_id,
                        "weak_link",
                        f"mandatory/high-risk PFMEA 与控制项 {control.control_plan_id} 文本重合度为 0",
                    )
                )

    for control in chain.controls:
        _audit_control_fields(control, manual_review_items)

    density = _step_density(chain)
    for step_id, values in density.items():
        if values["pfmea"] == 0 or values["cp"] == 0:
            warnings.append(
                f"工序 {step_id} 覆盖密度偏低：PFMEA={values['pfmea']}，CP={values['cp']}"
            )

    counts = {
        "process_steps": len(chain.process_steps),
        "failure_modes": len(chain.failure_modes),
        "controls": len(chain.controls),
        "mandatory_failures": sum(
            1 for item in chain.failure_modes if item.is_mandatory_control
        ),
        "mechanical_links": len(mechanical_links),
        "weak_links": len(weak_links),
        "manual_review_items": len(manual_review_items),
    }
    return AuditReport(
        counts=counts,
        mechanical_links=mechanical_links,
        weak_links=weak_links,
        manual_review_items=manual_review_items,
        warnings=warnings,
        step_density=density,
    )


def audit_apqp_chain(chain: APQPChain | dict[str, Any]) -> AuditReport:
    return audit_chain(chain)


def run_quality_audit(chain: APQPChain | dict[str, Any]) -> AuditReport:
    return audit_chain(chain)


def audit_report_json(report: AuditReport) -> str:
    return json.dumps(report.model_dump(), ensure_ascii=False, indent=2)


def _audit_failure_fields(failure: FailureMode, items: list[AuditItem]) -> None:
    required_text = {
        "failure_mode": failure.failure_mode,
        "failure_effect": failure.failure_effect,
        "failure_cause": failure.failure_cause,
    }
    for field_name, value in required_text.items():
        if not value.strip():
            items.append(
                AuditItem(
                    failure.pfmea_id, "pfmea_incomplete", f"PFMEA 缺少 {field_name}"
                )
            )
    for field_name, value in {
        "severity": failure.severity,
        "occurrence": failure.occurrence,
        "detection": failure.detection,
    }.items():
        if int(value or 0) <= 0:
            items.append(
                AuditItem(
                    failure.pfmea_id, "pfmea_incomplete", f"PFMEA 缺少 {field_name}"
                )
            )


def _audit_control_fields(control: ControlItem, items: list[AuditItem]) -> None:
    required = {
        "specification": control.specification,
        "measurement_method": control.measurement_method,
        "control_method": control.control_method,
        "reaction_plan": control.reaction_plan,
    }
    for field_name, value in required.items():
        if not value.strip():
            items.append(
                AuditItem(
                    control.control_plan_id,
                    "cp_incomplete",
                    f"控制计划缺少 {field_name}",
                )
            )


def _step_density(chain: APQPChain) -> dict[str, dict[str, int]]:
    result = {
        step.process_step_id: {"pfd": 1, "pfmea": 0, "cp": 0}
        for step in chain.process_steps
    }
    for failure in chain.failure_modes:
        result.setdefault(failure.process_step_id, {"pfd": 0, "pfmea": 0, "cp": 0})
        result[failure.process_step_id]["pfmea"] += 1
    for control in chain.controls:
        result.setdefault(control.process_step_id, {"pfd": 0, "pfmea": 0, "cp": 0})
        result[control.process_step_id]["cp"] += 1
    return result


def _failure_text(failure: FailureMode) -> set[str]:
    return _tokens(
        failure.classification,
        failure.process_function,
        failure.failure_mode,
        failure.failure_effect,
        failure.failure_cause,
    )


def _control_text(control: ControlItem) -> set[str]:
    return _tokens(
        control.classification,
        control.product_process_characteristic,
        control.specification,
        control.measurement_method,
        control.control_method,
        control.reaction_plan,
    )


def _tokens(*values: str) -> set[str]:
    return quality_tokens(*values)


def _overlap_score(left: set[str], right: set[str]) -> int:
    return overlap_score(left, right)
