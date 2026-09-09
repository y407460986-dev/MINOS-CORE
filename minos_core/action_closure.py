"""Action closure checks for AIAG-VDA PFMEA rows."""

from __future__ import annotations

from datetime import date
from typing import Any

CLOSED_STATUSES = {"已关闭", "已验证"}
DONE_STATUSES = {"已完成", "已验证", "已关闭"}


def action_closure_issues(rows: Any, *, today: date | None = None) -> list[dict[str, str]]:
    today = today or date.today()
    issues: list[dict[str, str]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("pfmea_id", "")).strip()
        ap = str(row.get("action_priority", row.get("AP", ""))).strip().upper()
        status = str(row.get("action_status", row.get("status", ""))).strip()
        if ap == "H" and not str(row.get("recommended_action", "")).strip():
            issues.append(_issue(row_id, "recommended_action", "高 AP 必须填写推荐措施。", "blocker"))
        if ap in {"H", "M"}:
            if not str(row.get("responsibility", "")).strip():
                issues.append(_issue(row_id, "responsibility", "高/中 AP 必须填写责任人。", "blocker"))
            if not str(row.get("target_date", "")).strip():
                issues.append(_issue(row_id, "target_date", "高/中 AP 必须填写目标完成日期。", "blocker"))
        due_date = _parse_date(row.get("target_date"))
        if due_date is not None and due_date < today and status not in CLOSED_STATUSES:
            issues.append(_issue(row_id, "target_date", "措施已逾期且未关闭。", "review"))
        if status in DONE_STATUSES:
            missing_after = [
                field
                for field in ("after_severity", "after_occurrence", "after_detection", "after_ap")
                if row.get(field) in {None, ""}
            ]
            for field in missing_after:
                issues.append(_issue(row_id, field, "措施完成后必须填写措施后 S/O/D/AP。", "blocker"))
            if str(row.get("after_ap", "")).strip().upper() == "H":
                issues.append(_issue(row_id, "after_ap", "措施后 AP 仍为 H，需要继续人工复核。", "review"))
    return issues


def _issue(row_id: str, field: str, message: str, severity: str) -> dict[str, str]:
    item_id = f"pfmea:{row_id}.{field}" if row_id else f"pfmea.{field}"
    return {
        "item_id": item_id,
        "category": "AIAG-VDA 措施闭环",
        "field": field,
        "severity": severity,
        "message": message,
    }


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
