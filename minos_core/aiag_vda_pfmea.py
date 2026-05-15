"""AIAG-VDA PFMEA helpers for AP scoring and row normalization."""

from __future__ import annotations

from typing import Any

from minos_core._text_utils import string_list, text


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
    """Legacy compatibility helper; AIAG-VDA 2019 PFMEA output uses AP."""

    return bounded_rating(severity) * bounded_rating(occurrence) * bounded_rating(detection)


def normalize_pfmea_row(row: dict[str, Any], process_step: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a PFMEA row with AIAG-VDA 2019 Form C fields populated."""

    process_step = process_step or {}
    normalized = dict(row)
    process_step_id = text(normalized.get("process_step_id"), process_step.get("process_step_id"))
    operation = text(
        normalized.get("operation"),
        normalized.get("process_step_name"),
        normalized.get("structure_process_step"),
        normalized.get("process_step"),
        process_step.get("operation"),
        process_step_id,
    )
    process_item = text(
        normalized.get("process_item"),
        normalized.get("structure_process_item"),
        normalized.get("function_process_item"),
        "制造过程",
    )
    process_work_element = text(
        normalized.get("process_work_element"),
        normalized.get("structure_work_element"),
        normalized.get("work_element"),
        normalized.get("equipment"),
        process_step.get("equipment"),
        process_step.get("tooling"),
        normalized.get("work_element_4m"),
        "人员/设备/工装/方法",
    )
    process_function = text(
        normalized.get("function_process_step"),
        normalized.get("function_requirement"),
        normalized.get("process_function"),
        process_step.get("process_function"),
        process_step.get("process_purpose"),
        operation,
    )
    work_element_function = text(
        normalized.get("function_work_element"),
        normalized.get("process_characteristic"),
        normalized.get("process_characteristics"),
        process_step.get("process_characteristic"),
        process_step.get("process_characteristics"),
        process_work_element,
    )
    severity = bounded_rating(normalized.get("severity", normalized.get("S")), default=5)
    occurrence = bounded_rating(normalized.get("occurrence", normalized.get("O")), default=3)
    detection = bounded_rating(normalized.get("detection", normalized.get("D")), default=6)
    ap = text(normalized.get("action_priority"), normalized.get("AP"), calculate_ap(severity, occurrence, detection)).upper()
    preventive_action = text(
        normalized.get("preventive_action"),
        normalized.get("recommended_preventive_action"),
        normalized.get("recommended_action"),
    )
    detection_action = text(
        normalized.get("detection_action"),
        normalized.get("recommended_detection_action"),
    )
    optimization_action = text(
        normalized.get("optimization_action"),
        "；".join(item for item in (preventive_action, detection_action) if item),
        normalized.get("recommended_action"),
    )
    responsible_person = text(
        normalized.get("responsible_person"),
        normalized.get("responsibility"),
        normalized.get("owner"),
    )
    status = text(normalized.get("status"), normalized.get("action_status"), "未开始")
    failure_cause = text(normalized.get("failure_cause"), normalized.get("cause"))
    failure_mode = text(normalized.get("failure_mode"), normalized.get("mode"), normalized.get("failure"))
    prevention_control = text(normalized.get("prevention_control"), normalized.get("current_prevention_control"))
    detection_control = text(normalized.get("detection_control"), normalized.get("current_detection_control"))
    cause_process_parameter = text(
        normalized.get("cause_process_parameter"),
        _joined_text(normalized.get("process_characteristic"), normalized.get("process_characteristics")),
        _joined_text(process_step.get("process_characteristic"), process_step.get("process_characteristics")),
        work_element_function,
    )
    prevention_control_target = text(
        normalized.get("prevention_control_target"),
        _prevention_target(failure_cause, cause_process_parameter),
    )
    prevention_control_timing = text(
        normalized.get("prevention_control_timing"),
        _control_timing(prevention_control, fallback="量产前、换型后和每班点检"),
    )
    detection_control_target = text(
        normalized.get("detection_control_target"),
        _joined_text(
            normalized.get("product_characteristic"),
            normalized.get("product_characteristics"),
            process_step.get("product_characteristic"),
            process_step.get("product_characteristics"),
        ),
        failure_mode,
    )
    detection_control_timing = text(
        normalized.get("detection_control_timing"),
        _control_timing(detection_control, fallback="首件和巡检"),
    )
    prevention_weak = _prevention_is_inspection_only(prevention_control)
    control_logic_review = text(
        normalized.get("control_logic_review"),
        _control_logic_review(
            failure_cause=failure_cause,
            prevention_control=prevention_control,
            detection_control=detection_control,
            prevention_weak=prevention_weak,
        ),
    )

    normalized.update(
        {
            "process_item": process_item,
            "process_step": operation,
            "process_step_name": operation,
            "process_work_element": process_work_element,
            "structure_process_item": process_item,
            "structure_process_step": operation,
            "structure_work_element": process_work_element,
            "function_process_item": text(normalized.get("function_process_item"), process_item),
            "function_process_step": process_function,
            "function_work_element": work_element_function,
            "function_requirement": process_function,
            "S": severity,
            "severity": severity,
            "O": occurrence,
            "occurrence": occurrence,
            "D": detection,
            "detection": detection,
            "AP": ap,
            "action_priority": ap,
            "preventive_action": preventive_action,
            "detection_action": detection_action,
            "optimization_action": optimization_action,
            "recommended_action": text(normalized.get("recommended_action"), optimization_action),
            "status": status,
            "action_status": text(normalized.get("action_status"), status),
            "responsible_person": responsible_person,
            "responsibility": text(normalized.get("responsibility"), responsible_person),
            "target_date": text(normalized.get("target_date"), normalized.get("completion_due_date")),
            "actual_completion_date": text(normalized.get("actual_completion_date"), normalized.get("completion_date")),
            "remarks": text(normalized.get("remarks"), normalized.get("note")),
            "cause_process_parameter": cause_process_parameter,
            "prevention_control_target": prevention_control_target,
            "prevention_control_timing": prevention_control_timing,
            "detection_control_target": detection_control_target,
            "detection_control_timing": detection_control_timing,
            "control_logic_review": control_logic_review,
            "needs_confirmation": bool(
                normalized.get("needs_confirmation", normalized.get("ai_inferred", False))
                or (ap == "H" and prevention_weak)
            ),
        }
    )
    normalized.pop("rpn", None)
    normalized.pop("RPN", None)
    normalized.pop("after_rpn", None)
    normalized.pop("after_RPN", None)
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
    return normalized


def _joined_text(*values: Any) -> str:
    for value in values:
        items = string_list(value)
        if items:
            return "、".join(items)
        value_text = text(value)
        if value_text:
            return value_text
    return ""


def _prevention_target(failure_cause: str, cause_process_parameter: str) -> str:
    if failure_cause and cause_process_parameter:
        return f"控制失效原因：{failure_cause}；关键过程参数：{cause_process_parameter}"
    if failure_cause:
        return f"控制失效原因：{failure_cause}"
    if cause_process_parameter:
        return f"控制关键过程参数：{cause_process_parameter}"
    return "控制失效原因和关键过程参数"


def _control_timing(control_text: str, *, fallback: str) -> str:
    value = control_text or ""
    if any(keyword in value for keyword in ("首件", "换型", "换模", "换批")):
        return "首件/换型/换批时"
    if any(keyword in value for keyword in ("生产前", "开机前", "放行前", "开发前期", "量产前")):
        return "生产前/放行前"
    if any(keyword in value for keyword in ("每班", "定期", "巡检", "按频次", "每批", "每小时")):
        return "每班/按规定频次"
    if any(keyword in value for keyword in ("100%", "全检")):
        return "生产中全检"
    return fallback


def _prevention_is_inspection_only(prevention_control: str) -> bool:
    value = prevention_control.strip()
    if not value:
        return True
    prevention_keywords = (
        "锁定",
        "防错",
        "参数",
        "点检",
        "保养",
        "维护",
        "培训",
        "校准",
        "控制",
        "限位",
        "权限",
        "标准",
        "作业指导",
    )
    if any(keyword in value for keyword in prevention_keywords):
        return False
    return any(keyword in value for keyword in ("检验", "检查", "测量", "确认", "复核"))


def _control_logic_review(
    *,
    failure_cause: str,
    prevention_control: str,
    detection_control: str,
    prevention_weak: bool,
) -> str:
    if not prevention_control and not detection_control:
        return "预防控制和探测控制均缺失，需人工补充控制逻辑。"
    if prevention_weak:
        return "预防控制偏向检查结果，需复核是否真正控制失效原因；探测控制需独立覆盖失效模式。"
    if failure_cause and prevention_control and detection_control:
        return "预防控制已指向失效原因，探测控制独立覆盖失效模式。"
    return "预防控制、探测控制已分列，需人工确认与失效原因的匹配性。"
