"""Three-table linkage analysis for PFD/PFMEA/CP unified traceability.

Provides a unified linkage map, gap detection, and quality evaluation for the
three core APQP tables: Process Flow Diagram (PFD), PFMEA, and Control Plan (CP).
"""

from __future__ import annotations

from typing import Any

from minos_core._text_utils import text

from .change_management import _group, _rows
from .domain import EntityType, TraceLinkType
from .three_table_linkage_reports import (
    build_sync_issues as _build_sync_issues,
)
from .three_table_linkage_reports import (
    build_sync_snapshot as _build_sync_snapshot,
)
from .three_table_linkage_reports import (
    build_sync_suggestions as _build_sync_suggestions,
)


def build_three_table_linkage_map(source: dict[str, Any]) -> dict[str, Any]:
    """Build a unified linkage map from a three-table payload.

    Reads process_flow, pfmea, and control_plan tables from *source* and
    produces a structured linkage map that includes all rows, generated links,
    detected gaps, and a numeric summary.

    The input *source* is never modified.
    """
    process_steps = _rows(source, "process_flow", "process_steps", "steps")
    pfmea_rows = _rows(source, "pfmea", "failure_modes", "rows")
    control_plan_rows = _rows(source, "control_plan", "controls", "rows")

    active_steps = [
        step for step in process_steps
        if isinstance(step, dict) and not step.get("deleted")
    ]
    active_pfmea = [
        row for row in pfmea_rows
        if isinstance(row, dict) and not row.get("deleted")
    ]
    active_cp = [
        row for row in control_plan_rows
        if isinstance(row, dict) and not row.get("deleted")
    ]

    step_by_id, step_ids = _index_steps(active_steps)
    pfmea_by_id, pfmea_ids = _index_pfmea(active_pfmea)
    pfmea_by_step = _group(active_pfmea, "process_step_id")
    cp_by_pfmea = _group(active_cp, "pfmea_id")
    cp_by_step = _group(active_cp, "process_step_id")

    characteristics = _collect_characteristics(active_steps, active_pfmea, active_cp)

    links = _build_links(
        active_steps, active_pfmea, active_cp,
        step_by_id, pfmea_by_id, pfmea_by_step, cp_by_pfmea,
    )

    gaps = _build_gaps(
        active_steps, active_pfmea, active_cp,
        step_ids, step_by_id, pfmea_by_id, pfmea_by_step, cp_by_pfmea, cp_by_step,
    )

    # Count gap categories for the summary
    uncovered_steps = sum(
        1 for g in gaps if g.get("category_key") == "pfd_pfmea_coverage"
    )
    uncontrolled_pfmea = sum(
        1 for g in gaps if g.get("category_key") == "pfmea_cp_coverage"
    )
    orphan_cp = sum(
        1 for g in gaps if g.get("category_key") in ("orphan_cp", "orphan_cp_step")
    )
    special_char_gaps = sum(
        1 for g in gaps
        if g.get("category_key") in ("special_char_step", "special_char_pfmea", "special_char_cp")
    )

    return {
        "document_type": "three_table_linkage_map",
        "schema_version": "minos-core.three_table_linkage.v1",
        "process_steps": active_steps,
        "pfmea_rows": active_pfmea,
        "control_plan_rows": active_cp,
        "characteristics": characteristics,
        "links": links,
        "gaps": gaps,
        "summary": {
            "process_step_count": len(active_steps),
            "pfmea_row_count": len(active_pfmea),
            "control_plan_row_count": len(active_cp),
            "uncovered_process_steps": uncovered_steps,
            "uncontrolled_pfmea_rows": uncontrolled_pfmea,
            "orphan_control_items": orphan_cp,
            "special_characteristic_gaps": special_char_gaps,
        },
    }


def evaluate_three_table_linkage(source: dict[str, Any]) -> dict[str, Any]:
    """Evaluate three-table linkage quality and return a linkage report.

    The report wraps the full linkage map and adds a top-level ``ok`` flag
    and a ``needs_review`` flag for downstream quality gates.
    """
    linkage_map = build_three_table_linkage_map(source)
    gaps = linkage_map.get("gaps", [])
    blocker_count = sum(1 for g in gaps if g.get("severity") == "blocker")
    return {
        "document_type": "three_table_linkage_report",
        "schema_version": "minos-core.three_table_linkage.v1",
        "ok": blocker_count == 0,
        "needs_review": len(gaps) > 0,
        "linkage_map": linkage_map,
        "blocker_count": blocker_count,
        "total_gap_count": len(gaps),
        "sync_snapshot": _build_sync_snapshot(linkage_map),
        "sync_issues": _build_sync_issues(linkage_map),
        "sync_suggestions": _build_sync_suggestions(linkage_map),
    }


def find_linkage_gaps(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Find all linkage gaps across the three tables.

    Returns a flat list of gap dicts. This is a convenience wrapper that
    delegates to :func:`build_three_table_linkage_map` and returns only the
    ``gaps`` list.
    """
    linkage_map = build_three_table_linkage_map(source)
    return list(linkage_map.get("gaps", []))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _index_steps(
    active_steps: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    step_by_id: dict[str, dict[str, Any]] = {}
    step_ids: set[str] = set()
    for step in active_steps:
        sid = text(
            step.get("process_step_id"), step.get("id"), step.get("step_no"),
        )
        if sid:
            step_ids.add(sid)
            step_by_id[sid] = step
    return step_by_id, step_ids


def _index_pfmea(
    active_pfmea: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    pfmea_by_id: dict[str, dict[str, Any]] = {}
    pfmea_ids: set[str] = set()
    for row in active_pfmea:
        pid = text(row.get("pfmea_id"), row.get("id"))
        if pid:
            pfmea_ids.add(pid)
            pfmea_by_id[pid] = row
    return pfmea_by_id, pfmea_ids


def _collect_characteristics(
    active_steps: list[dict[str, Any]],
    active_pfmea: list[dict[str, Any]],
    active_cp: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    characteristics: list[dict[str, Any]] = []
    seen: set[str] = set()

    for step in active_steps:
        step_id = text(step.get("process_step_id"))
        for ref in _list_str(step.get("characteristic_refs", [])):
            if ref and ref not in seen:
                seen.add(ref)
                characteristics.append(
                    {"characteristic_id": ref, "name": ref, "source": f"process_flow:{step_id}"}
                )
        for ref in _list_str(step.get("special_characteristics", [])):
            if ref and ref not in seen:
                seen.add(ref)
                characteristics.append(
                    {"characteristic_id": ref, "name": ref, "source": f"process_flow:{step_id}"}
                )

    for row in active_pfmea:
        pfmea_id = text(row.get("pfmea_id"))
        for ref in _list_str(row.get("characteristic_refs", [])):
            if ref and ref not in seen:
                seen.add(ref)
                characteristics.append(
                    {"characteristic_id": ref, "name": ref, "source": f"pfmea:{pfmea_id}"}
                )

    for row in active_cp:
        cp_id = text(row.get("control_plan_id"))
        for ref in _list_str(row.get("characteristic_refs", [])):
            if ref and ref not in seen:
                seen.add(ref)
                characteristics.append(
                    {"characteristic_id": ref, "name": ref, "source": f"control_plan:{cp_id}"}
                )

    return characteristics


def _list_str(value: Any) -> list[str]:
    """Coerce *value* to a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _normalize_char_name(name: str) -> str:
    """Strip CHR-/SC- prefix for fuzzy characteristic matching."""
    for prefix in ("CHR-", "SC-"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _build_links(
    active_steps: list[dict[str, Any]],
    active_pfmea: list[dict[str, Any]],
    active_cp: list[dict[str, Any]],
    step_by_id: dict[str, dict[str, Any]],
    pfmea_by_id: dict[str, dict[str, Any]],
    pfmea_by_step: dict[str, list[dict[str, Any]]],
    cp_by_pfmea: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []

    # PFD -> PFMEA links
    for row in active_pfmea:
        pfmea_id = text(row.get("pfmea_id"), row.get("id"))
        step_id = text(row.get("process_step_id"), row.get("step_no"), row.get("step"))
        if not pfmea_id or not step_id:
            continue
        if step_id not in step_by_id:
            continue
        evidence_refs = _list_str(row.get("evidence_refs"))
        links.append({
            "trace_link_id": f"TL-PFD-PFMEA-{step_id}-{pfmea_id}",
            "from_type": EntityType.PROCESS_STEP.value,
            "from_id": step_id,
            "to_type": EntityType.FAILURE_MODE.value,
            "to_id": pfmea_id,
            "link_type": TraceLinkType.PFD_TO_PFMEA.value,
            "evidence_refs": evidence_refs,
            "confidence": _compute_confidence(evidence_refs),
            "ai_inferred": bool(row.get("ai_inferred", False)),
            "needs_confirmation": bool(row.get("needs_confirmation", False)),
        })

    # PFMEA -> CP links
    for row in active_cp:
        control_plan_id = text(row.get("control_plan_id"), row.get("id"))
        pfmea_id = text(row.get("pfmea_id"), row.get("source_pfmea_id"))
        if not control_plan_id or not pfmea_id:
            continue
        if pfmea_id not in pfmea_by_id:
            continue
        evidence_refs = _list_str(row.get("evidence_refs"))
        links.append({
            "trace_link_id": f"TL-PFMEA-CP-{pfmea_id}-{control_plan_id}",
            "from_type": EntityType.FAILURE_MODE.value,
            "from_id": pfmea_id,
            "to_type": EntityType.CONTROL_ITEM.value,
            "to_id": control_plan_id,
            "link_type": TraceLinkType.PFMEA_TO_CP.value,
            "evidence_refs": evidence_refs,
            "confidence": _compute_confidence(evidence_refs),
            "ai_inferred": bool(row.get("ai_inferred", False)),
            "needs_confirmation": bool(row.get("needs_confirmation", False)),
        })

    # Characteristic -> Step links (via characteristic_refs on steps)
    for step in active_steps:
        step_id = text(step.get("process_step_id"))
        if not step_id:
            continue
        char_refs = _list_str(step.get("characteristic_refs", []))
        char_refs.extend(_list_str(step.get("special_characteristics", [])))
        for ref in sorted(set(char_refs)):
            links.append({
                "trace_link_id": f"TL-CHAR-STEP-{ref}-{step_id}",
                "from_type": EntityType.CHARACTERISTIC.value,
                "from_id": ref,
                "to_type": EntityType.PROCESS_STEP.value,
                "to_id": step_id,
                "link_type": TraceLinkType.CHARACTERISTIC_TO_STEP.value,
                "evidence_refs": _list_str(step.get("evidence_refs")),
                "confidence": None,
                "ai_inferred": False,
                "needs_confirmation": False,
            })

    return links


def _compute_confidence(evidence_refs: list[str]) -> float | None:
    """Return a default confidence when evidence refs are present."""
    return 0.7 if evidence_refs else None


def _build_gaps(
    active_steps: list[dict[str, Any]],
    active_pfmea: list[dict[str, Any]],
    active_cp: list[dict[str, Any]],
    step_ids: set[str],
    step_by_id: dict[str, dict[str, Any]],
    pfmea_by_id: dict[str, dict[str, Any]],
    pfmea_by_step: dict[str, list[dict[str, Any]]],
    cp_by_pfmea: dict[str, list[dict[str, Any]]],
    cp_by_step: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []

    # --- PFD -> PFMEA coverage ---
    for step in active_steps:
        step_id = text(step.get("process_step_id"))
        if not step_id:
            continue
        pfmea_for_step = pfmea_by_step.get(step_id, [])
        if not pfmea_for_step:
            gaps.append({
                "gap_id": f"GAP-PFD-PFMEA-{step_id}",
                "category": "三表联动",
                "category_key": "pfd_pfmea_coverage",
                "severity": "blocker",
                "source": f"process_flow:{step_id}",
                "target": "pfmea",
                "message": f"PFD 工序 {step_id} 没有关联 PFMEA 风险行。",
                "recommended_action": (
                    "为该工序补充至少一条 PFMEA 风险行，"
                    "或人工确认该工序无风险分析要求。"
                ),
                "status": "待处理",
                "evidence_refs": [],
            })

    # --- Special characteristics: PFD has them but PFMEA row does not ---
    #     Only flag explicit characteristic references (SC-xxx, CHR-xxx).
    #     Classification codes like "SC", "CC", "特殊特性" are markers,
    #     not specific characteristics to match.
    _classification_markers = {"SC", "CC", "SC ", "CC ", "特殊特性", "关键特性", "重要特性"}
    for step in active_steps:
        step_id = text(step.get("process_step_id"))
        if not step_id:
            continue
        special_chars = _list_str(step.get("special_characteristics", []))
        # Filter out classification markers — only keep actual characteristic IDs/names
        real_chars = [sc for sc in special_chars if sc.strip() not in _classification_markers]
        if not real_chars:
            continue
        pfmea_for_step = pfmea_by_step.get(step_id, [])
        if not pfmea_for_step:
            continue  # covered by the gap above
        # Normalize for fuzzy matching (handle CHR-/SC- prefix differences)
        pfmea_norms: set[str] = set()
        for pfmea_row in pfmea_for_step:
            for c in _list_str(pfmea_row.get("characteristic_refs", [])):
                pfmea_norms.add(_normalize_char_name(c))
        # Explicit SC-xxx characteristic IDs: blocker if missing from any PFMEA
        sc_ids = [sc for sc in real_chars if sc.startswith("SC-")]
        if sc_ids:
            for pfmea_row in pfmea_for_step:
                pfmea_id = text(pfmea_row.get("pfmea_id"))
                pfmea_char_refs = set(_list_str(pfmea_row.get("characteristic_refs", [])))
                sc_missing = sorted(sc for sc in sc_ids if sc not in pfmea_char_refs)
                if sc_missing:
                    gaps.append({
                        "gap_id": f"GAP-SPEC-CHAR-PFMEA-{step_id}-{pfmea_id}",
                        "category": "三表联动",
                        "category_key": "special_char_step",
                        "severity": "blocker",
                        "source": f"process_flow:{step_id}",
                        "target": f"pfmea:{pfmea_id}",
                        "message": (
                            f"PFD 工序 {step_id} 有特殊特性 {', '.join(sc_missing)}，"
                            f"但 PFMEA 行 {pfmea_id} 未关联这些特性。"
                        ),
                        "recommended_action": (
                            f"在 PFMEA 行 {pfmea_id} 的 characteristic_refs 中"
                            f"补入 {', '.join(sc_missing)}。"
                        ),
                        "status": "待处理",
                        "evidence_refs": [],
                    })
        # Non-SC characteristics not matched in PFMEA: warning only
        other_chars = [sc for sc in real_chars if not sc.startswith("SC-")]
        other_missing = sorted(
            sc for sc in other_chars
            if _normalize_char_name(sc) not in pfmea_norms
        )
        if other_missing:
            for pfmea_row in pfmea_for_step:
                pfmea_id = text(pfmea_row.get("pfmea_id"))
                classification = text(pfmea_row.get("classification"))
                if classification:
                    gaps.append({
                        "gap_id": f"GAP-STEP-CHAR-PFMEA-{step_id}-{pfmea_id}",
                        "category": "三表联动",
                        "category_key": "step_char_pfmea",
                        "severity": "warning",
                        "source": f"process_flow:{step_id}",
                        "target": f"pfmea:{pfmea_id}",
                        "message": (
                            f"PFD 工序 {step_id} 有特性 {', '.join(other_missing)}，"
                            f"PFMEA {pfmea_id} 未显式关联。"
                        ),
                        "recommended_action": "确认 PFMEA 是否需要引用这些特性。",
                        "status": "待处理",
                        "evidence_refs": [],
                    })
                    break

    # --- Special characteristics: PFMEA has them but CP does not ---
    #     Blocker: SC-xxx characteristics or PFMEA with explicit classification
    #     Warning: step special_characteristics referenced in PFMEA but missing from CP
    #     Review: regular CHR-xxx characteristics not in CP
    for row in active_pfmea:
        pfmea_id = text(row.get("pfmea_id"))
        if not pfmea_id:
            continue
        pfmea_char_refs = set(_list_str(row.get("characteristic_refs", [])))
        if not pfmea_char_refs:
            continue
        classification = text(row.get("classification"))

        # Categorize characteristic refs: SC-xxx are explicitly special.
        # Classification field is only meaningful when it carries a
        # real classification code (not a CHR-/SC- characteristic id).
        sc_explicit: set[str] = {c for c in pfmea_char_refs if c.startswith("SC-")}
        if classification and not classification.startswith("CHR-") and not classification.startswith("SC-"):
            sc_explicit.update(pfmea_char_refs)
        non_sc_refs = pfmea_char_refs - sc_explicit

        cp_rows = cp_by_pfmea.get(pfmea_id, [])
        if not cp_rows:
            continue  # covered by pfmea_cp_coverage gap below
        cp_char_refs: set[str] = set()
        for cp_row in cp_rows:
            cp_char_refs.update(_list_str(cp_row.get("characteristic_refs", [])))

        # Blocker: explicitly special characteristics missing from CP
        missing_sc = sorted(sc_explicit - cp_char_refs)
        if missing_sc:
            gaps.append({
                "gap_id": f"GAP-SPEC-CHAR-CP-{pfmea_id}",
                "category": "三表联动",
                "category_key": "special_char_cp",
                "severity": "blocker",
                "source": f"pfmea:{pfmea_id}",
                "target": "control_plan",
                "message": (
                    f"PFMEA 行 {pfmea_id} 有特殊特性 {', '.join(missing_sc)}，"
                    f"但关联的 CP 行未包含这些特性。"
                ),
                "recommended_action": (
                    f"在 CP 行的 characteristic_refs 中补入 {', '.join(missing_sc)}。"
                ),
                "status": "待处理",
                "evidence_refs": [],
            })

        # Warning: step special_characteristics may be relevant to PFMEA
        step_id = text(row.get("process_step_id"))
        linked_step = step_by_id.get(step_id) if step_id else None
        step_specials = (
            set(_list_str(linked_step.get("special_characteristics", [])))
            if linked_step
            else set()
        )
        step_rel_refs = {
            c for c in non_sc_refs
            if _normalize_char_name(c) in {_normalize_char_name(s) for s in step_specials}
            or any(
                _normalize_char_name(c) in _normalize_char_name(s)
                or _normalize_char_name(s) in _normalize_char_name(c)
                for s in step_specials
            )
        }
        missing_step_rel = sorted(step_rel_refs - cp_char_refs)
        if missing_step_rel:
            gaps.append({
                "gap_id": f"GAP-STEP-CHAR-CP-{pfmea_id}",
                "category": "三表联动",
                "category_key": "step_char_cp",
                "severity": "warning",
                "source": f"pfmea:{pfmea_id}",
                "target": "control_plan",
                "message": (
                    f"工序 {step_id} 的特殊特性与 PFMEA {pfmea_id}"
                    f"的特性 {', '.join(missing_step_rel)} 相关，"
                    f"但 CP 未体现，建议确认。"
                ),
                "recommended_action": "确认 CP 是否需补充对应特性的控制方法。",
                "status": "待处理",
                "evidence_refs": [],
            })

        # Review: regular characteristics not in CP
        remaining = non_sc_refs - step_rel_refs
        missing_remaining = sorted(remaining - cp_char_refs)
        if missing_remaining:
            gaps.append({
                "gap_id": f"GAP-CHAR-REF-CP-{pfmea_id}",
                "category": "三表联动",
                "category_key": "char_ref_cp",
                "severity": "review",
                "source": f"pfmea:{pfmea_id}",
                "target": "control_plan",
                "message": (
                    f"PFMEA 行 {pfmea_id} 的特性 {', '.join(missing_remaining)}"
                    f"未在关联 CP 行中体现，建议确认是否需要补充。"
                ),
                "recommended_action": "确认 CP 是否需补充对应特性的控制方法。",
                "status": "待处理",
                "evidence_refs": [],
            })

    # --- PFMEA row: check that CP carries through step special characteristics ---
    #     Only flag explicitly SC-marked characteristics as blockers.
    #     Classification markers ("SC", "CC") and fuzzy names are warnings.
    for row in active_pfmea:
        pfmea_id = text(row.get("pfmea_id"))
        if not pfmea_id:
            continue
        step_id = text(row.get("process_step_id"))
        linked_step = step_by_id.get(step_id) if step_id else None
        linked_step_specials = (
            _list_str(linked_step.get("special_characteristics", []))
            if linked_step
            else []
        )
        if not linked_step_specials:
            continue
        # Filter to only SC-xxx IDs — markers like "SC"/"CC" are not matchable
        sc_only = [s for s in linked_step_specials if s.startswith("SC-")]
        if not sc_only:
            continue
        pfmea_char_refs = set(_list_str(row.get("characteristic_refs", [])))
        missing_pfmea = sorted(set(sc_only) - pfmea_char_refs)
        if missing_pfmea:
            gaps.append({
                "gap_id": f"GAP-SPEC-CHAR-PFMEA-{step_id}-{pfmea_id}",
                "category": "三表联动",
                "category_key": "special_char_pfmea",
                "severity": "blocker",
                "source": f"process_flow:{step_id}",
                "target": f"pfmea:{pfmea_id}",
                "message": (
                    f"PFD 工序 {step_id} 有特殊特性 {', '.join(missing_pfmea)}，"
                    f"但 PFMEA 行 {pfmea_id} 未关联这些特性。"
                ),
                "recommended_action": (
                    f"在 PFMEA 行 {pfmea_id} 的 characteristic_refs 中"
                    f"补入 {', '.join(missing_pfmea)}。"
                ),
                "status": "待处理",
                "evidence_refs": [],
            })

    # --- PFMEA -> CP coverage: AP=H or severity>=9 must have CP ---
    for row in active_pfmea:
        pfmea_id = text(row.get("pfmea_id"))
        if not pfmea_id:
            continue
        ap = text(row.get("action_priority"), row.get("AP")).upper()
        severity = _int_value(row.get("severity"), row.get("S"))
        if ap != "H" and severity < 9:
            continue
        cp_rows = cp_by_pfmea.get(pfmea_id, [])
        if not cp_rows:
            gaps.append({
                "gap_id": f"GAP-PFMEA-CP-{pfmea_id}",
                "category": "三表联动",
                "category_key": "pfmea_cp_coverage",
                "severity": "blocker",
                "source": f"pfmea:{pfmea_id}",
                "target": "control_plan",
                "message": (
                    f"高 AP/高严重度 PFMEA 行 {pfmea_id} "
                    f"(AP={ap}, severity={severity}) 没有关联控制计划行。"
                ),
                "recommended_action": (
                    "为该 PFMEA 风险行补充至少一条控制计划行，"
                    "或人工确认无需控制。"
                ),
                "status": "待处理",
                "evidence_refs": [],
            })

    # --- Orphan PFMEA: PFMEA row references a process_step_id not in PFD ---
    pfmea_step_ids: set[str] = set()
    for row in active_pfmea:
        sid = text(row.get("process_step_id"), row.get("step_no"), row.get("step"))
        if sid:
            pfmea_step_ids.add(sid)
    orphan_step_ids = pfmea_step_ids - step_ids
    for step_id in sorted(orphan_step_ids):
        orphan_rows = [
            text(r.get("pfmea_id"))
            for r in active_pfmea
            if text(r.get("process_step_id"), r.get("step_no"), r.get("step")) == step_id
        ]
        for pfmea_id in orphan_rows:
            gaps.append({
                "gap_id": f"GAP-ORPHAN-PFMEA-{pfmea_id}",
                "category": "三表联动",
                "category_key": "orphan_pfmea",
                "severity": "blocker",
                "source": f"pfmea:{pfmea_id}",
                "target": "process_flow",
                "message": (
                    f"PFMEA 行 {pfmea_id} 引用了不存在的 PFD 工序 {step_id}。"
                ),
                "recommended_action": (
                    f"将 PFMEA 行 {pfmea_id} 的 process_step_id 改为有效 PFD 工序 ID，"
                    f"或删除该 PFMEA 行。"
                ),
                "status": "待处理",
                "evidence_refs": [],
            })

    # --- Orphan CP: CP row references a non-existent pfmea_id or process_step_id ---
    for row in active_cp:
        cp_id = text(row.get("control_plan_id"), row.get("id"))
        if not cp_id:
            continue
        pfmea_id = text(row.get("pfmea_id"), row.get("source_pfmea_id"))
        step_id = text(row.get("process_step_id"), row.get("step_no"))

        if pfmea_id and pfmea_id not in pfmea_by_id:
            gaps.append({
                "gap_id": f"GAP-ORPHAN-CP-PFMEA-{cp_id}",
                "category": "三表联动",
                "category_key": "orphan_cp",
                "severity": "blocker",
                "source": f"control_plan:{cp_id}",
                "target": "pfmea",
                "message": (
                    f"CP 行 {cp_id} 引用了不存在的 PFMEA 行 {pfmea_id}。"
                ),
                "recommended_action": (
                    f"将 CP 行 {cp_id} 的 pfmea_id 改为有效 PFMEA 行 ID，"
                    f"或删除该 CP 行。"
                ),
                "status": "待处理",
                "evidence_refs": [],
            })

        if step_id and step_id not in step_ids:
            gaps.append({
                "gap_id": f"GAP-ORPHAN-CP-STEP-{cp_id}",
                "category": "三表联动",
                "category_key": "orphan_cp_step",
                "severity": "blocker",
                "source": f"control_plan:{cp_id}",
                "target": "process_flow",
                "message": (
                    f"CP 行 {cp_id} 引用了不存在的 PFD 工序 {step_id}。"
                ),
                "recommended_action": (
                    f"将 CP 行 {cp_id} 的 process_step_id 改为有效 PFD 工序 ID，"
                    f"或删除该 CP 行。"
                ),
                "status": "待处理",
                "evidence_refs": [],
            })

    # De-duplicate gaps by gap_id (special_char_step and special_char_pfmea may overlap)
    return _deduplicate_gaps(gaps)


def _int_value(*values: Any) -> int:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _deduplicate_gaps(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate gaps by gap_id, keeping the first occurrence."""
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for gap in gaps:
        gid = gap.get("gap_id", "")
        if gid in seen:
            continue
        seen.add(gid)
        result.append(gap)
    return result
