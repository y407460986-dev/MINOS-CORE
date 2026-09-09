"""Change impact analysis for PFD/PFMEA/CP three-table edits."""

from __future__ import annotations

from typing import Any

from minos_core._text_utils import text


def field_diff(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    keys = sorted(set(before) | set(after))
    return [
        {"field": key, "before": before.get(key, ""), "after": after.get(key, "")}
        for key in keys
        if before.get(key, "") != after.get(key, "")
    ]


def analyze_change_impacts(source: dict[str, Any]) -> list[dict[str, str]]:
    process_rows = _rows(source, "process_flow", "process_steps", "steps")
    pfmea_rows = _rows(source, "pfmea", "failure_modes", "rows")
    cp_rows = _rows(source, "control_plan", "controls", "rows")
    pfmea_by_step = _group(pfmea_rows, "process_step_id")
    cp_by_step = _group(cp_rows, "process_step_id")
    cp_by_pfmea = _group(cp_rows, "pfmea_id")
    impacts: list[dict[str, str]] = []

    for step in process_rows:
        if not isinstance(step, dict):
            continue
        step_id = text(step.get("process_step_id"))
        status = text(step.get("change_impact_status"))
        if step.get("deleted"):
            linked_pfmea_ids = {
                text(row.get("pfmea_id")) for row in pfmea_by_step.get(step_id, []) if text(row.get("pfmea_id"))
            }
            if pfmea_by_step.get(step_id):
                impacts.append(
                    _impact(
                        "PFD 删除工序",
                        f"process_flow:{step_id}",
                        "PFMEA 关联风险需处理",
                        status or "待人工确认",
                    )
                )
            if cp_by_step.get(step_id) or any(cp_by_pfmea.get(pfmea_id) for pfmea_id in linked_pfmea_ids):
                impacts.append(
                    _impact(
                        "PFD 删除工序",
                        f"process_flow:{step_id}",
                        "CP 关联控制项需处理",
                        status or "待人工确认",
                    )
                )
            continue
        if step.get("review_status") == "人工新增" or step.get("change_type") == "pfd_added":
            if not pfmea_by_step.get(step_id):
                impacts.append(_impact("PFD 新增工序", f"process_flow:{step_id}", "PFMEA 需补风险", status))
            if not cp_by_step.get(step_id):
                impacts.append(_impact("PFD 新增工序", f"process_flow:{step_id}", "CP 需补控制", status))
        if step.get("review_status") == "人工修改" or _changed_any(
            step,
            (
                "operation",
                "process_function",
                "product_characteristics",
                "process_characteristics",
                "special_characteristics",
            ),
        ):
            impacts.append(
                _impact(
                    "PFD 关键字段修改", f"process_flow:{step_id}", "PFMEA 继承字段需同步确认", status or "待人工确认"
                )
            )

    for row in pfmea_rows:
        if not isinstance(row, dict) or row.get("deleted"):
            continue
        pfmea_id = text(row.get("pfmea_id"))
        ap = text(row.get("action_priority"), row.get("AP")).upper()
        status = text(row.get("change_impact_status"))
        if ap == "H" and not cp_by_pfmea.get(pfmea_id):
            impacts.append(_impact("PFMEA 高 AP", f"pfmea:{pfmea_id}", "CP 必须新增控制", status))
        if row.get("review_status") == "人工修改" and _changed_any(
            row, ("prevention_control", "detection_control", "classification", "action_priority")
        ):
            impacts.append(
                _impact("PFMEA 控制/特性修改", f"pfmea:{pfmea_id}", "CP 控制方法需同步确认", status or "待人工确认")
            )

    active_pfmea_ids = {
        text(row.get("pfmea_id")) for row in pfmea_rows if isinstance(row, dict) and not row.get("deleted")
    }
    for control in cp_rows:
        if not isinstance(control, dict):
            continue
        cp_id = text(control.get("control_plan_id"))
        pfmea_id = text(control.get("pfmea_id"))
        status = text(control.get("change_impact_status"))
        if control.get("deleted") and pfmea_id in active_pfmea_ids:
            impacts.append(_impact("CP 删除控制项", f"control_plan:{cp_id}", "检查是否留下未控制高风险", status))
        if control.get("deleted"):
            continue
        if control.get("review_status") == "人工新增":
            impacts.append(
                _impact("CP 新增控制项", f"control_plan:{cp_id}", "PFMEA 需确认控制覆盖", status or "待人工确认")
            )
        if control.get("review_status") == "人工修改" and _changed_any(
            control, ("measurement_method", "sample_size", "sample_frequency", "control_method", "specification")
        ):
            impacts.append(
                _impact(
                    "CP 控制方法字段修改",
                    f"control_plan:{cp_id}",
                    "测量/控制方法变更需质量确认",
                    status or "待人工确认",
                )
            )
        if _changed_any(control, ("classification", "product_process_characteristic", "specification")):
            impacts.append(
                _impact("CP 特性/规范修改", f"control_plan:{cp_id}", "PFMEA 特性分类需同步确认", status or "待人工确认")
            )
    return impacts


def blocking_change_impacts(impacts: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        impact
        for impact in impacts
        if impact.get("status") not in {"已处理", "无影响"}
        and not (impact.get("status") == "已忽略" and impact.get("ignore_reason"))
    ]


def _rows(source: dict[str, Any], table: str, chain_key: str, table_key: str) -> list[Any]:
    if table in source and isinstance(source.get(table), dict):
        rows = source[table].get(table_key)
        if isinstance(rows, list):
            return rows
    rows = source.get(chain_key)
    return rows if isinstance(rows, list) else []


def _group(rows: list[Any], key: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if isinstance(row, dict) and not row.get("deleted"):
            result.setdefault(text(row.get(key)), []).append(row)
    return result


def _impact(kind: str, target: str, message: str, status: str) -> dict[str, str]:
    return {
        "item_id": f"{target}.{kind}.{message}",
        "category": "变更影响",
        "target": target,
        "message": message,
        "status": status or "待同步",
        "ignore_reason": "",
        "severity": "blocker",
    }


def _changed_any(row: dict[str, Any], fields: tuple[str, ...]) -> bool:
    changes = row.get("changed_fields")
    if isinstance(changes, list):
        return any(field in changes for field in fields)
    return False


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------

# Key fields used to detect meaningful modifications in each table.
_PFD_KEY_FIELDS = (
    "operation",
    "process_function",
    "product_characteristics",
    "process_characteristics",
    "special_characteristics",
    "equipment",
    "tooling",
    "gauges",
)

_PFMEA_KEY_FIELDS = (
    "failure_mode",
    "failure_effect",
    "severity",
    "failure_cause",
    "cause_process_parameter",
    "occurrence",
    "prevention_control",
    "prevention_control_target",
    "prevention_control_timing",
    "detection_control",
    "detection_control_target",
    "detection_control_timing",
    "detection",
    "action_priority",
    "control_logic_review",
    "recommended_action",
    "characteristic_refs",
)

_CP_KEY_FIELDS = (
    "product_process_characteristic",
    "specification",
    "measurement_method",
    "sample_size",
    "sample_frequency",
    "control_method",
    "process_parameter",
    "parameter_specification",
    "process_control_method",
    "setup_verification",
    "poka_yoke_device",
    "poka_yoke_verification",
    "process_record",
    "reaction_plan",
)

_TABLE_CONFIG: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("process_flow", "process_steps", "steps", "process_step_id", _PFD_KEY_FIELDS),
    ("pfmea", "failure_modes", "rows", "pfmea_id", _PFMEA_KEY_FIELDS),
    ("control_plan", "controls", "rows", "control_plan_id", _CP_KEY_FIELDS),
)

_SUMMARY_PREFIX: dict[str, str] = {
    "process_flow": "pfd",
    "pfmea": "pfmea",
    "control_plan": "cp",
}


def compare_three_table_baseline(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Compare two three-table payloads and return a structured diff.

    Returns a dictionary with ``document_type``, ``schema_version``,
    per-table ``changes`` (added / deleted / modified), and a numeric
    ``summary``.
    """
    changes: dict[str, dict[str, list[dict[str, Any]]]] = {}
    summary: dict[str, int] = {}

    for table_name, chain_key, table_key, id_field, key_fields in _TABLE_CONFIG:
        before_rows = _rows(before, table_name, chain_key, table_key)
        after_rows = _rows(after, table_name, chain_key, table_key)

        before_by_id, after_by_id = _index_rows(before_rows, after_rows, id_field)

        added: list[dict[str, Any]] = []
        deleted: list[dict[str, Any]] = []
        modified: list[dict[str, Any]] = []

        for rid, after_row in after_by_id.items():
            if after_row.get("deleted"):
                # Soft-deleted in *after* → only count as deletion when it
                # existed in *before*.
                if rid in before_by_id:
                    deleted.append(
                        _change_item(
                            rid,
                            "deleted",
                            table_name,
                            [],
                            before_snapshot=before_by_id[rid],
                            after_snapshot=after_row,
                        )
                    )
                continue

            if rid not in before_by_id:
                added.append(
                    _change_item(
                        rid,
                        "added",
                        table_name,
                        [],
                        after_snapshot=after_row,
                    )
                )
            else:
                before_row = before_by_id[rid]
                before_sub = {k: before_row.get(k, "") for k in key_fields}
                after_sub = {k: after_row.get(k, "") for k in key_fields}
                diffs = field_diff(before_sub, after_sub)
                if diffs:
                    modified.append(
                        _change_item(
                            rid,
                            "modified",
                            table_name,
                            diffs,
                            before_snapshot=before_row,
                            after_snapshot=after_row,
                        )
                    )

        # Deleted: exists in *before* but not in *after* at all.
        for rid, before_row in before_by_id.items():
            if rid not in after_by_id:
                deleted.append(
                    _change_item(
                        rid,
                        "deleted",
                        table_name,
                        [],
                        before_snapshot=before_row,
                    )
                )

        changes[table_name] = {
            "added": added,
            "deleted": deleted,
            "modified": modified,
        }

        prefix = _SUMMARY_PREFIX[table_name]
        summary[f"{prefix}_added"] = len(added)
        summary[f"{prefix}_deleted"] = len(deleted)
        summary[f"{prefix}_modified"] = len(modified)

    return {
        "document_type": "three_table_baseline_comparison",
        "schema_version": "minos-core.baseline_compare.v1",
        "changes": changes,
        "summary": summary,
    }


def analyze_linked_change_impacts(
    source: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Analyze change impacts based on the three-table linkage map.

    When *baseline* is ``None`` the behaviour is identical to
    :func:`analyze_change_impacts`.

    When *baseline* is provided the function first computes a structured
    A/B diff via :func:`compare_three_table_baseline`, then uses
    :func:`~minos_core.three_table_linkage.build_three_table_linkage_map`
    to infer downstream impacts on linked rows.
    """
    if baseline is None:
        return analyze_change_impacts(source)

    comparison = compare_three_table_baseline(baseline, source)

    # Build linkage maps from both *source* (after) and *baseline*.
    # The after map is used for added / modified items; the baseline map
    # is used for deleted items whose rows have already been removed from
    # the after payload.
    from .three_table_linkage import build_three_table_linkage_map  # noqa: E402

    after_linkage = build_three_table_linkage_map(source)
    baseline_linkage = build_three_table_linkage_map(baseline)

    def _build_lookups(
        links: list[dict[str, Any]],
    ) -> tuple[
        dict[str, set[str]],
        dict[str, set[str]],
        dict[str, set[str]],
        dict[str, str],
    ]:
        step_to_pf: dict[str, set[str]] = {}
        pf_to_cp: dict[str, set[str]] = {}
        st_to_cp: dict[str, set[str]] = {}
        cp_to_pf: dict[str, str] = {}
        for link in links:
            lt = link.get("link_type", "")
            if lt == "pfd_to_pfmea":
                step_to_pf.setdefault(link["from_id"], set()).add(link["to_id"])
            elif lt == "pfmea_to_control_plan":
                pf_to_cp.setdefault(link["from_id"], set()).add(link["to_id"])
                cp_to_pf[link["to_id"]] = link["from_id"]
        for sid, pf_ids in step_to_pf.items():
            for pid in pf_ids:
                for cid in pf_to_cp.get(pid, ()):
                    st_to_cp.setdefault(sid, set()).add(cid)
        return step_to_pf, pf_to_cp, st_to_cp, cp_to_pf

    after_stp, after_ptc, after_stc, after_ctp = _build_lookups(after_linkage.get("links", []))
    base_stp, base_ptc, base_stc, base_ctp = _build_lookups(baseline_linkage.get("links", []))

    impacts: list[dict[str, Any]] = []
    changes = comparison.get("changes", {})

    # --- PFD changes ---
    pfd_changes = changes.get("process_flow", {})

    # PFD added -> PFMEA 需新增风险, CP 需新增控制
    for item in pfd_changes.get("added", []):
        sid = item["id"]
        impacts.append(
            _linked_impact(
                "PFD 新增工序",
                "process_flow",
                sid,
                "pfmea",
                "",
                f"PFD 新增工序 {sid}，PFMEA 需新增风险分析",
                "blocker",
            )
        )
        impacts.append(
            _linked_impact(
                "PFD 新增工序",
                "process_flow",
                sid,
                "control_plan",
                "",
                f"PFD 新增工序 {sid}，CP 需新增控制项",
                "blocker",
            )
        )

    # PFD deleted -> use *baseline* linkage map (the rows are gone from after)
    for item in pfd_changes.get("deleted", []):
        sid = item["id"]
        for pfmea_id in sorted(base_stp.get(sid, set())):
            impacts.append(
                _linked_impact(
                    "PFD 删除工序",
                    "process_flow",
                    sid,
                    "pfmea",
                    pfmea_id,
                    f"PFD 工序 {sid} 已删除，关联 PFMEA 行 {pfmea_id} 需处理",
                    "blocker",
                )
            )
        for cp_id in sorted(base_stc.get(sid, set())):
            impacts.append(
                _linked_impact(
                    "PFD 删除工序",
                    "process_flow",
                    sid,
                    "control_plan",
                    cp_id,
                    f"PFD 工序 {sid} 已删除，关联 CP 行 {cp_id} 需处理",
                    "blocker",
                )
            )

    # PFD key-fields modified -> use *after* linkage map
    for item in pfd_changes.get("modified", []):
        sid = item["id"]
        diff_fields = {d["field"] for d in item.get("field_diffs", [])}
        if diff_fields & set(_PFD_KEY_FIELDS):
            for pfmea_id in sorted(after_stp.get(sid, set())):
                impacts.append(
                    _linked_impact(
                        "PFD 关键字段修改",
                        "process_flow",
                        sid,
                        "pfmea",
                        pfmea_id,
                        f"PFD 工序 {sid} 关键字段变更，关联 PFMEA 行 {pfmea_id} 过程项/功能/失效模式需复核",
                        "warning",
                    )
                )

    # --- PFMEA changes ---
    pfmea_changes = changes.get("pfmea", {})

    # PFMEA added -> use *after* linkage map
    for item in pfmea_changes.get("added", []):
        pfmea_id = item["id"]
        for cp_id in sorted(after_ptc.get(pfmea_id, set())):
            impacts.append(
                _linked_impact(
                    "PFMEA 新增风险行",
                    "pfmea",
                    pfmea_id,
                    "control_plan",
                    cp_id,
                    f"PFMEA 新增风险行 {pfmea_id}，关联 CP 行 {cp_id} 控制覆盖需确认",
                    "warning",
                )
            )

    # PFMEA deleted -> use *baseline* linkage map
    for item in pfmea_changes.get("deleted", []):
        pfmea_id = item["id"]
        for cp_id in sorted(base_ptc.get(pfmea_id, set())):
            impacts.append(
                _linked_impact(
                    "PFMEA 删除风险行",
                    "pfmea",
                    pfmea_id,
                    "control_plan",
                    cp_id,
                    f"PFMEA 风险行 {pfmea_id} 已删除，关联 CP 行 {cp_id} 需处理",
                    "blocker",
                )
            )

    # PFMEA key-fields modified -> use *after* linkage map
    for item in pfmea_changes.get("modified", []):
        pfmea_id = item["id"]
        diff_fields = {d["field"] for d in item.get("field_diffs", [])}
        if diff_fields & set(_PFMEA_KEY_FIELDS):
            for cp_id in sorted(after_ptc.get(pfmea_id, set())):
                impacts.append(
                    _linked_impact(
                        "PFMEA 关键字段修改",
                        "pfmea",
                        pfmea_id,
                        "control_plan",
                        cp_id,
                        f"PFMEA 行 {pfmea_id} 关键字段变更，关联 CP 行 {cp_id} 控制方法是否仍匹配需复核",
                        "warning",
                    )
                )

    # --- CP changes ---
    cp_changes = changes.get("control_plan", {})

    # CP added -> use *after* linkage map
    for item in cp_changes.get("added", []):
        cp_id = item["id"]
        pfmea_id = after_ctp.get(cp_id, "")
        if pfmea_id:
            impacts.append(
                _linked_impact(
                    "CP 新增控制项",
                    "control_plan",
                    cp_id,
                    "pfmea",
                    pfmea_id,
                    f"CP 新增控制项 {cp_id}，关联 PFMEA 行 {pfmea_id} 需确认控制覆盖",
                    "warning",
                )
            )

    # CP deleted -> use *baseline* linkage map
    for item in cp_changes.get("deleted", []):
        cp_id = item["id"]
        pfmea_id = base_ctp.get(cp_id, "")
        if pfmea_id:
            impacts.append(
                _linked_impact(
                    "CP 删除控制项",
                    "control_plan",
                    cp_id,
                    "pfmea",
                    pfmea_id,
                    f"CP 控制项 {cp_id} 已删除，关联 PFMEA 行 {pfmea_id} 需检查是否留下未控制高风险",
                    "blocker",
                )
            )

    # CP key-fields modified -> PFMEA 预防/探测控制需复核
    for item in cp_changes.get("modified", []):
        cp_id = item["id"]
        diff_fields = {d["field"] for d in item.get("field_diffs", [])}
        if diff_fields & set(_CP_KEY_FIELDS):
            # Try after map first, fall back to baseline map
            pfmea_id = after_ctp.get(cp_id, "") or base_ctp.get(cp_id, "")
            if pfmea_id:
                impacts.append(
                    _linked_impact(
                        "CP 关键字段修改",
                        "control_plan",
                        cp_id,
                        "pfmea",
                        pfmea_id,
                        f"CP 行 {cp_id} 关键字段变更，关联 PFMEA 行 {pfmea_id} 预防/探测控制需复核",
                        "review",
                    )
                )

    return impacts


# ---------------------------------------------------------------------------
# Internal helpers (shared)
# ---------------------------------------------------------------------------


def _index_rows(
    before_rows: list[Any],
    after_rows: list[Any],
    id_field: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Index row lists by *id_field*, returning (before_map, after_map)."""
    before_map: dict[str, dict[str, Any]] = {}
    after_map: dict[str, dict[str, Any]] = {}

    for row in before_rows:
        if isinstance(row, dict):
            rid = text(row.get(id_field))
            if rid:
                before_map[rid] = row

    for row in after_rows:
        if isinstance(row, dict):
            rid = text(row.get(id_field))
            if rid:
                after_map[rid] = row

    return before_map, after_map


def _change_item(
    rid: str,
    change_type: str,
    table: str,
    field_diffs: list[dict[str, Any]],
    *,
    before_snapshot: dict[str, Any] | None = None,
    after_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a single change-item dict for :func:`compare_three_table_baseline`."""
    item: dict[str, Any] = {
        "id": rid,
        "type": change_type,
        "table": table,
        "field_diffs": field_diffs,
    }
    if before_snapshot is not None:
        item["before_snapshot"] = before_snapshot
    if after_snapshot is not None:
        item["after_snapshot"] = after_snapshot
    return item


def _linked_impact(
    kind: str,
    source_table: str,
    source_id: str,
    target_table: str,
    target_id: str,
    message: str,
    severity: str,
) -> dict[str, Any]:
    """Build an impact dict for :func:`analyze_linked_change_impacts`."""
    return {
        "item_id": f"{source_table}:{source_id}.{target_table}:{target_id}.{kind}",
        "category": "变更影响",
        "source_table": source_table,
        "source_id": source_id,
        "target_table": target_table,
        "target_id": target_id,
        "message": message,
        "severity": severity,
        "status": "待人工确认",
        "ignore_reason": "",
        "evidence_refs": [],
    }
