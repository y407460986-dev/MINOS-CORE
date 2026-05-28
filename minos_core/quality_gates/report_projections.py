"""Report projections: manual review items and review issue construction."""
from __future__ import annotations

from typing import Any

from ..audit import AuditItem
from ..review_issues import (
    build_review_issue,
    review_issue_from_manual_item,
)

__all__ = [
    "_dedupe_review_issues",
    "_dict_manual_review_items",
    "_recommendation_manual_review_items",
    "_review_issues_from_gate_debts",
    "_row_needs_confirmation_manual_review_items",
]


def _dict_manual_review_items(items: list[dict[str, Any]]) -> list[AuditItem]:
    return [
        AuditItem(
            str(item.get("item_id", "")),
            str(item.get("category", "人工复核")),
            str(item.get("message", "")),
            str(item.get("severity", "review")),
        )
        for item in items
    ]


def _recommendation_manual_review_items(items: list[dict[str, Any]]) -> list[AuditItem]:
    return [
        AuditItem(
            str(item.get("recommendation_id", item.get("item_id", ""))),
            "知识库推荐",
            str(item.get("reason", "知识库推荐需要人工采纳或填写忽略原因。")),
            "review",
        )
        for item in items
    ]


def _review_issues_from_gate_debts(
    *,
    manual_review_items: list[Any],
    needs_confirmation_items: list[str],
    recommendation_blockers: list[dict[str, Any]],
    change_blockers: list[dict[str, Any]],
    existing_review_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in manual_review_items:
        issues.append(review_issue_from_manual_item(item))
    for item in needs_confirmation_items:
        issues.append(
            build_review_issue(
                category="人工确认",
                message="关键对象标记为待确认，需要人工确认后才能正式放行。",
                severity="review",
                source="quality_gate",
                target=item,
            )
        )
    for item in recommendation_blockers:
        issues.append(
            build_review_issue(
                category="知识库推荐",
                message=str(item.get("reason", "知识库推荐需要人工采纳或填写忽略原因。")),
                severity="blocker",
                source="knowledge_recommendation",
                target=str(item.get("target_id", "")),
                recommendation_id=str(item.get("recommendation_id", "")),
                confidence=item.get("confidence"),
            )
        )
    for item in change_blockers:
        issues.append(
            build_review_issue(
                category="变更影响",
                message=str(item.get("message", "变更影响需要处理后才能正式放行。")),
                severity=str(item.get("severity", "blocker")),
                source="change_management",
                target=str(item.get("target", "")),
                change_impact_id=str(item.get("item_id", "")),
            )
        )
    issues.extend(dict(item) for item in existing_review_issues)
    return _dedupe_review_issues(issues)


def _dedupe_review_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        issue_id = str(item.get("issue_id", "")).strip()
        if not issue_id:
            continue
        if issue_id in seen:
            continue
        result.append(item)
        seen.add(issue_id)
    return result


def _row_needs_confirmation_manual_review_items(items: list[str]) -> list[AuditItem]:
    return [
        AuditItem(
            item,
            "row_needs_confirmation",
            "关键对象标记为待确认，需要人工复核后才能正式放行",
            "review",
        )
        for item in items
    ]
