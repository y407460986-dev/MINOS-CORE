"""Audit trail recording for three-table operations."""

from __future__ import annotations

import copy
import hashlib
import json
import random
import time
from typing import Any

AUDIT_TRAIL_KEY = "audit_trail"

_ACTIONS = {
    "edit", "add", "delete", "confirm", "accept_recommendation",
    "ignore_recommendation", "close_action", "lock_release",
    "create_baseline",
}

_ENTITY_TYPES = {
    "pfmea", "control_plan", "process_step", "action_item",
    "recommendation", "release",
}


def build_audit_event(
    *,
    run_id: str | None = None,
    entity_type: str = "",
    entity_id: str = "",
    action: str = "",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
    actor: str = "local_user",
    source: str = "desktop",
) -> dict[str, Any]:
    """Build a single audit event dict.

    The event is used by :func:`append_audit_event` to record an
    auditable action inside the result's ``metadata.audit_trail`` list.
    """
    timestamp = _now_iso()
    event_id = f"AUDIT-{int(time.time())}-{random.randint(1000, 9999)}"

    before_hash = _object_hash(before) if before is not None else ""
    after_hash = _object_hash(after) if after is not None else ""

    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "run_id": run_id,
        "actor": actor,
        "source": source,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "reason": reason,
        "before_hash": before_hash,
        "after_hash": after_hash,
    }


def append_audit_event(
    result: dict[str, Any], event: dict[str, Any]
) -> dict[str, Any]:
    """Append *event* to ``result["metadata"]["audit_trail"]``.

    The *result* dict is deep-copied before modification so the
    caller's original is not mutated.
    """
    patched = copy.deepcopy(result)
    metadata = patched.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        patched["metadata"] = metadata
    trail = metadata.setdefault(AUDIT_TRAIL_KEY, [])
    if not isinstance(trail, list):
        trail = []
        metadata[AUDIT_TRAIL_KEY] = trail
    trail.append(copy.deepcopy(event))
    return patched


def audit_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Return a summary of the audit trail stored in *result*."""
    metadata = result.get("metadata", {})
    trail = metadata.get(AUDIT_TRAIL_KEY, []) if isinstance(metadata, dict) else []
    if not isinstance(trail, list):
        trail = []

    actions_by_type: dict[str, int] = {}
    last_event_at: str = ""
    for event in trail:
        if not isinstance(event, dict):
            continue
        action = str(event.get("action", "")).strip()
        if action:
            actions_by_type[action] = actions_by_type.get(action, 0) + 1
        ts = str(event.get("timestamp", ""))
        if ts and (not last_event_at or ts > last_event_at):
            last_event_at = ts

    return {
        "total_events": len(trail),
        "last_event_at": last_event_at,
        "actions_by_type": actions_by_type,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current time as ISO-8601 string (local time)."""
    from datetime import datetime

    return datetime.now().isoformat()


def _object_hash(obj: Any) -> str:
    """SHA-256 hash of a JSON-normalised object."""
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
