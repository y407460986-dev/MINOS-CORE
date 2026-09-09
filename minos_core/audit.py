"""Quality audit for APQP chains.

The audit layer is intentionally softer than validation. Validation answers
"is the chain structurally usable?"; audit answers "where should an engineer
look before trusting the content?".
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
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
        """Audit report is always ok -- structural validity is handled separately."""
        return True

    @property
    def valid(self) -> bool:
        """Audit report is always valid -- structural validity is handled separately."""
        return True

    def __bool__(self) -> bool:
        """Always True -- the audit report itself is not a fail/pass gate."""
        return True

    def model_dump(self) -> dict[str, Any]:
        """Dump the audit report to a plain dict for serialization.

        Returns:
            A dict with counts, mechanical_links, weak_links,
            manual_review_items, warnings, and step_density.
        """
        return {
            "counts": self.counts,
            "mechanical_links": self.mechanical_links,
            "weak_links": self.weak_links,
            "manual_review_items": [item.__dict__ for item in self.manual_review_items],
            "warnings": self.warnings,
            "step_density": self.step_density,
        }

    def to_text(self) -> str:
        """Format the audit report as a human-readable text summary.

        Returns:
            A multi-line string with counts, warnings, and the
            manual-review checklist (first 20 items).
        """
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
        """Delegate to to_text() for a human-readable summary."""
        return self.to_text()


def audit_chain(chain: APQPChain | dict[str, Any]) -> AuditReport:
    """Audit an APQP chain for quality gaps that need engineer attention.

    Checks include: duplicate control IDs, missing PFMEA fields, missing control
    fields, weak text overlap between mandatory PFMEAs and their controls, and
    step-level coverage density.

    Args:
        chain: The APQP chain (or a dict that can be deserialized into one).

    Returns:
        An AuditReport with counts, warnings, weak/mechanical links, and a
        manual-review checklist.
    """
    if isinstance(chain, dict):
        chain = APQPChain(**chain)

    manual_review_items: list[AuditItem] = []
    _audit_duplicate_control_ids(chain.controls, manual_review_items)
    controls_by_id = _first_controls_by_id(chain.controls)
    controls_by_pfmea = _first_active_controls_by_pfmea(chain.controls)
    _audit_pfmea_control_coverage(
        chain, controls_by_pfmea, controls_by_id, manual_review_items
    )
    mechanical_links: list[dict[str, str]] = []
    weak_links: list[dict[str, str]] = []
    warnings: list[str] = []

    for failure in chain.failure_modes:
        if failure.deleted:
            continue
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
                        (
                            f"PFMEA 只通过 linked_control_plan_id 覆盖到 {control.control_plan_id}，"
                            "控制项未反向记录 pfmea_id"
                        ),
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
        if control.deleted:
            continue
        _audit_control_fields(control, manual_review_items)

    _audit_red_rust_240h_control_coverage(chain, manual_review_items)

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
    """Alias for audit_chain. Provided for API compatibility."""
    return audit_chain(chain)


def run_quality_audit(chain: APQPChain | dict[str, Any]) -> AuditReport:
    """Alias for audit_chain. Provided for API compatibility."""
    return audit_chain(chain)


def audit_report_json(report: AuditReport) -> str:
    """Serialize an AuditReport to a JSON string.

    Args:
        report: The audit report to serialize.

    Returns:
        A pretty-printed JSON string (UTF-8, non-ASCII preserved).
    """
    return json.dumps(report.model_dump(), ensure_ascii=False, indent=2)


def _audit_failure_fields(failure: FailureMode, items: list[AuditItem]) -> None:
    """Check PFMEA failure for missing required text and rating fields."""
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
    for rating_name, rating in {
        "severity": failure.severity,
        "occurrence": failure.occurrence,
        "detection": failure.detection,
    }.items():
        if int(rating or 0) <= 0:
            items.append(
                AuditItem(
                    failure.pfmea_id, "pfmea_incomplete", f"PFMEA 缺少 {rating_name}"
                )
            )


def _audit_control_fields(control: ControlItem, items: list[AuditItem]) -> None:
    """Check control plan items for missing fields and generic control text."""
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
    if not control.product_process_characteristic.strip():
        items.append(
            AuditItem(
                control.control_plan_id,
                "missing_cp_characteristic",
                f"控制计划 {control.control_plan_id} 缺少 product_process_characteristic"
                f"（pfmea_id={control.pfmea_id or '未填写'}）",
                "blocker",
            )
        )
    generic_fields = [
        field_name
        for field_name, value in {
            **required,
            "parameter_specification": control.parameter_specification,
            "process_control_method": control.process_control_method,
        }.items()
        if _is_generic_control_text(value)
    ]
    if generic_fields:
        items.append(
            AuditItem(
                control.control_plan_id,
                "generic_control_text",
                f"控制计划 {control.control_plan_id}（pfmea_id={control.pfmea_id or '未填写'}）"
                f" 的 {', '.join(generic_fields)} 只有泛化文本，不能支撑正式输出",
                "blocker",
            )
        )


def _audit_duplicate_control_ids(
    controls: list[ControlItem], items: list[AuditItem]
) -> None:
    """Find control plan IDs that appear more than once across the chain."""
    counts = _control_plan_id_counts(controls)
    pfmea_ids_by_cp: dict[str, set[str]] = defaultdict(set)
    for control in controls:
        if control.deleted:
            continue
        control_plan_id = control.control_plan_id.strip()
        if control_plan_id:
            pfmea_ids_by_cp[control_plan_id].add(control.pfmea_id.strip() or "未填写")

    for control_plan_id, count in counts.items():
        if count <= 1:
            continue
        pfmea_ids = ", ".join(sorted(pfmea_ids_by_cp[control_plan_id]))
        items.append(
            AuditItem(
                control_plan_id,
                "duplicate_control_plan_id",
                f"控制计划 ID {control_plan_id} 重复 {count} 次，关联 PFMEA: {pfmea_ids}",
                "blocker",
            )
        )


def _audit_pfmea_control_coverage(
    chain: APQPChain,
    controls_by_pfmea: dict[str, ControlItem],
    controls_by_id: dict[str, ControlItem],
    items: list[AuditItem],
) -> None:
    """Flag PFMEA entries that have no matching, non-deleted control plan."""
    for failure in chain.failure_modes:
        if failure.deleted:
            continue
        if failure.pfmea_id in controls_by_pfmea:
            continue
        if (
            failure.linked_control_plan_id
            and failure.linked_control_plan_id in controls_by_id
        ):
            continue
        items.append(
            AuditItem(
                failure.pfmea_id,
                "uncovered_pfmea",
                f"PFMEA {failure.pfmea_id} 没有任何未删除控制计划通过 pfmea_id 覆盖",
                "blocker",
            )
        )


def _audit_red_rust_240h_control_coverage(
    chain: APQPChain, items: list[AuditItem]
) -> None:
    """Warn if evidence mentions red-rust 240h salt spray but no control covers it."""
    if not _chain_requires_red_rust_240h(chain):
        return
    if any(_control_covers_red_rust_240h(control) for control in chain.controls):
        return
    items.append(
        AuditItem(
            "TECHREQ-SALT-SPRAY-RED-RUST-MISSING",
            "technical_requirement_control_gap",
            "TECHREQ-SALT-SPRAY-RED-RUST-MISSING: 技术证据包含红锈 240h 盐雾要求，但未删除控制计划未覆盖红锈 + 240h。",
            "blocker",
        )
    )


def _chain_requires_red_rust_240h(chain: APQPChain) -> bool:
    """Check whether any evidence segment mentions red rust 240h."""
    return any(_mentions_red_rust_240h(evidence.content) for evidence in chain.evidence)


def _control_covers_red_rust_240h(control: ControlItem) -> bool:
    """Check whether a control plan item mentions red rust 240h in any of its fields."""
    if control.deleted:
        return False
    return _mentions_red_rust_240h(
        control.product_process_characteristic,
        control.specification,
        control.measurement_method,
        control.control_method,
        control.process_parameter,
        control.parameter_specification,
        control.process_control_method,
        control.reaction_plan,
    )


def _mentions_red_rust_240h(*values: str) -> bool:
    """Check if any of the given strings mention both 'red rust' and '240h'."""
    return any(
        "红锈" in segment and re.search(r"240\s*(?:h|H|小时)", segment) is not None
        for value in values
        for segment in re.split(r"[；;。.\n\r，,、/／()（）]", value or "")
    )


def _control_plan_id_counts(controls: list[ControlItem]) -> Counter[str]:
    """Count occurrences of each non-deleted control plan ID."""
    counts: Counter[str] = Counter()
    for control in controls:
        if control.deleted:
            continue
        control_plan_id = control.control_plan_id.strip()
        if control_plan_id:
            counts[control_plan_id] += 1
    return counts


def _first_controls_by_id(controls: list[ControlItem]) -> dict[str, ControlItem]:
    """Return the first non-deleted control for each control plan ID."""
    result: dict[str, ControlItem] = {}
    for control in controls:
        control_plan_id = control.control_plan_id.strip()
        if control.deleted:
            continue
        if control_plan_id and control_plan_id not in result:
            result[control_plan_id] = control
    return result


def _first_active_controls_by_pfmea(
    controls: list[ControlItem],
) -> dict[str, ControlItem]:
    """Return the first non-deleted control for each PFMEA ID."""
    result: dict[str, ControlItem] = {}
    for control in controls:
        pfmea_id = control.pfmea_id.strip()
        if control.deleted or not pfmea_id or pfmea_id in result:
            continue
        result[pfmea_id] = control
    return result


_GENERIC_CONTROL_PHRASES = {
    "按图纸",
    "按规范",
    "按批准规范",
    "按作业指导书",
    "根据作业指导书",
    "按工艺卡",
}

_GENERIC_CONTROL_SUFFIXES = {
    "",
    "执行",
    "要求",
    "控制",
    "确认",
    "判定",
    "进行控制",
    "进行过程控制",
}


def _is_generic_control_text(value: str) -> bool:
    """Check if a control text field contains only generic boilerplate phrases."""
    candidate = value.strip()
    if not candidate:
        return False
    if not any(phrase in candidate for phrase in _GENERIC_CONTROL_PHRASES):
        return False

    normalized = re.sub(r"[\s:：，,。.;；、/／()（）]+", "", candidate)
    for phrase in _GENERIC_CONTROL_PHRASES:
        phrase_normalized = re.sub(r"\s+", "", phrase)
        for suffix in _GENERIC_CONTROL_SUFFIXES:
            if normalized == f"{phrase_normalized}{suffix}":
                return True

    if _has_concrete_control_detail(candidate):
        return False
    return len(normalized) <= 24


def _has_concrete_control_detail(value: str) -> bool:
    """Check if a control text field contains specific numbers, standards, or keywords."""
    return bool(
        re.search(r"\d", value)
        or re.search(r"\b(?:GB|ISO|SAE|JIS|DIN|ASTM|JLV|WI|CMM|SPC)\b", value, re.IGNORECASE)
        or any(
            keyword in value
            for keyword in (
                "公差",
                "尺寸",
                "孔径",
                "孔距",
                "位置度",
                "同轴度",
                "毛刺",
                "裂纹",
                "凹坑",
                "凸起",
                "膜厚",
                "盐雾",
                "白锈",
                "红锈",
                "照度",
                "校准",
                "量具",
                "检具",
                "首件",
                "巡检",
                "抽检",
                "点检",
                "防错",
                "参数",
                "工装",
                "夹具",
                "批次",
                "隔离",
                "复检",
                "记录",
                "限度样件",
            )
        )
    )


def _step_density(chain: APQPChain) -> dict[str, dict[str, int]]:
    """Count PFMEA and control plan entries per process step."""
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
    """Extract quality tokens from a PFMEA failure for overlap scoring."""
    return _tokens(
        failure.classification,
        failure.process_function,
        failure.failure_mode,
        failure.failure_effect,
        failure.failure_cause,
    )


def _control_text(control: ControlItem) -> set[str]:
    """Extract quality tokens from a control plan item for overlap scoring."""
    return _tokens(
        control.classification,
        control.product_process_characteristic,
        control.specification,
        control.measurement_method,
        control.control_method,
        control.reaction_plan,
    )


def _tokens(*values: str) -> set[str]:
    """Tokenize strings for overlap comparison via quality_matching."""
    return quality_tokens(*values)


def _overlap_score(left: set[str], right: set[str]) -> int:
    """Compute overlap score between two token sets via quality_matching."""
    return overlap_score(left, right)
