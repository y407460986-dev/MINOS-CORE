"""Control Plan generation stage — LLM infers CP from confirmed PFMEA + PFD.

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
from .observability.errors import PipelineError
from .observability.logging import get_logger
from .pipeline._llm_protected import get_llm_service_pool, wrap_llm_call

logger = get_logger(__name__)
struct_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# LLM Prompt 模板
# ---------------------------------------------------------------------------

CP_SYSTEM_PROMPT = """\
你是一个 IATF 16949 / AIAG CP-1:2024 控制计划设计专家。
你的任务是基于已确认的 PFMEA，按照 AIAG 控制计划第一版 (2024) 标准 13 列格式生成控制计划。

每个控制计划行必须包含以下标准字段：

【工序信息】
- control_plan_id: CP 行编号 (CP-{工序编号}-{序号}，如 CP-P01-01)
- process_step_id: 关联的 PFD 工序编号 (必须与 PFD 的工序编号一致)
- pfmea_id: 关联的 PFMEA 行编号 (追溯失效分析来源)
- process_name: 工序名称/操作描述（动词+名词格式）
- equipment: 制造用机器、设备、夹具、工具

【特性】
- characteristic_number: 编号（交叉引用 PFMEA/流程图编号）
- product_characteristic: 产品特性（零件可区分特征，如尺寸、硬度、颜色）
- process_characteristic: 过程特性（影响产品特性的过程变量，如温度、压力、转速）
- special_characteristic_class: 特性分类，取值为 SC(重要特性) / CC(关键特性) / 无

【方法】
- specification_tolerance: 产品/过程规格和公差（包含名义值和公差范围）
- process_parameter: 过程参数（现场需要设定或稳定的变量，如冲压力、温度、扭矩、夹具定位状态）。禁止写成"是否..."问句形式，必须是可测量/可设定的物理量或状态参数
- parameter_specification: 参数规格/设定范围（目标值、上下限、配方号或作业指导书范围）
- process_control_method: 过程控制方法（预防性控制，如参数锁定、设备点检、SPC、防错验证、权限控制）
- setup_verification: 首件/换型确认（开机、换型、换批后如何确认过程已正确设定）
- poka_yoke_device: 防错装置/机制（如扫码、防漏装传感器、参数权限锁、限位夹具）
- poka_yoke_verification: 防错验证方法和频次
- process_record: 过程记录/表单（参数记录、点检表、首件确认单等）
- measurement_method: 评价/测量技术（具体量具名称，如千分尺、CMM、目视检查）
- sample_size: 样本量（如 5件、3件）
- sample_frequency: 抽样频率（如 每班1次、每小时1次、首件）
- control_method: 综合控制方法（过程控制 + 结果检验的摘要；不要只写结果检验）

【反应】
- reaction_plan: 反应计划（出现不合格时的具体纠正措施及责任人，如"隔离产品→通知质量工程师→调整参数→100%检验"）

【确认标记】
- needs_confirmation: 仅在以下情况设为 true：(1) 缺少图纸数据无法确定具体规格数值 (2) 工艺参数需要现场验证。对于基于通用工程知识可合理推断的字段（如标准测量方法、通用抽样频率、常规反应计划），不应标记为需确认

为每一条未删除的 PFMEA 行生成对应的控制计划行，确保正式导出前 PFMEA 风险均被 CP 覆盖。

输出只能是符合 schema 的 JSON 对象，不要输出 Markdown、原因判断、处理方案、说明文字或任何 JSON 之外的内容。"""

# ---------------------------------------------------------------------------
# JSON Schema 输出约束
# ---------------------------------------------------------------------------

CP_OUTPUT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "control_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "control_plan_id": {"type": "string"},
                            "process_step_id": {"type": "string"},
                            "pfmea_id": {"type": "string"},
                            "process_name": {"type": "string"},
                            "equipment": {"type": "string"},
                            "characteristic_number": {"type": "string"},
                            "product_characteristic": {"type": "string"},
                            "process_characteristic": {"type": "string"},
                            "special_characteristic_class": {
                                "type": "string",
                                "enum": ["SC", "CC", "无"],
                            },
                            "specification_tolerance": {"type": "string"},
                            "process_parameter": {"type": "string"},
                            "parameter_specification": {"type": "string"},
                            "process_control_method": {"type": "string"},
                            "setup_verification": {"type": "string"},
                            "poka_yoke_device": {"type": "string"},
                            "poka_yoke_verification": {"type": "string"},
                            "process_record": {"type": "string"},
                            "measurement_method": {"type": "string"},
                            "sample_size": {"type": "string"},
                            "sample_frequency": {"type": "string"},
                            "control_method": {"type": "string"},
                            "reaction_plan": {"type": "string"},
                            "needs_confirmation": {"type": "boolean"},
                        },
                        "required": [
                            "control_plan_id",
                            "process_step_id",
                            "pfmea_id",
                            "process_name",
                            "equipment",
                            "characteristic_number",
                            "product_characteristic",
                            "process_characteristic",
                            "special_characteristic_class",
                            "specification_tolerance",
                            "process_parameter",
                            "parameter_specification",
                            "process_control_method",
                            "setup_verification",
                            "poka_yoke_device",
                            "poka_yoke_verification",
                            "process_record",
                            "measurement_method",
                            "sample_size",
                            "sample_frequency",
                            "control_method",
                            "reaction_plan",
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


def _build_cp_pfmea_row_prompt(
    context_text: str,
    pfd_step: dict[str, Any],
    pfmea_row: dict[str, Any],
) -> str:
    pfd_text = json.dumps(pfd_step or {}, ensure_ascii=False, indent=2)
    pfmea_text = json.dumps(pfmea_row, ensure_ascii=False, indent=2)
    return f"""请基于以下已确认的单条 PFMEA 和对应 PFD 工序，生成控制计划 (Control Plan)。

图纸分析摘要:
{context_text}

已确认的 PFD 工序:
{pfd_text}

已确认的 PFMEA 行:
{pfmea_text}

请只为这一条 PFMEA 行生成对应的控制计划行。
输出行的 pfmea_id 必须等于该 PFMEA 行编号，process_step_id 必须等于该 PFMEA 行的工序编号。
重要：如果该 PFMEA 行的 special_characteristics 为 SC 或 CC，则输出行的 special_characteristic_class 必须继承该值，不得输出"无"。
重要：specification_tolerance 必须填写该工序实际控制的产品/过程规格和公差。**只有当图纸数值与该工序直接相关时才引用**：例如铆接工序引用铆接力、表面处理工序引用盐雾时间和膜厚、检验工序引用承载力等。绝不要把不相关工序的数值（如把盐雾时间用在铆接、把铆接力用在表面处理）硬塞进去。如果图纸没有该工序对应的数值，应基于 PFMEA 失效原因和预防控制写出合理的工艺规范（如"铆接高度按工艺卡 ±0.1mm"、"扭矩按工装设定"），而不是引用无关数值。
控制计划必须先说明过程如何被控制，再说明结果如何被检验：
- process_parameter 优先来自 PFMEA 的 cause_process_parameter，其次才是 PFMEA/PFD 过程特性。禁止写成"是否..."问句（如"是否涂覆均匀"是错误的，正确写法是"涂覆厚度"或"喷涂压力"）。parameter_specification / process_control_method 必须来自 PFMEA 的失效原因和预防控制。
- setup_verification、poka_yoke_device、poka_yoke_verification、process_record 必须给出现场可执行的首件/换型确认、防错验证和记录要求。
- measurement_method、sample_size、sample_frequency 只描述结果检验，不要替代过程控制。
确保高/中 AP 项有明确反应计划，测量方法具体到量具或检查技术。
对不确定的字段请将 needs_confirmation 设为 true。
只输出 JSON，不要输出原因判断、处理方案、Markdown 或任何解释文字。"""


def _extract_cp_base_fields(
    row: dict[str, Any],
    pfmea_row: dict[str, Any],
    pfd_step: dict[str, Any],
    step_id: str,
    pfmea_id: str,
) -> dict[str, Any]:
    return {
        "pfmea_id": pfmea_id,
        "source_pfmea_id": pfmea_id,
        "process_step_id": step_id,
        "process_name": text(
            row.get("process_name"),
            pfmea_row.get("process_step_name"),
            pfmea_row.get("operation"),
            pfd_step.get("operation"),
            step_id,
        ),
        "equipment": text(row.get("equipment"), pfmea_row.get("equipment"), pfd_step.get("equipment")),
        "characteristic_number": text(row.get("characteristic_number"), pfmea_id),
        "product_characteristic": text(
            row.get("product_characteristic"),
            pfmea_row.get("product_characteristic"),
            pfmea_row.get("product_characteristics"),
        ),
        "process_characteristic": text(
            row.get("process_characteristic"),
            pfmea_row.get("process_characteristic"),
            pfmea_row.get("process_characteristics"),
        ),
        "special_characteristic_class": text(
            row.get("special_characteristic_class"),
            pfmea_row.get("special_characteristics"),
            pfmea_row.get("special_characteristic_class"),
            pfmea_row.get("classification"),
            "无",
        ),
        "specification_tolerance": text(
            row.get("specification_tolerance"),
            row.get("specification"),
            pfmea_row.get("specification_tolerance"),
            pfmea_row.get("specification"),
        ),
    }


def _extract_cp_control_fields(
    row: dict[str, Any],
    pfmea_row: dict[str, Any],
) -> dict[str, Any]:
    return {
        "process_parameter": text(
            row.get("process_parameter"),
            pfmea_row.get("process_parameter"),
            pfmea_row.get("cause_process_parameter"),
            pfmea_row.get("process_characteristic"),
            pfmea_row.get("process_characteristics"),
            pfmea_row.get("function_work_element"),
        ),
        "parameter_specification": text(
            row.get("parameter_specification"),
            pfmea_row.get("parameter_specification"),
            pfmea_row.get("failure_cause"),
            "参数目标值/上下限待依据作业指导书确认",
        ),
        "process_control_method": text(
            row.get("process_control_method"),
            pfmea_row.get("process_control_method"),
            pfmea_row.get("prevention_control"),
        ),
        "setup_verification": text(
            row.get("setup_verification"),
            "首件/换型后确认过程参数、设备状态和工装状态",
        ),
        "poka_yoke_device": text(
            row.get("poka_yoke_device"),
            "过程参数防错或权限控制",
        ),
        "poka_yoke_verification": text(
            row.get("poka_yoke_verification"),
            "每班/换型后验证防错有效",
        ),
        "process_record": text(
            row.get("process_record"),
            row.get("record_form"),
            "过程参数点检/首件确认记录",
        ),
        "measurement_method": text(row.get("measurement_method"), pfmea_row.get("detection_control")),
        "control_method": text(
            row.get("control_method"),
            pfmea_row.get("prevention_control"),
            pfmea_row.get("detection_control"),
        ),
    }


def _extract_cp_reaction_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "reaction_plan": text(row.get("reaction_plan"), "隔离可疑产品，通知质量人员，并验证纠正措施"),
        "needs_confirmation": bool(row.get("needs_confirmation", True)),
        "ai_inferred": True,
    }


def _normalize_chain_cp_row(
    raw_row: Any,
    pfd_map: dict[str, dict[str, Any]],
    pfmea_map: dict[str, dict[str, Any]],
    counters: dict[str, int],
    *,
    expected_pfmea_id: str | None = None,
    fallback_evidence_refs: list[str] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(raw_row, dict):
        return None
    pfmea_id = str(raw_row.get("pfmea_id", "") or expected_pfmea_id or "").strip()
    if not pfmea_id:
        raise ValueError("CP row has no pfmea_id")
    if expected_pfmea_id and pfmea_id != expected_pfmea_id:
        raise ValueError(f"CP row pfmea_id {pfmea_id} does not match expected {expected_pfmea_id}")
    if pfmea_id not in pfmea_map:
        raise ValueError(f"CP row references unknown confirmed PFMEA row: {pfmea_id}")

    pfmea_row = pfmea_map[pfmea_id]
    expected_step_id = str(pfmea_row.get("process_step_id", "")).strip()
    step_id = str(raw_row.get("process_step_id", "") or expected_step_id).strip()
    if not step_id:
        raise ValueError(f"CP row for {pfmea_id} has no process_step_id")
    if expected_step_id and step_id != expected_step_id:
        raise ValueError(f"CP row process_step_id {step_id} does not match PFMEA {pfmea_id} step {expected_step_id}")
    if step_id not in pfd_map:
        raise ValueError(f"CP row references unknown confirmed PFD step: {step_id}")

    pfd_step = pfd_map[step_id]
    counters[step_id] = counters.get(step_id, 0) + 1
    row = dict(raw_row)
    row.update(_extract_cp_base_fields(row, pfmea_row, pfd_step, step_id, pfmea_id))
    row.update(_extract_cp_control_fields(row, pfmea_row))
    row.update(_extract_cp_reaction_fields(row))
    if not text(row.get("product_process_characteristic")):
        row["product_process_characteristic"] = text(
            row.get("product_characteristic"),
            row.get("process_characteristic"),
        )
    if not string_list(row.get("source_special_characteristics")):
        row["source_special_characteristics"] = (
            string_list(pfmea_row.get("characteristic_refs"))
            or string_list(pfmea_row.get("source_special_characteristics"))
            or string_list(pfd_step.get("special_characteristics"))
        )
    row.setdefault("sample_size", "")
    row.setdefault("sample_frequency", "")
    if not text(row.get("specification")):
        row["specification"] = text(
            row.get("specification_tolerance"),
            row.get("parameter_specification"),
        )
    if not string_list(row.get("evidence_refs")):
        row["evidence_refs"] = (
            string_list(raw_row.get("evidence_refs"))
            or string_list(pfmea_row.get("evidence_refs"))
            or string_list(pfd_step.get("evidence_refs"))
            or string_list(fallback_evidence_refs)
        )
    row["control_plan_id"] = f"CP-{step_id}-{counters[step_id]:02d}"
    return row


# ---------------------------------------------------------------------------
# Stage 3: 基于已确认 PFMEA 生成 CP
# ---------------------------------------------------------------------------


def generate_cp_from_confirmed_pfmea(
    drawing_analysis: dict[str, Any],
    confirmed_pfd: dict[str, Any],
    confirmed_pfmea: dict[str, Any],
    model: str | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """基于已确认的 PFMEA + PFD，LLM 推理生成控制计划。

    Args:
        drawing_analysis: 图纸分析 bundle
        confirmed_pfd: 已确认的 process_flow
        confirmed_pfmea: 已确认的 pfmea bundle
        model: LLM 模型名

    Returns:
        control_plan bundle 字典（含 rows 列表和 metadata）
    """
    from .pipeline_chain import (  # noqa: PLC0415
        _build_drawing_context,
        _drawing_page_evidence_refs,
        _ensure_list,
        _now_iso,
    )

    pfmea_rows = [
        r
        for r in (confirmed_pfmea.get("rows") or [])
        if isinstance(r, dict) and not r.get("deleted") and not r.get("soft_deleted")
    ]
    if not pfmea_rows:
        raise PipelineError(
            "Confirmed PFMEA has no rows — cannot generate CP",
            stage="cp",
            user_message_zh="已确认的 PFMEA 中没有可用的行，无法生成控制计划。",
        )

    target_rows = pfmea_rows

    context_text = _build_drawing_context(drawing_analysis)
    drawing_evidence_refs = _drawing_page_evidence_refs(drawing_analysis)
    pfd_map = {
        str(step.get("process_step_id", "")).strip(): step
        for step in (confirmed_pfd.get("steps") or [])
        if isinstance(step, dict) and str(step.get("process_step_id", "")).strip()
    }
    pfmea_map = {
        str(row.get("pfmea_id", "")).strip(): row
        for row in pfmea_rows
        if isinstance(row, dict) and str(row.get("pfmea_id", "")).strip()
    }
    cp_rows: list[dict[str, Any]] = []
    failed_row_ids: list[str] = []
    counters: dict[str, int] = {}
    # Select endpoint from service pool for health tracking
    _pool = get_llm_service_pool()
    _endpoint = _pool.get_next_endpoint()
    if _endpoint:
        logger.debug("cp_pool_endpoint", name=_endpoint.name, healthy=_endpoint.is_healthy)

    from .adapters.llm_text import OpenAITextGenerator

    llm = OpenAITextGenerator()

    # Prepare tasks for parallel execution
    valid_pfmea_rows = [
        (i, pfmea_row)
        for i, pfmea_row in enumerate(target_rows)
        if isinstance(pfmea_row, dict) and str(pfmea_row.get("pfmea_id", "")).strip()
    ]

    # Validate all rows before parallel execution
    for _, pfmea_row in valid_pfmea_rows:
        pfmea_id = str(pfmea_row.get("pfmea_id", "")).strip()
        process_step_id = str(pfmea_row.get("process_step_id", "")).strip()
        if process_step_id and process_step_id not in pfd_map:
            raise ValueError(f"PFMEA row {pfmea_id} references unknown confirmed PFD step: {process_step_id}")

    def _generate_cp_for_row(
        index: int, row: dict[str, Any]
    ) -> tuple[int, str, str, dict[str, Any]]:
        pid = str(row.get("pfmea_id", "")).strip()
        step_id = str(row.get("process_step_id", "")).strip()
        logger.info("CHAIN [Stage 3] Calling LLM to generate CP", pfmea_id=pid)
        result = wrap_llm_call(llm.generate_structured, name=f"cp_{pid}")(
            system_prompt=CP_SYSTEM_PROMPT,
            user_prompt=_build_cp_pfmea_row_prompt(context_text, pfd_map.get(step_id, {}), row),
            response_format=CP_OUTPUT_SCHEMA,
            model=model,
        )
        return index, pid, step_id, result

    parallel_batch_size = 4
    completed_count = 0
    for batch_start in range(0, len(valid_pfmea_rows), parallel_batch_size):
        batch = valid_pfmea_rows[batch_start : batch_start + parallel_batch_size]
        batch_results: dict[int, tuple[str, str, dict[str, Any] | None]] = {}
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = {executor.submit(_generate_cp_for_row, idx, row): (idx, row) for idx, row in batch}
            for future in as_completed(futures):
                idx, pfmea_row = futures[future]
                pfmea_id = str(pfmea_row.get("pfmea_id", "")).strip()
                process_step_id = str(pfmea_row.get("process_step_id", "")).strip()
                try:
                    _, _, process_step_id, generated_result = future.result()
                except Exception as exc:
                    logger.error(
                        "CHAIN [Stage 3] CP generation failed after retries", pfmea_id=pfmea_id, error=str(exc)
                    )
                    failed_row_ids.append(pfmea_id)
                    batch_results[idx] = (pfmea_id, process_step_id, None)
                    continue
                batch_results[idx] = (pfmea_id, process_step_id, generated_result)

        # Process results in original order
        for idx, _pfmea_row in batch:
            entry = batch_results.get(idx)
            if entry is None:
                continue
            pfmea_id, process_step_id, generated_cp = entry
            if generated_cp is None:
                continue
            step_rows = []
            for raw_row in _ensure_list(generated_cp, "rows"):
                try:
                    row = _normalize_chain_cp_row(
                        raw_row,
                        pfd_map,
                        pfmea_map,
                        counters,
                        expected_pfmea_id=pfmea_id,
                        fallback_evidence_refs=drawing_evidence_refs,
                    )
                except ValueError as exc:
                    logger.error("CHAIN [Stage 3] CP row validation failed", pfmea_id=pfmea_id, error=str(exc))
                    raise
                except Exception as exc:
                    logger.warning("CHAIN [Stage 3] CP row normalization failed", pfmea_id=pfmea_id, error=str(exc))
                    continue
                if row:
                    step_rows.append(row)
                    cp_rows.append(row)
            completed_count += 1
            if on_progress and step_rows:
                on_progress(
                    {
                        "type": "step_complete",
                        "stage": "cp",
                        "step_index": completed_count - 1,
                        "total_steps": len(valid_pfmea_rows),
                        "step_id": pfmea_id,
                        "rows_so_far": len(cp_rows),
                        "new_rows": step_rows,
                    }
                )

    if not cp_rows:
        raise ValueError("CP generation returned no rows")

    logger.info("CHAIN [Stage 3] CP generated", row_count=len(cp_rows), failed_rows=failed_row_ids)
    struct_logger.info(
        "pipeline_chain.stage_done",
        stage="cp",
        row_count=len(cp_rows),
        failed_row_ids=failed_row_ids,
    )

    return {
        "rows": cp_rows,
        "metadata": {
            "chain_stage": "cp",
            "chain_stage_status": "generated",
            "chain_pfmea_snapshot": confirmed_pfmea,
            "cp_generation_strategy": "per_pfmea_row",
            "generated_at": _now_iso(),
            "failed_row_ids": failed_row_ids,
        },
    }
