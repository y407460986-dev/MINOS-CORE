"""Lightweight local knowledge recommendations for three-table drafts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from minos_core._paths import configs_dir
from minos_core.observability.logging import get_logger

logger = get_logger(__name__)


def _default_rules_path() -> Path:
    return configs_dir() / "knowledge" / "fmea_rules.zh-CN.json"


_DEFAULT_RULES_PATH = _default_rules_path()

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
    family_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate knowledge-based recommendations for PFMEA rows.

    Matches each PFMEA row against knowledge rules and family context
    patterns to produce actionable recommendations.

    Args:
        source: The full three-table data source containing process_flow
            and pfmea tables.
        rules: List of knowledge rules to match against. If None, loads
            rules via :func:`load_knowledge_rules`.
        family_context: Optional part-family context for family-based
            pattern matching.

    Returns:
        A deduplicated list of recommendation dicts.
    """
    if rules is None:
        rules = load_knowledge_rules()
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
                recommendations.extend(_recommendations_from_rule(row, step, rule))
    recommendations.extend(
        _recommendations_from_family_context(source, pfd_by_step, family_context)
    )
    return _dedupe_recommendations(recommendations)


def load_knowledge_rules(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load knowledge rules via knowledge_base v2.

    Delegates to :func:`minos_core.knowledge_base.load_knowledge_base` and
    filters to active items only.  The signature is kept backward-compatible:
    callers can still pass *path* or omit it.
    """
    from .knowledge_base import active_knowledge_items, load_knowledge_base

    items = load_knowledge_base(path)
    return active_knowledge_items(items) or [dict(rule) for rule in DEFAULT_KNOWLEDGE_RULES]


def recommend_from_local_knowledge(
    source: dict[str, Any],
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Generate recommendations using local knowledge rules from a file path.

    Convenience wrapper that loads rules from *path* (or the default
    location) and passes them to :func:`recommend_from_knowledge`.

    Args:
        source: The full three-table data source.
        path: Optional path to a knowledge rules file. Falls back to
            the default rules path if omitted.

    Returns:
        A deduplicated list of recommendation dicts.
    """
    return recommend_from_knowledge(source, load_knowledge_rules(path))


def unresolved_recommendations(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter recommendations that are still unresolved (blocking).

    A recommendation is considered unresolved unless it is:
    - applied (lifecycle_status="applied" or status="已应用")
    - ignored with a non-empty ignore_reason
    Expired recommendations are always considered unresolved.

    Args:
        recommendations: List of recommendation dicts to filter.

    Returns:
        List of unresolved recommendation dicts.
    """
    result = []
    for item in recommendations:
        status = str(item.get("status", "待确认")).strip()
        lifecycle = str(item.get("lifecycle_status", "proposed")).strip()
        # applied: never blocks
        if lifecycle == "applied" or status == "已应用":
            continue
        # ignored with reason: does not block
        if (lifecycle == "ignored" or status == "已忽略") and str(item.get("ignore_reason", "")).strip():
            continue
        # expired: always blocks
        if lifecycle == "expired":
            result.append(item)
            continue
        # proposed / accepted: blocks
        result.append(item)
    return result


def _matches_rule(row: dict[str, Any], step: dict[str, Any], rule: dict[str, Any]) -> bool:
    """Check whether a PFMEA row matches a single knowledge rule."""
    # --- requires_high_ap (old format; also supported in new format) ---
    if rule.get("requires_high_ap") and str(row.get("action_priority", row.get("AP", ""))).upper() != "H":
        return False

    # --- requires_special_characteristic (old) / special_characteristic_required (new) ---
    needs_sc = rule.get("requires_special_characteristic") or rule.get("special_characteristic_required")
    if needs_sc and not (
        row.get("classification") or row.get("characteristic_refs") or step.get("special_characteristics")
    ):
        return False

    # --- process_terms (new format) or operation_terms (old format) ---
    # Use process_terms if present (even as empty list); fall back to operation_terms only if absent.
    process_terms = rule.get("process_terms")
    if process_terms is None:
        process_terms = rule.get("operation_terms")

    characteristic_terms = rule.get("characteristic_terms")

    # If the rule has no matching conditions at all, don't match.
    has_any_condition = bool(
        rule.get("requires_high_ap") or needs_sc or process_terms or characteristic_terms
    )
    if not has_any_condition:
        return False

    # --- match process_terms against operation / process_function / failure_mode / failure_cause ---
    if process_terms:
        process_text = " ".join(
            str(value)
            for value in (
                step.get("operation", ""),
                step.get("process_function", ""),
                row.get("failure_mode", ""),
                row.get("failure_cause", ""),
            )
        ).lower()
        if not any(str(term).lower() in process_text for term in process_terms):
            return False

    # --- match characteristic_terms against product/process/special characteristics and row classification/refs ---
    if characteristic_terms:
        char_parts: list[str] = []
        for key in ("product_characteristics", "process_characteristics"):
            val = step.get(key, "")
            if isinstance(val, list):
                char_parts.extend(str(v) for v in val)
            elif val:
                char_parts.append(str(val))
        for key in ("special_characteristics",):
            val = step.get(key, "")
            if isinstance(val, list):
                char_parts.extend(str(v) for v in val)
            elif val:
                char_parts.append(str(val))
        for key in ("characteristic_refs",):
            val = row.get(key, "")
            if isinstance(val, list):
                char_parts.extend(str(v) for v in val)
            elif val:
                char_parts.append(str(val))
        classification = row.get("classification", "")
        if classification:
            char_parts.append(str(classification))
        char_text = " ".join(char_parts).lower()
        if not any(str(term).lower() in char_text for term in characteristic_terms):
            return False

    return True


def _recommendation(row: dict[str, Any], step: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    """Build a single recommendation dict from a matched rule."""
    pfmea_id = str(row.get("pfmea_id", "")).strip()
    rule_id = str(rule.get("knowledge_id", rule.get("rule_id", ""))).strip()

    # --- linked_control_plan_suggestion ---
    linked_cp = None
    controls = rule.get("recommended_controls", {})
    if isinstance(controls, dict):
        cp_parts = {}
        for cp_key in ("measurement_method", "sample_frequency", "reaction_plan"):
            val = controls.get(cp_key)
            if val:
                cp_parts[cp_key] = val
        if cp_parts:
            linked_cp = cp_parts

    # --- suggested_fields: merge risk + controls + rating_hint ---
    suggested_fields: dict[str, Any] = {}
    existing_sf = rule.get("suggested_fields", {})
    if isinstance(existing_sf, dict):
        suggested_fields.update(existing_sf)

    risk = rule.get("risk", {})
    if isinstance(risk, dict):
        for k in ("failure_mode", "failure_effect", "failure_cause"):
            if risk.get(k):
                suggested_fields.setdefault(k, risk[k])

    if isinstance(controls, dict):
        for k in ("prevention_control", "detection_control"):
            if controls.get(k):
                suggested_fields.setdefault(k, controls[k])

    rating = rule.get("rating_hint", {})
    if isinstance(rating, dict):
        for k in ("severity", "occurrence", "detection"):
            if rating.get(k) is not None:
                suggested_fields.setdefault(k, rating[k])

    # --- recommendation_type: use explicit if set; otherwise auto-detect from rule content ---
    rec_type = rule.get("recommendation_type", "")
    if not rec_type:
        has_risk_fm = isinstance(risk, dict) and bool(risk.get("failure_mode"))
        has_risk_fc = isinstance(risk, dict) and bool(risk.get("failure_cause"))
        has_ctrl_pc = isinstance(controls, dict) and bool(controls.get("prevention_control"))
        has_ctrl_dc = isinstance(controls, dict) and bool(controls.get("detection_control"))
        has_ctrl = isinstance(controls, dict) and bool(controls)
        has_rating = isinstance(rating, dict) and bool(rating)

        all_present = has_risk_fm and has_risk_fc and has_ctrl_pc and has_ctrl_dc and has_rating and has_ctrl
        if all_present:
            rec_type = "comprehensive"
        elif has_risk_fm:
            rec_type = "failure_mode"
        elif has_risk_fc:
            rec_type = "failure_cause"
        elif has_ctrl_pc:
            rec_type = "prevention_control"
        elif has_ctrl_dc:
            rec_type = "detection_control"
        elif has_ctrl:
            rec_type = "control_plan"
        elif has_rating:
            rec_type = "rating_hint"
        else:
            rec_type = "知识库推荐"

    # --- recommendation_id: new format with knowledge_id, old format fallback ---
    rec_type_str = str(rec_type).strip()
    recommendation_id = f"{rule_id}:{rec_type_str}:{pfmea_id}" if rule.get("knowledge_id") else f"{rule_id}:{pfmea_id}"

    return {
        "recommendation_id": recommendation_id,
        "target_table": "pfmea",
        "target_id": pfmea_id,
        "recommendation_type": rec_type,
        "source": rule_id,
        "reason": rule.get("message", ""),
        "confidence": rule.get("confidence", 0.0),
        "suggested_fields": suggested_fields,
        "linked_control_plan_suggestion": linked_cp,
        "ai_inferred": False,
        "needs_confirmation": True,
        "status": "待确认",
        "lifecycle_status": "proposed",
        "ignore_reason": "",
        "process_step_id": row.get("process_step_id", step.get("process_step_id", "")),
        "knowledge_id": rule.get("knowledge_id", rule.get("rule_id", "")),
        "knowledge_version": rule.get("version", "1.0"),
        "created_from": "knowledge_base",
        "decision": "",
        "decision_reason": "",
        "applied_fields": [],
        "source_refs": _source_refs(rule),
        "is_special_characteristic_rule": _rule_is_special_characteristic_rule(rule),
        "special_characteristic_primary": _rule_is_generic_special_characteristic_rule(rule),
    }


def _recommendations_from_rule(
    row: dict[str, Any], step: dict[str, Any], rule: dict[str, Any]
) -> list[dict[str, Any]]:
    """Generate one or more recommendations from a single matching rule.

    For new-format rules that carry multiple recommendation dimensions
    (failure_mode, failure_cause, prevention_control, detection_control,
    control_plan, rating_hint), a separate recommendation is emitted for
    each dimension so that the user can accept/ignore them independently.
    Old-format rules (with an explicit ``recommendation_type`` and no
    risk/controls/rating_hint blocks) produce a single recommendation.
    """
    risk = rule.get("risk", {})
    controls = rule.get("recommended_controls", {})
    rating = rule.get("rating_hint", {})

    has_risk_fm = isinstance(risk, dict) and bool(risk.get("failure_mode"))
    has_risk_fc = isinstance(risk, dict) and bool(risk.get("failure_cause"))
    has_ctrl_pc = isinstance(controls, dict) and bool(controls.get("prevention_control"))
    has_ctrl_dc = isinstance(controls, dict) and bool(controls.get("detection_control"))
    has_ctrl_cp = isinstance(controls, dict) and bool(
        controls.get("measurement_method") or controls.get("sample_frequency") or controls.get("reaction_plan")
    )
    has_rating = isinstance(rating, dict) and bool(rating)

    # Collect dimensions present in this rule.
    dimension_types: list[str] = []
    if has_risk_fm:
        dimension_types.append("failure_mode")
    if has_risk_fc:
        dimension_types.append("failure_cause")
    if has_ctrl_pc:
        dimension_types.append("prevention_control")
    if has_ctrl_dc:
        dimension_types.append("detection_control")
    if has_ctrl_cp:
        dimension_types.append("control_plan")
    if has_rating:
        dimension_types.append("rating_hint")

    # Old-style rules (no risk/controls/rating_hint blocks) get a single recommendation.
    if not dimension_types:
        return [_recommendation(row, step, rule)]

    # Build one recommendation per dimension.
    results: list[dict[str, Any]] = []
    pfmea_id = str(row.get("pfmea_id", "")).strip()
    rule_id = str(rule.get("knowledge_id", rule.get("rule_id", ""))).strip()

    # Field subsets for each recommendation type.
    type_fields: dict[str, set[str]] = {
        "failure_mode": {"failure_mode", "failure_effect"},
        "failure_cause": {"failure_cause"},
        "prevention_control": {"prevention_control"},
        "detection_control": {"detection_control"},
        "rating_hint": {"severity", "occurrence", "detection"},
        "control_plan": set(),  # linked_control_plan_suggestion carries CP fields
        "comprehensive": {
            "failure_mode", "failure_effect", "failure_cause",
            "prevention_control", "detection_control",
            "severity", "occurrence", "detection",
        },
    }

    for dim_type in dimension_types:
        rec = _recommendation(row, step, rule)
        generic_special = _rule_is_generic_special_characteristic_rule(rule)
        generic_high_ap = _rule_is_generic_high_ap_rule(rule)
        if generic_special:
            rec_type = "special_characteristic"
        elif generic_high_ap:
            rec_type = f"high_ap_{dim_type}"
        else:
            rec_type = dim_type
        rec["recommendation_type"] = rec_type
        if generic_special:
            rec["recommendation_id"] = f"{rule_id}:{rec_type}:{dim_type}:{pfmea_id}"
        else:
            rec["recommendation_id"] = f"{rule_id}:{rec_type}:{pfmea_id}"

        # Filter suggested_fields to only the fields relevant to this type.
        allowed = type_fields.get(dim_type)
        if allowed is not None:
            sf = rec.get("suggested_fields", {})
            if isinstance(sf, dict):
                rec["suggested_fields"] = {k: v for k, v in sf.items() if k in allowed}

        results.append(rec)

    return results


def _dedupe_recommendations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate and keep the highest-scoring recommendation per key."""
    result: list[dict[str, Any]] = []
    indexes: dict[tuple[str, str, tuple[str, ...]], int] = {}
    for item in items:
        normalized = _normalize_recommendation(item)
        key = _recommendation_dedupe_key(normalized)
        if key in indexes:
            existing_index = indexes[key]
            existing = result[existing_index]
            if _recommendation_score(normalized) > _recommendation_score(existing):
                result[existing_index] = normalized
            continue
        indexes[key] = len(result)
        result.append(normalized)
    return _limit_special_characteristic_recommendations(result)


def _recommendations_from_family_context(
    source: dict[str, Any],
    pfd_by_step: dict[str, dict[str, Any]],
    family_context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Generate recommendations from part-family context patterns."""
    if not isinstance(family_context, dict) or not family_context:
        return []
    if _family_key(family_context) == "unknown":
        return []

    recommendations: list[dict[str, Any]] = []
    rows = [
        row
        for row in _rows(source, "pfmea", "failure_modes", "rows")
        if isinstance(row, dict) and not row.get("deleted")
    ]
    for row in rows:
        step = pfd_by_step.get(str(row.get("process_step_id", "")).strip(), {})
        for pattern in _dict_items(family_context.get("pfmea_patterns")):
            rec = _family_pfmea_recommendation(row, step, pattern, family_context)
            if rec:
                recommendations.append(rec)
        for pattern in _dict_items(family_context.get("control_plan_patterns")):
            rec = _family_control_plan_recommendation(row, step, pattern, family_context)
            if rec:
                recommendations.append(rec)
    return recommendations


def _family_pfmea_recommendation(
    row: dict[str, Any],
    step: dict[str, Any],
    pattern: dict[str, Any],
    family_context: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a PFMEA pattern recommendation from a family match."""
    match = _family_match(row, step, pattern, family_context)
    if match is None:
        return None

    suggested_fields: dict[str, Any] = {}
    for field in (
        "failure_mode",
        "failure_effect",
        "failure_cause",
        "classification",
        "prevention_control",
        "detection_control",
    ):
        value = pattern.get(field)
        if _has_value(value):
            suggested_fields[field] = value

    rating = pattern.get("rating_hint", {})
    if isinstance(rating, dict):
        for field in ("severity", "occurrence", "detection", "action_priority"):
            value = rating.get(field)
            if _has_value(value):
                suggested_fields[field] = value

    if not suggested_fields:
        return None

    pattern_id = _pattern_id(pattern, family_context, "pfmea")
    pfmea_id = str(row.get("pfmea_id", "")).strip()
    family_name = str(family_context.get("family_name") or family_context.get("name") or "").strip()
    rec = {
        "recommendation_id": f"{pattern_id}:pfmea_pattern:{pfmea_id}",
        "target_table": "pfmea",
        "target_id": pfmea_id,
        "recommendation_type": "pfmea_pattern",
        "source": pattern_id,
        "reason": f"基于{family_name or '零件族'} PFMEA 历史模式，建议复核并补充相似风险字段。",
        "confidence": match["score"] / 100,
        "score": match["score"],
        "match_level": match["match_level"],
        "suggested_fields": suggested_fields,
        "linked_control_plan_suggestion": None,
        "source_refs": _source_refs(pattern, family_context),
        "ai_inferred": False,
        "needs_confirmation": True,
        "status": "待确认",
        "lifecycle_status": "proposed",
        "ignore_reason": "",
        "process_step_id": row.get("process_step_id", step.get("process_step_id", "")),
        "knowledge_id": pattern_id,
        "knowledge_version": family_context.get("schema_version", "part_family"),
        "created_from": "part_family_knowledge",
        "decision": "",
        "decision_reason": "",
        "applied_fields": [],
    }
    return _normalize_recommendation(rec)


def _family_control_plan_recommendation(
    row: dict[str, Any],
    step: dict[str, Any],
    pattern: dict[str, Any],
    family_context: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a control-plan pattern recommendation from a family match."""
    match = _family_match(row, step, pattern, family_context)
    if match is None:
        return None

    linked_cp: dict[str, Any] = {}
    field_map = {
        "characteristic": "product_process_characteristic",
        "classification": "classification",
        "specification": "specification",
        "measurement_method": "measurement_method",
        "sample_size": "sample_size",
        "sample_frequency": "sample_frequency",
        "control_method": "control_method",
        "reaction_plan": "reaction_plan",
    }
    for source_field, target_field in field_map.items():
        value = pattern.get(source_field)
        if _has_value(value):
            linked_cp[target_field] = value

    suggested_fields: dict[str, Any] = {}
    classification = pattern.get("classification")
    if _has_value(classification):
        suggested_fields["classification"] = classification

    if not linked_cp and not suggested_fields:
        return None

    pattern_id = _pattern_id(pattern, family_context, "control_plan")
    pfmea_id = str(row.get("pfmea_id", "")).strip()
    family_name = str(family_context.get("family_name") or family_context.get("name") or "").strip()
    rec = {
        "recommendation_id": f"{pattern_id}:control_plan_pattern:{pfmea_id}",
        "target_table": "pfmea",
        "target_id": pfmea_id,
        "recommendation_type": "control_plan_pattern",
        "source": pattern_id,
        "reason": f"基于{family_name or '零件族'}控制计划历史模式，建议复核控制方法、频次和反应计划。",
        "confidence": match["score"] / 100,
        "score": match["score"],
        "match_level": match["match_level"],
        "suggested_fields": suggested_fields,
        "linked_control_plan_suggestion": linked_cp or None,
        "source_refs": _source_refs(pattern, family_context),
        "ai_inferred": False,
        "needs_confirmation": True,
        "status": "待确认",
        "lifecycle_status": "proposed",
        "ignore_reason": "",
        "process_step_id": row.get("process_step_id", step.get("process_step_id", "")),
        "knowledge_id": pattern_id,
        "knowledge_version": family_context.get("schema_version", "part_family"),
        "created_from": "part_family_knowledge",
        "decision": "",
        "decision_reason": "",
        "applied_fields": [],
    }
    return _normalize_recommendation(rec)


def _family_match(
    row: dict[str, Any],
    step: dict[str, Any],
    pattern: dict[str, Any],
    family_context: dict[str, Any],
) -> dict[str, Any] | None:
    """Score how well a PFMEA row matches a family pattern."""
    same_family = _same_family_context(family_context)
    operation_match = _operation_matches(row, step, pattern)
    characteristic_match = _characteristic_matches(row, step, pattern)

    if same_family and operation_match and characteristic_match:
        return {"score": 100, "match_level": "family_operation_characteristic"}
    if same_family and operation_match:
        return {"score": 85, "match_level": "family_operation"}
    if operation_match and characteristic_match:
        return {"score": 75, "match_level": "operation_characteristic"}
    if _is_global_pattern(pattern):
        return {"score": 55, "match_level": "global"}
    return None


def _operation_matches(
    row: dict[str, Any],
    step: dict[str, Any],
    pattern: dict[str, Any],
) -> bool:
    """Check whether a pattern's operation text matches the row or step."""
    pattern_step = str(pattern.get("process_step_id", "")).strip()
    row_step = str(row.get("process_step_id", step.get("process_step_id", ""))).strip()
    if pattern_step and row_step and pattern_step == row_step:
        return True
    pattern_texts = _texts(pattern, ("operation", "process_function", "process_step_name"))
    row_texts = _texts(
        step,
        ("operation", "process_function", "process_step_name"),
    ) + _texts(
        row,
        ("operation", "process_function", "process_step_name", "process_step_operation"),
    )
    return _text_lists_match(pattern_texts, row_texts)


def _characteristic_matches(
    row: dict[str, Any],
    step: dict[str, Any],
    pattern: dict[str, Any],
) -> bool:
    """Check whether a pattern's characteristic text matches the row or step."""
    pattern_texts = _texts(
        pattern,
        ("characteristic", "classification", "failure_mode", "product_process_characteristic"),
    )
    row_texts = _texts(
        row,
        (
            "classification",
            "failure_mode",
            "product_process_characteristic",
            "characteristic",
            "product_characteristics",
            "process_characteristics",
            "characteristic_refs",
            "special_characteristics",
        ),
    ) + _texts(
        step,
        (
            "product_characteristics",
            "process_characteristics",
            "special_characteristics",
        ),
    )
    return _text_lists_match(pattern_texts, row_texts)


def _is_global_pattern(pattern: dict[str, Any]) -> bool:
    """Check whether a pattern has no operation or characteristic fields."""
    operation_fields = _texts(pattern, ("process_step_id", "operation", "process_function"))
    characteristic_fields = _texts(
        pattern,
        ("characteristic", "classification", "failure_mode", "product_process_characteristic"),
    )
    return not operation_fields and not characteristic_fields


def _same_family_context(family_context: dict[str, Any]) -> bool:
    """Check whether the family context identifies a known part family."""
    key = _family_key(family_context)
    if key and key != "unknown":
        return True
    name = str(family_context.get("family_name") or family_context.get("name") or "").strip()
    return bool(name and name != "未知零件族")


def _family_key(family_context: dict[str, Any]) -> str:
    """Extract the family key identifier from a family context dict."""
    return str(family_context.get("family_key") or family_context.get("key") or "").strip()


def _pattern_id(pattern: dict[str, Any], family_context: dict[str, Any], kind: str) -> str:
    """Derive a stable pattern identifier from the pattern or family context."""
    value = str(pattern.get("pattern_id") or pattern.get("knowledge_id") or pattern.get("id") or "").strip()
    if value:
        return value
    family_key = _family_key(family_context) or "part_family"
    return f"{family_key}-{kind}-pattern"


def _normalize_recommendation(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a recommendation dict by adding computed fields."""
    normalized = dict(item)
    normalized["target_field_keys"] = _target_field_keys(normalized)
    normalized.setdefault("source_refs", _source_refs(normalized))
    if not _has_value(normalized.get("score")):
        normalized["score"] = round(float(normalized.get("confidence", 0.0) or 0.0) * 100)
    normalized.setdefault("match_level", "knowledge_rule")
    return normalized


def _target_field_keys(item: dict[str, Any]) -> list[str]:
    """Extract field key strings from suggested_fields and linked_control_plan_suggestion."""
    keys: list[str] = []
    target_table = str(item.get("target_table", "")).strip()
    suggested_fields = item.get("suggested_fields", {})
    if isinstance(suggested_fields, dict):
        for field in suggested_fields:
            if isinstance(field, str) and field:
                keys.append(f"{target_table}.{field}" if target_table else field)
    linked_cp = item.get("linked_control_plan_suggestion", {})
    if isinstance(linked_cp, dict):
        for field in linked_cp:
            if isinstance(field, str) and field:
                keys.append(f"control_plan.{field}")
    return sorted(set(keys))


def _recommendation_dedupe_key(item: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    """Compute a deduplication key from target_id, recommendation_type, and field_keys."""
    target_id = str(item.get("target_id", "")).strip()
    rec_type = str(item.get("recommendation_type", "")).strip()
    field_keys = tuple(item.get("target_field_keys", []))
    if target_id or rec_type or field_keys:
        return (target_id, rec_type, field_keys)
    rec_id = str(item.get("recommendation_id", "")).strip()
    return (rec_id, "", ())


def _recommendation_score(item: dict[str, Any]) -> float:
    """Extract the numeric score from a recommendation item."""
    try:
        return float(item.get("score", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _limit_special_characteristic_recommendations(
    items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keep only the highest-scoring special-characteristic recommendation per target."""
    best_index_by_target: dict[str, int] = {}
    best_score_by_target: dict[str, float] = {}
    for index, item in enumerate(items):
        if not item.get("special_characteristic_primary"):
            continue
        target_id = str(item.get("target_id", "")).strip()
        if not target_id:
            continue
        score = _recommendation_score(item)
        if target_id not in best_index_by_target or score > best_score_by_target[target_id]:
            best_index_by_target[target_id] = index
            best_score_by_target[target_id] = score

    result: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if item.get("special_characteristic_primary"):
            target_id = str(item.get("target_id", "")).strip()
            if target_id and best_index_by_target.get(target_id) != index:
                continue
        result.append(item)
    return result


def _rule_is_special_characteristic_rule(rule: dict[str, Any]) -> bool:
    """Check whether a rule targets special characteristics."""
    return bool(
        rule.get("requires_special_characteristic")
        or rule.get("special_characteristic_required")
    )


def _rule_is_generic_special_characteristic_rule(rule: dict[str, Any]) -> bool:
    """Check whether a rule is a generic special-characteristic rule (no terms)."""
    if not _rule_is_special_characteristic_rule(rule):
        return False
    return not bool(rule.get("process_terms") or rule.get("operation_terms") or rule.get("characteristic_terms"))


def _rule_is_generic_high_ap_rule(rule: dict[str, Any]) -> bool:
    """Check whether a rule is a generic high-AP rule (no terms)."""
    if not rule.get("requires_high_ap"):
        return False
    return not bool(rule.get("process_terms") or rule.get("operation_terms") or rule.get("characteristic_terms"))


def _source_refs(*items: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect deduplicated source references from one or more dicts."""
    refs: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("source_refs", "knowledge_source_refs", "source_ref", "knowledge_source_ref"):
            value = item.get(key)
            if isinstance(value, list):
                for ref in value:
                    normalized = _source_ref(ref)
                    if normalized:
                        refs.append(normalized)
            else:
                normalized = _source_ref(value)
                if normalized:
                    refs.append(normalized)
        source = item.get("source")
        if isinstance(source, str) and source.strip():
            refs.append({"source_id": source.strip()})
    result: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for ref in refs:
        ref_key = tuple(sorted((name, str(value)) for name, value in ref.items()))
        if ref_key in seen:
            continue
        seen.add(ref_key)
        result.append(ref)
    return result


def _source_ref(value: Any) -> dict[str, Any]:
    """Normalize a single source reference value into a dict."""
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items() if _has_value(item)}
    if isinstance(value, str) and value.strip():
        return {"source_id": value.strip()}
    return {}


def _dict_items(value: Any) -> list[dict[str, Any]]:
    """Extract a list of dicts from a value, or return an empty list."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _texts(row: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    """Collect non-empty string values for the given keys from a dict."""
    values: list[str] = []
    for key in keys:
        values.extend(_string_values(row.get(key)))
    return values


def _string_values(value: Any) -> list[str]:
    """Flatten a nested value (list, dict, or scalar) into a list of stripped strings."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(_string_values(item))
        return result
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(_string_values(item))
        return result
    text = str(value).strip()
    return [text] if text else []


def _text_lists_match(left: list[str], right: list[str]) -> bool:
    """Check whether any string in *left* is related to any string in *right*."""
    return any(_texts_related(a, b) for a in left for b in right)


def _texts_related(left: str, right: str) -> bool:
    """Check whether two texts are related by substring or token overlap."""
    a = _normalize_match_text(left)
    b = _normalize_match_text(right)
    if not a or not b:
        return False
    if len(a) >= 2 and len(b) >= 2 and (a in b or b in a):
        return True
    left_tokens = {token for token in a.split() if len(token) >= 2}
    right_tokens = {token for token in b.split() if len(token) >= 2}
    return bool(left_tokens and right_tokens and left_tokens & right_tokens)


def _normalize_match_text(value: Any) -> str:
    """Normalize text for fuzzy matching by lowercasing and splitting punctuation."""
    text = str(value or "").lower().strip()
    for char in ("，", "。", "；", ";", ",", "/", "\\", "|", "、", ":", "：", "-", "_", "(", ")", "（", "）"):
        text = text.replace(char, " ")
    return " ".join(text.split())


def _has_value(value: Any) -> bool:
    """Check whether a value is non-empty (not None, not blank string, not empty collection)."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _load_json_rules(path: Path) -> list[dict[str, Any]]:
    """Load knowledge rules from a JSON file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        rules = payload.get("rules", [])
        if isinstance(rules, list):
            return [item for item in rules if isinstance(item, dict)]
    return []


def _load_sqlite_rules(path: Path) -> list[dict[str, Any]]:
    """Load knowledge rules from a SQLite database."""
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
    """Extract rows from a source dict by trying table.table_key then chain_key."""
    if table in source and isinstance(source.get(table), dict):
        rows = source[table].get(table_key)
        if isinstance(rows, list):
            return rows
    rows = source.get(chain_key)
    return rows if isinstance(rows, list) else []
