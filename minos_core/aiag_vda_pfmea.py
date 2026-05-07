"""AIAG-VDA PFMEA helpers for AP scoring and row normalization."""

from __future__ import annotations

from typing import Any

from minos_core._text_utils import text


ACTION_STATUS_OPEN = {"未制定", "待执行", "执行中", "已逾期"}
ACTION_STATUS_DONE = {"已完成", "已验证", "已关闭"}


def bounded_rating(value: Any, default: int = 1) -> int:
    try:
        rating = int(value or default)
    except (TypeError, ValueError):
        rating = default
    return max(1, min(rating, 10))


def calculate_ap(severity: Any, occurrence: Any, detection: Any) -> str:
    """Return an AIAG-VDA style action priority bucket.

    This uses a conservative deterministic approximation suitable for MINOS
    draft gating. Customer-specific AP tables can replace it behind this API.
    """

    s = bounded_rating(severity)
    o = bounded_rating(occurrence)
    d = bounded_rating(detection)
    if s >= 9:
        return "H" if o >= 2 or d >= 5 else "M"
    if s >= 8 and (o >= 5 or d >= 7):
        return "H"
    if s >= 7 and o >= 5 and d >= 5:
        return "H"
    if s >= 7 or o >= 6 or d >= 8:
        return "M"
    return "L"


def calculate_rpn(severity: Any, occurrence: Any, detection: Any) -> int:
    return bounded_rating(severity) * bounded_rating(occurrence) * bounded_rating(detection)


def normalize_pfmea_row(row: dict[str, Any], process_step: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a PFMEA row with AIAG-VDA draft fields populated."""

    process_step = process_step or {}
    normalized = dict(row)
    process_step_id = text(normalized.get("process_step_id"), process_step.get("process_step_id"))
    operation = text(normalized.get("operation"), normalized.get("process_step_name"), process_step.get("operation"))
    process_function = text(
        normalized.get("process_function"),
        process_step.get("process_function"),
        process_step.get("process_purpose"),
        operation,
    )
    severity = bounded_rating(normalized.get("severity", normalized.get("S")), default=5)
    occurrence = bounded_rating(normalized.get("occurrence", normalized.get("O")), default=3)
    detection = bounded_rating(normalized.get("detection", normalized.get("D")), default=6)
    ap = text(normalized.get("action_priority"), normalized.get("AP"), calculate_ap(severity, occurrence, detection)).upper()

    normalized.update(
        {
            "process_item": text(normalized.get("process_item"), "制造过程"),
            "process_step": text(normalized.get("process_step"), operation, process_step_id),
            "process_work_element": text(
                normalized.get("process_work_element"),
                process_step.get("equipment"),
                process_step.get("tooling"),
                "人员/设备/工装/方法",
            ),
            "function_requirement": text(normalized.get("function_requirement"), process_function),
            "S": severity,
            "severity": severity,
            "O": occurrence,
            "occurrence": occurrence,
            "D": detection,
            "detection": detection,
            "AP": ap,
            "action_priority": ap,
            "rpn": calculate_rpn(severity, occurrence, detection),
            "action_status": text(normalized.get("action_status"), normalized.get("status"), "未制定"),
            "responsibility": text(normalized.get("responsibility"), normalized.get("owner")),
            "target_date": text(normalized.get("target_date"), normalized.get("completion_due_date")),
            "actual_completion_date": text(normalized.get("actual_completion_date"), normalized.get("completion_date")),
            "remarks": text(normalized.get("remarks"), normalized.get("note")),
        }
    )
    after_s = normalized.get("after_severity", normalized.get("severity_after"))
    after_o = normalized.get("after_occurrence", normalized.get("occurrence_after"))
    after_d = normalized.get("after_detection", normalized.get("detection_after"))
    if after_s not in {None, ""}:
        normalized["after_severity"] = bounded_rating(after_s, default=severity)
    if after_o not in {None, ""}:
        normalized["after_occurrence"] = bounded_rating(after_o, default=occurrence)
    if after_d not in {None, ""}:
        normalized["after_detection"] = bounded_rating(after_d, default=detection)
    if all(normalized.get(field) not in {None, ""} for field in ("after_severity", "after_occurrence", "after_detection")):
        normalized["after_ap"] = text(
            normalized.get("after_ap"),
            calculate_ap(
                normalized["after_severity"],
                normalized["after_occurrence"],
                normalized["after_detection"],
            ),
        ).upper()
        normalized["after_rpn"] = calculate_rpn(
            normalized["after_severity"],
            normalized["after_occurrence"],
            normalized["after_detection"],
        )
    return normalized
