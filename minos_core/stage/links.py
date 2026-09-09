"""TraceLink generation between APQP artifacts."""
from __future__ import annotations

from typing import Any

from ..domain import EntityType, TraceLinkType
from ._utils import _list_value, _text_value


def _generated_pfd_pfmea_links(
    process_steps: list[Any], candidate_rows: list[Any], pfmea_rows: list[Any],
    evidence_rows: list[Any] | None = None,
) -> list[dict[str, Any]]:
    step_ids = {
        step_id
        for step in process_steps
        if isinstance(step, dict)
        for step_id in [_text_value(step, "process_step_id", "id", "step_no")]
        if step_id
    }
    candidate_refs = {
        _text_value(candidate, "candidate_id", "id"): _list_value(candidate, "evidence_refs")
        for candidate in candidate_rows
        if isinstance(candidate, dict)
    }
    links: list[dict[str, Any]] = []
    for row in pfmea_rows:
        if not isinstance(row, dict):
            continue
        pfmea_id = _text_value(row, "pfmea_id", "id")
        step_id = _text_value(row, "process_step_id", "step_no", "step")
        if not pfmea_id or not step_id or (step_ids and step_id not in step_ids):
            continue
        source_candidate_id = _text_value(row, "source_candidate_id")
        evidence_refs = _list_value(row, "evidence_refs")
        if source_candidate_id and not evidence_refs:
            evidence_refs = candidate_refs.get(source_candidate_id, [])
        links.append(
            {
                "trace_link_id": f"TL-PFD-PFMEA-{step_id}-{pfmea_id}",
                "from": step_id,
                "to": pfmea_id,
                "from_id": step_id,
                "to_id": pfmea_id,
                "from_type": EntityType.PROCESS_STEP.value,
                "to_type": EntityType.FAILURE_MODE.value,
                "link_type": TraceLinkType.PFD_TO_PFMEA.value,
                "evidence_refs": evidence_refs,
                "created_by_stage": "assemble_generated_apqp_chain",
                "confidence": _compute_confidence(evidence_refs, evidence_rows or []),
                "ai_inferred": True,
                "needs_confirmation": True,
            }
        )
    return links


def _generated_pfmea_cp_links(
    pfmea_rows: list[Any], control_rows: list[Any],
    evidence_rows: list[Any] | None = None,
) -> list[dict[str, Any]]:
    pfmea_by_id = {
        _text_value(row, "pfmea_id", "id"): row
        for row in pfmea_rows
        if isinstance(row, dict) and _text_value(row, "pfmea_id", "id")
    }
    links: list[dict[str, Any]] = []
    for row in control_rows:
        if not isinstance(row, dict):
            continue
        control_plan_id = _text_value(row, "control_plan_id", "id")
        pfmea_id = _text_value(row, "pfmea_id", "source_pfmea_id")
        if not control_plan_id or not pfmea_id:
            continue
        evidence_refs = _list_value(row, "evidence_refs")
        if not evidence_refs and pfmea_id in pfmea_by_id:
            evidence_refs = _list_value(pfmea_by_id[pfmea_id], "evidence_refs")
        links.append(
            {
                "trace_link_id": f"TL-PFMEA-CP-{pfmea_id}-{control_plan_id}",
                "from": pfmea_id,
                "to": control_plan_id,
                "from_id": pfmea_id,
                "to_id": control_plan_id,
                "from_type": EntityType.FAILURE_MODE.value,
                "to_type": EntityType.CONTROL_ITEM.value,
                "link_type": TraceLinkType.PFMEA_TO_CP.value,
                "evidence_refs": evidence_refs,
                "created_by_stage": "assemble_generated_apqp_chain",
                "confidence": _compute_confidence(evidence_refs, evidence_rows or []),
                "ai_inferred": True,
                "needs_confirmation": True,
            }
        )
    return links


def _compute_confidence(evidence_refs: list[str], evidence_rows: list[Any]) -> float | None:
    """Compute average confidence from evidence rows matching the given refs."""
    if not evidence_refs or not evidence_rows:
        return None
    confidences = [
        ev["confidence"]
        for ev in evidence_rows
        if isinstance(ev, dict)
        and ev.get("evidence_id") in evidence_refs
        and ev.get("confidence") is not None
    ]
    return sum(confidences) / len(confidences) if confidences else None


def _generated_step_candidate_links(
    process_steps: list[Any], candidate_rows: list[Any]
) -> list[dict[str, Any]]:
    """Create TraceLink entries linking PFD steps to failure mode candidates."""
    step_ids = {
        _text_value(step, "process_step_id", "id", "step_no")
        for step in process_steps
        if isinstance(step, dict)
    }
    links: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        if not isinstance(candidate, dict):
            continue
        candidate_id = _text_value(candidate, "candidate_id", "id")
        step_id = _text_value(candidate, "process_step_id", "step_no")
        if not candidate_id or not step_id or step_id not in step_ids:
            continue
        links.append({
            "trace_link_id": f"TL-STEP-CAND-{step_id}-{candidate_id}",
            "from": step_id,
            "to": candidate_id,
            "from_id": step_id,
            "to_id": candidate_id,
            "from_type": EntityType.PROCESS_STEP.value,
            "to_type": EntityType.FAILURE_MODE_CANDIDATE.value,
            "link_type": TraceLinkType.STEP_TO_CANDIDATE.value,
            "evidence_refs": _list_value(candidate, "evidence_refs"),
            "created_by_stage": "assemble_generated_apqp_chain",
            "confidence": candidate.get("confidence") if isinstance(candidate, dict) else None,
            "ai_inferred": bool(candidate.get("ai_inferred")) if isinstance(candidate, dict) else False,
            "needs_confirmation": True,
        })
    return links
