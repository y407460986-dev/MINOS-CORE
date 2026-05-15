"""Review report builders for edited three-table drafts."""

from __future__ import annotations

from typing import Any

from .three_table_result import three_table_manual_review


def build_review_dashboard(
    payload: dict[str, Any],
    edit_gate: dict[str, Any],
    risk_structure: dict[str, Any] | None = None,
    linkage_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a unified review dashboard from edit gate, risk and linkage data."""

    unconfirmed_row_count = len(edit_gate.get("unconfirmed_items", []))
    unresolved_recommendation_count = len(edit_gate.get("knowledge_recommendations", []))
    unresolved_change_impact_count = len(edit_gate.get("change_impacts", []))
    manual_review_count = len(edit_gate.get("review_issues", []))
    soft_deleted_count = len(edit_gate.get("soft_deleted_items", []))
    final_export_allowed = bool(edit_gate.get("final_export_allowed", False))

    open_action_count = 0
    if risk_structure and isinstance(risk_structure, dict):
        summary = risk_structure.get("summary", {})
        if isinstance(summary, dict):
            open_action_count = int(summary.get("open_action_count", 0))

    action_summary = payload.get("metadata", {}).get("action_items_summary", {})
    unresolved_action_count = (
        action_summary.get("unresolved", 0) if isinstance(action_summary, dict) else 0
    )
    overdue_action_count = (
        action_summary.get("overdue", 0) if isinstance(action_summary, dict) else 0
    )
    closed_wo_evidence_count = (
        action_summary.get("closed_without_evidence", 0)
        if isinstance(action_summary, dict)
        else 0
    )

    sync_blocker_count = 0
    if linkage_report and isinstance(linkage_report, dict):
        sync_issues = linkage_report.get("sync_issues", [])
        if isinstance(sync_issues, list):
            sync_blocker_count = sum(
                1
                for issue in sync_issues
                if isinstance(issue, dict) and issue.get("severity") == "blocker"
            )

    actions: list[dict[str, Any]] = []
    if unconfirmed_row_count > 0:
        actions.append(
            {
                "priority": 1,
                "action": "确认或编辑所有活动三表行。",
                "count": unconfirmed_row_count,
            }
        )
    if sync_blocker_count > 0:
        actions.append(
            {
                "priority": 2,
                "action": "处理三表联动阻断项。",
                "count": sync_blocker_count,
            }
        )
    if open_action_count > 0:
        actions.append(
            {
                "priority": 3,
                "action": "补齐高 AP 风险的负责人、期限和完成状态。",
                "count": open_action_count,
            }
        )
    if unresolved_action_count > 0:
        actions.append(
            {
                "priority": 4,
                "action": f"关闭 {unresolved_action_count} 条高风险 PFMEA 行动项。",
                "count": unresolved_action_count,
            }
        )
    if overdue_action_count > 0:
        actions.append(
            {
                "priority": 5,
                "action": f"有 {overdue_action_count} 条行动项已逾期。",
                "count": overdue_action_count,
            }
        )
    if closed_wo_evidence_count > 0:
        actions.append(
            {
                "priority": 6,
                "action": f"{closed_wo_evidence_count} 条已关闭行动项缺少闭环证据。",
                "count": closed_wo_evidence_count,
            }
        )
    if unresolved_recommendation_count > 0:
        actions.append(
            {
                "priority": 7,
                "action": "处理知识库推荐：采纳、应用或忽略并说明理由。",
                "count": unresolved_recommendation_count,
            }
        )
    if unresolved_change_impact_count > 0:
        actions.append(
            {
                "priority": 8,
                "action": "处理人工编辑带来的下游影响。",
                "count": unresolved_change_impact_count,
            }
        )
    if soft_deleted_count > 0:
        actions.append(
            {
                "priority": 9,
                "action": "软删除行已排除，审计页保留记录。",
                "count": soft_deleted_count,
            }
        )
    if final_export_allowed:
        actions.append(
            {
                "priority": 10,
                "action": "全部完成，可以执行正式导出。",
                "count": 0,
            }
        )

    status = "ok" if final_export_allowed else "needs_review"
    return {
        "status": status,
        "status_display": "可以导出" if status == "ok" else "待人工复核",
        "final_export_allowed": final_export_allowed,
        "sync_blocker_count": sync_blocker_count,
        "open_action_count": open_action_count,
        "unresolved_action_count": unresolved_action_count,
        "overdue_action_count": overdue_action_count,
        "closed_without_evidence_count": closed_wo_evidence_count,
        "unconfirmed_row_count": unconfirmed_row_count,
        "unresolved_recommendation_count": unresolved_recommendation_count,
        "unresolved_change_impact_count": unresolved_change_impact_count,
        "manual_review_count": manual_review_count,
        "next_actions": actions[:10],
    }


def build_manual_review_payload(
    quality_gates: dict[str, Any],
    edit_gate: dict[str, Any],
) -> dict[str, Any]:
    manual_review = three_table_manual_review(quality_gates)
    edit_items = manual_review_items_from_edit_gate(edit_gate)
    raw_items = list(manual_review.get("raw_items", [])) + edit_items
    manual_review["raw_items"] = raw_items
    manual_review["items"] = list(manual_review.get("items", [])) + edit_items
    manual_review["raw_count"] = len(raw_items)
    manual_review["required"] = bool(raw_items)
    manual_review["summary"] = {
        "display_count": len(manual_review["items"]),
        "raw_count": len(raw_items),
        "message": f"当前编辑结果仍有 {len(edit_gate['unconfirmed_items'])} 行未逐行确认。",
    }
    return manual_review


def manual_review_items_from_edit_gate(
    gate_result: dict[str, Any],
) -> list[dict[str, Any]]:
    items = [
        {
            "item_id": item,
            "category": "逐行确认",
            "severity": "blocker",
            "severity_display": "阻断",
            "message": "正式导出前，所有未软删除的 PFD/PFMEA/CP 行都必须人工确认。",
        }
        for item in gate_result.get("unconfirmed_items", [])
    ]
    items.extend(
        {
            "item_id": item,
            "category": "人工复核问题",
            "severity": "blocker",
            "severity_display": "阻断",
            "message": "正式导出前，未处理的人工复核问题必须先关闭。",
        }
        for item in gate_result.get("review_issues", [])
    )
    items.extend(
        {
            "item_id": item,
            "category": "知识库推荐",
            "severity": "blocker",
            "severity_display": "阻断",
            "message": "高置信知识库推荐必须采纳，或填写忽略原因。",
        }
        for item in gate_result.get("knowledge_recommendations", [])
    )
    items.extend(
        {
            "item_id": item,
            "category": "变更影响",
            "severity": "blocker",
            "severity_display": "阻断",
            "message": "未处理的变更影响必须处理后才能正式导出。",
        }
        for item in gate_result.get("change_impacts", [])
    )
    return items
