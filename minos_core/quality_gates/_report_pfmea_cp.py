"""PFMEA and Control Plan bundle reports."""
from __future__ import annotations

from typing import Any

from ..audit import AuditItem
from ._rows import _document_manual_review_items, _document_rows_report


def _pfmea_bundle_report(pfmea_bundle: dict[str, Any]) -> dict[str, Any]:
    """Produce a coverage report for a PFMEA bundle."""
    rows = pfmea_bundle.get("rows", pfmea_bundle.get("failure_modes", []))
    report = _document_rows_report(
        rows=rows,
        evidence=pfmea_bundle.get("evidence", []),
        pending_fields=pfmea_bundle.get("pending_fields", []),
        ai_inferred_items=pfmea_bundle.get("ai_inferred_items", []),
        stage_mode="generate_pfmea",
        next_stage="generate_control_plan",
        row_label="pfmea_row",
        id_field="pfmea_id",
        required_fields=(
            "pfmea_id",
            "process_step_id",
            "failure_mode",
            "failure_effect",
            "failure_cause",
            "evidence_refs",
        ),
        review_fields=("severity", "occurrence", "detection"),
    )
    _extend_pfmea_pfd_linkage_report(report, pfmea_bundle, rows)
    return report


def _control_plan_bundle_report(control_plan_bundle: dict[str, Any]) -> dict[str, Any]:
    """Produce a coverage report for a Control Plan bundle."""
    rows = control_plan_bundle.get(
        "rows", control_plan_bundle.get("control_plan_items", control_plan_bundle.get("controls", []))
    )
    report = _document_rows_report(
        rows=rows,
        evidence=control_plan_bundle.get("evidence", []),
        pending_fields=control_plan_bundle.get("pending_fields", []),
        ai_inferred_items=control_plan_bundle.get("ai_inferred_items", []),
        stage_mode="generate_control_plan",
        next_stage="validate",
        row_label="control_plan_row",
        id_field="control_plan_id",
        required_fields=(
            "control_plan_id",
            "process_step_id",
            "pfmea_id",
            "product_process_characteristic",
            "specification",
            "measurement_method",
            "control_method",
            "reaction_plan",
            "evidence_refs",
        ),
        review_fields=("sample_size", "sample_frequency"),
    )
    _extend_control_plan_linkage_report(report, control_plan_bundle, rows)
    return report


def _extend_pfmea_pfd_linkage_report(
    report: dict[str, Any], pfmea_bundle: dict[str, Any], rows: Any
) -> None:
    """Check PFMEA-PFD linkage: ensure each process step has a PFMEA risk row."""
    process_steps = pfmea_bundle.get("process_steps", pfmea_bundle.get("steps", []))
    if not isinstance(process_steps, list) or not isinstance(rows, list):
        return
    step_ids = {
        str(step.get("process_step_id", step.get("id", ""))).strip()
        for step in process_steps
        if isinstance(step, dict) and str(step.get("process_step_id", step.get("id", ""))).strip()
    }
    row_step_ids = {
        str(row.get("process_step_id", "")).strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("process_step_id", "")).strip()
    }
    for step_id in sorted(step_ids - row_step_ids):
        report["uncovered_items"].append(f"process_step:{step_id}.pfmea_risk")
    for step_id in sorted(row_step_ids - step_ids):
        report["uncovered_items"].append(f"pfmea_row.process_step_missing:{step_id}")
    report["ok"] = bool(report["ok"] and not any(
        item.endswith(".pfmea_risk") or "process_step_missing" in item
        for item in report["uncovered_items"]
    ))


def _extend_control_plan_linkage_report(
    report: dict[str, Any], control_plan_bundle: dict[str, Any], rows: Any
) -> None:
    """Check Control-Plan-PFMEA linkage: ensure PFMEA risks have corresponding controls."""
    pfmea_rows = control_plan_bundle.get("pfmea_rows", control_plan_bundle.get("failure_modes", []))
    process_steps = control_plan_bundle.get("process_steps", [])
    if not isinstance(rows, list):
        return
    if isinstance(process_steps, list) and process_steps:
        step_ids = {
            str(step.get("process_step_id", step.get("id", ""))).strip()
            for step in process_steps
            if isinstance(step, dict) and str(step.get("process_step_id", step.get("id", ""))).strip()
        }
        for row in rows:
            if not isinstance(row, dict):
                continue
            step_id = str(row.get("process_step_id", "")).strip()
            control_id = str(row.get("control_plan_id", "")).strip()
            if step_id and step_id not in step_ids:
                report["uncovered_items"].append(
                    f"control_plan_row:{control_id}.process_step_missing:{step_id}"
                )
    if isinstance(pfmea_rows, list) and pfmea_rows:
        controlled_pfmea_ids = {
            str(row.get("pfmea_id", "")).strip()
            for row in rows
            if isinstance(row, dict) and str(row.get("pfmea_id", "")).strip()
        }
        for pfmea_row in pfmea_rows:
            if not isinstance(pfmea_row, dict) or not _pfmea_row_requires_control(pfmea_row):
                continue
            pfmea_id = str(pfmea_row.get("pfmea_id", "")).strip()
            if pfmea_id and pfmea_id not in controlled_pfmea_ids:
                report["uncovered_items"].append(
                    f"pfmea_row:{pfmea_id}.control_plan_control"
                )
    report["ok"] = bool(report["ok"] and not any(
        "process_step_missing" in item or item.endswith(".control_plan_control")
        for item in report["uncovered_items"]
    ))


def _pfmea_row_requires_control(row: dict[str, Any]) -> bool:
    """Return True if the PFMEA row requires a corresponding Control Plan item."""
    action_priority = str(row.get("action_priority", row.get("AP", ""))).strip().upper()
    classification = str(row.get("classification", "")).strip()
    try:
        severity = int(row.get("severity", row.get("S", 0)) or 0)
    except (TypeError, ValueError):
        severity = 0
    return bool(action_priority in {"H", "M"} or severity >= 9 or classification)


def _pfmea_manual_review_items(report: dict[str, Any]) -> list[AuditItem]:
    """Convert a PFMEA report into AuditItem objects for manual review."""
    return _document_manual_review_items(
        report,
        incomplete_category="pfmea_incomplete",
        missing_ref_category="pfmea_missing_ref",
        pending_category="pfmea_pending_field",
        needs_confirmation_category="pfmea_needs_confirmation",
        ai_category="pfmea_ai_inferred",
        review_category="pfmea_review_field",
        message_prefix="PFMEA",
    )


def _control_plan_manual_review_items(report: dict[str, Any]) -> list[AuditItem]:
    """Convert a Control Plan report into AuditItem objects for manual review."""
    return _document_manual_review_items(
        report,
        incomplete_category="control_plan_incomplete",
        missing_ref_category="control_plan_missing_ref",
        pending_category="control_plan_pending_field",
        needs_confirmation_category="control_plan_needs_confirmation",
        ai_category="control_plan_ai_inferred",
        review_category="control_plan_review_field",
        message_prefix="控制计划",
    )
