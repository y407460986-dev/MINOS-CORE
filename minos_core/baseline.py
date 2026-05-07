"""Baseline snapshot creation and content hashing for three-table results."""

from __future__ import annotations

import copy
import hashlib
import json
import time
from typing import Any


def create_baseline(
    result: dict[str, Any],
    *,
    label: str,
    created_by: str = "",
    created_at: str = "",
) -> dict[str, Any]:
    """Create a baseline snapshot from a *three_table_generation_result*.

    Returns a baseline dict suitable for comparison and release tracking.
    """
    pfd_steps = copy.deepcopy(_extract_rows(result, "process_flow"))
    pfmea_rows = copy.deepcopy(_extract_rows(result, "pfmea"))
    cp_rows = copy.deepcopy(_extract_rows(result, "control_plan"))

    tables = {
        "pfd": pfd_steps,
        "pfmea": pfmea_rows,
        "control_plan": cp_rows,
    }

    content_hash = _hash_tables(tables)
    timestamp = created_at or str(int(time.time()))
    baseline_id = f"BL-{timestamp}-{content_hash[:8]}"

    action_items = _nested_get(result, ["metadata", "action_items"], [])
    action_items_summary = _nested_get(
        result, ["metadata", "action_items_summary"], {}
    )
    open_count = action_items_summary.get("unresolved", _count_open_actions(action_items))

    knowledge_recs = _nested_get(
        result, ["metadata", "knowledge_recommendations"],
        _nested_get(result, ["knowledge_recommendations"], []),
    )
    unresolved_recs = sum(
        1 for r in knowledge_recs
        if isinstance(r, dict) and r.get("status") == "unresolved"
    )

    linkage_report = _nested_get(result, ["linkage_report"], {})
    sync_blocker_count = _count_sync_blockers(linkage_report)

    return {
        "baseline_id": baseline_id,
        "label": label,
        "created_at": timestamp,
        "created_by": created_by,
        "content_hash": content_hash,
        "tables": tables,
        "metadata": result.get("metadata", {}),
        "readiness": {
            "sync_blocker_count": sync_blocker_count,
            "open_action_count": open_count,
            "unresolved_recommendation_count": unresolved_recs,
        },
    }


def baseline_hash(baseline: dict[str, Any]) -> str:
    """Compute the SHA-256 content hash of a baseline's *tables*."""
    tables = baseline.get("tables", {})
    return _hash_tables(tables)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hash_tables(tables: dict[str, Any]) -> str:
    """SHA-256 over sorted JSON of *tables*."""
    payload = json.dumps(tables, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_rows(result: dict[str, Any], table: str) -> list[dict[str, Any]]:
    """Extract row list from *result* for a given *table* name.

    Tries both the direct ``result[table][key]`` path and the
    ``result["chain"]["key"]`` path used by ``_three_table_generation_envelope``.
    """
    # Direct table payload path (e.g. result["process_flow"]["steps"])
    table_payload = result.get(table)
    if isinstance(table_payload, dict):
        rows = table_payload.get("steps") or table_payload.get("rows")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]

    # Chain path (e.g. result["chain"]["process_steps"])
    chain = result.get("chain")
    if isinstance(chain, dict):
        key_map = {
            "process_flow": "process_steps",
            "pfmea": "failure_modes",
            "control_plan": "controls",
        }
        rows = chain.get(key_map.get(table, ""))
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]

    return []


def _nested_get(
    d: dict[str, Any], keys: list[str], default: Any = None
) -> Any:
    """Safely traverse nested dict by a list of keys."""
    current: Any = d
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
    return current if current is not None else default


def _count_open_actions(action_items: list[dict[str, Any]]) -> int:
    """Count unresolved action items (status not closed/ignored)."""
    closed = {"closed", "ignored", "已完成", "已关闭", "已验证", "已忽略"}
    count = 0
    for item in action_items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).strip()
        if status not in closed:
            count += 1
    return count


def _count_sync_blockers(linkage_report: dict[str, Any]) -> int:
    """Count blocker-level sync issues from a linkage report."""
    if not isinstance(linkage_report, dict):
        return 0
    sync_issues = linkage_report.get("sync_issues", [])
    if not isinstance(sync_issues, list):
        return 0
    return sum(
        1 for issue in sync_issues
        if isinstance(issue, dict) and issue.get("severity") == "blocker"
    )
