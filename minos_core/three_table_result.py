"""Result envelope helpers for drawing-driven three-table generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._text_utils import float_or_none, string_list, text
from .run_manifest import build_run_manifest, write_run_manifest


CANONICAL_THREE_TABLE_SCHEMA_VERSION = "minos-core.generated.v1"


def canonical_three_table_bundle(
    bundle: dict[str, Any] | None,
    *,
    document_type: str,
    row_key: str,
) -> dict[str, Any]:
    """Return one canonical PFD/PFMEA/CP stage bundle.

    Compatibility aliases are read here, then the returned bundle uses the
    canonical row container passed by ``row_key``.
    """

    source = dict(bundle or {})
    schema_version = text(
        source.get("schema_version"), CANONICAL_THREE_TABLE_SCHEMA_VERSION
    )
    rows = _canonical_rows(
        _bundle_rows(source, document_type=document_type, row_key=row_key),
        schema_version=schema_version,
    )
    source["document_type"] = document_type
    source["schema_version"] = schema_version
    source[row_key] = rows
    return source


def build_canonical_three_table_bundle(
    *,
    process_flow: dict[str, Any] | None,
    pfmea: dict[str, Any] | None,
    control_plan: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Build the canonical three-table bundle map used inside core."""

    return {
        "process_flow": canonical_three_table_bundle(
            process_flow, document_type="process_flow", row_key="steps"
        ),
        "pfmea": canonical_three_table_bundle(
            pfmea, document_type="pfmea", row_key="rows"
        ),
        "control_plan": canonical_three_table_bundle(
            control_plan, document_type="control_plan", row_key="rows"
        ),
    }


def build_three_table_generation_envelope(
    *,
    status: str,
    drawing_analysis: dict[str, Any] | None,
    process_flow: dict[str, Any] | None,
    pfmea: dict[str, Any] | None,
    control_plan: dict[str, Any] | None,
    chain: dict[str, Any] | None,
    quality_gates: dict[str, Any],
    exports: dict[str, Any],
    output_dir: Path,
    inputs: dict[str, Any],
    blocked_stage: str | None,
    warnings: list[str],
    manual_review: dict[str, Any] | None = None,
    linkage_map: dict[str, Any] | None = None,
    linkage_gaps: list[dict[str, Any]] | None = None,
    characteristic_registry: dict[str, Any] | None = None,
    knowledge_recommendations: list[dict[str, Any]] | None = None,
    risk_structure: dict[str, Any] | None = None,
    review_dashboard: dict[str, Any] | None = None,
    part_family_classification: dict[str, Any] | None = None,
    family_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "part_family_classification": part_family_classification or {},
        "family_context": family_context or {},
    }
    envelope: dict[str, Any] = {
        "document_type": "three_table_generation_result",
        "schema_version": "minos-core.three_table_generation_result.v1",
        "status": status,
        "status_display": three_table_status_display(status),
        "blocked_stage": blocked_stage,
        "drawing_analysis": drawing_analysis,
        "process_flow": process_flow,
        "pfmea": pfmea,
        "control_plan": control_plan,
        "chain": chain,
        "quality_gate": quality_gates.get("final_three_table")
        or _last_mapping_value(quality_gates),
        "quality_gates": quality_gates,
        "exports": exports,
        "manifest": {},
        "metadata": metadata,
        "manual_review": manual_review or three_table_manual_review(quality_gates),
        "warnings": warnings,
        "linkage_map": linkage_map or {},
        "linkage_gaps": linkage_gaps or [],
        "characteristic_registry": characteristic_registry or {},
        "knowledge_recommendations": knowledge_recommendations or [],
        "risk_structure": risk_structure or {},
        "review_dashboard": review_dashboard or {},
    }
    manifest = build_run_manifest(
        inputs=inputs,
        outputs={"status": status, "exports": exports},
        stage_results=_three_table_stage_results(quality_gates),
        quality_gates=list(quality_gates.values()),
        review_confirmations=[],
        artifacts=_three_table_artifacts(
            drawing_analysis=drawing_analysis,
            process_flow=process_flow,
            pfmea=pfmea,
            control_plan=control_plan,
            chain=chain,
            exports=exports,
            linkage_map=linkage_map,
            linkage_gaps=linkage_gaps,
            characteristic_registry=characteristic_registry,
            knowledge_recommendations=knowledge_recommendations,
            risk_structure=risk_structure,
            part_family_classification=part_family_classification,
            family_context=family_context,
        ),
        warnings=warnings,
    )
    manifest_path = write_run_manifest(output_dir / "run_manifest.json", manifest)
    envelope["manifest"] = {
        "path": str(manifest_path),
        "run_id": manifest.get("run_id", ""),
        "artifact_hashes": manifest.get("artifact_hashes", {}),
    }
    return envelope


def three_table_manual_review(quality_gates: dict[str, Any]) -> dict[str, Any]:
    items: list[Any] = []
    for gate in quality_gates.values():
        if not isinstance(gate, dict):
            continue
        items.extend(gate.get("manual_review_items", []))
        items.extend(gate.get("needs_confirmation_items", []))
    raw_items = _dedupe_manual_review_items(items)
    grouped_items = _group_three_table_manual_review_items(raw_items)
    return {
        "required": bool(raw_items),
        "items": grouped_items,
        "raw_items": raw_items,
        "raw_count": len(raw_items),
        "summary": _manual_review_summary(grouped_items, len(raw_items)),
    }


def three_table_status_display(status: str) -> str:
    return {
        "draft_ready": "草案已就绪",
        "needs_review": "待人工复核",
        "blocked": "已阻断",
    }.get(status, status)


def _bundle_rows(
    bundle: dict[str, Any],
    *,
    document_type: str,
    row_key: str,
) -> list[Any]:
    rows = bundle.get(row_key)
    if isinstance(rows, list):
        return rows
    if document_type == "process_flow":
        rows = bundle.get("process_steps")
    elif document_type == "pfmea":
        rows = bundle.get("failure_modes") or bundle.get("pfmea_items")
    elif document_type == "control_plan":
        rows = bundle.get("controls") or bundle.get("control_plan_items")
    return rows if isinstance(rows, list) else []


def _canonical_rows(rows: list[Any], *, schema_version: str) -> list[Any]:
    return [
        _canonical_row(row, schema_version=schema_version)
        if isinstance(row, dict)
        else row
        for row in rows
    ]


def _canonical_row(row: dict[str, Any], *, schema_version: str) -> dict[str, Any]:
    normalized = dict(row)
    normalized["schema_version"] = text(
        normalized.get("schema_version"), schema_version
    )
    normalized["evidence_refs"] = string_list(normalized.get("evidence_refs", []))
    confidence = float_or_none(normalized.get("confidence"))
    normalized["confidence"] = max(0.0, min(confidence, 1.0)) if confidence is not None else 0.0
    normalized["ai_inferred"] = bool(normalized.get("ai_inferred", True))
    normalized["needs_confirmation"] = bool(
        normalized.get(
            "needs_confirmation",
            not normalized["evidence_refs"] or normalized["confidence"] == 0.0,
        )
    )

    refs = _characteristic_refs(
        normalized.get("characteristic_refs"),
        normalized.get("special_characteristics"),
        normalized.get("source_special_characteristics"),
    )
    explicit_special_class = text(normalized.get("special_characteristic_class"))
    special_class = explicit_special_class or _special_class(
        normalized.get("classification"),
        normalized.get("product_characteristic_class"),
        normalized.get("process_characteristic_class"),
        normalized.get("special_characteristics"),
    )
    if special_class in {"", "无"}:
        special_class = _special_class_from_refs(refs)
    normalized["special_characteristic_class"] = special_class
    normalized["characteristic_refs"] = refs
    normalized.pop("classification", None)
    return normalized


def _special_class(*values: Any) -> str:
    for value in values:
        marker = text(value).upper()
        if marker in {"SC", "CC"}:
            return marker
        for item in string_list(value):
            marker = item.upper()
            if marker in {"SC", "CC"}:
                return marker
    return "无"


def _special_class_from_refs(refs: list[str]) -> str:
    if any(ref == "CC" or ref.startswith("CC-") for ref in refs):
        return "CC"
    if any(ref == "SC" or ref.startswith("SC-") for ref in refs):
        return "SC"
    return "无"


def _characteristic_refs(*sources: Any) -> list[str]:
    refs: list[str] = []
    for source in sources:
        for item in string_list(source):
            if item in {"无", "SC", "CC"}:
                continue
            if item and item not in refs:
                refs.append(item)
    return refs


def dedupe_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _three_table_stage_results(quality_gates: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "stage": stage,
            "status": "ok" if gate.get("can_continue") else "blocked",
            "quality_gate": gate,
        }
        for stage, gate in quality_gates.items()
        if isinstance(gate, dict)
    ]


def _group_three_table_manual_review_items(items: list[Any]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for item in items:
        normalized = _manual_review_record(item)
        bucket_key = _manual_review_bucket_key(normalized)
        bucket = buckets.setdefault(
            bucket_key,
            {
                "item_id": bucket_key,
                "category": _manual_review_bucket_category(bucket_key),
                "message": _manual_review_bucket_message(bucket_key),
                "severity": _manual_review_bucket_severity(normalized),
                "severity_display": _manual_review_severity_display(
                    _manual_review_bucket_severity(normalized)
                ),
                "count": 0,
                "examples": [],
            },
        )
        bucket["count"] += 1
        if normalized["target"] and len(bucket["examples"]) < 8:
            bucket["examples"].append(normalized["target"])
        if normalized["severity"] == "blocker":
            bucket["severity"] = "blocker"
            bucket["severity_display"] = _manual_review_severity_display("blocker")
    return list(buckets.values())


def _manual_review_record(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        target = ""
        for field_name in ("item_id", "id", "field", "target"):
            value = str(item.get(field_name, "")).strip()
            if value:
                target = value
                break
        return {
            "target": target,
            "category": str(item.get("category", "")).strip(),
            "message": str(item.get("message", "")).strip(),
            "severity": str(item.get("severity", "review")).strip() or "review",
        }
    if hasattr(item, "__dict__"):
        return _manual_review_record(dict(item.__dict__))
    text = str(item).strip()
    return {
        "target": text,
        "category": "",
        "message": "",
        "severity": "review",
    }


def _manual_review_bucket_key(item: dict[str, str]) -> str:
    category = item.get("category", "")
    target = item.get("target", "")
    if category.startswith("drawing_recognition"):
        return "drawing_recognition"
    if category.startswith("pfd") or target.startswith(("process_step:", "trace_link:")):
        return "process_flow_review"
    if category.startswith("pfmea") or target.startswith(("PFMEA-", "failure_mode:")):
        return "pfmea_review"
    if category == "知识库推荐":
        return "pfmea_review"
    if category.startswith("control_plan") or target.startswith(("CP-", "control_item:")):
        return "control_plan_review"
    if category.startswith("evidence"):
        return "evidence_review"
    if category.startswith("row_needs_confirmation"):
        if target.startswith("failure_mode:"):
            return "pfmea_review"
        if target.startswith("control_item:"):
            return "control_plan_review"
        if target.startswith(("process_step:", "trace_link:")):
            return "process_flow_review"
        return "row_confirmation_review"
    return category or "manual_review"


def _manual_review_bucket_category(key: str) -> str:
    return {
        "drawing_recognition": "图纸识别复核",
        "process_flow_review": "过程流程图复核",
        "pfmea_review": "PFMEA 复核",
        "control_plan_review": "控制计划复核",
        "evidence_review": "证据链复核",
        "row_confirmation_review": "草案确认复核",
        "manual_review": "人工复核",
    }.get(key, "人工复核")


def _manual_review_bucket_message(key: str) -> str:
    return {
        "drawing_recognition": "图纸识别存在低置信度或待补字段，需要工程人员确认。",
        "process_flow_review": "过程流程图存在 AI 推断、空字段或顺序关系待确认。",
        "pfmea_review": "PFMEA 风险行为 AI 草案，需要确认高风险和不确定项。",
        "control_plan_review": "控制计划由 PFMEA 草案推导，需要确认规格、方法、频次和反应计划。",
        "evidence_review": "部分对象的证据引用需要确认，正式放行前不能忽略。",
        "row_confirmation_review": "部分草案对象标记为待确认，需要人工复核。",
        "manual_review": "存在需要人工确认的草案项。",
    }.get(key, "存在需要人工确认的草案项。")


def _manual_review_bucket_severity(item: dict[str, str]) -> str:
    return "blocker" if item.get("severity") == "blocker" else "review"


def _manual_review_severity_display(severity: str) -> str:
    return {"blocker": "阻断", "review": "需复核"}.get(severity, "需复核")


def _manual_review_summary(items: list[dict[str, Any]], raw_count: int) -> dict[str, Any]:
    return {
        "display_count": len(items),
        "raw_count": raw_count,
        "message": f"已将 {raw_count} 条明细复核项合并为 {len(items)} 类中文复核摘要。",
    }


def _dedupe_manual_review_items(items: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    deferred_strings: list[str] = []
    for item in items:
        key = _manual_review_key(item)
        if not key:
            continue
        if isinstance(item, str):
            deferred_strings.append(item)
            continue
        if key in seen:
            continue
        result.append(item)
        seen.add(key)
    for item in deferred_strings:
        key = _manual_review_key(item)
        if key and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _manual_review_key(item: Any) -> str:
    if isinstance(item, str):
        return _canonical_manual_review_target(item.strip())
    if isinstance(item, dict):
        for field_name in ("item_id", "id", "field", "target"):
            value = str(item.get(field_name, "")).strip()
            if value:
                return _canonical_manual_review_target(value)
        return json.dumps(item, ensure_ascii=False, sort_keys=True)
    if hasattr(item, "__dict__"):
        return _manual_review_key(dict(item.__dict__))
    return _canonical_manual_review_target(str(item).strip())


def _canonical_manual_review_target(value: str) -> str:
    text = str(value).strip()
    if text.startswith("failure_mode:"):
        return "pfmea:" + text.split(":", 1)[1].strip()
    if text.startswith("control_item:"):
        return "control_plan:" + text.split(":", 1)[1].strip()
    if text.startswith("process_step:"):
        return "pfd:" + text.split(":", 1)[1].strip()
    if text.startswith("PFMEA-"):
        return "pfmea:" + text
    if text.startswith("CP-"):
        return "control_plan:" + text
    if re_match := _process_step_review_pattern(text):
        return "pfd:" + re_match
    return text


def _process_step_review_pattern(value: str) -> str:
    if value.startswith("P") and value[1:].isdigit():
        return value
    return ""


def _three_table_artifacts(
    *,
    drawing_analysis: dict[str, Any] | None,
    process_flow: dict[str, Any] | None,
    pfmea: dict[str, Any] | None,
    control_plan: dict[str, Any] | None,
    chain: dict[str, Any] | None,
    exports: dict[str, Any],
    linkage_map: dict[str, Any] | None = None,
    linkage_gaps: list[dict[str, Any]] | None = None,
    characteristic_registry: dict[str, Any] | None = None,
    knowledge_recommendations: list[dict[str, Any]] | None = None,
    risk_structure: dict[str, Any] | None = None,
    part_family_classification: dict[str, Any] | None = None,
    family_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for name, payload in (
        ("drawing_analysis", drawing_analysis),
        ("process_flow", process_flow),
        ("pfmea", pfmea),
        ("control_plan", control_plan),
        ("chain", chain),
    ):
        if payload is not None:
            artifacts[name] = payload
    for name, path in exports.items():
        if path:
            artifacts[name] = path
    for name, payload in (
        ("linkage_map", linkage_map),
        ("linkage_gaps", linkage_gaps),
        ("characteristic_registry", characteristic_registry),
        ("knowledge_recommendations", knowledge_recommendations),
        ("risk_structure", risk_structure),
        ("part_family_classification", part_family_classification),
        ("family_context", family_context),
    ):
        if payload:
            artifacts[name] = payload
    return artifacts


def _last_mapping_value(values: dict[str, Any]) -> Any:
    for value in reversed(list(values.values())):
        return value
    return None
