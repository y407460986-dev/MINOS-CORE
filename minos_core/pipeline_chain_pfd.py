"""PFD generation stage — LLM infers Process Flow Diagram from drawing analysis.

Extracted from pipeline_chain.py. Pure extraction, no logic changes.
"""

# Prompt lines intentionally retain their semantic grouping for LLM input.
# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from ._text_utils import flow_type_display, string_list, text
from .drawing_to_pfd_build import normalize_process_flow_steps
from .observability.logging import get_logger
from .pipeline._llm_protected import get_llm_service_pool, wrap_llm_call

logger = get_logger(__name__)
struct_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# LLM Prompt 模板
# ---------------------------------------------------------------------------

PFD_SYSTEM_PROMPT = """\
你是一个 IATF 16949 / APQP 过程流程图 (Process Flow Diagram) 设计专家。
你的任务是基于图纸分析结果，按照 AIAG APQP 手册 Section 3.3 标准格式，为制造零件设计完整的过程流程图。

每个工序必须包含以下标准字段：
- process_step_id: 工序编号 (P01, P02, P03...)，这是链接 PFMEA 和控制计划的关键字段
- flow_type: 标准流程符号，必须取 operation / inspection / transport / storage / rework / outsourced 之一
- flow_symbol: 同 flow_type，必须使用英文标准值；中文符号可放在 flow_type_display
- flow_type_display: 中文显示值，如 加工 / 检验 / 运输 / 存储 / 返工 / 外协
- operation_type: 工序类型符号，取值为 加工 / 检验 / 运输 / 存储
- operation: 工序名称（中文，动词+名词格式如"来料检验""冲压成形"）
- input_material: 本工序输入物料/上一工序输出
- output_result: 本工序输出结果
- previous_step_ids: 上一工序编号数组，首工序为空数组 []
- next_step_ids: 下一工序编号数组，末工序为空数组 []
- process_function: 工序功能描述，说明该步骤对产品做了什么
- equipment: 所需设备、工装、夹具
- product_characteristics: 该工序影响的产品特性（输出变量，如外径、硬度）
- product_characteristic_class: 产品特性分类，取值为 SC(重要) / CC(关键) / 无。只有图纸上明确标注了特殊特性符号（如倒三角△、菱形◇、星号★或文字"SC""CC"）的特性才能标 SC 或 CC，其余一律填"无"。不要根据工序重要性自行推断。
- process_characteristics: 该工序的过程特性（输入变量，如冲压力、温度）
- process_characteristic_class: 过程特性分类，取值为 SC / CC / 无。规则同上：必须有图纸标注依据，不得自行推断。
- special_characteristics: 该工序涉及的特殊特性清单 (SC/CC)，无则为空数组 []
- needs_confirmation: AI 不确定时应设为 true

工序数量控制在 5-20 个，覆盖从来料检验、加工、过程检验到最终检验的完整制造流程。
根据图纸特征推断合理的工艺路线。不要凭空编造设备和工序。
SC/CC 标注原则：一个典型零件通常只有 2-5 个工序涉及特殊特性（图纸上有明确标注的），不是所有工序都有。如果图纸分析中没有提到特殊特性符号，则所有工序的 characteristic_class 都应填"无"。"""

# ---------------------------------------------------------------------------
# JSON Schema 输出约束
# ---------------------------------------------------------------------------

PFD_OUTPUT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "process_flow_diagram",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "process_step_id": {
                                "type": "string",
                                "description": "工序编号 P01, P02,...",
                            },
                            "flow_type": {
                                "type": "string",
                                "enum": ["operation", "inspection", "transport", "storage", "rework", "outsourced"],
                            },
                            "flow_symbol": {
                                "type": "string",
                                "enum": ["operation", "inspection", "transport", "storage", "rework", "outsourced"],
                            },
                            "flow_type_display": {"type": "string"},
                            "operation_type": {
                                "type": "string",
                                "enum": ["加工", "检验", "运输", "存储", "返工", "外协"],
                            },
                            "operation": {"type": "string"},
                            "input_material": {"type": "string"},
                            "output_result": {"type": "string"},
                            "previous_step_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "next_step_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "process_function": {"type": "string"},
                            "equipment": {"type": "string"},
                            "product_characteristics": {"type": "string"},
                            "product_characteristic_class": {
                                "type": "string",
                                "enum": ["SC", "CC", "无"],
                            },
                            "process_characteristics": {"type": "string"},
                            "process_characteristic_class": {
                                "type": "string",
                                "enum": ["SC", "CC", "无"],
                            },
                            "special_characteristics": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "needs_confirmation": {"type": "boolean"},
                        },
                        "required": [
                            "process_step_id", "flow_type", "flow_symbol",
                            "flow_type_display", "operation_type", "operation",
                            "input_material", "output_result",
                            "previous_step_ids", "next_step_ids",
                            "process_function", "equipment",
                            "product_characteristics",
                            "product_characteristic_class",
                            "process_characteristics",
                            "process_characteristic_class",
                            "special_characteristics",
                            "needs_confirmation",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["steps"],
            "additionalProperties": False,
        },
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_flow_type_from_step(step: dict[str, Any]) -> str:
    symbol = str(step.get("flow_symbol", "")).strip()
    if symbol in ("检验", "inspection", "检查", "试验"):
        return "inspection"
    if symbol in ("加工", "operation", "生产", "成形", "冲压"):
        return "operation"
    if symbol in ("搬运", "transport"):
        return "transport"
    if symbol in ("存储", "storage", "仓储"):
        return "storage"
    if symbol in ("返工", "rework"):
        return "rework"
    if symbol in ("外协", "outsourced"):
        return "outsourced"
    op_type = str(step.get("operation_type", "")).strip()
    if op_type in ("检验", "inspection"):
        return "inspection"
    if op_type in ("加工", "operation"):
        return "operation"
    operation = str(step.get("operation", "")).strip()
    if any(t in operation for t in ("检验", "检查", "试验", "测试")):
        return "inspection"
    return "operation"


# ---------------------------------------------------------------------------
# Stage 1: LLM 推理生成 PFD
# ---------------------------------------------------------------------------


def generate_pfd_from_drawing(
    drawing_analysis: dict[str, Any],
    model: str | None = None,
) -> dict[str, Any]:
    """基于图纸分析结果，LLM 推理生成过程流程图。

    Args:
        drawing_analysis: 图纸分析 bundle（来自 OCR + Vision）
        model: LLM 模型名

    Returns:
        process_flow bundle 字典（含 steps 列表和 metadata）
    """
    from .pipeline_chain import (  # noqa: PLC0415  -- shared helpers avoid circular import
        _attach_special_candidate_labels_to_pfd_steps,
        _build_drawing_context,
        _drawing_page_evidence_refs,
        _ensure_list,
        _family_route_summary,
        _now_iso,
    )

    logger.info("CHAIN [Stage 1] Calling LLM to generate PFD")
    struct_logger.info("pipeline_chain.stage_start", stage="pfd")
    context_text = _build_drawing_context(drawing_analysis)

    # 附加零件族信息
    pfc = drawing_analysis.get("_part_family")
    if pfc and isinstance(pfc, dict):
        family_name = text(
            pfc.get("family_name")
            or pfc.get("part_family")
            or pfc.get("family_key")
        )
        if family_name:
            context_text += f"\n零件族: {family_name}"
    family_context = drawing_analysis.get("_family_context")
    if isinstance(family_context, dict):
        route_templates = family_context.get("process_route_templates")
        if isinstance(route_templates, list) and route_templates:
            route_summary = _family_route_summary(route_templates)
            if route_summary:
                context_text += f"\n知识库建议工艺路线: {route_summary}"

    user_prompt = f"""请基于以下图纸分析结果生成完整的过程流程图 (PFD)。

图纸分析摘要:
{context_text}

请生成完整的 steps 数组。每个工序必须有 process_step_id、flow_type、flow_symbol、operation、input_material、output_result、previous_step_ids、next_step_ids、process_function、equipment。
对不确定的字段请将 needs_confirmation 设为 true。"""

    # Select endpoint from service pool for health tracking
    _pool = get_llm_service_pool()
    _endpoint = _pool.get_next_endpoint()
    if _endpoint:
        logger.debug("pfd_pool_endpoint", name=_endpoint.name, healthy=_endpoint.is_healthy)

    from .adapters.llm_text import OpenAITextGenerator
    llm = OpenAITextGenerator()
    pfd_result = wrap_llm_call(llm.generate_structured, name="pfd")(
        system_prompt=PFD_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_format=PFD_OUTPUT_SCHEMA,
        model=model,
    )

    pfd_steps = _ensure_list(pfd_result, "steps")
    default_input_material = text(
        (drawing_analysis.get("drawing_identity") or {}).get("part_name", "")
    ) or "来料"
    for i, step in enumerate(pfd_steps):
        if not step.get("process_step_id"):
            step["process_step_id"] = f"P{i + 1:02d}"
        if not string_list(step.get("evidence_refs")):
            step["evidence_refs"] = _drawing_page_evidence_refs(drawing_analysis)
        step.setdefault("special_characteristics", [])
        step.setdefault("product_characteristics", "")
        step.setdefault("process_characteristics", "")
        step["ai_inferred"] = True
        # Infer flow_type from available fields
        if not step.get("flow_type"):
            step["flow_type"] = _infer_flow_type_from_step(step)
        step.setdefault("flow_symbol", step["flow_type"])
        step.setdefault("flow_type_display", flow_type_display(step.get("flow_type", "operation")))
        step.setdefault("operation_type", step["flow_type_display"])
        step.setdefault("input_material", default_input_material if i == 0 else "")
        step.setdefault("output_result", step.get("operation", ""))
        step.setdefault("previous_step_ids", [])
        step.setdefault("next_step_ids", [])
    normalize_process_flow_steps(
        pfd_steps,
        default_input_material=default_input_material,
    )
    _attach_special_candidate_labels_to_pfd_steps(pfd_steps, drawing_analysis)

    logger.info("CHAIN [Stage 1] PFD generated", step_count=len(pfd_steps))
    struct_logger.info(
        "pipeline_chain.stage_done",
        stage="pfd",
        step_count=len(pfd_steps),
    )

    return {
        "steps": pfd_steps,
        "metadata": {
            "chain_stage": "pfd",
            "chain_stage_status": "generated",
            "part_family_hint": pfd_result.get("part_family_hint", ""),
            "process_route_summary": pfd_result.get("process_route_summary", ""),
            "generated_at": _now_iso(),
        },
    }
