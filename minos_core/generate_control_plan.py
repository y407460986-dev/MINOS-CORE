"""Generate control plans from PFMEA bundles."""

from __future__ import annotations

from typing import Any


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
    return {
        "document_type": "control_plan",
        "schema_version": "minos-core.generated.v1",
        "source_document_type": pfmea_bundle.get("document_type", "pfmea"),
        "product": pfmea_bundle.get("product", {}),
        "evidence": pfmea_bundle.get("evidence", []),
        "rows": control_rows,
        "pending_fields": pfmea_bundle.get("pending_fields", []),
        "ai_inferred_items": pfmea_bundle.get("ai_inferred_items", []),
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
        "function_requirement",
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

    return {
        "control_plan_id": _control_plan_id(row, pfmea_id, process_step_id, index),
        "process_step_id": process_step_id,
        "pfmea_id": pfmea_id,
        "product_process_characteristic": _characteristic(row),
        "specification": specification,
        "classification": classification,
        "measurement_method": measurement_method,
        "sample_size": sample_size,
        "sample_frequency": sample_frequency,
        "control_method": control_method,
        "reaction_plan": reaction_plan,
        "evidence_refs": _string_list(row.get("evidence_refs", [])),
        "needs_confirmation": _needs_confirmation(
            row,
            [
                direct_specification,
                direct_measurement,
                direct_sample_size,
                direct_sample_frequency,
                direct_control_method,
                direct_reaction_plan,
            ],
        ),
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
        return f"Control for: {failure_mode}"
    return _text(row, "process_function", "process", "operation", default="")


def _derived_specification(row: dict[str, Any]) -> str:
    failure_mode = _text(row, "failure_mode", "mode", "failure", default="")
    if failure_mode:
        return f"Prevent or detect: {failure_mode}"
    process_function = _text(row, "process_function", "process", default="")
    if process_function:
        return f"Maintain process function: {process_function}"
    return "Confirm specification from PFMEA and product requirements"


def _default_measurement_method(row: dict[str, Any]) -> str:
    detection = _int(row.get("detection"))
    if detection >= 8:
        return "Enhanced inspection or error-proofing verification"
    if detection >= 5:
        return "Documented inspection per PFMEA detection control"
    return "Standard inspection per control plan"


def _control_method(row: dict[str, Any]) -> str:
    prevention_control = _text(row, "prevention_control", default="")
    detection_control = _text(row, "detection_control", default="")
    if prevention_control and detection_control:
        return f"Prevention: {prevention_control}; Detection: {detection_control}"
    if prevention_control:
        return prevention_control
    if detection_control:
        return detection_control
    action_priority = _text(row, "action_priority", default="").upper()
    if action_priority in {"H", "M"}:
        return f"Define control for AP {action_priority} PFMEA risk"
    return "Define routine process control"


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
        return "5 pcs"
    return "1 pc"


def _default_sample_frequency(risk_level: str) -> str:
    if risk_level == "high":
        return "Every part"
    if risk_level == "medium":
        return "Each lot and setup"
    return "First-off and periodic"


def _reaction_plan(risk_level: str) -> str:
    if risk_level == "high":
        return (
            "Stop process, contain suspect product, notify quality, and verify "
            "corrective action before restart"
        )
    if risk_level == "medium":
        return "Contain suspect product and notify quality or process owner"
    return "Segregate nonconforming product and follow nonconformance procedure"


def _needs_confirmation(row: dict[str, Any], direct_fields: list[str]) -> bool:
    if bool(row.get("needs_confirmation", False)):
        return True
    return not all(direct_fields)


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


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
