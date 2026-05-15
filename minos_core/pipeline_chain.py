"""
链式三表生成 Pipeline (PFD → PFMEA → CP)

每个阶段基于上一阶段的确认快照，调用 LLM 推理生成下一阶段内容。
绘图分析（OCR + Vision）复用现有 pipeline，不在此模块中重复实现。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from ._text_utils import text, flow_type_display
from .adapters.llm_text import OpenAITextGenerator
from .aiag_vda_pfmea import normalize_pfmea_row
from .drawing_to_pfd import normalize_process_flow_steps

logger = logging.getLogger(__name__)

STAGE_STATUS = ("not_started", "running", "generated", "confirmed", "blocked", "failed")

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
- product_characteristic_class: 产品特性分类，取值为 SC(重要) / CC(关键) / 无
- process_characteristics: 该工序的过程特性（输入变量，如冲压力、温度）
- process_characteristic_class: 过程特性分类，取值为 SC / CC / 无
- special_characteristics: 该工序涉及的特殊特性清单 (SC/CC)，无则为空数组 []
- needs_confirmation: AI 不确定时应设为 true

工序数量控制在 5-20 个，覆盖从来料检验、加工、过程检验到最终检验的完整制造流程。
根据图纸特征推断合理的工艺路线。不要凭空编造设备和工序。"""

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
- work_element_4m: 工作要素 4M 类型，取值为 人 / 机 / 料 / 法

【功能分析 Step 3】
- function_process_item: 功能分析-过程项功能
- function_process_step: 过程步骤功能 + 产品特性
- function_work_element: 工作要素功能 + 过程特性

【失效分析 Step 4】
- failure_effect: 失效后果 (FE)，对最终用户或下一工序的影响
- severity: 严重度 S (1-10)，基于 AIAG-VDA 严重度评估表（10=安全风险，7-9=主要功能丧失）
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
- needs_confirmation: AI 不确定时应设为 true

每个工序应生成 1-5 个失效模式行，覆盖不同类型和 4M 来源的失效方式。
重点关注图纸中的特殊特性 (SC/CC) 和关键尺寸对应的工序。"""

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
- process_parameter: 过程参数（现场需要设定或稳定的变量，如冲压力、温度、扭矩、夹具定位状态）
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
- needs_confirmation: AI 不确定时应设为 true

重点为 PFMEA 中 action_priority 为 H 和 M 的行生成对应的控制计划行。
低风险 (L) 的行可以不生成控制计划行，除非涉及特殊特性 (SC/CC)。

输出只能是符合 schema 的 JSON 对象，不要输出 Markdown、原因判断、处理方案、说明文字或任何 JSON 之外的内容。"""

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
                                "description": "工序编号 P01, P02,..."
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
                                "type": "integer", "minimum": 1, "maximum": 10
                            },
                            "failure_mode": {"type": "string"},
                            "failure_cause": {"type": "string"},
                            "cause_process_parameter": {"type": "string"},
                            "prevention_control": {"type": "string"},
                            "prevention_control_target": {"type": "string"},
                            "prevention_control_timing": {"type": "string"},
                            "occurrence": {
                                "type": "integer", "minimum": 1, "maximum": 10
                            },
                            "detection_control": {"type": "string"},
                            "detection_control_target": {"type": "string"},
                            "detection_control_timing": {"type": "string"},
                            "detection": {
                                "type": "integer", "minimum": 1, "maximum": 10
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
                            "pfmea_id", "process_step_id",
                            "process_item", "process_step_name",
                            "structure_process_item",
                            "structure_process_step",
                            "structure_work_element",
                            "work_element_4m",
                            "function_process_item",
                            "function_process_step", "function_work_element",
                            "failure_effect", "severity",
                            "failure_mode", "failure_cause",
                            "cause_process_parameter",
                            "prevention_control",
                            "prevention_control_target",
                            "prevention_control_timing",
                            "occurrence",
                            "detection_control",
                            "detection_control_target",
                            "detection_control_timing",
                            "detection",
                            "action_priority", "special_characteristics",
                            "preventive_action", "detection_action",
                            "optimization_action",
                            "responsible_person", "target_date", "status",
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
                            "control_plan_id", "process_step_id", "pfmea_id",
                            "process_name", "equipment",
                            "characteristic_number", "product_characteristic",
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
                            "sample_size", "sample_frequency",
                            "control_method", "reaction_plan",
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
# 绘图分析上下文构建
# ---------------------------------------------------------------------------

def _build_drawing_context(drawing_analysis: dict) -> str:
    """将图纸分析结果格式化为 LLM 可读的文本上下文。"""
    parts: list[str] = []

    identity = drawing_analysis.get("drawing_identity") or {}
    parts.append(f"零件名: {text(identity.get('part_name', '未识别'))}")
    parts.append(f"图号: {text(identity.get('drawing_number', '未识别'))}")

    for key, label in [
        ("materials", "材料"),
        ("dimensions", "关键尺寸"),
        ("special_characteristics", "特殊特性"),
        ("technical_requirements", "技术要求"),
        ("manufacturing_clues", "制造线索"),
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
            else:
                texts = [text(i.get('description', i.get('name', str(i)))) for i in items]
            parts.append(f"{label}: {'; '.join(texts)}")

    return "\n".join(parts)


def _ensure_list(result: dict, key: str) -> list[dict]:
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
    return datetime.now(timezone.utc).isoformat()


def _infer_flow_type_from_step(step: dict) -> str:
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
    drawing_analysis: dict,
    model: str | None = None,
) -> dict:
    """基于图纸分析结果，LLM 推理生成过程流程图。

    Args:
        drawing_analysis: 图纸分析 bundle（来自 OCR + Vision）
        model: LLM 模型名

    Returns:
        process_flow bundle 字典（含 steps 列表和 metadata）
    """
    logger.info("CHAIN [Stage 1] Calling LLM to generate PFD")
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

    llm = OpenAITextGenerator()
    pfd_result = llm.generate_structured(
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

    logger.info("CHAIN [Stage 1] PFD generated: %d steps", len(pfd_steps))

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


# ---------------------------------------------------------------------------
# Stage 2: 基于已确认 PFD 生成 PFMEA
# ---------------------------------------------------------------------------

def generate_pfmea_from_confirmed_pfd(
    drawing_analysis: dict,
    confirmed_pfd: dict,
    model: str | None = None,
) -> dict:
    """基于已确认的 PFD，LLM 推理生成 PFMEA。

    Args:
        drawing_analysis: 图纸分析 bundle（作为工程上下文）
        confirmed_pfd: 用户已确认锁定的 process_flow bundle
        model: LLM 模型名

    Returns:
        pfmea bundle 字典（含 rows 列表和 metadata）
    """
    pfd_steps = confirmed_pfd.get("steps") or []
    if not pfd_steps:
        raise ValueError("Confirmed PFD has no steps — cannot generate PFMEA")

    context_text = _build_drawing_context(drawing_analysis)
    step_map = {
        str(step.get("process_step_id", "")).strip(): step
        for step in pfd_steps
        if isinstance(step, dict) and str(step.get("process_step_id", "")).strip()
    }
    pfmea_rows = []
    failed_step_ids: list[str] = []
    counters: dict[str, int] = {}
    llm = OpenAITextGenerator()
    for step in pfd_steps:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("process_step_id", "")).strip()
        if not step_id:
            continue
        logger.info("CHAIN [Stage 2] Calling LLM to generate PFMEA for %s", step_id)
        try:
            pfmea_result = llm.generate_structured(
                system_prompt=PFMEA_SYSTEM_PROMPT,
                user_prompt=_build_pfmea_step_prompt(context_text, step),
                response_format=PFMEA_OUTPUT_SCHEMA,
                model=model,
            )
        except Exception as exc:
            logger.error("CHAIN [Stage 2] PFMEA generation failed for %s: %s", step_id, exc)
            raise ValueError(
                f"Cannot generate PFMEA for step {step_id}: {exc}"
            ) from exc
        for raw_row in _ensure_list(pfmea_result, "rows"):
            try:
                row = _normalize_chain_pfmea_row(raw_row, step_map, counters, expected_step_id=step_id)
            except ValueError as exc:
                # Validation error (data integrity issue) → fail immediately
                logger.error("CHAIN [Stage 2] PFMEA row validation failed for %s: %s", step_id, exc)
                raise
            except Exception as exc:
                # Other errors (e.g., type conversion) → log and skip row
                logger.warning("CHAIN [Stage 2] PFMEA row normalization failed for %s: %s", step_id, exc)
                continue
            if row:
                pfmea_rows.append(row)

    if not pfmea_rows:
        raise ValueError("PFMEA generation returned no rows")

    logger.info("CHAIN [Stage 2] PFMEA generated: %d rows (failed steps: %s)", len(pfmea_rows), failed_step_ids)

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


def _build_pfmea_step_prompt(context_text: str, step: dict[str, Any]) -> str:
    step_text = json.dumps([step], ensure_ascii=False, indent=2)
    return f"""请基于以下已确认的单个过程流程图 (PFD) 工序和图纸分析结果，生成 PFMEA。

图纸分析摘要:
{context_text}

已确认的 PFD 工序:
{step_text}

请只为这个工序生成 1-5 个潜在的失效模式行。
所有输出行的 process_step_id 必须等于该工序编号。
重点关注图纸中的特殊特性 (SC/CC) 和关键尺寸。
预防控制必须控制失效原因或原因过程参数，探测控制必须单独说明探测对象和时机。
根据 AIAG-VDA 2019 Action Priority 表评定 H/M/L；不要输出旧版 RPN。
对不确定的评定请将 needs_confirmation 设为 true。"""


def _normalize_chain_pfmea_row(
    raw_row: Any,
    step_map: dict[str, dict[str, Any]],
    counters: dict[str, int],
    *,
    expected_step_id: str | None = None,
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
    row.update(
        {
            "process_step_id": step_id,
            "operation": operation,
            "process_step_name": operation,
            "process_function": process_function,
            "process_step": operation,
            "process_item": text(row.get("process_item"), row.get("structure_process_item"), "制造过程"),
            "process_work_element": text(
                row.get("process_work_element"),
                row.get("structure_work_element"),
                step.get("equipment"),
                step.get("tooling"),
                row.get("work_element_4m"),
            ),
            "structure_process_item": text(row.get("structure_process_item"), row.get("process_item"), "制造过程"),
            "structure_process_step": operation,
            "structure_work_element": text(
                row.get("structure_work_element"),
                row.get("process_work_element"),
                step.get("equipment"),
                step.get("tooling"),
                row.get("work_element_4m"),
            ),
            "function_process_item": text(row.get("function_process_item"), row.get("process_item"), "制造过程"),
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
    if not text(row.get("pfmea_id")):
        row["pfmea_id"] = f"PFMEA-{step_id}-{counters[step_id]:02d}"
    return normalize_pfmea_row(row, step)


# ---------------------------------------------------------------------------
# Stage 3: 基于已确认 PFMEA 生成 CP
# ---------------------------------------------------------------------------

def generate_cp_from_confirmed_pfmea(
    drawing_analysis: dict,
    confirmed_pfd: dict,
    confirmed_pfmea: dict,
    model: str | None = None,
) -> dict:
    """基于已确认的 PFMEA + PFD，LLM 推理生成控制计划。

    Args:
        drawing_analysis: 图纸分析 bundle
        confirmed_pfd: 已确认的 process_flow
        confirmed_pfmea: 已确认的 pfmea bundle
        model: LLM 模型名

    Returns:
        control_plan bundle 字典（含 rows 列表和 metadata）
    """
    pfmea_rows = confirmed_pfmea.get("rows") or []
    if not pfmea_rows:
        raise ValueError("Confirmed PFMEA has no rows — cannot generate CP")

    high_ap_rows = [r for r in pfmea_rows if r.get("action_priority") in ("H", "M")]
    target_rows = high_ap_rows if high_ap_rows else pfmea_rows

    context_text = _build_drawing_context(drawing_analysis)
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
    cp_rows = []
    failed_row_ids: list[str] = []
    counters: dict[str, int] = {}
    llm = OpenAITextGenerator()
    for pfmea_row in target_rows:
        if not isinstance(pfmea_row, dict):
            continue
        pfmea_id = str(pfmea_row.get("pfmea_id", "")).strip()
        if not pfmea_id:
            raise ValueError("Confirmed PFMEA row has no pfmea_id — cannot generate CP")
        process_step_id = str(pfmea_row.get("process_step_id", "")).strip()
        if process_step_id and process_step_id not in pfd_map:
            raise ValueError(f"PFMEA row {pfmea_id} references unknown confirmed PFD step: {process_step_id}")
        logger.info("CHAIN [Stage 3] Calling LLM to generate CP for %s", pfmea_id)
        try:
            cp_result = llm.generate_structured(
                system_prompt=CP_SYSTEM_PROMPT,
                user_prompt=_build_cp_pfmea_row_prompt(context_text, pfd_map.get(process_step_id, {}), pfmea_row),
                response_format=CP_OUTPUT_SCHEMA,
                model=model,
            )
        except Exception as exc:
            logger.error("CHAIN [Stage 3] CP generation failed for %s: %s", pfmea_id, exc)
            raise ValueError(
                f"Cannot generate Control Plan for PFMEA {pfmea_id}: {exc}"
            ) from exc
        for raw_row in _ensure_list(cp_result, "rows"):
            try:
                row = _normalize_chain_cp_row(
                    raw_row,
                    pfd_map,
                    pfmea_map,
                    counters,
                    expected_pfmea_id=pfmea_id,
                )
            except ValueError as exc:
                # Validation error → fail immediately
                logger.error("CHAIN [Stage 3] CP row validation failed for %s: %s", pfmea_id, exc)
                raise
            except Exception as exc:
                # Other errors → log and skip row
                logger.warning("CHAIN [Stage 3] CP row normalization failed for %s: %s", pfmea_id, exc)
                continue
            if row:
                cp_rows.append(row)

    if not cp_rows:
        raise ValueError("CP generation returned no rows")

    logger.info("CHAIN [Stage 3] CP generated: %d rows (failed rows: %s)", len(cp_rows), failed_row_ids)

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
控制计划必须先说明过程如何被控制，再说明结果如何被检验：
- process_parameter 优先来自 PFMEA 的 cause_process_parameter，其次才是 PFMEA/PFD 过程特性；parameter_specification / process_control_method 必须来自 PFMEA 的失效原因和预防控制。
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
    row.setdefault("sample_size", "")
    row.setdefault("sample_frequency", "")
    if not text(row.get("control_plan_id")):
        row["control_plan_id"] = f"CP-{step_id}-{counters[step_id]:02d}"
    return row
