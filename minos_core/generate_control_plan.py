"""Generate control plans from PFMEA bundles."""

from __future__ import annotations

from typing import Any

from minos_core._text_utils import row_text, string_list, integer, dedupe


LOW_CONFIDENCE_THRESHOLD = 0.75


def generate_control_plan_from_pfmea(
    pfmea_bundle: dict[str, Any],
) -> dict[str, Any]:
    """Generate a thin, rules-based control plan from PFMEA rows.

    The generator is intentionally deterministic: it copies direct PFMEA fields
    when present and uses small risk-based defaults for sampling and reaction
    planning when the PFMEA does not already provide control-plan fields.
    """

    rows = _pfmea_rows(pfmea_bundle)
    control_rows = [
        _control_row(row, index)
        for index, row in enumerate(rows, start=1)
        if isinstance(row, dict)
    ]
    ai_inferred_items = dedupe(
        list(pfmea_bundle.get("ai_inferred_items", []))
        + [
            row["control_plan_id"]
            for row in control_rows
            if row.get("ai_inferred") and row.get("control_plan_id")
        ]
    )
    return {
        "document_type": "control_plan",
        "schema_version": "minos-core.generated.v1",
        "source_document_type": pfmea_bundle.get("document_type", "pfmea"),
        "product": pfmea_bundle.get("product", {}),
        "evidence": pfmea_bundle.get("evidence", []),
        "process_steps": pfmea_bundle.get("process_steps", []),
        "pfmea_rows": rows,
        "rows": control_rows,
        "pending_fields": pfmea_bundle.get("pending_fields", []),
        "ai_inferred_items": ai_inferred_items,
        "metadata": {
            "generation_mode": "pfmea_control_plan_rules",
            "llm_used": False,
            "source_stage": "generate_pfmea",
        },
    }


def _pfmea_rows(pfmea_bundle: dict[str, Any]) -> list[Any]:
    if isinstance(pfmea_bundle.get("rows"), list):
        return pfmea_bundle["rows"]
    if isinstance(pfmea_bundle.get("failure_modes"), list):
        return pfmea_bundle["failure_modes"]
    if isinstance(pfmea_bundle.get("pfmea_items"), list):
        return pfmea_bundle["pfmea_items"]
    pfmea = pfmea_bundle.get("pfmea")
    if isinstance(pfmea, dict):
        return _pfmea_rows(pfmea)
    return []


def _control_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    pfmea_id = row_text(row, "pfmea_id", "id", default=f"PFMEA-{index:03d}")
    process_step_id = row_text(row, "process_step_id", "step_no", "step", default="")
    classification = row_text(
        row,
        "special_characteristic_class",
        "classification",
        "special_characteristic",
        "special_characteristic_classification",
        default="",
    )
    risk_level = _risk_level(row, classification)
    direct_specification = row_text(
        row,
        "specification_tolerance",
        "specification",
        "product_process_requirement",
        "process_requirement",
        "requirement",
        default="",
    )
    direct_measurement = row_text(
        row,
        "measurement_method",
        "measurement",
        "detection_control",
        "detection_method",
        default="",
    )
    direct_sample_size = row_text(row, "sample_size", default="")
    direct_sample_frequency = row_text(row, "sample_frequency", default="")
    direct_control_method = row_text(row, "control_method", default="")
    direct_reaction_plan = row_text(row, "reaction_plan", default="")
    direct_process_parameter = row_text(
        row,
        "process_parameter",
        "cause_process_parameter",
        "process_characteristic",
        "process_characteristics",
        "function_work_element",
        default="",
    )
    direct_parameter_specification = row_text(
        row,
        "parameter_specification",
        "process_parameter_specification",
        "parameter_tolerance",
        default="",
    )
    direct_process_control_method = row_text(
        row,
        "process_control_method",
        "parameter_control_method",
        default="",
    )
    direct_setup_verification = row_text(row, "setup_verification", default="")
    direct_poka_yoke_device = row_text(row, "poka_yoke_device", default="")
    direct_poka_yoke_verification = row_text(row, "poka_yoke_verification", default="")
    direct_process_record = row_text(row, "process_record", "record_form", default="")

    specification = direct_specification or _derived_specification(row)
    measurement_method = direct_measurement or _default_measurement_method(row)
    sample_size = direct_sample_size or _default_sample_size(risk_level)
    sample_frequency = direct_sample_frequency or _default_sample_frequency(risk_level)
    control_method = direct_control_method or _control_method(row)
    reaction_plan = direct_reaction_plan or _reaction_plan(risk_level)
    process_parameter = direct_process_parameter or _process_parameter(row)
    parameter_specification = direct_parameter_specification or _parameter_specification(row)
    process_control_method = direct_process_control_method or _process_control_method(row)
    setup_verification = direct_setup_verification or _setup_verification(row)
    poka_yoke_device = direct_poka_yoke_device or _poka_yoke_device(row)
    poka_yoke_verification = direct_poka_yoke_verification or _poka_yoke_verification(row)
    process_record = direct_process_record or _process_record(row)
    inferred_fields = _inferred_control_fields(
        {
            "specification": direct_specification,
            "measurement_method": direct_measurement,
            "sample_size": direct_sample_size,
            "sample_frequency": direct_sample_frequency,
            "control_method": direct_control_method,
            "reaction_plan": direct_reaction_plan,
            "process_parameter": direct_process_parameter,
            "parameter_specification": direct_parameter_specification,
            "process_control_method": direct_process_control_method,
            "setup_verification": direct_setup_verification,
            "poka_yoke_device": direct_poka_yoke_device,
            "poka_yoke_verification": direct_poka_yoke_verification,
            "process_record": direct_process_record,
        }
    )
    ai_inferred = bool(
        row.get("ai_inferred", row.get("created_by_ai", False)) or inferred_fields
    )
    confidence = _confidence(row)
    evidence_refs = string_list(row.get("evidence_refs", []))
    needs_confirmation = _needs_confirmation(
        row,
        risk_level=risk_level,
        classification=classification,
        confidence=confidence,
        evidence_refs=evidence_refs,
    )
    control_plan_id = _control_plan_id(row, pfmea_id, process_step_id, index)

    return {
        "control_plan_id": control_plan_id,
        "process_step_id": process_step_id,
        "pfmea_id": pfmea_id,
        "source_pfmea_id": pfmea_id,
        "process_name": row_text(row, "process_name", "process_step_name", "operation", default=""),
        "product_process_characteristic": _characteristic(row),
        "product_characteristic": row_text(row, "product_characteristic", default=""),
        "process_characteristic": row_text(row, "process_characteristic", default=""),
        "specification": specification,
        "specification_tolerance": row_text(
            row, "specification_tolerance", "specification", default=specification
        ),
        "classification": classification,
        "special_characteristic_class": row_text(
            row, "special_characteristic_class", "classification", default=classification
        ),
        "measurement_method": measurement_method,
        "sample_size": sample_size,
        "sample_frequency": sample_frequency,
        "control_method": control_method,
        "process_parameter": process_parameter,
        "parameter_specification": parameter_specification,
        "process_control_method": process_control_method,
        "setup_verification": setup_verification,
        "poka_yoke_device": poka_yoke_device,
        "poka_yoke_verification": poka_yoke_verification,
        "process_record": process_record,
        "reaction_plan": reaction_plan,
        "characteristic_number": row_text(row, "characteristic_number", default=""),
        "equipment": row_text(
            row, "equipment", "machine_device", "inspection_equipment", default=""
        ),
        "gauges": _source_gauges(row),
        "inspection_equipment": _inspection_equipment(row),
        "evidence_refs": evidence_refs,
        "confidence": confidence,
        "ai_inferred": ai_inferred,
        "needs_confirmation": needs_confirmation,
        "ai_reasoning": _control_reasoning(row, pfmea_id, risk_level, inferred_fields),
        "source_risk_level": risk_level,
        "source_action_priority": row_text(row, "action_priority", default=""),
        "source_severity": integer(row.get("severity", row.get("S"))),
        "source_occurrence": integer(row.get("occurrence")),
        "source_detection": integer(row.get("detection")),
        "source_failure_cause": row_text(row, "failure_cause", "cause", default=""),
        "source_prevention_control": row_text(row, "prevention_control", default=""),
        "source_detection_control": row_text(row, "detection_control", default=""),
        "source_special_characteristics": _source_special_characteristics(row, classification),
        "source_high_risk": risk_level == "high",
        "inferred_fields": inferred_fields,
    }


def _control_plan_id(
    row: dict[str, Any],
    pfmea_id: str,
    process_step_id: str,
    index: int,
) -> str:
    linked_id = row_text(row, "linked_control_plan_id", "control_plan_id", default="")
    if linked_id:
        return linked_id
    if pfmea_id:
        return f"CP-{pfmea_id}"
    if process_step_id:
        return f"CP-{process_step_id}-{index:03d}"
    return f"CP-{index:03d}"


def _characteristic(row: dict[str, Any]) -> str:
    explicit = row_text(
        row,
        "product_characteristic",
        "process_characteristic",
        "product_process_characteristic",
        "characteristic",
        "special_characteristic",
        "classification",
        default="",
    )
    if explicit:
        return explicit
    failure_mode = row_text(row, "failure_mode", "mode", "failure", default="")
    if failure_mode:
        return f"针对失效模式的控制：{failure_mode}"
    return row_text(row, "process_function", "process", "operation", default="")


def _source_special_characteristics(row: dict[str, Any], classification: str) -> list[str]:
    values: list[str] = []
    for source in (
        row.get("characteristic_refs", []),
        row.get("special_characteristics", []),
        row.get("product_characteristics", []),
        row.get("process_characteristics", []),
        classification,
    ):
        for item in string_list(source):
            if item not in values:
                values.append(item)
    return values


def _source_gauges(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for source in (
        row.get("gauges", []),
        row.get("inspection_gauges", []),
        row.get("measurement_devices", []),
        row.get("inspection_equipment", []),
    ):
        for item in string_list(source):
            if item not in values:
                values.append(item)
    return values


def _inspection_equipment(row: dict[str, Any]) -> str:
    explicit = row_text(
        row,
        "inspection_equipment",
        "gauge",
        "gages",
        "measurement_device",
        default="",
    )
    if explicit:
        return explicit
    gauges = _source_gauges(row)
    if gauges:
        return "、".join(gauges)
    return ""


def _derived_specification(row: dict[str, Any]) -> str:
    requirement = row_text(
        row,
        "drawing_specification",
        "drawing_requirement",
        "technical_requirement",
        "inspection_requirement",
        default="",
    )
    if requirement:
        return requirement
    failure_mode = row_text(row, "failure_mode", "mode", "failure", default="")
    if failure_mode:
        return f"草案控制意图：预防或探测 {failure_mode}"
    process_function = row_text(row, "process_function", "process", default="")
    if process_function:
        return f"草案控制意图：保持 {process_function}"
    return "草案控制意图：待依据受控图纸规格确认"


def _default_measurement_method(row: dict[str, Any]) -> str:
    detection_control = row_text(row, "detection_control", "current_detection_control", default="")
    if detection_control:
        return detection_control
    detection = integer(row.get("detection"))
    if detection >= 8:
        return "按 PFMEA 探测风险执行强化检验或防错验证"
    if detection >= 5:
        return "按 PFMEA 探测控制执行记录化检验"
    return "按控制计划执行常规检验"


def _control_method(row: dict[str, Any]) -> str:
    prevention_control = row_text(row, "prevention_control", default="")
    detection_control = row_text(row, "detection_control", default="")
    if prevention_control and detection_control:
        return f"预防：{prevention_control}；探测：{detection_control}"
    if prevention_control:
        return prevention_control
    if detection_control:
        return detection_control
    action_priority = row_text(row, "action_priority", default="").upper()
    if action_priority in {"H", "M"}:
        return f"针对 AP {action_priority} 的 PFMEA 风险定义控制方法"
    return "定义常规过程控制方法"


def _process_parameter(row: dict[str, Any]) -> str:
    explicit = row_text(
        row,
        "process_parameter",
        "cause_process_parameter",
        "process_characteristic",
        "process_characteristics",
        "function_work_element",
        default="",
    )
    if explicit:
        if explicit.startswith("是否"):
            explicit = explicit[2:].strip()
            if not explicit:
                explicit = ""
            else:
                return explicit
        else:
            return explicit
    cause = row_text(row, "failure_cause", "cause", default="")
    if cause:
        return f"针对失效原因的过程参数：{cause}"
    return row_text(row, "process_function", "process_step_name", "operation", default="过程参数待确认")


def _parameter_specification(row: dict[str, Any]) -> str:
    direct = row_text(
        row,
        "parameter_specification",
        "process_parameter_specification",
        "parameter_tolerance",
        default="",
    )
    if direct:
        return direct
    cause = row_text(row, "failure_cause", "cause", default="")
    parameter = _process_parameter(row)
    if cause:
        return f"控制 {cause}；{parameter} 的目标值/上下限待依据作业指导书确认"
    return f"{parameter} 的目标值/上下限待依据作业指导书确认"


def _process_control_method(row: dict[str, Any]) -> str:
    direct = row_text(row, "process_control_method", "parameter_control_method", default="")
    if direct:
        return direct
    prevention_control = row_text(row, "prevention_control", default="")
    if prevention_control:
        return prevention_control
    control = _control_method(row)
    return f"按过程参数点检执行：{control}"


def _setup_verification(row: dict[str, Any]) -> str:
    direct = row_text(row, "setup_verification", default="")
    if direct:
        return direct
    parameter = _process_parameter(row)
    return f"首件/换型后确认 {parameter} 设定、设备状态和工装状态"


def _poka_yoke_device(row: dict[str, Any]) -> str:
    direct = row_text(row, "poka_yoke_device", default="")
    if direct:
        return direct
    parameter = _process_parameter(row)
    return f"{parameter} 防错或参数权限控制"


def _poka_yoke_verification(row: dict[str, Any]) -> str:
    direct = row_text(row, "poka_yoke_verification", default="")
    if direct:
        return direct
    device = _poka_yoke_device(row)
    return f"每班/换型后验证 {device} 有效"


def _process_record(row: dict[str, Any]) -> str:
    direct = row_text(row, "process_record", "record_form", default="")
    if direct:
        return direct
    parameter = _process_parameter(row)
    return f"{parameter} 点检/首件确认记录"


def _risk_level(row: dict[str, Any], classification: str) -> str:
    action_priority = row_text(row, "action_priority", default="").upper()
    severity = integer(row.get("severity"))
    occurrence = integer(row.get("occurrence"))
    if action_priority == "H" or severity >= 9:
        return "high"
    if classification or action_priority == "M" or severity >= 7 or occurrence >= 7:
        return "medium"
    return "low"


def _default_sample_size(risk_level: str) -> str:
    if risk_level == "high":
        return "100%"
    if risk_level == "medium":
        return "5 件"
    return "1 件"


def _default_sample_frequency(risk_level: str) -> str:
    if risk_level == "high":
        return "每件或每循环检查，直到风险降低"
    if risk_level == "medium":
        return "每批和每次换型"
    return "首件和定期巡检"


def _reaction_plan(risk_level: str) -> str:
    if risk_level == "high":
        return "停机，隔离可疑产品，通知质量人员，并在重启前验证纠正措施"
    if risk_level == "medium":
        return "隔离可疑产品，并通知质量人员或过程责任人"
    return "隔离不合格品，并按不合格品流程处理"


def _needs_confirmation(
    row: dict[str, Any],
    *,
    risk_level: str,
    classification: str,
    confidence: float,
    evidence_refs: list[str],
) -> bool:
    if bool(row.get("needs_confirmation", False)):
        return True
    if risk_level == "high" or classification:
        return True
    if confidence and confidence < LOW_CONFIDENCE_THRESHOLD:
        return True
    if not evidence_refs:
        return True
    return _ai_is_uncertain(row)


def _inferred_control_fields(direct_fields: dict[str, str]) -> list[str]:
    return [field for field, value in direct_fields.items() if not value]


def _control_reasoning(
    row: dict[str, Any],
    pfmea_id: str,
    risk_level: str,
    inferred_fields: list[str],
) -> str:
    existing = row_text(row, "ai_reasoning", default="")
    source = f"控制计划行来源于 PFMEA {pfmea_id}，风险等级：{_risk_level_text(risk_level)}"
    if inferred_fields:
        fields = "、".join(_field_text(field) for field in inferred_fields)
        source = f"{source}；已补充草案控制计划字段：{fields}"
    if existing:
        return f"{existing}；{source}"
    return source


def _risk_level_text(risk_level: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(risk_level, risk_level)


def _field_text(field_name: str) -> str:
    return {
        "specification": "规格要求",
        "measurement_method": "测量方法",
        "sample_size": "样本容量",
        "sample_frequency": "检查频次",
        "control_method": "控制方法",
        "reaction_plan": "反应计划",
        "process_parameter": "过程参数",
        "parameter_specification": "参数规格",
        "process_control_method": "过程控制方法",
        "setup_verification": "首件/换型确认",
        "poka_yoke_device": "防错装置",
        "poka_yoke_verification": "防错验证",
        "process_record": "过程记录",
    }.get(field_name, field_name)


def _ai_is_uncertain(row: dict[str, Any]) -> bool:
    uncertainty_text = " ".join(
        row_text(row, key, default="")
        for key in (
            "ai_reasoning",
            "reasoning",
            "uncertainty",
            "uncertainties",
            "recommended_action",
        )
    ).lower()
    return any(
        token in uncertainty_text
        for token in (
            "uncertain",
            "not confirmed",
            "requires engineer",
            "requires engineering",
            "requires quality",
            "requires review",
            "pending",
            "待确认",
            "不确定",
            "需复核",
        )
    )


def _confidence(row: dict[str, Any]) -> float:
    try:
        return float(row.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def normalize_control_plan_rows(rows: list[dict[str, Any]]) -> None:
    """Ensure every control plan row carries the standard CP-2024 field set."""
    for row in rows:
        row.setdefault("control_plan_id", "")
        row.setdefault("process_step_id", "")
        row.setdefault("pfmea_id", "")
        row.setdefault("process_name", "")
        row.setdefault("equipment", row.get("machine_device", ""))
        row.setdefault("machine_device", row.get("equipment", ""))
        row.setdefault("characteristic_number", "")
        row.setdefault("product_characteristic", row.get("product_process_characteristic", ""))
        row.setdefault("process_characteristic", "")
        row.setdefault("product_process_characteristic", "")
        row.setdefault("special_characteristic_class", row.get("classification", ""))
        row.setdefault("classification", "")
        row.setdefault("specification_tolerance", row.get("specification", row.get("tolerance", "")))
        row.setdefault("specification", row.get("tolerance", ""))
        row.setdefault("evaluation_method", "")
        row.setdefault("measurement_method", row.get("measurement", ""))
        row.setdefault("sample_size", "")
        row.setdefault("sample_frequency", "")
        row.setdefault("control_method", "")
        row.setdefault("process_parameter", row.get("process_characteristic", ""))
        row.setdefault("parameter_specification", "")
        row.setdefault("process_control_method", "")
        row.setdefault("setup_verification", "")
        row.setdefault("poka_yoke_device", "")
        row.setdefault("poka_yoke_verification", "")
        row.setdefault("process_record", row.get("record_form", ""))
        row.setdefault("reaction_plan", "")
        row.setdefault("needs_confirmation", row.get("ai_inferred", False))

