"""PFMEA generation stage — LLM infers PFMEA from confirmed PFD.

Extracted from pipeline_chain.py. Pure extraction, no logic changes.
"""

# Prompt lines intentionally retain their semantic grouping for LLM input.
# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ._text_utils import string_list, text
from .aiag_vda_pfmea import normalize_pfmea_row, validate_severity_floor
from .observability.errors import PipelineError
from .observability.logging import get_logger
from .pipeline._llm_protected import get_llm_service_pool, wrap_llm_call

logger = get_logger(__name__)
struct_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# LLM Prompt 模板
# ---------------------------------------------------------------------------

PFMEA_SYSTEM_PROMPT = """\
你是一个 AIAG-VDA FMEA 第一版 (2019) 七步法专家。
你的任务是基于已确认的过程流程图 (PFD)，按照 AIAG & VDA PFMEA Form C 标准格式生成 PFMEA。

每个失效模式行必须包含以下标准字段：

【结构分析 Step 2】
- pfmea_id: 行编号 (PFMEA-{工序编号}-{序号}，如 PFMEA-P01-01)
- process_step_id: 关联的 PFD 工序编号
- process_item: 过程项（上一级/最终产品名称）
- process_step_name: 过程步骤名称（来自 PFD 的 operation）
- structure_process_item: 结构分析-过程项
- structure_process_step: 结构分析-过程步骤
- structure_work_element: 结构分析-工作要素
- work_element_4m: 工作要素 4M 类型，取值为 人 / 机 / 料 / 法。对锻件/铸件/金属加工类零件，"料"相关失效原因（如来料缺陷、材料批次波动、硬度不均、内部裂纹）应占比≥20%，不要过度集中在"法"和"机"

【功能分析 Step 3】
- function_process_item: 功能分析-过程项功能
- function_process_step: 过程步骤功能 + 产品特性
- function_work_element: 工作要素功能 + 过程特性

【失效分析 Step 4】
- failure_effect: 失效后果 (FE)，对最终用户或下一工序的影响
- severity: 严重度 S (1-10)，基于 AIAG-VDA 严重度评估表（10=安全风险，7-9=主要功能丧失）。安全/法规强制规则：当失效后果涉及"人身安全/召回/法规/伤害/致命/起火/爆炸/有毒"时 S 必须≥9；涉及"整车功能丧失"或"完全失效"时 S 必须≥9
- failure_mode: 失效模式 (FM)，过程步骤可能如何失效
- failure_cause: 失效原因 (FC)，为什么失效会发生，关联 4M 要素
- cause_process_parameter: 原因过程参数，导致该失效原因的关键过程变量/工装状态/材料状态

【风险分析 Step 5】
- prevention_control: 预防控制 (PC)，当前防止失效原因发生的措施
- prevention_control_target: 预防控制对象，必须指向失效原因或原因过程参数，不要只写结果检验
- prevention_control_timing: 预防控制时机，如生产前、换型后、首件、每班点检
- occurrence: 发生度 O (1-10)，考虑预防控制后的失效原因发生可能性
- detection_control: 探测控制 (DC)，当前探测失效模式或原因的检测手段
- detection_control_target: 探测对象，说明探测的是失效模式、失效原因还是产品/过程特性
- detection_control_timing: 探测时机，如首件、巡检、每批、全检、出货前
- detection: 探测度 D (1-10)，基于探测方法成熟度、时机和能力
- action_priority: H / M / L，基于 S/O/D 组合查 AIAG-VDA Action Priority 表
- special_characteristics: 特殊特性标识，取值为 SC / CC / 无
- control_logic_review: 控制逻辑复核摘要，说明失效原因、预防控制、探测控制是否分清
注意：AIAG-VDA 2019 PFMEA 以 AP 为主，不输出旧版 RPN 排序字段。

【优化措施 Step 6】
- preventive_action: 建议的预防措施（降低 O）
- detection_action: 建议的探测措施（降低 D）
- optimization_action: 综合优化措施摘要
- responsible_person: 负责人姓名
- target_date: 目标完成日期
- status: 状态，取值为 未开始 / 进行中 / 已完成 / 已放弃

【确认标记】
- needs_confirmation: 仅在以下情况设为 true：(1) 缺少图纸数据无法确定具体数值 (2) 工艺参数需要现场验证。对于基于通用工程知识可合理推断的字段（如标准预防控制、通用探测方法、常规反应计划），不应标记为需确认

每个工序应生成 1-5 个失效模式行，覆盖不同类型和 4M 来源的失效方式。
重点关注图纸中的特殊特性 (SC/CC) 和关键尺寸对应的工序。

【评分校准约束】
- S/O/D 评分必须覆盖至少 4 个不同档位（如 S 不能只用 5-9，O 不能只用 3-5，D 不能只用 4-7）
- AP 分布约束：H 不超过总行数 40%，L 不低于 10%。如果所有行都是 H/M，说明评分缺乏区分度，需重新校准
- AP 判定硬约束：只有 S≥9，或 S≥8 且 O≥5，或 S≥7 且 O≥5 且 D≥5 时才可给 H
- O 评分必须考虑预防控制的有效性：有成熟 SPC/防错的工序 O 应≤3；仅靠人工点检的 O 应≥5
- D 评分必须考虑探测方法的能力：自动化在线检测 D≤3；抽检 D=5-7；仅靠目视 D≥8
- 低风险工序（如包装、标识、搬运）的 S 应≤5，O 应≤3
- 高风险工序（如热处理、焊接、铆接承载件）的 S 应≥7"""

# ---------------------------------------------------------------------------
# JSON Schema 输出约束
# ---------------------------------------------------------------------------

PFMEA_OUTPUT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "pfmea_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pfmea_id": {"type": "string"},
                            "process_step_id": {"type": "string"},
                            "process_item": {"type": "string"},
                            "process_step_name": {"type": "string"},
                            "structure_process_item": {"type": "string"},
                            "structure_process_step": {"type": "string"},
                            "structure_work_element": {"type": "string"},
                            "work_element_4m": {
                                "type": "string",
                                "enum": ["人", "机", "料", "法"],
                            },
                            "function_process_item": {"type": "string"},
                            "function_process_step": {"type": "string"},
                            "function_work_element": {"type": "string"},
                            "failure_effect": {"type": "string"},
                            "severity": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10,
                            },
                            "failure_mode": {"type": "string"},
                            "failure_cause": {"type": "string"},
                            "cause_process_parameter": {"type": "string"},
                            "prevention_control": {"type": "string"},
                            "prevention_control_target": {"type": "string"},
                            "prevention_control_timing": {"type": "string"},
                            "occurrence": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10,
                            },
                            "detection_control": {"type": "string"},
                            "detection_control_target": {"type": "string"},
                            "detection_control_timing": {"type": "string"},
                            "detection": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10,
                            },
                            "action_priority": {
                                "type": "string",
                                "enum": ["H", "M", "L"],
                            },
                            "special_characteristics": {
                                "type": "string",
                                "enum": ["SC", "CC", "无"],
                            },
                            "preventive_action": {"type": "string"},
                            "detection_action": {"type": "string"},
                            "optimization_action": {"type": "string"},
                            "responsible_person": {"type": "string"},
                            "target_date": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["未开始", "进行中", "已完成", "已放弃"],
                            },
                            "control_logic_review": {"type": "string"},
                            "needs_confirmation": {"type": "boolean"},
                        },
                        "required": [
                            "pfmea_id",
                            "process_step_id",
                            "process_item",
                            "process_step_name",
                            "structure_process_item",
                            "structure_process_step",
                            "structure_work_element",
                            "work_element_4m",
                            "function_process_item",
                            "function_process_step",
                            "function_work_element",
                            "failure_effect",
                            "severity",
                            "failure_mode",
                            "failure_cause",
                            "cause_process_parameter",
                            "prevention_control",
                            "prevention_control_target",
                            "prevention_control_timing",
                            "occurrence",
                            "detection_control",
                            "detection_control_target",
                            "detection_control_timing",
                            "detection",
                            "action_priority",
                            "special_characteristics",
                            "preventive_action",
                            "detection_action",
                            "optimization_action",
                            "responsible_person",
                            "target_date",
                            "status",
                            "control_logic_review",
                            "needs_confirmation",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["rows"],
            "additionalProperties": False,
        },
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _step_context_with_relevant_specs(
    context_text: str,
    step: dict[str, Any],
    registry: dict[str, Any],
) -> str:
    """Append step-relevant specs to context, or note their absence."""
    from minos_core.characteristic_registry import characteristics_for_step  # noqa: PLC0415

    relevant = characteristics_for_step(registry, step)
    if relevant:
        spec_lines = []
        for item in relevant:
            spec = item.get("specification", "")
            if spec:
                spec_lines.append(f"- {item['name']}: {spec}")
        if spec_lines:
            return context_text + "\n\n该工序直接相关的图纸规格:\n" + "\n".join(spec_lines)
    return (
        context_text
        + "\n\n注意：图纸中未找到该工序直接相关的数值规格，请基于通用工程判断填写，不要引用其他工序的数值。"
    )


def _build_pfmea_step_prompt(context_text: str, step: dict[str, Any]) -> str:
    step_text = json.dumps([step], ensure_ascii=False, indent=2)
    sc_status = text(step.get("product_characteristic_class"), step.get("process_characteristic_class"))
    if sc_status in ("SC", "CC"):
        sc_note = f'该工序为特殊特性工序（{sc_status}），所有输出行的 special_characteristics 必须为"{sc_status}"。'
    else:
        sc_note = '该工序不涉及特殊特性，所有输出行的 special_characteristics 必须为"无"。'
    return f"""请基于以下已确认的单个过程流程图 (PFD) 工序和图纸分析结果，生成 PFMEA。

图纸分析摘要:
{context_text}

已确认的 PFD 工序:
{step_text}

请只为这个工序生成 1-5 个潜在的失效模式行。
所有输出行的 process_step_id 必须等于该工序编号。
{sc_note}
重要：失效后果和严重度评估应结合该工序**直接相关**的图纸技术指标。例如铆接工序可引用"铆接力≥14.3KN"、表面处理工序可引用"盐雾≥120h"、整体检验可引用"纵向力≥25000N"。**绝不要把不相关工序的数值硬塞进失效后果**（如把盐雾时间用在铆接失效、把铆接力用在喷涂失效）。如果图纸没有该工序对应的数值，请基于通用工程判断给出合理后果描述。
预防控制必须控制失效原因或原因过程参数，探测控制必须单独说明探测对象和时机。
根据 AIAG-VDA 2019 Action Priority 表评定 H/M/L；不要输出旧版 RPN。
对不确定的评定请将 needs_confirmation 设为 true。
公差利用：如上下文含公差要求，引用具体公差值评估失效后果严重度（紧公差 S+1），并据此调整发生度。
检验要求利用：如上下文含检验要求（全检/CMM/在线检测 → D≤4；抽检/目视 → D≥6），直接作为探测控制依据。
标准引用利用：如上下文含引用标准，作为控制方法依据填入 prevention_control 或 process_parameter。
评分校准要求：同一零件的多个工序，S/O/D 不应高度集中在某几个值。请确保评分反映各工序实际风险差异。"""


def _normalize_chain_pfmea_row(
    raw_row: Any,
    step_map: dict[str, dict[str, Any]],
    counters: dict[str, int],
    *,
    expected_step_id: str | None = None,
    part_name: str = "制造过程",
) -> dict[str, Any] | None:
    if not isinstance(raw_row, dict):
        return None
    step_id = str(raw_row.get("process_step_id", "")).strip()
    if step_id not in step_map:
        raise ValueError(f"PFMEA row references unknown confirmed PFD step: {step_id or '<empty>'}")
    if expected_step_id and step_id != expected_step_id:
        raise ValueError(f"PFMEA row process_step_id {step_id} does not match expected {expected_step_id}")
    if not text(raw_row.get("failure_mode")):
        raise ValueError(f"PFMEA row for {step_id} has no failure_mode")

    step = step_map[step_id]
    operation = text(step.get("operation"), step.get("process_step_name"), step_id)
    process_function = text(
        step.get("process_function"),
        step.get("process_purpose"),
        raw_row.get("function_process_step"),
        operation,
    )
    counters[step_id] = counters.get(step_id, 0) + 1
    row = dict(raw_row)
    if not string_list(row.get("evidence_refs")):
        row["evidence_refs"] = string_list(step.get("evidence_refs"))
    row.update(
        {
            "process_step_id": step_id,
            "operation": operation,
            "process_step_name": operation,
            "process_function": process_function,
            "process_step": operation,
            "process_item": part_name,
            "process_work_element": text(
                row.get("process_work_element"),
                row.get("structure_work_element"),
                step.get("equipment"),
                step.get("tooling"),
                row.get("work_element_4m"),
            ),
            "structure_process_item": part_name,
            "structure_process_step": operation,
            "structure_work_element": text(
                row.get("structure_work_element"),
                row.get("process_work_element"),
                step.get("equipment"),
                step.get("tooling"),
                row.get("work_element_4m"),
            ),
            "function_process_item": part_name,
            "function_process_step": process_function,
            "function_work_element": text(
                row.get("function_work_element"),
                step.get("process_characteristics"),
                step.get("process_characteristic"),
                step.get("equipment"),
            ),
            "function_requirement": process_function,
            "product_characteristics": step.get("product_characteristics", row.get("product_characteristics", "")),
            "process_characteristics": step.get("process_characteristics", row.get("process_characteristics", "")),
            "ai_inferred": True,
        }
    )
    pfd_sc = text(
        step.get("product_characteristic_class"),
        step.get("process_characteristic_class"),
    )
    pfd_special_refs = string_list(step.get("special_characteristics"))
    if pfd_sc in ("SC", "CC"):
        row["special_characteristics"] = pfd_sc
    else:
        row["special_characteristics"] = "无"
    if pfd_special_refs and not string_list(row.get("characteristic_refs")):
        row["characteristic_refs"] = pfd_special_refs
    if not text(row.get("pfmea_id")):
        row["pfmea_id"] = f"PFMEA-{step_id}-{counters[step_id]:02d}"
    row = validate_severity_floor(row)
    return normalize_pfmea_row(row, step)


# ---------------------------------------------------------------------------
# Stage 2: 基于已确认 PFD 生成 PFMEA
# ---------------------------------------------------------------------------


def generate_pfmea_from_confirmed_pfd(
    drawing_analysis: dict[str, Any],
    confirmed_pfd: dict[str, Any],
    model: str | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """基于已确认的 PFD，LLM 推理生成 PFMEA。

    Args:
        drawing_analysis: 图纸分析 bundle（作为工程上下文）
        confirmed_pfd: 用户已确认锁定的 process_flow bundle
        model: LLM 模型名

    Returns:
        pfmea bundle 字典（含 rows 列表和 metadata）
    """
    from .pipeline_chain import _build_drawing_context, _ensure_list, _now_iso  # noqa: PLC0415

    pfd_steps = [
        s
        for s in (confirmed_pfd.get("steps") or [])
        if isinstance(s, dict) and not s.get("deleted") and not s.get("soft_deleted")
    ]
    if not pfd_steps:
        raise PipelineError(
            "Confirmed PFD has no steps — cannot generate PFMEA",
            stage="pfmea",
            user_message_zh="已确认的 PFD 中没有可用的工序，无法生成 PFMEA。",
        )

    context_text = _build_drawing_context(drawing_analysis)
    from minos_core.characteristic_registry import build_characteristic_registry  # noqa: PLC0415

    _registry = build_characteristic_registry(drawing_analysis)
    part_name = text(
        drawing_analysis.get("part_name"),
        drawing_analysis.get("title"),
        confirmed_pfd.get("metadata", {}).get("part_name"),
        "制造过程",
    )
    step_map = {
        str(step.get("process_step_id", "")).strip(): step
        for step in pfd_steps
        if isinstance(step, dict) and str(step.get("process_step_id", "")).strip()
    }
    pfmea_rows: list[dict[str, Any]] = []
    failed_step_ids: list[str] = []
    failed_step_messages: list[str] = []
    counters: dict[str, int] = {}
    # Select endpoint from service pool for health tracking
    _pool = get_llm_service_pool()
    _endpoint = _pool.get_next_endpoint()
    if _endpoint:
        logger.debug("pfmea_pool_endpoint", name=_endpoint.name, healthy=_endpoint.is_healthy)

    from .adapters.llm_text import OpenAITextGenerator

    llm = OpenAITextGenerator()

    # Prepare tasks for parallel execution
    valid_steps = [
        (i, step)
        for i, step in enumerate(pfd_steps)
        if isinstance(step, dict) and str(step.get("process_step_id", "")).strip()
    ]

    def _generate_for_step(
        index: int, step: dict[str, Any]
    ) -> tuple[int, str, dict[str, Any]]:
        step_id = str(step.get("process_step_id", "")).strip()
        logger.info("CHAIN [Stage 2] Calling LLM to generate PFMEA", step_id=step_id)
        result = wrap_llm_call(llm.generate_structured, name=f"pfmea_{step_id}")(
            system_prompt=PFMEA_SYSTEM_PROMPT,
            user_prompt=_build_pfmea_step_prompt(
                _step_context_with_relevant_specs(context_text, step, _registry),
                step,
            ),
            response_format=PFMEA_OUTPUT_SCHEMA,
            model=model,
        )
        return index, step_id, result

    parallel_batch_size = 4
    completed_count = 0
    for batch_start in range(0, len(valid_steps), parallel_batch_size):
        batch = valid_steps[batch_start : batch_start + parallel_batch_size]
        # Collect results keyed by original index to preserve order
        batch_results: dict[int, tuple[str, dict[str, Any] | None, str | None]] = {}
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = {executor.submit(_generate_for_step, idx, step): (idx, step) for idx, step in batch}
            for future in as_completed(futures):
                idx, step = futures[future]
                step_id = str(step.get("process_step_id", "")).strip()
                try:
                    _, _, generated_result = future.result()
                except Exception as exc:
                    logger.error("CHAIN [Stage 2] PFMEA generation failed", step_id=step_id, error=str(exc))
                    batch_results[idx] = (step_id, None, str(exc))
                else:
                    batch_results[idx] = (step_id, generated_result, None)

        # Process results in original order
        for idx, step in batch:
            step_id, pfmea_result, failure_message = batch_results.get(
                idx,
                (str(step.get("process_step_id", "")).strip(), None, "PFMEA generation failed"),
            )
            if failure_message:
                failed_step_ids.append(step_id)
                failed_step_messages.append(f"{step_id}: {failure_message}")
                if on_progress:
                    on_progress(
                        {
                            "type": "step_failed",
                            "stage": "pfmea",
                            "step_index": completed_count,
                            "total_steps": len(valid_steps),
                            "step_id": step_id,
                            "rows_so_far": len(pfmea_rows),
                            "message": failure_message,
                        }
                    )
                completed_count += 1
                continue
            if pfmea_result is None:
                continue
            step_rows = []
            for raw_row in _ensure_list(pfmea_result, "rows"):
                try:
                    row = _normalize_chain_pfmea_row(
                        raw_row, step_map, counters, expected_step_id=step_id, part_name=part_name
                    )
                except ValueError as exc:
                    logger.error("CHAIN [Stage 2] PFMEA row validation failed", step_id=step_id, error=str(exc))
                    raise
                except Exception as exc:
                    logger.warning("CHAIN [Stage 2] PFMEA row normalization failed", step_id=step_id, error=str(exc))
                    continue
                if row:
                    step_rows.append(row)
                    pfmea_rows.append(row)
            completed_count += 1
            if on_progress and step_rows:
                on_progress(
                    {
                        "type": "step_complete",
                        "stage": "pfmea",
                        "step_index": completed_count,
                        "total_steps": len(valid_steps),
                        "step_id": step_id,
                        "rows_so_far": len(pfmea_rows),
                        "new_rows": step_rows,
                    }
                )

    if not pfmea_rows:
        if failed_step_messages:
            raise ValueError(f"PFMEA generation returned no rows: {'; '.join(failed_step_messages)}")
        raise ValueError("PFMEA generation returned no rows")

    logger.info("CHAIN [Stage 2] PFMEA generated", row_count=len(pfmea_rows), failed_steps=failed_step_ids)
    struct_logger.info(
        "pipeline_chain.stage_done",
        stage="pfmea",
        row_count=len(pfmea_rows),
        failed_step_ids=failed_step_ids,
    )

    return {
        "rows": pfmea_rows,
        "metadata": {
            "chain_stage": "pfmea",
            "chain_stage_status": "generated",
            "chain_pfd_snapshot": confirmed_pfd,
            "pfmea_generation_strategy": "per_pfd_step",
            "generated_at": _now_iso(),
            "failed_step_ids": failed_step_ids,
        },
    }
