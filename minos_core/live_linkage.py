"""Live linkage for PFD/PFMEA/CP three-table edit events and downstream sync.

Provides three core functions for V1.11 work package A+B+C:

1. :func:`build_live_edit_events` -- extract actionable events from an edit patch.
2. :func:`preview_live_linkage_impacts` -- preview downstream impacts for events.
3. :func:`build_live_sync_patch` -- generate a standards-compliant edit patch for
   user-selected impacts.
"""

from __future__ import annotations

import copy
from typing import Any

from minos_core._table_constants import TABLE_ID_FIELDS as _ID_FIELDS

from .change_management import _rows as _cm_rows, _group
from minos_core._text_utils import text
from .three_table_linkage import build_three_table_linkage_map
from .edit_patch import EDIT_PATCH_VERSION

# ---------------------------------------------------------------------------
# Table-to-row-key mapping
# ---------------------------------------------------------------------------

_TABLE_ROWS_KEY = {
    "process_flow": "steps",
    "pfmea": "rows",
    "control_plan": "rows",
}

_TABLE_CHAIN_KEY = {
    "process_flow": "process_steps",
    "pfmea": "failure_modes",
    "control_plan": "controls",
}


# ---------------------------------------------------------------------------
# Metadata / non-sync actions (these do NOT produce linkage events)
# ---------------------------------------------------------------------------

_METADATA_ACTIONS = frozenset({
    "confirm",
    "accept_recommendation",
    "ignore_recommendation",
    "resolve_change_impact",
    "resolve_review_issue",
})

# ---------------------------------------------------------------------------
# Trigger fields for inherited-field sync
# ---------------------------------------------------------------------------

_PFD_INHERITED_FIELDS = frozenset({
    "operation",
    "process_function",
    "product_characteristics",
    "process_characteristics",
    "special_characteristics",
    "characteristic_refs",
})

_PFMEA_CP_RELEVANT_FIELDS = frozenset({
    "failure_mode",
    "failure_effect",
    "failure_cause",
    "prevention_control",
    "detection_control",
    "action_priority",
    "severity",
    "characteristic_refs",
    "classification",
})

# Fields synced PFD -> PFMEA for sync_inherited_fields
_PFD_TO_PFMEA_SYNC_FIELDS = [
    "operation",
    "process_function",
    "product_characteristics",
    "process_characteristics",
    "special_characteristics",
    "characteristic_refs",
]

# Fields synced PFD -> CP for sync_inherited_fields
_PFD_TO_CP_SYNC_FIELDS = [
    "product_process_characteristic",
    "classification",
    "source_special_characteristics",
]


# ===================================================================
# 1. build_live_edit_events
# ===================================================================

def build_live_edit_events(before: dict, edit_patch: dict) -> list[dict]:
    """Extract actionable linkage events from an edit_patch.

    The *before* payload uses the standard three-table shape recognised by
    :func:`minos_core.change_management._rows`.

    Returns a list of event dicts with keys ``event_id``, ``source_table``,
    ``source_id``, ``action``, ``changed_fields``, ``before``, ``after``.
    """
    items = _patch_items(edit_patch)
    events: list[dict] = []
    for idx, item in enumerate(items):
        action = item.get("action", "")
        table = item.get("table", "")

        # Skip metadata / non-sync actions
        if action in _METADATA_ACTIONS:
            continue
        if table not in _TABLE_ROWS_KEY:
            continue

        before_rows = _read_rows(before, table)
        before_by_id = _index_by_id(before_rows, table)

        if action == "add":
            row = item.get("row") or {}
            target_id = _row_id(row, table)
            after = dict(row)
            events.append({
                "event_id": f"EVT-{idx:03d}",
                "source_table": table,
                "source_id": target_id,
                "action": action,
                "changed_fields": sorted(row.keys()),
                "before": None,
                "after": after,
            })

        elif action == "update":
            target_id = str(item.get("target_id", "")).strip()
            changes = item.get("changes") or {}
            before_row = before_by_id.get(target_id)
            if before_row is not None:
                before_row = dict(before_row)
            after_row = dict(before_row) if before_row else {}
            after_row.update(changes)
            events.append({
                "event_id": f"EVT-{idx:03d}",
                "source_table": table,
                "source_id": target_id,
                "action": action,
                "changed_fields": sorted(changes.keys()),
                "before": before_row,
                "after": after_row,
            })

        elif action == "soft_delete":
            target_id = str(item.get("target_id", "")).strip()
            before_row = before_by_id.get(target_id)
            if before_row is not None:
                before_row = dict(before_row)
            after_row = dict(before_row) if before_row else {}
            after_row["deleted"] = True
            events.append({
                "event_id": f"EVT-{idx:03d}",
                "source_table": table,
                "source_id": target_id,
                "action": action,
                "changed_fields": [],
                "before": before_row,
                "after": after_row,
            })

    return events


# ===================================================================
# 2. preview_live_linkage_impacts
# ===================================================================

def preview_live_linkage_impacts(before: dict, edit_patch: dict) -> dict:
    """Preview downstream impacts caused by edit events against current state.

    Returns a dict with ``document_type``, ``schema_version``, ``events``,
    ``impacts``, and ``summary``.
    """
    events = build_live_edit_events(before, edit_patch)
    impacts: list[dict] = []

    # State after applying the edit patch (for active-row lookups)
    after_state = _apply_patch_safe(before, edit_patch)

    # Build linkage map from the after state
    linkage = build_three_table_linkage_map(after_state)

    # After-state groupings
    pfmea_by_step = _group(linkage.get("pfmea_rows", []), "process_step_id")
    cp_by_step = _group(linkage.get("control_plan_rows", []), "process_step_id")
    cp_by_pfmea = _group(linkage.get("control_plan_rows", []), "pfmea_id")

    # Before-state rows (for soft_delete: find rows that existed before)
    before_pfmea_rows = _read_rows(before, "pfmea")
    before_cp_rows = _read_rows(before, "control_plan")
    before_pfmea_by_step = _group(before_pfmea_rows, "process_step_id")
    before_cp_by_step = _group(before_cp_rows, "process_step_id")
    before_cp_by_pfmea = _group(before_cp_rows, "pfmea_id")

    # After-state rows for active (non-deleted) checks
    after_pfmea_rows = _read_rows(after_state, "pfmea")
    after_cp_rows = _read_rows(after_state, "control_plan")

    for event in events:
        st = event["source_table"]
        sid = event["source_id"]
        act = event["action"]
        changed = event.get("changed_fields", [])

        if st == "process_flow":
            if act == "update":
                _pfd_update_impacts(
                    impacts, event, sid, changed,
                    pfmea_by_step, cp_by_step, cp_by_pfmea,
                )
            elif act == "soft_delete":
                _pfd_soft_delete_impacts(
                    impacts, event, sid,
                    before_pfmea_by_step, before_cp_by_step, before_cp_by_pfmea,
                    after_pfmea_rows, after_cp_rows,
                )
            elif act == "add":
                _pfd_add_impacts(impacts, event, sid, event.get("after", {}))

        elif st == "pfmea":
            if act == "update":
                _pfmea_update_impacts(
                    impacts, event, sid, changed, cp_by_pfmea,
                )
            elif act == "soft_delete":
                _pfmea_soft_delete_impacts(
                    impacts, event, sid,
                    before_cp_by_pfmea, after_cp_rows,
                )
            elif act == "add":
                _pfmea_add_impacts(impacts, event, sid, event.get("after", {}))

        # CP updates generate no upstream impacts by design

    blocker_count = sum(1 for i in impacts if i.get("severity") == "blocker")
    review_count = sum(1 for i in impacts if i.get("severity") == "review")

    return {
        "document_type": "live_linkage_preview",
        "schema_version": "minos-core.live_linkage.v1",
        "events": events,
        "impacts": impacts,
        "summary": {
            "impact_count": len(impacts),
            "blocker_count": blocker_count,
            "review_count": review_count,
        },
    }


# ===================================================================
# 3. build_live_sync_patch
# ===================================================================

def build_live_sync_patch(
    before: dict, edit_patch: dict, selected_impact_ids: list[str],
) -> dict:
    """Generate edit-patch items for user-selected impacts.

    Returns a standards-compliant edit patch dict
    (version ``minos-core.edit_patch.v1``).
    """
    preview = preview_live_linkage_impacts(before, edit_patch)
    impacts_by_id: dict[str, dict] = {
        i["impact_id"]: i for i in preview.get("impacts", [])
    }
    events_by_source = _events_by_source(preview.get("events", []))

    items: list[dict] = []
    after_state = _apply_patch_safe(before, edit_patch)

    for impact_id in selected_impact_ids:
        impact = impacts_by_id.get(impact_id)
        if not impact:
            continue
        ra = impact.get("recommended_action", "")
        src_table = impact.get("source_table", "")
        src_id = impact.get("source_id", "")

        # Find the corresponding event
        linkage_event = events_by_source.get((src_table, src_id))
        link_event_id = linkage_event["event_id"] if linkage_event else ""

        if ra == "sync_inherited_fields":
            sub_items = _build_sync_inherited_items(
                before, after_state, impact, link_event_id,
            )
            items.extend(sub_items)

        elif ra == "create_cp_stub":
            item = _build_cp_stub(impact, link_event_id, after_state)
            if item:
                items.append(item)

        elif ra == "mark_downstream_needs_review":
            item = _build_mark_review_item(before, impact, link_event_id)
            if item:
                items.append(item)

    return {
        "edit_patch_version": EDIT_PATCH_VERSION,
        "items": items,
    }


# ===================================================================
# Internal: row reading and indexing
# ===================================================================

def _read_rows(source: dict, table: str) -> list[dict]:
    chain_key = _TABLE_CHAIN_KEY.get(table, "")
    table_key = _TABLE_ROWS_KEY.get(table, "")
    rows = _cm_rows(source, table, chain_key, table_key)
    return [r for r in rows if isinstance(r, dict)]


def _index_by_id(rows: list[dict], table: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        rid = _row_id(row, table)
        if rid:
            result[rid] = row
    return result


def _row_id(row: dict, table: str) -> str:
    for f in _ID_FIELDS.get(table, ()):
        v = text(row.get(f))
        if v:
            return v
    return text(row.get("id"), row.get("process_step_id"),
                 row.get("pfmea_id"), row.get("control_plan_id"))


# ===================================================================
# Internal: patch helpers
# ===================================================================

def _patch_items(patch: dict) -> list[dict]:
    items = patch.get("items")
    if not isinstance(items, list):
        return []
    return [it for it in items if isinstance(it, dict)]


def _events_by_source(events: list[dict]) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    for ev in events:
        key = (ev.get("source_table", ""), ev.get("source_id", ""))
        result[key] = ev
    return result


# ===================================================================
# Internal: safe patch application (for after-state)
# ===================================================================

def _apply_patch_safe(before: dict, edit_patch: dict) -> dict:
    """Deep-copy *before* and apply add/update/soft_delete actions."""
    payload = copy.deepcopy(before)
    for item in _patch_items(edit_patch):
        action = item.get("action", "")
        table = item.get("table", "")
        if action in _METADATA_ACTIONS:
            continue
        if table not in _TABLE_ROWS_KEY:
            continue

        # Ensure the table container and rows key exist
        rows_key = _TABLE_ROWS_KEY[table]
        if table not in payload:
            payload[table] = {}
        if rows_key not in payload[table]:
            payload[table][rows_key] = []

        if action == "add":
            row = copy.deepcopy(item.get("row") or {})
            payload[table][rows_key].append(row)

        elif action == "update":
            target_id = str(item.get("target_id", "")).strip()
            changes = item.get("changes") or {}
            for r in payload[table][rows_key]:
                if _row_id(r, table) == target_id:
                    r.update(copy.deepcopy(changes))
                    break

        elif action == "soft_delete":
            target_id = str(item.get("target_id", "")).strip()
            for r in payload[table][rows_key]:
                if _row_id(r, table) == target_id:
                    r["deleted"] = True
                    break

    return payload


# ===================================================================
# Internal: impact construction
# ===================================================================

def _mk_impact(
    source_table: str,
    source_id: str,
    target_table: str,
    target_id: str,
    severity: str,
    recommended_action: str,
    message: str,
    requires_user_choice: bool,
) -> dict:
    if target_id:
        impact_id = (
            f"LIVE-{source_table.upper().replace('_', '')}"
            f"-{source_id}-{target_table.upper()}"
        )
    else:
        impact_id = (
            f"LIVE-{source_table.upper().replace('_', '')}"
            f"-{source_id}-{target_table.upper()}"
        )
    return {
        "impact_id": impact_id,
        "severity": severity,
        "source_table": source_table,
        "source_id": source_id,
        "target_table": target_table,
        "target_id": target_id,
        "message": message,
        "recommended_action": recommended_action,
        "requires_user_choice": requires_user_choice,
    }


# ===================================================================
# Internal: impact rule implementations
# ===================================================================

def _pfd_update_impacts(
    impacts: list[dict],
    event: dict,
    step_id: str,
    changed_fields: list[str],
    pfmea_by_step: dict[str, list[dict]],
    cp_by_step: dict[str, list[dict]],
    cp_by_pfmea: dict[str, list[dict]],
) -> None:
    inherited_hit = bool(set(changed_fields) & _PFD_INHERITED_FIELDS)
    if not inherited_hit:
        return

    # PFMEA
    for pf_row in pfmea_by_step.get(step_id, []):
        pfmea_id = text(pf_row.get("pfmea_id"))
        if pfmea_id:
            impacts.append(_mk_impact(
                "process_flow", step_id, "pfmea", pfmea_id,
                "review", "sync_inherited_fields",
                f"PFD 工序 {step_id} 的关键字段已修改，PFMEA 继承字段需要同步确认。",
                True,
            ))

    # CP (direct and indirect)
    seen_cp: set[str] = set()
    for cp_row in cp_by_step.get(step_id, []):
        cp_id = text(cp_row.get("control_plan_id"))
        if cp_id and cp_id not in seen_cp:
            seen_cp.add(cp_id)
            impacts.append(_mk_impact(
                "process_flow", step_id, "control_plan", cp_id,
                "review", "sync_inherited_fields",
                f"PFD 工序 {step_id} 的关键字段已修改，CP 继承字段需要同步确认。",
                True,
            ))
    for pf_row in pfmea_by_step.get(step_id, []):
        pfmea_id = text(pf_row.get("pfmea_id"))
        for cp_row in cp_by_pfmea.get(pfmea_id, []):
            cp_id = text(cp_row.get("control_plan_id"))
            if cp_id and cp_id not in seen_cp:
                seen_cp.add(cp_id)
                impacts.append(_mk_impact(
                    "process_flow", step_id, "control_plan", cp_id,
                    "review", "sync_inherited_fields",
                    f"PFD 工序 {step_id} 的关键字段已修改，PFMEA {pfmea_id} 关联 CP {cp_id} 需同步确认。",
                    True,
                ))


def _pfd_soft_delete_impacts(
    impacts: list[dict],
    event: dict,
    step_id: str,
    before_pfmea_by_step: dict[str, list[dict]],
    before_cp_by_step: dict[str, list[dict]],
    before_cp_by_pfmea: dict[str, list[dict]],
    after_pfmea_rows: list[dict],
    after_cp_rows: list[dict],
) -> None:
    # Active downstream rows in the after state
    active_pfmea_ids = {
        text(r.get("pfmea_id"))
        for r in after_pfmea_rows
        if text(r.get("process_step_id")) == step_id and not r.get("deleted")
    }
    active_cp_ids = {
        text(r.get("control_plan_id"))
        for r in after_cp_rows
        if text(r.get("process_step_id")) == step_id and not r.get("deleted")
    }
    has_any_active = bool(active_pfmea_ids or active_cp_ids)
    severity = "blocker" if has_any_active else "review"
    ra = "mark_downstream_needs_review" if has_any_active else "mark_downstream_needs_review"

    for pf_row in before_pfmea_by_step.get(step_id, []):
        pfmea_id = text(pf_row.get("pfmea_id"))
        if pfmea_id:
            impacts.append(_mk_impact(
                "process_flow", step_id, "pfmea", pfmea_id,
                severity, ra,
                f"PFD 工序 {step_id} 已删除，关联 PFMEA {pfmea_id} 需处理。",
                True,
            ))

    seen_cp: set[str] = set()
    for cp_row in before_cp_by_step.get(step_id, []):
        cp_id = text(cp_row.get("control_plan_id"))
        if cp_id and cp_id not in seen_cp:
            seen_cp.add(cp_id)
            impacts.append(_mk_impact(
                "process_flow", step_id, "control_plan", cp_id,
                severity, ra,
                f"PFD 工序 {step_id} 已删除，关联 CP {cp_id} 需处理。",
                True,
            ))

    # Also via PFMEA -> CP
    for pf_row in before_pfmea_by_step.get(step_id, []):
        pfmea_id = text(pf_row.get("pfmea_id"))
        for cp_row in before_cp_by_pfmea.get(pfmea_id, []):
            cp_id = text(cp_row.get("control_plan_id"))
            if cp_id and cp_id not in seen_cp:
                seen_cp.add(cp_id)
                impacts.append(_mk_impact(
                    "process_flow", step_id, "control_plan", cp_id,
                    severity, ra,
                    f"PFD 工序 {step_id} 已删除，关联 CP {cp_id} 需处理。",
                    True,
                ))


def _pfd_add_impacts(
    impacts: list[dict], event: dict, step_id: str, after: dict,
) -> None:
    impacts.append(_mk_impact(
        "process_flow", step_id, "pfmea", "",
        "review", "regenerate_pfmea_from_confirmed_pfd",
        f"PFD 新增工序 {step_id}，需要基于确认后的 PFD 重新推理 PFMEA。",
        True,
    ))

    sc = after.get("special_characteristics", [])
    if isinstance(sc, (list, tuple)):
        sc_list = [s for s in sc if str(s).strip()]
    elif sc and str(sc).strip():
        sc_list = [str(sc).strip()]
    else:
        sc_list = []

    if sc_list:
        impacts.append(_mk_impact(
            "process_flow", step_id, "control_plan", "",
            "review", "create_cp_stub",
            f"PFD 新增工序 {step_id} 含特殊特性 {', '.join(sc_list)}，建议新增 CP 控制项。",
            True,
        ))


def _pfmea_update_impacts(
    impacts: list[dict],
    event: dict,
    pfmea_id_s: str,
    changed_fields: list[str],
    cp_by_pfmea: dict[str, list[dict]],
) -> None:
    if not set(changed_fields) & _PFMEA_CP_RELEVANT_FIELDS:
        return
    for cp_row in cp_by_pfmea.get(pfmea_id_s, []):
        cp_id = text(cp_row.get("control_plan_id"))
        if cp_id:
            impacts.append(_mk_impact(
                "pfmea", pfmea_id_s, "control_plan", cp_id,
                "review", "sync_inherited_fields",
                f"PFMEA {pfmea_id_s} 关键字段已修改，CP {cp_id} 需同步确认。",
                True,
            ))


def _pfmea_soft_delete_impacts(
    impacts: list[dict],
    event: dict,
    pfmea_id_s: str,
    before_cp_by_pfmea: dict[str, list[dict]],
    after_cp_rows: list[dict],
) -> None:
    active_cp_ids = {
        text(r.get("control_plan_id"))
        for r in after_cp_rows
        if text(r.get("pfmea_id")) == pfmea_id_s and not r.get("deleted")
    }
    severity = "blocker" if active_cp_ids else "review"

    for cp_row in before_cp_by_pfmea.get(pfmea_id_s, []):
        cp_id = text(cp_row.get("control_plan_id"))
        if cp_id:
            impacts.append(_mk_impact(
                "pfmea", pfmea_id_s, "control_plan", cp_id,
                severity, "mark_downstream_needs_review",
                f"PFMEA {pfmea_id_s} 已删除，关联 CP {cp_id} 需处理。",
                True,
            ))


def _pfmea_add_impacts(
    impacts: list[dict], event: dict, pfmea_id_s: str, after: dict,
) -> None:
    ap = text(after.get("action_priority"), after.get("AP")).upper()
    sev = _int_val(after.get("severity"), after.get("S"))
    if ap == "H" or sev >= 9:
        impacts.append(_mk_impact(
            "pfmea", pfmea_id_s, "control_plan", "",
            "review", "create_cp_stub",
            f"PFMEA 新增高 AP / 高严重度行 {pfmea_id_s} (AP={ap}, Sev={sev})，建议新增 CP 控制项。",
            True,
        ))


# ===================================================================
# Internal: sync patch item builders
# ===================================================================

_LINKAGE_META = {
    "source": "live_linkage",
    "sync_policy": "user_selected",
}


def _build_sync_inherited_items(
    before: dict,
    after_state: dict,
    impact: dict,
    link_event_id: str,
) -> list[dict]:
    """Generate update items for inherited-field sync (PFD->PFMEA or PFD->CP)."""
    items: list[dict] = []
    target_table = impact.get("target_table", "")
    target_id = impact.get("target_id", "")
    source_id = impact.get("source_id", "")

    if not target_id:
        return items  # Cannot sync without a target row ID

    target_rows = _read_rows(after_state, target_table)
    target_row = None
    for r in target_rows:
        if _row_id(r, target_table) == target_id:
            target_row = r
            break
    if target_row is None:
        return items

    source_rows = _read_rows(after_state, "process_flow")
    source_row = None
    for r in source_rows:
        if _row_id(r, "process_flow") == source_id:
            source_row = r
            break
    if source_row is None:
        return items

    if target_table == "pfmea":
        sync_fields = _PFD_TO_PFMEA_SYNC_FIELDS
        # Map PFD fields to PFMEA field names
        field_map = {
            "operation": "operation",
            "process_function": "process_function",
            "product_characteristics": "product_characteristics",
            "process_characteristics": "process_characteristics",
            "special_characteristics": "special_characteristics",
            "characteristic_refs": "characteristic_refs",
        }
    elif target_table == "control_plan":
        sync_fields = _PFD_TO_CP_SYNC_FIELDS
        field_map = {
            "product_process_characteristic": "product_process_characteristic",
            "classification": "classification",
            "source_special_characteristics": "source_special_characteristics",
        }
    else:
        return items

    changes: dict[str, Any] = {}
    for pf in sync_fields:
        mapped = field_map.get(pf, pf)
        # Only overwrite if target field is empty/falsy AND source has a value
        target_val = target_row.get(mapped)
        source_val = source_row.get(pf)
        if _is_empty(target_val) and not _is_empty(source_val):
            changes[mapped] = source_val

    if not changes:
        return items

    items.append({
        "action": "update",
        "table": target_table,
        "target_id": target_id,
        "changes": changes,
        "needs_confirmation": True,
        "review_status": "联动同步",
        "source": "live_linkage",
        "linkage_event_id": link_event_id,
        "linkage_impact_id": impact.get("impact_id", ""),
        "sync_policy": "user_selected",
    })
    return items


def _build_cp_stub(
    impact: dict, link_event_id: str, after_state: dict,
) -> dict | None:
    """Generate a CP add item from a create_cp_stub recommendation."""
    source_table = impact.get("source_table", "")
    source_id = impact.get("source_id", "")
    target_table = impact.get("target_table", "")

    if source_table == "process_flow":
        step_id = source_id
        pfmea_id = ""  # Unknown; will be linked later
        # Inherit characteristics from PFD
        pfd_rows = _read_rows(after_state, "process_flow")
        pfd_row = {}
        for r in pfd_rows:
            if _row_id(r, "process_flow") == step_id:
                pfd_row = r
                break
        characteristic = text(
            pfd_row.get("product_characteristics", ""),
            pfd_row.get("process_function", ""),
        )
        classification = text(pfd_row.get("classification", ""))
        special_chars = pfd_row.get("special_characteristics", [])
        if not isinstance(special_chars, list):
            special_chars = [special_chars] if special_chars else []
    elif source_table == "pfmea":
        step_id = ""
        pfmea_id = source_id
        # Find the step_id from PFMEA row
        pfmea_rows = _read_rows(after_state, "pfmea")
        for r in pfmea_rows:
            if _row_id(r, "pfmea") == pfmea_id:
                step_id = text(r.get("process_step_id"))
                break
        characteristic = "待确认"
        classification = ""
        special_chars = []
    else:
        return None

    cp_id = f"CP-{source_id}-001"
    return {
        "action": "add",
        "table": "control_plan",
        "row": {
            "control_plan_id": cp_id,
            "pfmea_id": pfmea_id,
            "process_step_id": step_id,
            "product_process_characteristic": characteristic,
            "specification": "待确认",
            "classification": classification,
            "measurement_method": "待确认测量方法",
            "sample_size": "5",
            "sample_frequency": "首件和巡检",
            "control_method": "",
            "reaction_plan": "隔离并通知质量工程师",
            "source_special_characteristics": special_chars,
            "ai_inferred": False,
            "needs_confirmation": True,
            "review_status": "联动新增",
        },
        "needs_confirmation": True,
        "review_status": "联动新增",
        "source": "live_linkage",
        "linkage_event_id": link_event_id,
        "linkage_impact_id": impact.get("impact_id", ""),
        "sync_policy": "user_selected",
    }


def _build_mark_review_item(
    before: dict, impact: dict, link_event_id: str,
) -> dict | None:
    """Set review_status on a downstream row to mark it needs review."""
    target_table = impact.get("target_table", "")
    target_id = impact.get("target_id", "")
    if not target_id:
        return None

    return {
        "action": "update",
        "table": target_table,
        "target_id": target_id,
        "changes": {"review_status": "待同步确认"},
        "needs_confirmation": True,
        "source": "live_linkage",
        "linkage_event_id": link_event_id,
        "linkage_impact_id": impact.get("impact_id", ""),
        "sync_policy": "user_selected",
    }


# ===================================================================
# Internal: utility helpers
# ===================================================================

def _int_val(*values: Any) -> int:
    for v in values:
        if v is None:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return 0


def _is_empty(value: Any) -> bool:
    """Check if a value is empty/falsy (None, empty str, empty list, 0)."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0
    if isinstance(value, (int, float)):
        return value == 0
    return False
