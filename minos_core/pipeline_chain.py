"""
链式三表生成 Pipeline (PFD → PFMEA → CP)

每个阶段基于上一阶段的确认快照，调用 LLM 推理生成下一阶段内容。
绘图分析（OCR + Vision）复用现有 pipeline，不在此模块中重复实现。

Stage functions are extracted into sub-modules:
  pipeline_chain_pfd.py   — PFD generation
  pipeline_chain_pfmea.py — PFMEA generation
  pipeline_chain_cp.py    — CP generation
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ._text_utils import string_list, text
from .adapters.llm_text import OpenAITextGenerator  # noqa: F401 — imported for test patching compatibility
from .observability.logging import get_logger
from .pipeline_chain_cp import generate_cp_from_confirmed_pfmea  # noqa: F401
from .pipeline_chain_pfd import generate_pfd_from_drawing  # noqa: F401
from .pipeline_chain_pfmea import generate_pfmea_from_confirmed_pfd  # noqa: F401

logger = get_logger(__name__)

__all__ = [
    "generate_cp_from_confirmed_pfmea",
    "generate_pfd_from_drawing",
    "generate_pfmea_from_confirmed_pfd",
]

STAGE_STATUS = ("not_started", "running", "generated", "confirmed", "blocked", "failed")

# ---------------------------------------------------------------------------
# 绘图分析上下文构建
# ---------------------------------------------------------------------------


def _build_drawing_context(drawing_analysis: dict[str, Any]) -> str:
    """将图纸分析结果格式化为 LLM 可读的文本上下文。"""
    parts: list[str] = []

    identity = drawing_analysis.get("drawing_identity") or {}
    parts.append(f"零件名: {text(identity.get('part_name', '未识别'))}")
    parts.append(f"图号: {text(identity.get('drawing_number', '未识别'))}")

    for key, label in [
        ("materials", "材料"),
        ("dimensions", "关键尺寸"),
        ("special_characteristics", "特殊特性"),
        ("special_characteristic_candidates", "特殊特性候选"),
        ("numeric_specifications", "数值型技术指标"),
        ("technical_requirements", "技术要求"),
        ("surface_treatments", "表面处理"),
        ("manufacturing_clues", "制造线索"),
        ("tolerances", "公差要求"),
        ("inspection_requirements", "检验要求"),
        ("standard_references", "引用标准"),
    ]:
        items = drawing_analysis.get(key) or []
        if items:
            if key == "materials":
                texts = [f"{text(m.get('name'))} ({text(m.get('specification'))})" for m in items]
            elif key == "dimensions":
                texts = [
                    f"{text(d.get('name'))}={text(d.get('value'))}{text(d.get('tolerance'))}"
                    for d in items
                ]
            elif key == "numeric_specifications":
                texts = [
                    f"{text(n.get('name'))}({text(n.get('value'))}{text(n.get('unit'))}): "
                    f"{text(n.get('source_text'))}"
                    for n in items
                ]
            elif key == "technical_requirements":
                texts = [text(i.get('text', i.get('description', i.get('name', '')))) for i in items]
            elif key == "surface_treatments":
                texts = [text(i.get('name', i.get('source_text', ''))) for i in items]
            elif key == "tolerances":
                texts = [
                    f"{text(t.get('name', t.get('dimension', '')))} "
                    f"{text(t.get('value', t.get('text', '')))}".strip()
                    for t in items
                ]
            elif key == "inspection_requirements":
                texts = [text(i.get('text', i.get('description', i.get('name', '')))) for i in items]
            elif key == "standard_references":
                texts = [f"{text(s.get('standard', ''))} {text(s.get('text', ''))}".strip() for s in items]
            elif key == "special_characteristic_candidates":
                texts = [_special_candidate_context_text(i) for i in items]
            else:
                texts = [text(i.get('description', i.get('name', i.get('text', str(i))))) for i in items]
            texts = [t for t in texts if t]
            if texts:
                parts.append(f"{label}: {'; '.join(texts)}")

    return "\n".join(parts)


def _special_candidate_context_text(item: Any) -> str:
    if not isinstance(item, dict):
        return text(item)
    candidate_type = _supported_special_candidate_type(
        text(item.get("candidate_type"), item.get("classification"))
    )
    symbol = text(item.get("symbol_text_or_shape"), item.get("symbol"), item.get("marker"))
    feature = text(item.get("linked_feature"), item.get("feature"), item.get("characteristic"), item.get("name"))
    reasoning = text(item.get("reasoning"), item.get("rationale"))
    parts = [value for value in (candidate_type, symbol, feature, reasoning) if value]
    return " / ".join(parts)


def _special_candidate_labels_from_drawing(
    drawing_analysis: dict[str, Any],
) -> list[str]:
    labels: list[str] = []
    for item in drawing_analysis.get("special_characteristic_candidates", []):
        if not isinstance(item, dict):
            continue
        candidate_type = _supported_special_candidate_type(
            text(item.get("candidate_type"), item.get("classification"))
        )
        label_type = f"{candidate_type}候选" if candidate_type else "特殊特性候选"
        symbol = text(item.get("symbol_text_or_shape"), item.get("symbol"), item.get("marker"))
        feature = text(item.get("linked_feature"), item.get("feature"), item.get("characteristic"), item.get("name"))
        detail = " / ".join(value for value in (symbol, feature) if value)
        label = f"{label_type}: {detail}" if detail else label_type
        if label not in labels:
            labels.append(label)
    return labels


def _supported_special_candidate_type(value: str) -> str:
    candidate_type = text(value).upper()
    return candidate_type if candidate_type in {"SC", "CC"} else ""


def _attach_special_candidate_labels_to_pfd_steps(
    steps: list[dict[str, Any]],
    drawing_analysis: dict[str, Any],
) -> None:
    labels = _special_candidate_labels_from_drawing(drawing_analysis)
    if not steps or not labels:
        return
    review_steps = [step for step in steps if _is_special_candidate_review_step(step)]
    target_steps = review_steps or [steps[-1]]
    for step in target_steps:
        existing = string_list(step.get("special_characteristic_candidates"))
        for label in labels:
            if label not in existing:
                existing.append(label)
        step["special_characteristic_candidates"] = existing
        step["needs_confirmation"] = True


def _is_special_candidate_review_step(step: dict[str, Any]) -> bool:
    value = " ".join(
        text(step.get(key))
        for key in ("operation", "process_function", "operation_type", "flow_type_display")
    ).lower()
    return any(
        term in value
        for term in ("检验", "检测", "测试", "确认", "inspection", "inspect", "check", "verify", "test")
    )


def _ensure_list(result: dict[str, Any], key: str) -> list[dict[str, Any]]:
    items = result.get(key)
    if isinstance(items, list):
        return items
    return []


def _family_route_summary(route_templates: list[Any]) -> str:
    parts: list[str] = []
    for template in route_templates[:2]:
        if not isinstance(template, dict):
            continue
        steps = template.get("steps")
        if not isinstance(steps, list):
            continue
        names: list[str] = []
        for step in steps[:16]:
            if not isinstance(step, dict):
                continue
            name = text(
                step.get("operation")
                or step.get("operation_key")
                or step.get("name")
            )
            if name:
                names.append(name)
        if names:
            parts.append(" -> ".join(names))
    return "; ".join(parts)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _drawing_page_evidence_refs(drawing_analysis: dict[str, Any]) -> list[str]:
    refs = string_list(drawing_analysis.get("drawing_page_evidence_refs"))
    if refs:
        return refs

    page_refs: list[str] = []
    first_ref = ""
    for item in drawing_analysis.get("evidence", []):
        if not isinstance(item, dict):
            continue
        ref = text(item.get("evidence_id"))
        if not ref:
            continue
        if not first_ref:
            first_ref = ref
        source = text(item.get("source"))
        if source.endswith("_page") or (ref.startswith("ocr_page_") and "_block_" not in ref):
            page_refs.append(ref)
    return _dedupe_texts(page_refs or ([first_ref] if first_ref else []))


def _dedupe_texts(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value_text = text(value)
        if value_text and value_text not in seen:
            result.append(value_text)
            seen.add(value_text)
    return result
