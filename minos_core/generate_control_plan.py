"""Generate control plans from PFMEA bundles."""

from __future__ import annotations

from typing import Any


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
    ai_inferred_items = _dedupe_ai_items(
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
    pfmea_id = _text(row, "pfmea_id", "id", default=f"PFMEA-{index:03d}")
    process_step_id = _text(row, "process_step_id", "step_no", "step", default="")
    classification = _text(
        row,
        "classification",
        "special_characteristic",
        "special_characteristic_classification",
        default="",
    )
    risk_level = _risk_level(row, classification)
    direct_specification = _text(
        row,
        "specification",
        "product_process_requirement",
        "process_requirement",
        "requirement",
        default="",
    )
    direct_measurement = _text(
        row,
        "measurement_method",
        "measurement",
        "detection_control",
        "detection_method",
        default="",
    )
    direct_sample_size = _text(row, "sample_size", default="")
    direct_sample_frequency = _text(row, "sample_frequency", default="")
    direct_control_method = _text(row, "control_method", default="")
    direct_reaction_plan = _text(row, "reaction_plan", default="")

    specification = direct_specification or _derived_specification(row)
    measurement_method = direct_measurement or _default_measurement_method(row)
    sample_size = direct_sample_size or _default_sample_size(risk_level)
    sample_frequency = direct_sample_frequency or _default_sample_frequency(risk_level)
    control_method = direct_control_method or _control_method(row)
    reaction_plan = direct_reaction_plan or _reaction_plan(risk_level)
    inferred_fields = _inferred_control_fields(
        {
            "specification": direct_specification,
            "measurement_method": direct_measurement,
            "sample_size": direct_sample_size,
            "sample_frequency": direct_sample_frequency,
            "control_method": direct_control_method,
            "reaction_plan": direct_reaction_plan,
        }
    )
    ai_inferred = bool(
        row.get("ai_inferred", row.get("created_by_ai", False)) or inferred_fields
    )
    confidence = _confidence(row)
    evidence_refs = _string_list(row.get("evidence_refs", []))
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
        "product_process_characteristic": _characteristic(row),
        "specification": specification,
        "classification": classification,
        "measurement_method": measurement_method,
        "sample_size": sample_size,
        "sample_frequency": sample_frequency,
        "control_method": control_method,
        "reaction_plan": reaction_plan,
        "gauges": _source_gauges(row),
        "inspection_equipment": _inspection_equipment(row),
        "evidence_refs": evidence_refs,
        "confidence": confidence,
        "ai_inferred": ai_inferred,
        "needs_confirmation": needs_confirmation,
        "ai_reasoning": _control_reasoning(row, pfmea_id, risk_level, inferred_fields),
        "source_risk_level": risk_level,
        "source_action_priority": _text(row, "action_priority", default=""),
        "source_severity": _int(row.get("severity", row.get("S"))),
        "source_occurrence": _int(row.get("occurrence")),
        "source_detection": _int(row.get("detection")),
        "source_failure_cause": _text(row, "failure_cause", "cause", default=""),
        "source_prevention_control": _text(row, "prevention_control", default=""),
        "source_detection_control": _text(row, "detection_control", default=""),
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
    linked_id = _text(row, "linked_control_plan_id", "control_plan_id", default="")
    if linked_id:
        return linked_id
    if pfmea_id:
        return f"CP-{pfmea_id}"
    if process_step_id:
        return f"CP-{process_step_id}-{index:03d}"
    return f"CP-{index:03d}"


def _characteristic(row: dict[str, Any]) -> str:
    explicit = _text(
        row,
        "product_process_characteristic",
        "characteristic",
        "product_characteristic",
        "process_characteristic",
        "special_characteristic",
        "classification",
        default="",
    )
    if explicit:
        return explicit
    failure_mode = _text(row, "failure_mode", "mode", "failure", default="")
    if failure_mode:
        return f"针对失效模式的控制：{failure_mode}"
    return _text(row, "process_function", "process", "operation", default="")


def _source_special_characteristics(row: dict[str, Any], classification: str) -> list[str]:
    values: list[str] = []
    for source in (
        row.get("characteristic_refs", []),
        row.get("special_characteristics", []),
        row.get("product_characteristics", []),
        row.get("process_characteristics", []),
        classification,
    ):
        for item in _string_list(source):
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
        for item in _string_list(source):
            if item not in values:
                values.append(item)
    return values


def _inspection_equipment(row: dict[str, Any]) -> str:
    explicit = _text(
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
    requirement = _text(
        row,
        "drawing_specification",
        "drawing_requirement",
        "technical_requirement",
        "inspection_requirement",
        default="",
    )
    if requirement:
        return requirement
    failure_mode = _text(row, "failure_mode", "mode", "failure", default="")
    if failure_mode:
        return f"草案控制意图：预防或探测 {failure_mode}"
    process_function = _text(row, "process_function", "process", default="")
    if process_function:
        return f"草案控制意图：保持 {process_function}"
    return "草案控制意图：待依据受控图纸规格确认"


def _default_measurement_method(row: dict[str, Any]) -> str:
    detection_control = _text(row, "detection_control", "current_detection_control", default="")
    if detection_control:
        return detection_control
    detection = _int(row.get("detection"))
    if detection >= 8:
        return "按 PFMEA 探测风险执行强化检验或防错验证"
    if detection >= 5:
        return "按 PFMEA 探测控制执行记录化检验"
    return "按控制计划执行常规检验"


def _control_method(row: dict[str, Any]) -> str:
    prevention_control = _text(row, "prevention_control", default="")
    detection_control = _text(row, "detection_control", default="")
    if prevention_control and detection_control:
        return f"预防：{prevention_control}；探测：{detection_control}"
    if prevention_control:
        return prevention_control
    if detection_control:
        return detection_control
    action_priority = _text(row, "action_priority", default="").upper()
    if action_priority in {"H", "M"}:
        return f"针对 AP {action_priority} 的 PFMEA 风险定义控制方法"
    return "定义常规过程控制方法"


def _risk_level(row: dict[str, Any], classification: str) -> str:
    action_priority = _text(row, "action_priority", default="").upper()
    severity = _int(row.get("severity"))
    occurrence = _int(row.get("occurrence"))
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
    existing = _text(row, "ai_reasoning", default="")
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
    }.get(field_name, field_name)


def _ai_is_uncertain(row: dict[str, Any]) -> bool:
    uncertainty_text = " ".join(
        _text(row, key, default="")
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


def _text(row: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _confidence(row: dict[str, Any]) -> float:
    try:
        return float(row.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe_ai_items(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = _ai_item_key(value)
        if not key or key in seen:
            continue
        result.append(value)
        seen.add(key)
    return result


def _ai_item_key(value: Any) -> str:
    if isinstance(value, dict):
        for field_name in ("control_plan_id", "pfmea_id", "evidence_id", "item_id", "id"):
            text = str(value.get(field_name, "")).strip()
            if text:
                return text
    return str(value).strip()
