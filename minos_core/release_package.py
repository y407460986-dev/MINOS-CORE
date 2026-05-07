"""Release packaging and locking for three-table governance."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

RELEASE_LOCK_KEY = "release_lock"
PREVIOUS_RELEASE_KEY = "previous_release"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_release_readiness(result: dict[str, Any]) -> dict[str, Any]:
    """Check the release readiness of a *three_table_generation_result*.

    Returns a ``readiness`` dict with an ``allowed`` flag and a list of
    individual ``checks``.
    """
    checks: list[dict[str, Any]] = []

    # --- sync_complete ---
    linkage_report = _nested_get(result, ["linkage_report"], {})
    sync_issues = linkage_report.get("sync_issues", [])
    if not isinstance(sync_issues, list):
        sync_issues = []
    sync_blockers = [
        s for s in sync_issues
        if isinstance(s, dict) and s.get("severity") == "blocker"
    ]
    checks.append({
        "check_id": "sync_complete",
        "label": "三表同步完整",
        "status": "passed" if not sync_blockers else "failed",
        "message": f"{len(sync_blockers)} 个同步阻断" if sync_blockers else "",
        "blocking": True,
    })

    # --- rows_confirmed ---
    unconfirmed = _count_unconfirmed_rows(result)
    checks.append({
        "check_id": "rows_confirmed",
        "label": "所有活动行已确认",
        "status": "passed" if unconfirmed == 0 else "failed",
        "message": f"{unconfirmed} 行未确认" if unconfirmed else "",
        "blocking": True,
    })

    # --- actions_closed ---
    action_items = _nested_get(result, ["metadata", "action_items"], [])
    if not isinstance(action_items, list):
        action_items = []
    high_open = _count_high_priority_open(action_items)
    checks.append({
        "check_id": "actions_closed",
        "label": "高风险行动项已关闭",
        "status": "passed" if high_open == 0 else "warning",
        "message": f"{high_open} 项未关闭" if high_open else "",
        "blocking": False,
    })

    # --- recommendations_handled ---
    knowledge_recs = _nested_get(
        result, ["metadata", "knowledge_recommendations"],
        _nested_get(result, ["knowledge_recommendations"], []),
    )
    if not isinstance(knowledge_recs, list):
        knowledge_recs = []
    unresolved_recs = sum(
        1 for r in knowledge_recs
        if isinstance(r, dict) and r.get("status") == "unresolved"
    )
    checks.append({
        "check_id": "recommendations_handled",
        "label": "知识推荐已处理",
        "status": "passed" if unresolved_recs == 0 else "failed",
        "message": f"{unresolved_recs} 条未处理" if unresolved_recs else "",
        "blocking": True,
    })

    blocking_count = sum(1 for c in checks if c.get("blocking") and c["status"] == "failed")
    warning_count = sum(1 for c in checks if not c.get("blocking") and c["status"] == "warning")

    allowed = blocking_count == 0

    if allowed:
        status = "ready"
    elif blocking_count > 0:
        status = "blocked"
    else:
        status = "draft"

    return {
        "allowed": allowed,
        "status": status,
        "checks": checks,
        "blocking_count": blocking_count,
        "warning_count": warning_count,
    }


def create_release_package(
    result: dict[str, Any],
    *,
    output_dir: str,
    release_id: str = "",
    revision: str = "A",
    actor: str = "",
) -> dict[str, Any]:
    """Create a release package in *output_dir*.

    The function first checks readiness.  If the release is not allowed
    (blocking checks failed) no files are written and the returned
    manifest only carries the readiness result.
    """
    target_dir = Path(output_dir)
    release_id = release_id or f"REL-{int(time.time())}"
    release_dir = target_dir / f"release_{release_id}"

    readiness = build_release_readiness(result)

    manifest: dict[str, Any] = {
        "release_id": release_id,
        "revision": revision,
        "created_at": _now_iso(),
        "actor": actor,
        "source_run_id": _nested_get(result, ["manifest", "run_id"], None),
        "baseline_hash": _compute_baseline_hash(result),
        "locked": False,
        "readiness": readiness,
        "files": [],
    }

    if not readiness["allowed"]:
        return manifest

    # Create output directory and write files
    release_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = release_dir / "release_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    # Also write a placeholder workbook path (caller can replace with real export)
    workbook_path = release_dir / "unified_workbook.xlsx"
    workbook_path.touch()

    manifest["files"].append({
        "name": "unified_workbook.xlsx",
        "sha256": _file_sha256(str(workbook_path)),
    })

    # Re-write manifest with file listing included
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    return manifest


def lock_release(
    result: dict[str, Any],
    *,
    release_id: str = "",
    revision: str = "A",
    actor: str = "",
) -> dict[str, Any]:
    """Lock a release by writing ``release_lock`` into metadata.

    Returns a deep copy of *result* with the lock applied.
    If the result is already locked, raises ``RuntimeError``.
    """
    metadata = result.get("metadata", {})
    if isinstance(metadata, dict) and metadata.get(RELEASE_LOCK_KEY):
        existing = metadata[RELEASE_LOCK_KEY]
        if isinstance(existing, dict) and existing.get("locked"):
            raise RuntimeError(
                f"Release is already locked (release_id={existing.get('release_id', '?')}, "
                f"revision={existing.get('revision', '?')})"
            )

    patched = copy.deepcopy(result)
    meta = patched.setdefault("metadata", {})
    if not isinstance(meta, dict):
        meta = {}
        patched["metadata"] = meta

    meta[RELEASE_LOCK_KEY] = {
        "release_id": release_id,
        "revision": revision,
        "locked_at": _now_iso(),
        "locked_by": actor,
        "locked": True,
    }

    # Also reflect on the chain metadata if present
    chain = patched.get("chain")
    if isinstance(chain, dict):
        chain_meta = chain.setdefault("metadata", {})
        if isinstance(chain_meta, dict):
            chain_meta[RELEASE_LOCK_KEY] = copy.deepcopy(meta[RELEASE_LOCK_KEY])

    return patched


def create_next_revision(
    result: dict[str, Any],
    *,
    next_revision: str = "",
    actor: str = "",
) -> dict[str, Any]:
    """Move the release lock into ``previous_release`` and reset to unlocked.

    Returns a deep copy of *result* ready for the next revision.
    """
    patched = copy.deepcopy(result)
    meta = patched.setdefault("metadata", {})
    if not isinstance(meta, dict):
        meta = {}
        patched["metadata"] = meta

    current_lock = meta.pop(RELEASE_LOCK_KEY, None)
    if isinstance(current_lock, dict):
        meta[PREVIOUS_RELEASE_KEY] = current_lock

    meta[RELEASE_LOCK_KEY] = {
        "release_id": "",
        "revision": next_revision,
        "locked_at": "",
        "locked_by": "",
        "locked": False,
    }

    # Also set revision in the document if a revision field exists
    if "revision" not in meta:
        meta["revision"] = next_revision

    # Reflect on chain metadata as well
    chain = patched.get("chain")
    if isinstance(chain, dict):
        chain_meta = chain.setdefault("metadata", {})
        if isinstance(chain_meta, dict):
            chain_meta.pop(RELEASE_LOCK_KEY, None)
            chain_meta[RELEASE_LOCK_KEY] = copy.deepcopy(meta[RELEASE_LOCK_KEY])

    return patched


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _nested_get(d: Any, keys: list[str], default: Any = None) -> Any:
    """Safely traverse a nested dict by a list of keys."""
    current = d
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
    return current if current is not None else default


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat()


def _count_unconfirmed_rows(result: dict[str, Any]) -> int:
    """Count active rows whose review_status is not '已确认'."""
    count = 0
    for table in ("process_flow", "pfmea", "control_plan"):
        rows = _extract_rows(result, table)
        for row in rows:
            if not isinstance(row, dict) or row.get("deleted"):
                continue
            status = str(row.get("review_status", "")).strip()
            if status != "已确认":
                count += 1
    return count


def _extract_rows(result: dict[str, Any], table: str) -> list[dict[str, Any]]:
    """Extract row list from *result* for a given *table* name."""
    table_payload = result.get(table)
    if isinstance(table_payload, dict):
        rows = table_payload.get("steps") or table_payload.get("rows")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]

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


def _count_high_priority_open(action_items: list[dict[str, Any]]) -> int:
    """Count high-priority action items that are not closed/ignored."""
    closed = {"closed", "ignored", "已完成", "已关闭", "已验证", "已忽略"}
    count = 0
    for item in action_items:
        if not isinstance(item, dict):
            continue
        priority = str(item.get("priority", "")).strip().lower()
        status = str(item.get("status", "")).strip()
        if priority == "high" and status not in closed:
            count += 1
    return count


def _compute_baseline_hash(result: dict[str, Any]) -> str:
    """Compute a quick content hash for the three-table rows."""
    tables = {
        "pfd": _extract_rows(result, "process_flow"),
        "pfmea": _extract_rows(result, "pfmea"),
        "control_plan": _extract_rows(result, "control_plan"),
    }
    raw = json.dumps(tables, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _file_sha256(path: str) -> str:
    """SHA-256 of file contents."""
    sha = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                sha.update(chunk)
    except OSError:
        return ""
    return sha.hexdigest()
