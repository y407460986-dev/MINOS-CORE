"""UI-neutral review issues for MINOS Core quality gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


REVIEW_ISSUE_VERSION = "minos-core.review_issue.v1"
RESOLVED_REVIEW_ISSUE_STATUSES = {"已处理", "已确认", "已采纳", "无影响"}


@dataclass(frozen=True)
class ReviewIssue:
    issue_id: str
    category: str
    message: str
    severity: str = "review"
    status: str = "待处理"
    source: str = "quality_gate"
    target: str = ""
    field: str = ""
    recommendation_id: str = ""
    change_impact_id: str = ""
    confidence: float | None = None
    automation_level: str = ""
    fix_proposal: dict[str, Any] | None = None
    can_batch_confirm: bool | None = None
    human_reason_required: bool | None = None

    def model_dump(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "review_issue_version": REVIEW_ISSUE_VERSION,
            "issue_id": self.issue_id,
            "category": self.category,
            "message": self.message,
            "severity": self.severity,
            "status": self.status,
            "source": self.source,
            "target": self.target,
            "field": self.field,
        }
        if self.recommendation_id:
            payload["recommendation_id"] = self.recommendation_id
        if self.change_impact_id:
            payload["change_impact_id"] = self.change_impact_id
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.automation_level:
            payload["automation_level"] = self.automation_level
        if self.fix_proposal:
            payload["fix_proposal"] = self.fix_proposal
        if self.can_batch_confirm is not None:
            payload["can_batch_confirm"] = self.can_batch_confirm
        if self.human_reason_required is not None:
            payload["human_reason_required"] = self.human_reason_required
        return payload


def build_review_issue(
    *,
    category: str,
    message: str,
    severity: str = "review",
    source: str = "quality_gate",
    target: str = "",
    field: str = "",
    status: str = "待处理",
    recommendation_id: str = "",
    change_impact_id: str = "",
    confidence: Any = None,
    automation_level: str = "",
    fix_proposal: Any = None,
    can_batch_confirm: Any = None,
    human_reason_required: Any = None,
) -> dict[str, Any]:
    issue = ReviewIssue(
        issue_id=_issue_id(source, category, target, field, recommendation_id, change_impact_id),
        category=str(category or "人工复核"),
        message=str(message or ""),
        severity=str(severity or "review"),
        status=str(status or "待处理"),
        source=str(source or "quality_gate"),
        target=str(target or ""),
        field=str(field or ""),
        recommendation_id=str(recommendation_id or ""),
        change_impact_id=str(change_impact_id or ""),
        confidence=_float_or_none(confidence),
        automation_level=str(automation_level or ""),
        fix_proposal=dict(fix_proposal) if isinstance(fix_proposal, dict) else None,
        can_batch_confirm=_bool_or_none(can_batch_confirm),
        human_reason_required=_bool_or_none(human_reason_required),
    )
    return issue.model_dump()


def review_issue_from_manual_item(item: Any, *, source: str = "quality_gate") -> dict[str, Any]:
    payload = _item_payload(item)
    return build_review_issue(
        category=payload.get("category", "人工复核"),
        message=payload.get("message", "存在需要人工复核的项目。"),
        severity=payload.get("severity", "review"),
        source=source,
        target=payload.get("item_id", payload.get("target", "")),
        field=payload.get("field", ""),
    )


def unresolved_review_issues(items: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "待处理")).strip()
        if status in RESOLVED_REVIEW_ISSUE_STATUSES:
            continue
        if status == "已忽略" and str(item.get("ignore_reason", "")).strip():
            continue
        result.append(item)
    return result


def _issue_id(
    source: str,
    category: str,
    target: str,
    field: str,
    recommendation_id: str,
    change_impact_id: str,
) -> str:
    raw = "|".join(
        str(value or "").strip()
        for value in (source, category, target, field, recommendation_id, change_impact_id)
    )
    slug = "".join(ch if ch.isalnum() else "-" for ch in raw.lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return f"RI-{slug[:160]}" if slug else "RI-review"


def _item_payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "__dict__"):
        return dict(item.__dict__)
    text = str(item or "").strip()
    return {"item_id": text, "category": "人工复核", "message": text, "severity": "review"}


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value in {None, ""} else float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "y"}:
            return True
        if text in {"false", "0", "no", "n"}:
            return False
    return bool(value)
