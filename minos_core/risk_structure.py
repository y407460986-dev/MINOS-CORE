"""APIS-style risk structure view built from three-table payloads."""

from __future__ import annotations

from typing import Any

from ._text_utils import integer, string_list, text
from .change_management import _rows


def build_risk_structure(source: dict[str, Any]) -> dict[str, Any]:
    """Build an APIS-style risk structure view from a three-table payload.

    Returns a nested ``process_node -> risk_node -> control_node`` tree
    together with orphan buckets and a numeric summary.
    """
    process_rows = _rows(source, "process_flow", "process_steps", "steps")
    pfmea_rows = _rows(source, "pfmea", "failure_modes", "rows")
    cp_rows = _rows(source, "control_plan", "controls", "rows")

    active_step_ids: set[str] = set()
    process_nodes: list[dict[str, Any]] = []
    for step in process_rows:
        if not isinstance(step, dict) or step.get("deleted"):
            continue
        sid = text(step.get("process_step_id"))
        if not sid:
            continue
        active_step_ids.add(sid)

        linked_pfmea = [
            row
            for row in pfmea_rows
            if isinstance(row, dict)
            and not row.get("deleted")
            and text(row.get("process_step_id")) == sid
        ]

        risk_nodes: list[dict[str, Any]] = []
        for pf_row in linked_pfmea:
            pfmea_id = text(pf_row.get("pfmea_id"))
            linked_cp = [
                row
                for row in cp_rows
                if isinstance(row, dict)
                and not row.get("deleted")
                and text(row.get("pfmea_id")) == pfmea_id
            ]

            risk_nodes.append(
                _build_risk_node(pf_row, linked_cp, source)
            )

        process_nodes.append(
            {
                "process_step_id": sid,
                "operation": text(step.get("operation")),
                "process_function": text(step.get("process_function")),
                "characteristic_refs": string_list(
                    step.get("characteristic_refs")
                    or step.get("product_characteristics")
                ),
                "risk_nodes": risk_nodes,
            }
        )

    # --- orphan PFMEA rows (no matching active PFD step) ---
    orphan_risk_nodes: list[dict[str, Any]] = []
    active_pfmea_ids: set[str] = set()
    all_pfmea_ids: set[str] = set()
    for row in pfmea_rows:
        if not isinstance(row, dict) or row.get("deleted"):
            continue
        pfmea_id = text(row.get("pfmea_id"))
        if not pfmea_id:
            continue
        all_pfmea_ids.add(pfmea_id)
        step_id = text(row.get("process_step_id"))
        if step_id not in active_step_ids:
            linked_cp = [
                cp
                for cp in cp_rows
                if isinstance(cp, dict)
                and not cp.get("deleted")
                and text(cp.get("pfmea_id")) == pfmea_id
            ]
            orphan_risk_nodes.append(_build_risk_node(row, linked_cp, source))
        else:
            active_pfmea_ids.add(pfmea_id)

    # --- orphan CP rows (no matching PFMEA at all) ---
    orphan_control_nodes: list[dict[str, Any]] = []
    for row in cp_rows:
        if not isinstance(row, dict) or row.get("deleted"):
            continue
        pfmea_id = text(row.get("pfmea_id"))
        if pfmea_id and pfmea_id not in all_pfmea_ids:
            orphan_control_nodes.append(_build_control_node(row))

    # --- summary ---
    open_action_count = 0
    review_node_count = 0
    risk_node_count = 0
    control_node_count = 0
    for pn in process_nodes:
        for rn in pn.get("risk_nodes", []):
            risk_node_count += 1
            if rn.get("open_action_required"):
                open_action_count += 1
            if rn.get("needs_review"):
                review_node_count += 1
            control_node_count += len(rn.get("control_nodes", []))
    for rn in orphan_risk_nodes:
        risk_node_count += 1
        if rn.get("open_action_required"):
            open_action_count += 1
        if rn.get("needs_review"):
            review_node_count += 1
        control_node_count += len(rn.get("control_nodes", []))
    control_node_count += len(orphan_control_nodes)

    return {
        "document_type": "risk_structure",
        "schema_version": "minos-core.risk_structure.v1",
        "process_nodes": process_nodes,
        "orphan_risk_nodes": orphan_risk_nodes,
        "orphan_control_nodes": orphan_control_nodes,
        "summary": {
            "process_node_count": len(process_nodes),
            "risk_node_count": risk_node_count,
            "control_node_count": control_node_count,
            "open_action_count": open_action_count,
            "review_node_count": review_node_count,
        },
    }


def _build_risk_node(
    pf_row: dict[str, Any],
    cp_rows: list[dict[str, Any]],
    source: dict[str, Any],
) -> dict[str, Any]:
    """Construct a single risk_node dict from a PFMEA row and its linked CP rows."""
    severity = integer(pf_row.get("severity"), 0)
    occurrence = integer(pf_row.get("occurrence"), 0)
    detection = integer(pf_row.get("detection"), 0)
    action_priority = text(pf_row.get("action_priority"), pf_row.get("AP")).upper()
    recommended_action = text(pf_row.get("recommended_action"))
    responsibility = text(pf_row.get("responsibility"))
    target_date = text(pf_row.get("target_date"))
    action_status = text(pf_row.get("action_status"))
    prevention_control = text(pf_row.get("prevention_control"))
    detection_control = text(pf_row.get("detection_control"))
    needs_confirmation = bool(pf_row.get("needs_confirmation"))
    ai_inferred = bool(pf_row.get("ai_inferred"))
    pfmea_id = text(pf_row.get("pfmea_id"))

    control_nodes = [_build_control_node(cp) for cp in cp_rows]

    open_action = _eval_open_action_required(
        action_priority=action_priority,
        severity=severity,
        recommended_action=recommended_action,
        responsibility=responsibility,
        target_date=target_date,
        action_status=action_status,
    )
    needs_review = _eval_needs_review(
        needs_confirmation=needs_confirmation,
        ai_inferred=ai_inferred,
        prevention_control=prevention_control,
        detection_control=detection_control,
        pfmea_id=pfmea_id,
        linkage_gaps=_get_linkage_gaps(source),
    )

    return {
        "pfmea_id": pfmea_id,
        "function_requirement": text(
            pf_row.get("function_requirement"), pf_row.get("requirement")
        ),
        "failure_mode": text(pf_row.get("failure_mode")),
        "failure_effect": text(
            pf_row.get("failure_effect"), pf_row.get("effect")
        ),
        "failure_cause": text(
            pf_row.get("failure_cause"), pf_row.get("cause")
        ),
        "prevention_control": prevention_control,
        "detection_control": detection_control,
        "severity": severity,
        "occurrence": occurrence,
        "detection": detection,
        "action_priority": action_priority,
        "recommended_action": recommended_action,
        "responsibility": responsibility,
        "target_date": target_date,
        "action_status": action_status,
        "control_nodes": control_nodes,
        "open_action_required": open_action,
        "needs_review": needs_review,
    }


def _build_control_node(cp_row: dict[str, Any]) -> dict[str, Any]:
    """Construct a single control_node dict from a CP row."""
    return {
        "control_plan_id": text(
            cp_row.get("control_plan_id"), cp_row.get("id")
        ),
        "product_process_characteristic": text(
            cp_row.get("product_process_characteristic"),
            cp_row.get("characteristic"),
        ),
        "specification": text(cp_row.get("specification")),
        "measurement_method": text(
            cp_row.get("measurement_method"), cp_row.get("measurement")
        ),
        "sample_frequency": text(cp_row.get("sample_frequency")),
        "reaction_plan": text(cp_row.get("reaction_plan")),
    }


def _eval_open_action_required(
    *,
    action_priority: str,
    severity: int,
    recommended_action: str,
    responsibility: str,
    target_date: str,
    action_status: str,
) -> bool:
    """Determine whether a PFMEA row requires open action.

    Returns True when:
    - action_priority == "H"
    - severity >= 9
    - recommended_action is non-empty but responsibility/target_date are
      empty OR action_status is NOT "已关闭" / "已关闭"
    """
    if action_priority == "H":
        return True
    if severity >= 9:
        return True
    if recommended_action:
        if not responsibility or not target_date:
            return True
        if action_status not in ("已完成", "已关闭"):
            return True
    return False


def _eval_needs_review(
    *,
    needs_confirmation: bool,
    ai_inferred: bool,
    prevention_control: str,
    detection_control: str,
    pfmea_id: str,
    linkage_gaps: list[dict[str, Any]],
) -> bool:
    """Determine whether a PFMEA row needs review.

    Returns True when:
    - needs_confirmation == True or ai_inferred == True
    - Both prevention_control and detection_control are empty
    - There is a sync/linkage gap pointing to this PFMEA row
    """
    if needs_confirmation or ai_inferred:
        return True
    if not prevention_control and not detection_control:
        return True
    if _has_linkage_gap(pfmea_id, linkage_gaps):
        return True
    return False


def _has_linkage_gap(
    pfmea_id: str,
    linkage_gaps: list[dict[str, Any]],
) -> bool:
    """Check whether any linkage gap references the given pfmea_id."""
    if not pfmea_id or not linkage_gaps:
        return False
    for gap in linkage_gaps:
        if not isinstance(gap, dict):
            continue
        target = text(gap.get("target", "") or gap.get("item_id", ""))
        ref = gap.get("ref", "")
        ref_id = text(gap.get("pfmea_id", ""))
        if pfmea_id in (target, ref, ref_id):
            return True
    return False


def _get_linkage_gaps(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract linkage_gaps from the source envelope or chain metadata."""
    gaps = source.get("linkage_gaps")
    if isinstance(gaps, list):
        return gaps
    linkage_map = source.get("linkage_map")
    if isinstance(linkage_map, dict):
        gaps = linkage_map.get("gaps")
        if isinstance(gaps, list):
            return gaps
    chain = source.get("chain")
    if isinstance(chain, dict):
        metadata = chain.get("metadata") or {}
        if isinstance(metadata, dict):
            gaps = metadata.get("linkage_gaps")
            if isinstance(gaps, list):
                return gaps
    return []


