"""PFMEA action item tracking -- generate, filter, and summarise action items."""

from __future__ import annotations

from datetime import date
from typing import Any

_STATUS_MAP: dict[str, str] = {
    "未制定": "open",
    "待处理": "open",
    "未开始": "open",
    "open": "open",
    "进行中": "in_progress",
    "in_progress": "in_progress",
    "受阻": "blocked",
    "blocked": "blocked",
    "已完成": "closed",
    "已关闭": "closed",
    "已验证": "closed",
    "closed": "closed",
    "已忽略": "ignored",
    "ignored": "ignored",
}

_CLOSED_OR_IGNORED = {"closed", "ignored"}
_DONE_STATUSES = {"已完成", "已关闭", "已验证", "closed"}


def build_action_items(
    source: dict[str, Any], *, today: date | None = None
) -> list[dict[str, Any]]:
    """Generate standalone action items from PFMEA rows.

    Only *active* (non-``deleted``) rows are considered.  An action item is
    created for a row when **any** of the following is true:

    * ``action_priority == "H"``
    * ``severity >= 9``
    * ``recommended_action`` is non-empty
    * ``action_status`` is non-empty and is **not** one of the closed/done
      statuses (``"已完成"``, ``"已关闭"``, ``"已验证"``, ``"closed"``)
    """
    rows = _extract_pfmea_rows(source)
    items: list[dict[str, Any]] = []
    counter: dict[str, int] = {}

    for row in rows:
        if not isinstance(row, dict) or row.get("deleted"):
            continue

        pfmea_id = str(row.get("pfmea_id", "")).strip()
        ap = str(row.get("action_priority", "")).strip().upper()
        sev = _to_int(row.get("severity"))
        rec_action = str(row.get("recommended_action", "")).strip()
        action_status = str(row.get("action_status", "")).strip()

        # ---- guard: does this row trigger an action item? ----
        triggers = (
            ap == "H"
            or sev >= 9
            or bool(rec_action)
            or (bool(action_status) and action_status not in _DONE_STATUSES)
        )
        if not triggers:
            continue

        # ---- index within the same PFMEA row ----
        counter.setdefault(pfmea_id, 0)
        counter[pfmea_id] += 1
        idx = counter[pfmea_id]

        # ---- mapped fields ----
        description = rec_action if rec_action else "补充高风险措施并完成有效性验证"
        resp = str(row.get("responsibility", "")).strip()
        owner_raw = str(row.get("owner", "")).strip()
        owner = resp if resp else owner_raw
        due_date = str(row.get("target_date", "")).strip()
        status = _STATUS_MAP.get(action_status, "open")
        priority = (
            "high"
            if (ap == "H" or sev >= 9)
            else "medium"
            if ap == "M"
            else "low"
        )

        items.append(
            {
                "action_id": f"ACT-{pfmea_id}-{idx:03d}",
                "source_pfmea_id": pfmea_id,
                "process_step_id": str(row.get("process_step_id", "")).strip(),
                "action_type": "risk_reduction",
                "description": description,
                "owner": owner,
                "due_date": due_date,
                "status": status,
                "priority": priority,
                "closure_evidence_refs": [],
                "manual_confirmation_event": "",
                "ignore_reason": "",
                "created_from": "pfmea",
                "closed_at": "",
                "closed_by": "",
            }
        )

    return items


def unresolved_action_items(
    action_items: list[dict[str, Any]], *, today: date | None = None
) -> list[dict[str, Any]]:
    """Return action items that block final export.

    An action item is unresolved when **any** of these hold:

    1. ``priority == "high"`` and *status* is not ``"closed"`` or ``"ignored"``.
    2. ``due_date`` is earlier than *today* and *status* is not ``"closed"`` or
       ``"ignored"`` (overdue).
    3. *status* is ``"closed"`` but both ``closure_evidence_refs`` and
       ``manual_confirmation_event`` are empty (缺少闭环证据).
    4. *status* is ``"ignored"`` but ``ignore_reason`` is empty (缺少忽略理由).
    """
    today = today or date.today()
    unresolved: list[dict[str, Any]] = []

    for item in action_items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).strip()
        priority = str(item.get("priority", "")).strip()
        due_date_str = str(item.get("due_date", "")).strip()

        # (1) high priority not closed/ignored
        if priority == "high" and status not in _CLOSED_OR_IGNORED:
            unresolved.append(item)
            continue

        # (2) overdue
        due_date = _parse_date(due_date_str)
        if (
            due_date is not None
            and due_date < today
            and status not in _CLOSED_OR_IGNORED
        ):
            unresolved.append(item)
            continue

        # (3) closed without evidence
        if status == "closed":
            evidence_refs = item.get("closure_evidence_refs")
            manual_event = str(item.get("manual_confirmation_event", "")).strip()
            if not evidence_refs and not manual_event:
                unresolved.append(item)
                continue

        # (4) ignored without reason
        if status == "ignored":
            ignore_reason = str(item.get("ignore_reason", "")).strip()
            if not ignore_reason:
                unresolved.append(item)
                continue

    return unresolved


def action_items_summary(
    action_items: list[dict[str, Any]], *, today: date | None = None
) -> dict[str, int]:
    """Return a statistical summary of *action_items*.

    Keys in the returned dict:

    * ``total``
    * ``open`` / ``in_progress`` / ``blocked`` / ``closed`` / ``ignored``
    * ``overdue`` -- due date before *today* and status not closed/ignored
    * ``unresolved`` -- same logic as :func:`unresolved_action_items`
    * ``high_priority`` -- priority == ``"high"``
    * ``high_priority_unresolved`` -- high priority **and** unresolved
    * ``closed_without_evidence`` -- closed but missing ``closure_evidence_refs``
      and ``manual_confirmation_event``
    """
    today = today or date.today()
    unresolved = unresolved_action_items(action_items, today=today)

    summary: dict[str, int] = {
        "total": len(action_items),
        "open": 0,
        "in_progress": 0,
        "blocked": 0,
        "closed": 0,
        "ignored": 0,
        "overdue": 0,
        "unresolved": len(unresolved),
        "high_priority": 0,
        "high_priority_unresolved": 0,
        "closed_without_evidence": 0,
    }

    unresolved_ids = {item.get("action_id") for item in unresolved}

    for item in action_items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).strip()
        priority = str(item.get("priority", "")).strip()
        due_date_str = str(item.get("due_date", "")).strip()

        # status bucket
        if status in summary:
            summary[status] += 1

        # high priority
        if priority == "high":
            summary["high_priority"] += 1

        # high priority unresolved
        if priority == "high" and item.get("action_id") in unresolved_ids:
            summary["high_priority_unresolved"] += 1

        # overdue
        due_date = _parse_date(due_date_str)
        if (
            due_date is not None
            and due_date < today
            and status not in _CLOSED_OR_IGNORED
        ):
            summary["overdue"] += 1

        # closed without evidence
        if status == "closed":
            evidence_refs = item.get("closure_evidence_refs")
            manual_event = str(item.get("manual_confirmation_event", "")).strip()
            if not evidence_refs and not manual_event:
                summary["closed_without_evidence"] += 1

    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_pfmea_rows(source: dict[str, Any]) -> list[Any]:
    """Pull PFMEA rows from a source dict, supporting multiple shapes."""
    # shape 1: source["pfmea"]["rows"]
    if "pfmea" in source and isinstance(source.get("pfmea"), dict):
        rows = source["pfmea"].get("rows")
        if isinstance(rows, list):
            return rows
    # shape 2: source["failure_modes"]
    rows = source.get("failure_modes")
    if isinstance(rows, list):
        return rows
    return []


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
