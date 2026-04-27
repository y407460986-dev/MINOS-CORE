"""Lightweight local knowledge recommendations for three-table drafts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_KNOWLEDGE_RULES = [
    {
        "rule_id": "KR-INSPECTION-GAUGE",
        "operation_terms": ("检验", "inspection", "check", "verify"),
        "recommendation_type": "探测控制",
        "message": "检验工序建议确认检具校准状态、检验频次和记录要求。",
        "suggested_fields": {"detection_control": "确认检具校准状态并记录检验结果"},
        "confidence": 0.82,
    },
    {
        "rule_id": "KR-SPECIAL-CHARACTERISTIC-CP",
        "requires_special_characteristic": True,
        "recommendation_type": "控制计划",
        "message": "特殊特性建议进入控制计划，并明确检具、频次和反应计划。",
        "suggested_fields": {"sample_frequency": "首件和定期巡检", "reaction_plan": "隔离并通知质量工程师"},
        "confidence": 0.9,
    },
    {
        "rule_id": "KR-HIGH-AP-REACTION",
        "requires_high_ap": True,
        "recommendation_type": "反应计划",
        "message": "高 AP 风险建议定义停机、隔离、通知质量和重启验证。",
        "suggested_fields": {"reaction_plan": "停机，隔离可疑产品，通知质量人员，并在重启前验证纠正措施"},
        "confidence": 0.88,
    },
]


def recommend_from_knowledge(
    source: dict[str, Any],
    rules: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rules = rules or DEFAULT_KNOWLEDGE_RULES
    recommendations: list[dict[str, Any]] = []
    pfd_by_step = {
        str(row.get("process_step_id", "")).strip(): row
        for row in _rows(source, "process_flow", "process_steps", "steps")
        if isinstance(row, dict)
    }
    for row in _rows(source, "pfmea", "failure_modes", "rows"):
        if not isinstance(row, dict) or row.get("deleted"):
            continue
        step = pfd_by_step.get(str(row.get("process_step_id", "")).strip(), {})
        for rule in rules:
            if _matches_rule(row, step, rule):
                recommendations.append(_recommendation(row, step, rule))
    return _dedupe_recommendations(recommendations)


def load_knowledge_rules(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load local knowledge rules, falling back to built-in seed rules."""

    if path is None:
        return [dict(rule) for rule in DEFAULT_KNOWLEDGE_RULES]
    file_path = Path(path)
    if not file_path.exists():
        return [dict(rule) for rule in DEFAULT_KNOWLEDGE_RULES]
    if file_path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        loaded = _load_sqlite_rules(file_path)
    else:
        loaded = _load_json_rules(file_path)
    return loaded or [dict(rule) for rule in DEFAULT_KNOWLEDGE_RULES]


def recommend_from_local_knowledge(
    source: dict[str, Any],
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    return recommend_from_knowledge(source, load_knowledge_rules(path))


def unresolved_recommendations(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in recommendations:
        status = str(item.get("status", "待确认")).strip()
        if status == "已采纳":
            continue
        if status == "已忽略" and str(item.get("ignore_reason", "")).strip():
            continue
        result.append(item)
    return result


def _matches_rule(row: dict[str, Any], step: dict[str, Any], rule: dict[str, Any]) -> bool:
    if rule.get("requires_high_ap") and str(row.get("action_priority", row.get("AP", ""))).upper() != "H":
        return False
    if rule.get("requires_special_characteristic") and not (
        row.get("classification") or row.get("characteristic_refs") or step.get("special_characteristics")
    ):
        return False
    terms = rule.get("operation_terms")
    if terms:
        text = " ".join(
            str(value)
            for value in (
                step.get("operation", ""),
                step.get("process_function", ""),
                row.get("failure_mode", ""),
                row.get("failure_cause", ""),
            )
        ).lower()
        return any(str(term).lower() in text for term in terms)
    return bool(rule.get("requires_high_ap") or rule.get("requires_special_characteristic"))


def _recommendation(row: dict[str, Any], step: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    pfmea_id = str(row.get("pfmea_id", "")).strip()
    rule_id = str(rule.get("rule_id", "")).strip()
    return {
        "recommendation_id": f"{rule_id}:{pfmea_id}",
        "target_table": "pfmea",
        "target_id": pfmea_id,
        "recommendation_type": rule.get("recommendation_type", "知识库推荐"),
        "source": rule_id,
        "reason": rule.get("message", ""),
        "confidence": rule.get("confidence", 0.0),
        "suggested_fields": dict(rule.get("suggested_fields", {})),
        "ai_inferred": False,
        "needs_confirmation": True,
        "status": "待确认",
        "ignore_reason": "",
        "process_step_id": row.get("process_step_id", step.get("process_step_id", "")),
    }


def _dedupe_recommendations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get("recommendation_id", "")).strip()
        if key and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _load_json_rules(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        rules = payload.get("rules", [])
        if isinstance(rules, list):
            return [item for item in rules if isinstance(item, dict)]
    return []


def _load_sqlite_rules(path: Path) -> list[dict[str, Any]]:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT rule_id, category, payload_json, enabled
            FROM knowledge_rules
            WHERE enabled = 1
            ORDER BY rule_id
            """
        ).fetchall()
    rules: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("rule_id", str(row["rule_id"]))
        payload.setdefault("knowledge_type", str(row["category"]))
        rules.append(payload)
    return rules


def _rows(source: dict[str, Any], table: str, chain_key: str, table_key: str) -> list[Any]:
    if table in source and isinstance(source.get(table), dict):
        rows = source[table].get(table_key)
        if isinstance(rows, list):
            return rows
    rows = source.get(chain_key)
    return rows if isinstance(rows, list) else []
