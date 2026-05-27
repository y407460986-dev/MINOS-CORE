"""Company process-boundary rules for generated PFD drafts."""

from __future__ import annotations

import copy
import re
from typing import Any


_DEFAULT_PROCESS_BOUNDARY_CONFIG: dict[str, Any] = {
    "enabled": True,
    "process_scope": "本公司总成制造过程",
    "supplier_processes_excluded": True,
    "in_house_processes": [
        "来料检验",
        "冲压",
        "冲孔",
        "机加工",
        "装配",
        "铆接",
        "检验",
        "包装",
        "仓储",
    ],
    "purchased_inputs": [
        "锻件",
        "铸件",
        "标准件",
        "外购表面处理件",
    ],
    "disallowed_internal_operations": [
        "加热坯料",
        "锻造成形",
        "锻造切边",
        "热处理锻件",
        "抛丸清理锻件",
        "锻压",
        "锻造模具",
        "锻压机",
        "摩擦压力机",
    ],
}


def default_process_boundary_config() -> dict[str, Any]:
    """Return the default global company process-boundary profile."""

    return copy.deepcopy(_DEFAULT_PROCESS_BOUNDARY_CONFIG)


def normalize_process_boundary_config(payload: Any) -> dict[str, Any]:
    """Normalize a user-supplied boundary payload onto the default structure."""

    config = default_process_boundary_config()
    if not isinstance(payload, dict):
        return config

    if "enabled" in payload:
        config["enabled"] = bool(payload.get("enabled"))
    if "process_scope" in payload:
        process_scope = str(payload.get("process_scope") or "").strip()
        if process_scope:
            config["process_scope"] = process_scope
    if "supplier_processes_excluded" in payload:
        config["supplier_processes_excluded"] = bool(
            payload.get("supplier_processes_excluded")
        )

    for key in (
        "in_house_processes",
        "purchased_inputs",
        "disallowed_internal_operations",
    ):
        if key in payload:
            config[key] = _normalize_string_list(payload.get(key))
    return config


def build_process_boundary_prompt(config: dict[str, Any] | None) -> str:
    """Build prompt text that constrains PFD generation to company scope."""

    if config is None:
        return ""
    normalized = normalize_process_boundary_config(config)
    if (
        not normalized.get("enabled", True)
        or not normalized.get("supplier_processes_excluded", True)
    ):
        return ""

    return "\n".join(
        [
            "公司工艺边界（必须遵守）：",
            f"- PFD 是{normalized['process_scope']}，不展开供应商制程。",
            "- 外购输入只能作为来料进入来料检验，不得展开外购件在供应商处的制造过程。",
            f"- 本厂可做工序：{'、'.join(normalized['in_house_processes'])}",
            f"- 外购输入：{'、'.join(normalized['purchased_inputs'])}",
            (
                "- 禁止作为本厂内部工序："
                f"{'、'.join(normalized['disallowed_internal_operations'])}"
            ),
            "- 例如锻件是外购输入，只能写外购锻件来料检验，不能写加热坯料、锻造成形、热处理锻件、抛丸清理锻件等供应商制程。",
        ]
    )


def apply_process_boundary_to_pfd(
    process_flow: dict[str, Any],
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Remove supplier-process steps from a PFD and relink the remaining flow."""

    normalized = normalize_process_boundary_config(config)
    result = copy.deepcopy(process_flow or {})
    metadata = dict(result.get("metadata") or {})
    if (
        not normalized.get("enabled", True)
        or not normalized.get("supplier_processes_excluded", True)
    ):
        metadata["process_boundary_applied"] = False
        metadata.setdefault("process_boundary_adjustments", [])
        result["metadata"] = metadata
        return result

    raw_steps = result.get("steps")
    steps = [step for step in raw_steps if isinstance(step, dict)] if isinstance(raw_steps, list) else []
    kept_steps: list[dict[str, Any]] = []
    removed_steps: list[dict[str, Any]] = []
    adjustments: list[dict[str, Any]] = []

    for step in steps:
        blocked_terms = _matched_disallowed_terms(step, normalized)
        if blocked_terms:
            removed_steps.append(step)
            adjustments.append(
                {
                    "action": "remove_supplier_process_step",
                    "removed_step_id": str(step.get("process_step_id") or ""),
                    "operation": str(step.get("operation") or ""),
                    "matched_terms": blocked_terms,
                    "reason": "供应商制程不属于本公司总成制造过程",
                }
            )
            continue
        kept_steps.append(step)

    if removed_steps and _removed_forging_supplier_process(removed_steps):
        changed = _ensure_purchased_input_on_incoming_inspection(kept_steps, "锻件")
        if changed:
            adjustments.append(
                {
                    "action": "annotate_incoming_inspection_input",
                    "input": "外购锻件",
                    "reason": "已删除锻件供应商制造过程，保留为本厂来料输入",
                }
            )

    _renumber_and_relink_linear_steps(kept_steps)
    result["steps"] = kept_steps
    result["links"] = _sequence_links(kept_steps)
    metadata["process_boundary_applied"] = True
    metadata["process_boundary_adjustments"] = adjustments
    result["metadata"] = metadata
    return result


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[\n,，;；、]+", value)
    elif isinstance(value, (list, tuple, set)):
        items = value
    else:
        return []

    normalized: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _matched_disallowed_terms(
    step: dict[str, Any],
    config: dict[str, Any],
) -> list[str]:
    combined = _step_search_text(step)
    matched = [
        term
        for term in config.get("disallowed_internal_operations", [])
        if term and term in combined
    ]
    if "锻件" in combined and "热处理" in combined and "热处理锻件" not in matched:
        matched.append("热处理锻件")
    if "锻件" in combined and "抛丸" in combined and "抛丸清理锻件" not in matched:
        matched.append("抛丸清理锻件")
    return matched


def _step_search_text(step: dict[str, Any]) -> str:
    fields = (
        "operation",
        "process_function",
        "equipment",
        "input_material",
        "output_result",
        "product_characteristics",
        "process_characteristics",
        "operation_type",
        "flow_type_display",
    )
    return " ".join(_to_text(step.get(field)) for field in fields)


def _to_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_to_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_to_text(item) for item in value.values())
    return str(value or "")


def _removed_forging_supplier_process(steps: list[dict[str, Any]]) -> bool:
    combined = " ".join(_step_search_text(step) for step in steps)
    return any(term in combined for term in ("锻件", "锻造", "锻压", "坯料", "抛丸"))


def _ensure_purchased_input_on_incoming_inspection(
    steps: list[dict[str, Any]],
    purchased_input: str,
) -> bool:
    if not steps:
        return False

    target = _incoming_inspection_step(steps) or steps[0]
    changed = False
    changed |= _append_text_field(target, "input_material", f"外购{purchased_input}")
    changed |= _append_text_field(
        target,
        "process_function",
        f"检验外购{purchased_input}状态和供应商放行记录",
    )
    if target.get("flow_type") in ("", None):
        target["flow_type"] = "inspection"
        target["flow_symbol"] = "inspection"
        target["flow_type_display"] = "检验"
        target["operation_type"] = "检验"
    target["needs_confirmation"] = bool(target.get("needs_confirmation", False)) or changed
    return changed


def _incoming_inspection_step(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    for step in steps:
        operation = str(step.get("operation") or "")
        if "来料" in operation and ("检验" in operation or "检查" in operation):
            return step
    for step in steps:
        operation = str(step.get("operation") or "")
        if "检验" in operation or step.get("flow_type") == "inspection":
            return step
    return None


def _append_text_field(step: dict[str, Any], field: str, value: str) -> bool:
    current = step.get(field)
    if isinstance(current, list):
        if value not in current:
            current.append(value)
            return True
        return False
    current_text = str(current or "").strip()
    if value in current_text:
        return False
    step[field] = f"{current_text}；{value}" if current_text else value
    return True


def _renumber_and_relink_linear_steps(steps: list[dict[str, Any]]) -> None:
    for index, step in enumerate(steps):
        step["process_step_id"] = f"P{index + 1:02d}"
    for index, step in enumerate(steps):
        previous_step_id = steps[index - 1]["process_step_id"] if index > 0 else ""
        next_step_id = steps[index + 1]["process_step_id"] if index + 1 < len(steps) else ""
        step["previous_step_ids"] = [previous_step_id] if previous_step_id else []
        step["next_step_ids"] = [next_step_id] if next_step_id else []


def _sequence_links(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for current, nxt in zip(steps, steps[1:]):
        refs: list[str] = []
        for ref in list(current.get("evidence_refs") or []) + list(nxt.get("evidence_refs") or []):
            if ref not in refs:
                refs.append(ref)
        links.append(
            {
                "from": current["process_step_id"],
                "to": nxt["process_step_id"],
                "link_type": "sequence",
                "evidence_refs": refs,
                "ai_inferred": True,
                "needs_confirmation": bool(
                    current.get("needs_confirmation") or nxt.get("needs_confirmation")
                ),
            }
        )
    return links
