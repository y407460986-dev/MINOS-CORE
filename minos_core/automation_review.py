"""UI-neutral AI-led pre-review for generated MINOS Core three-table drafts."""

from __future__ import annotations

import copy
import logging
from typing import Any

from minos_core._text_utils import float_or_none

from .edit_patch import EDIT_PATCH_VERSION
from .quality_gates import evaluate_export_gate
from .review_issues import build_review_issue, unresolved_review_issues


logger = logging.getLogger(__name__)


AUTOMATION_REVIEW_VERSION = "minos-core.automation_review.v1"
DEFAULT_BATCH_CONFIRM_CONFIDENCE = 0.85

_TABLE_CONFIG = {
    "process_flow": {
        "chain_key": "process_steps",
        "table_key": "steps",
        "id_fields": ("process_step_id", "id", "step_no"),
        "target_type": "process_step",
    },
    "pfmea": {
        "chain_key": "failure_modes",
        "table_key": "rows",
        "id_fields": ("pfmea_id", "id"),
        "target_type": "failure_mode",
    },
    "control_plan": {
        "chain_key": "controls",
        "table_key": "rows",
        "id_fields": ("control_plan_id", "id"),
        "target_type": "control_item",
    },
}


def build_automation_review(
    source: dict[str, Any],
    *,
    min_confidence: float = DEFAULT_BATCH_CONFIRM_CONFIDENCE,
) -> dict[str, Any]:
    """Build AI pre-review tasks and safe batch-confirm candidates."""

    if not isinstance(source, dict):
        raise TypeError("source must be a JSON object")
    chain = _as_chain(source)
    gate = evaluate_export_gate(chain)
    gate_payload = gate.model_dump()
    blocking_issues = _blocking_issues(source, gate_payload)
    blocking_targets = _blocking_targets(blocking_issues)

    automation_tasks: list[dict[str, Any]] = []
    batch_confirm_candidates: list[dict[str, Any]] = []
    for table, row in _iter_rows(source, chain):
        if not isinstance(row, dict):
            continue
        row_id = _row_id(table, row)
        if not row_id:
            automation_tasks.append(
                _task(table, "", row, ["缺少行 ID"], can_batch_confirm=False)
            )
            continue
        reasons = _batch_reject_reasons(
            source=source,
            chain=chain,
            table=table,
            row=row,
            row_id=row_id,
            min_confidence=min_confidence,
            blocking_targets=blocking_targets,
        )
        if reasons:
            automation_tasks.append(_task(table, row_id, row, reasons, can_batch_confirm=False))
            continue
        candidate = _candidate(table, row_id, row)
        batch_confirm_candidates.append(candidate)
        automation_tasks.append(
            {
                "task_id": f"AR-{table}-{row_id}",
                "task_type": "batch_confirm_candidate",
                "table": table,
                "target_id": row_id,
                "target": candidate["target"],
                "automation_level": "ai_recommended_batch",
                "can_batch_confirm": True,
                "human_reason_required": False,
                "message": "低风险且证据充分，AI 建议纳入批量确认。",
                "fix_proposal": {},
            }
        )

    # Cross-table semantic review
    review_issues: list[dict[str, Any]] = []
    try:
        from .semantic_review import semantic_review_cross_table
        pfd_steps = chain.get("process_steps", [])
        pfmea_rows = chain.get("failure_modes", [])
        cp_rows = chain.get("controls", [])
        cross_issues = semantic_review_cross_table(pfd_steps, pfmea_rows, cp_rows)
        for issue in cross_issues:
            if isinstance(issue, dict):
                review_issues.append(automation_review_issue(
                    category=issue.get("category", "semantic"),
                    message=issue.get("message", str(issue)),
                    target=issue.get("target", ""),
                    severity="review",
                    fix_proposal=issue.get("fix_proposal"),
                ))
    except ImportError:
        logger.info("semantic_review module not available, skipping cross-table semantic review")

    return {
        "automation_review_version": AUTOMATION_REVIEW_VERSION,
        "review_stage": "after_control_plan",
        "human_decision_priority": True,
        "automation_tasks": automation_tasks,
        "batch_confirm_candidates": batch_confirm_candidates,
        "blocking_issues": blocking_issues,
        "review_issues": review_issues,
        "summary": {
            "message": (
                f"AI 预审完成：{len(batch_confirm_candidates)} 项可批量确认，"
                f"{len(automation_tasks) - len(batch_confirm_candidates)} 项需要人工处理，"
                f"{len(blocking_issues)} 项阻断问题，"
                f"{len(review_issues)} 项语义审查建议。"
            ),
            "batch_confirm_candidate_count": len(batch_confirm_candidates),
            "human_task_count": len(automation_tasks) - len(batch_confirm_candidates),
            "blocking_issue_count": len(blocking_issues),
            "review_issue_count": len(review_issues),
            "min_confidence": min_confidence,
            "decision_policy": "AI 只提供三表总审核建议；人工判断优先于 AI 建议。",
        },
    }


def build_batch_confirm_patch(
    candidates: list[dict[str, Any]],
    *,
    edited_by: str = "automation_review",
    edited_at: str = "",
    reason: str = "AI 预审建议批量确认低风险高置信度项目",
) -> dict[str, Any]:
    """Create an edit patch for candidates returned by build_automation_review."""

    items = []
    for candidate in candidates if isinstance(candidates, list) else []:
        if not isinstance(candidate, dict):
            continue
        table = str(candidate.get("table", "")).strip()
        target_id = str(candidate.get("target_id", "")).strip()
        if table and target_id:
            items.append(
                {
                    "action": "confirm",
                    "table": table,
                    "target_id": target_id,
                    "metadata": {
                        "confirmation_mode": "ai_recommended_batch",
                        "source": "automation_review",
                    },
                }
            )
    return {
        "edit_patch_version": EDIT_PATCH_VERSION,
        "edited_by": edited_by,
        "edited_at": edited_at,
        "reason": reason,
        "items": items,
    }


def _as_chain(source: dict[str, Any]) -> dict[str, Any]:
    if source.get("document_type") == "three_table_generation_result":
        chain = copy.deepcopy(source.get("chain") or {})
        chain.update(
            {
                "document_type": "apqp_chain",
                "process_steps": copy.deepcopy(_table_rows(source, "process_flow")),
                "failure_modes": copy.deepcopy(_table_rows(source, "pfmea")),
                "controls": copy.deepcopy(_table_rows(source, "control_plan")),
            }
        )
        chain.setdefault("schema_version", source.get("schema_version", "minos-core.generated.v1"))
        chain.setdefault("product", (source.get("process_flow") or {}).get("product", {}))
        chain.setdefault("evidence", (source.get("drawing_analysis") or {}).get("evidence", []))
        chain.setdefault("links", (source.get("process_flow") or {}).get("links", []))
        metadata = dict((source.get("chain") or {}).get("metadata", {}))
        metadata.update(dict(source.get("metadata", {})))
        chain["metadata"] = metadata
        return chain
    return copy.deepcopy(source)


def _iter_rows(source: dict[str, Any], chain: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for table in _TABLE_CONFIG:
        table_rows = _table_rows(source, table)
        if not table_rows:
            table_rows = chain.get(_TABLE_CONFIG[table]["chain_key"], [])
        rows.extend((table, row) for row in table_rows if isinstance(row, dict))
    return rows


def _table_rows(source: dict[str, Any], table: str) -> list[Any]:
    config = _TABLE_CONFIG[table]
    document = source.get(table)
    if isinstance(document, dict):
        rows = document.get(config["table_key"])
        if isinstance(rows, list):
            return rows
    rows = source.get(config["chain_key"])
    return rows if isinstance(rows, list) else []


def _batch_reject_reasons(
    *,
    source: dict[str, Any],
    chain: dict[str, Any],
    table: str,
    row: dict[str, Any],
    row_id: str,
    min_confidence: float,
    blocking_targets: set[str],
) -> list[str]:
    reasons: list[str] = []
    target = _target(table, row_id)
    confidence = float_or_none(row.get("confidence"))
    evidence_refs = [str(ref).strip() for ref in row.get("evidence_refs", []) if str(ref).strip()]
    if _is_deleted(row):
        reasons.append("软删除项目不能批量确认")
    if confidence is None or confidence < min_confidence:
        reasons.append(f"置信度低于 {min_confidence:.2f}")
    if not evidence_refs:
        reasons.append("缺少 evidence_refs")
    if _is_high_ap(row):
        reasons.append("高 AP 风险必须人工确认")
    if _has_special_characteristic(row, table, chain):
        reasons.append("特殊特性必须人工确认")
    if _is_broken_link(table, row, chain):
        reasons.append("上下游链路不完整")
    if target in blocking_targets or row_id in blocking_targets:
        reasons.append("已有阻断问题")
    if _has_open_change_impact(source, target):
        reasons.append("存在未处理的变更影响")
    # Semantic checks (per-row)
    try:
        from .semantic_review import semantic_review_row
        pfd_steps = chain.get("process_steps", [])
        pfmea_rows = chain.get("failure_modes", [])
        reasons.extend(semantic_review_row(row, table, pfd_steps=pfd_steps, pfmea_rows=pfmea_rows))
    except ImportError:
        logger.info("semantic_review module not available, skipping per-row semantic review")
    return _dedupe(reasons)


def _blocking_issues(source: dict[str, Any], gate_payload: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for issue in gate_payload.get("review_issues", []):
        if isinstance(issue, dict) and str(issue.get("severity", "")).strip() == "blocker":
            issues.append(issue)
    metadata = _metadata(source)
    issues.extend(
        dict(issue)
        for issue in unresolved_review_issues(metadata.get("review_issues", []))
        if isinstance(issue, dict) and str(issue.get("severity", "")).strip() == "blocker"
    )
    return _dedupe_issues(issues)


def _blocking_targets(issues: list[dict[str, Any]]) -> set[str]:
    targets: set[str] = set()
    for issue in issues:
        for field_name in ("target", "item_id", "issue_id"):
            value = str(issue.get(field_name, "")).strip()
            if value:
                targets.add(value)
                if ":" in value:
                    targets.add(value.split(":", 1)[1])
    return targets


def _task(
    table: str,
    row_id: str,
    row: dict[str, Any],
    reasons: list[str],
    *,
    can_batch_confirm: bool,
) -> dict[str, Any]:
    target = _target(table, row_id) if row_id else table
    return {
        "task_id": f"AR-{table}-{row_id or 'row'}",
        "task_type": "human_review",
        "table": table,
        "target_id": row_id,
        "target": target,
        "automation_level": "human_required",
        "can_batch_confirm": can_batch_confirm,
        "human_reason_required": True,
        "message": "；".join(reasons) if reasons else "需要人工复核。",
        "reasons": reasons,
        "fix_proposal": _fix_proposal(table, row_id, row, reasons),
    }


def _candidate(table: str, row_id: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "table": table,
        "target_id": row_id,
        "target": _target(table, row_id),
        "confidence": float_or_none(row.get("confidence")),
        "evidence_refs": [str(ref).strip() for ref in row.get("evidence_refs", []) if str(ref).strip()],
        "confirmation_mode": "ai_recommended_batch",
        "source": "automation_review",
        "message": "低风险高置信度项目，可由 AI 建议批量确认。",
    }


def _fix_proposal(table: str, row_id: str, row: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    suggestion_parts: list[str] = []

    if any("缺少 evidence_refs" in reason for reason in reasons):
        changes["evidence_refs"] = []
        suggestion_parts.append("请补充证据引用")
    if any("置信度" in reason for reason in reasons):
        changes["needs_confirmation"] = True
        suggestion_parts.append("请人工确认并提高置信度")

    # RPN arithmetic errors
    if any("RPN" in reason or "rpn" in reason.lower() for reason in reasons):
        sev = _int_or(row.get("severity"), 1)
        occ = _int_or(row.get("occurrence"), 1)
        det = _int_or(row.get("detection"), 1)
        correct_rpn = sev * occ * det
        changes["rpn"] = correct_rpn
        suggestion_parts.append(
            f"RPN应为 S x O x D = {sev} x {occ} x {det} = {correct_rpn}，请修正"
        )

    # Cause/effect logic issues
    if any(
        keyword in reason
        for reason in reasons
        for keyword in ("因果", "失效原因", "逻辑矛盾", "cause", "effect")
    ):
        changes["needs_cause_effect_clarification"] = True
        suggestion_parts.append(
            "请区分失效模式、失效后果与失效原因三个字段，确保因果关系逻辑清晰"
        )

    # Detection vs failure type mismatch
    if any(
        keyword in reason
        for reason in reasons
        for keyword in ("探测", "检测方法", "detection", "探测度")
    ):
        changes["needs_detection_method"] = True
        suggestion_parts.append("请根据失效模式类型补充或调整探测/检测方法")

    # Measurement vs tolerance mismatch
    if any(
        keyword in reason
        for reason in reasons
        for keyword in ("测量", "量测", "公差", "measurement", "tolerance")
    ):
        changes["needs_precise_measurement"] = True
        suggestion_parts.append("请选用精度更高的测量方法以匹配公差要求")

    if not changes:
        return {}
    result: dict[str, Any] = {
        "edit_patch_version": EDIT_PATCH_VERSION,
        "action": "update",
        "table": table,
        "target_id": row_id,
        "changes": changes,
        "metadata": {"source": "ai_fix_proposal"},
    }
    if suggestion_parts:
        result["suggestion"] = "；".join(suggestion_parts)
    return result


def _int_or(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _row_id(table: str, row: dict[str, Any]) -> str:
    for field_name in _TABLE_CONFIG[table]["id_fields"]:
        value = str(row.get(field_name, "")).strip()
        if value:
            return value
    return ""


def _target(table: str, row_id: str) -> str:
    return f"{_TABLE_CONFIG[table]['target_type']}:{row_id}"


def _is_deleted(row: dict[str, Any]) -> bool:
    return bool(row.get("deleted") or row.get("soft_deleted"))


def _is_high_ap(row: dict[str, Any]) -> bool:
    return str(row.get("action_priority", row.get("AP", ""))).strip().upper() == "H"


def _has_special_characteristic(row: dict[str, Any], table: str, chain: dict[str, Any]) -> bool:
    direct = (
        row.get("classification")
        or row.get("characteristic_refs")
        or row.get("special_characteristics")
        or row.get("source_special_characteristics")
    )
    if direct:
        return True
    if table != "process_flow":
        step_id = str(row.get("process_step_id", "")).strip()
        for step in chain.get("process_steps", []):
            if isinstance(step, dict) and str(step.get("process_step_id", "")).strip() == step_id:
                return bool(step.get("special_characteristics"))
    return False


def _is_broken_link(table: str, row: dict[str, Any], chain: dict[str, Any]) -> bool:
    step_ids = {
        str(item.get("process_step_id", "")).strip()
        for item in chain.get("process_steps", [])
        if isinstance(item, dict) and not _is_deleted(item)
    }
    if table in {"pfmea", "control_plan"}:
        step_id = str(row.get("process_step_id", "")).strip()
        if step_id and step_ids and step_id not in step_ids:
            return True
    if table == "control_plan":
        pfmea_ids = {
            str(item.get("pfmea_id", "")).strip()
            for item in chain.get("failure_modes", [])
            if isinstance(item, dict) and not _is_deleted(item)
        }
        pfmea_id = str(row.get("pfmea_id", row.get("source_pfmea_id", ""))).strip()
        if pfmea_id and pfmea_ids and pfmea_id not in pfmea_ids:
            return True
    return False


def _has_open_change_impact(source: dict[str, Any], target: str) -> bool:
    for item in _metadata(source).get("change_impacts", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("target", "")).strip() != target:
            continue
        if str(item.get("status", "待处理")).strip() not in {"已处理", "已确认", "无影响"}:
            return True
    return False


def _metadata(source: dict[str, Any]) -> dict[str, Any]:
    metadata = {}
    chain = source.get("chain")
    if isinstance(chain, dict) and isinstance(chain.get("metadata"), dict):
        metadata.update(chain["metadata"])
    if isinstance(source.get("metadata"), dict):
        metadata.update(source["metadata"])
    return metadata




def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _dedupe_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get("issue_id", item.get("target", ""))).strip()
        if not key:
            key = str(item)
        if key in seen:
            continue
        result.append(item)
        seen.add(key)
    return result


def automation_review_issue(
    *,
    category: str,
    message: str,
    target: str,
    severity: str = "review",
    fix_proposal: dict[str, Any] | None = None,
    can_batch_confirm: bool = False,
) -> dict[str, Any]:
    return build_review_issue(
        category=category,
        message=message,
        severity=severity,
        source="automation_review",
        target=target,
        automation_level="ai_pre_review",
        fix_proposal=fix_proposal or {},
        can_batch_confirm=can_batch_confirm,
        human_reason_required=not can_batch_confirm,
    )
