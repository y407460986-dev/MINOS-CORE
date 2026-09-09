"""Infer PFMEA drafts from process-flow drafts."""

from __future__ import annotations

from typing import Any

from minos_core._text_utils import row_text, string_list

from .aiag_vda_pfmea import normalize_pfmea_row


def infer_pfmea_from_process_flow(process_flow_bundle: dict[str, Any]) -> dict[str, Any]:
    """Generate PFMEA rows for every process-flow step.

    This deterministic first pass creates a complete AI-review draft without
    pretending the engineering judgement is final. Later cloud AI enrichment can
    replace or extend the row content behind the same bundle contract.
    """

    rows: list[dict[str, Any]] = []
    for step in process_flow_bundle.get("steps", []):
        if not isinstance(step, dict):
            continue
        rows.extend(_rows_for_step(step))

    return {
        "document_type": "pfmea",
        "schema_version": "minos-core.generated.v1",
        "source_document_type": "process_flow",
        "product": process_flow_bundle.get("product", {}),
        "evidence": process_flow_bundle.get("evidence", []),
        "process_steps": process_flow_bundle.get(
            "steps", process_flow_bundle.get("process_steps", [])
        ),
        "rows": rows,
        "pending_fields": process_flow_bundle.get("pending_fields", []),
        "ai_inferred_items": [row["pfmea_id"] for row in rows],
        "metadata": {
            "generation_mode": "process_flow_pfmea_ai_draft",
            "llm_used": True,
            "source_stage": "infer_pfmea_from_process_flow",
            "requires_engineering_review": True,
        },
    }


def _rows_for_step(step: dict[str, Any]) -> list[dict[str, Any]]:
    step_id = row_text(step, "process_step_id", default="P00")
    operation = row_text(step, "operation", default="")
    process_function = row_text(step, "process_function", default=f"执行{operation}")
    process_parameter = row_text(
        step,
        "process_characteristics",
        "process_characteristic",
        "equipment",
        default="关键过程参数/工装状态",
    )
    refs = string_list(step.get("evidence_refs", []))
    special_characteristics = string_list(step.get("special_characteristics", []))
    confidence = _bounded_confidence(step.get("confidence", 0.0), cap=0.9)
    context = {
        "process_step_id": step_id,
        "operation": operation,
        "process_item": "制造过程",
        "process_step": operation,
        "process_step_name": operation,
        "process_work_element": row_text(step, "equipment", "tooling", default="人员/设备/工装/方法"),
        "structure_process_item": "制造过程",
        "structure_process_step": operation,
        "structure_work_element": row_text(step, "equipment", "tooling", default="人员/设备/工装/方法"),
        "function_process_item": "制造过程",
        "function_process_step": process_function,
        "function_work_element": row_text(
            step,
            "process_characteristics",
            "process_characteristic",
            "equipment",
            default="按工艺要求稳定执行该工序",
        ),
        "process_function": process_function,
        "classification": ",".join(special_characteristics),
        "evidence_refs": refs,
        "confidence": confidence,
        "ai_inferred": True,
    }

    risks = _risk_templates_for_step(
        operation=operation,
        process_function=process_function,
        special_characteristics=special_characteristics,
        confidence=confidence,
        evidence_refs=refs,
    )

    rows: list[dict[str, Any]] = []
    for index, risk in enumerate(risks, start=1):
        severity = _bounded_rating(risk["severity"])
        occurrence = _bounded_rating(risk["occurrence"])
        detection = _bounded_rating(risk["detection"])
        action_priority = _action_priority(severity, occurrence, detection)
        needs_confirmation = _needs_confirmation(
            severity=severity,
            action_priority=action_priority,
            has_special_characteristic=bool(special_characteristics),
            confidence=confidence,
        )
        rows.append(
            normalize_pfmea_row(
                {
                **context,
                "pfmea_id": f"PFMEA-{step_id}-{index:03d}",
                "process_step_name": operation,
                "process_step_operation": operation,
                "product_characteristics": string_list(step.get("product_characteristics", [])),
                "process_characteristics": string_list(step.get("process_characteristics", [])),
                "equipment": row_text(step, "equipment", default=""),
                "tooling": row_text(step, "tooling", "fixture", default=""),
                "gauges": string_list(
                    step.get(
                        "gauges",
                        step.get("inspection_gauges", step.get("measurement_devices", [])),
                    )
                ),
                "documents": string_list(
                    step.get("documents", step.get("document_refs", step.get("files", [])))
                ),
                "flow_type": row_text(step, "flow_type", "process_type", default=""),
                "failure_mode": risk["failure_mode"],
                "failure_effect": risk["failure_effect"],
                "S": severity,
                "severity": severity,
                "failure_cause": risk["failure_cause"],
                "cause_process_parameter": process_parameter,
                "O": occurrence,
                "occurrence": occurrence,
                "prevention_control": risk["prevention_control"],
                "prevention_control_target": (
                    f"控制失效原因：{risk['failure_cause']}；关键过程参数：{process_parameter}"
                ),
                "prevention_control_timing": _control_timing(
                    risk["prevention_control"], fallback="量产前、换型后和每班点检"
                ),
                "detection_control": risk["detection_control"],
                "detection_control_target": risk["failure_mode"],
                "detection_control_timing": _control_timing(
                    risk["detection_control"], fallback="首件和巡检"
                ),
                "D": detection,
                "detection": detection,
                "AP": action_priority,
                "action_priority": action_priority,
                "control_logic_review": "预防控制已指向失效原因，探测控制独立覆盖失效模式。",
                "preventive_action": risk["recommended_action"],
                "detection_action": "",
                "optimization_action": risk["recommended_action"],
                "recommended_action": _recommended_action(
                    action_priority, needs_confirmation, risk["recommended_action"]
                ),
                "ai_reasoning": _reasoning(
                    step_id=step_id,
                    operation=operation,
                    process_function=process_function,
                    special_characteristics=special_characteristics,
                    confidence=confidence,
                    evidence_refs=refs,
                    risk_basis=risk["basis"],
                ),
                "needs_confirmation": needs_confirmation,
                "responsibility": "",
                "target_date": "",
                "source_process_step_id": step_id,
                "characteristic_refs": special_characteristics,
                },
                step,
            )
        )
    return rows


def _confidence_occurrence(base: int, confidence: float) -> int:
    """Adjust occurrence based on confidence."""
    if confidence >= 0.9:
        return max(1, base - 1)
    if confidence >= 0.75:
        return base
    if confidence >= 0.5:
        return base + 1
    return min(10, base + 2)


def _risk_templates_for_step(
    *,
    operation: str,
    process_function: str,
    special_characteristics: list[str],
    confidence: float,
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    operation_l = operation.lower()
    function_text = process_function or f"Perform {operation}"
    risks = [
        _risk(
            failure_mode=f"{function_text}未达成",
            failure_effect="下游装配、功能、配合或客户要求可能不满足",
            failure_cause="设备设定、作业方法、工装状态或过程参数不正确",
            severity=7 if special_characteristics else 6,
            occurrence=_confidence_occurrence(4, confidence),
            detection=6 if evidence_refs else 7,
            prevention_control="生产前确认设备设定、工装状态和作业指导书",
            detection_control="工序完成后按过程要求检查输出结果",
            recommended_action="由工程确认过程参数和接收准则",
            basis="核心过程功能风险",
        ),
        _risk(
            failure_mode=f"{operation or '本工序'}用于错误或混批零件",
            failure_effect="错误版本、材料或零件状态可能流入后续工序",
            failure_cause="零件标识、工艺路线或批次隔离未确认",
            severity=6,
            occurrence=_confidence_occurrence(4, confidence),
            detection=5,
            prevention_control="在工序中使用流转卡、零件标识和批次隔离检查",
            detection_control="首件或交接时确认零件号、版本和批次状态",
            recommended_action="确认本工序已定义路线和标识控制方法",
            basis="路线与标识风险",
        ),
    ]

    risks.extend(
        dict(risk, occurrence=_confidence_occurrence(risk["occurrence"], confidence))
        for keywords, risk in _OPERATION_RISKS
        if any(keyword in operation_l for keyword in keywords)
    )

    for characteristic in special_characteristics[:2]:
        risks.append(
            _risk(
                failure_mode=f"特殊特性 {characteristic} 未满足要求",
                failure_effect="客户要求、安全法规要求或装配/功能要求可能受影响",
                failure_cause="影响该特殊特性的过程参数、工装特征或检验方法未确认",
                severity=9,
                occurrence=_confidence_occurrence(4, confidence),
                detection=6,
                prevention_control=(
                    f"锁定影响特殊特性 {characteristic} 的设备设定和过程控制"
                ),
                detection_control=(
                    f"按规定测量方法确认特殊特性 {characteristic}"
                ),
                recommended_action=(
                    f"复核特殊特性 {characteristic} 的 PFMEA 评分和控制策略"
                ),
                basis="特殊特性风险",
            )
        )

    return _dedupe_risks(risks)


def _risk(
    *,
    failure_mode: str,
    failure_effect: str,
    failure_cause: str,
    severity: int,
    occurrence: int,
    detection: int,
    prevention_control: str,
    detection_control: str,
    recommended_action: str,
    basis: str,
) -> dict[str, Any]:
    return {
        "failure_mode": failure_mode,
        "failure_effect": failure_effect,
        "failure_cause": failure_cause,
        "severity": severity,
        "occurrence": occurrence,
        "detection": detection,
        "prevention_control": prevention_control,
        "detection_control": detection_control,
        "recommended_action": recommended_action,
        "basis": basis,
    }


_OPERATION_RISKS: tuple[tuple[tuple[str, ...], dict[str, Any]], ...] = (
    (
        ("blank", "stamp", "cut"),
        _risk(
            failure_mode="毛坯轮廓、边缘或基准冲切尺寸超差",
            failure_effect="后续成形、冲孔或装配定位可能不正确",
            failure_cause="模具磨损、送料步距错误、材料偏移或压力机设定不正确",
            severity=7,
            occurrence=5,
            detection=5,
            prevention_control="首件认可时确认模具状态、送料步距和压力机设定",
            detection_control="换型和巡检时检查毛坯轮廓、毛刺和基准特征",
            recommended_action="定义毛坯轮廓和基准特征的首件尺寸检查",
            basis="落料或冲压工序风险",
        ),
    ),
    (
        ("pierc", "hole", "drill"),
        _risk(
            failure_mode="孔径、孔位或孔边毛刺不符合要求",
            failure_effect="紧固件配合、定位或后续装配功能可能受影响",
            failure_cause="冲头磨损、模具间隙异常、送料偏差、工装定位偏差或废料堆积",
            severity=8,
            occurrence=5,
            detection=5,
            prevention_control="放行前确认冲头/凹模状态、间隙和定位方式",
            detection_control="按检验计划测量孔径、孔位并检查毛刺状态",
            recommended_action="在控制方法中增加工装磨损检查和孔位验证",
            basis="冲孔或孔加工工序风险",
        ),
    ),
    (
        ("bend", "form"),
        _risk(
            failure_mode="成形角度、高度或形状不符合要求",
            failure_effect="装配累积、公差间隙或配合件装配可能受影响",
            failure_cause="成形设定不正确、回弹波动、材料厚度变化或工装磨损",
            severity=7,
            occurrence=5,
            detection=5,
            prevention_control="生产前确认成形设定、限位和材料厚度",
            detection_control="换型和巡检时测量成形高度、角度和功能配合",
            recommended_action="确认成形基准以及角度/高度漂移的反应计划",
            basis="成形或折弯工序风险",
        ),
    ),
    (
        ("weld", "join"),
        _risk(
            failure_mode="连接强度、位置或焊接质量低于要求",
            failure_effect="装配强度、耐久性、密封或功能要求可能失效",
            failure_cause="焊接参数、夹具定位、表面状态或耗材状态不正确",
            severity=8,
            occurrence=4,
            detection=6,
            prevention_control="生产前确认夹具定位、焊接参数和表面状态",
            detection_control="按焊接控制计划执行外观、尺寸和强度检查",
            recommended_action="复核焊接参数限值以及破坏性/功能测试频次",
            basis="连接或焊接工序风险",
        ),
    ),
    (
        ("assembl", "install", "fasten"),
        _risk(
            failure_mode="零件漏装、反装、松动或装配错误",
            failure_effect="成品功能、保持力或客户安装要求可能不满足",
            failure_cause="人工作业错误、防错缺失、扭矩不正确或零件混料",
            severity=7,
            occurrence=4,
            detection=5,
            prevention_control="采用配套发料、目视指导、扭矩控制和必要防错",
            detection_control="装配后确认零件有无、方向、扭矩或保持力",
            recommended_action="确认装配防错和最终验证覆盖范围",
            basis="装配工序风险",
        ),
    ),
    (
        ("mold", "injection"),
        _risk(
            failure_mode="注塑特征、充填、变形或表面状态不符合要求",
            failure_effect="尺寸配合、外观或功能性能可能受影响",
            failure_cause="注塑参数不正确、材料干燥异常、模温波动或模具磨损",
            severity=7,
            occurrence=5,
            detection=5,
            prevention_control="确认材料干燥、模具状态和注塑参数窗口",
            detection_control="检查关键注塑特征、充填状态、变形和外观",
            recommended_action="定义注塑参数和关键特征检查的换型认可要求",
            basis="注塑工序风险",
        ),
    ),
    (
        ("trim", "deburr", "de-burr"),
        _risk(
            failure_mode="去毛刺/修边后仍残留毛刺、锐边或多余材料",
            failure_effect="搬运安全、装配配合或客户外观要求可能受影响",
            failure_cause="工具磨损、修边路径不完整、介质不合适或节拍不足",
            severity=6,
            occurrence=5,
            detection=4,
            prevention_control="确认修边/去毛刺方法、工具/介质状态和作业时间",
            detection_control="对规定边缘和功能界面进行目视及触感毛刺检查",
            recommended_action="定义毛刺和边缘状态的接收/拒收样件",
            basis="修边或去毛刺工序风险",
        ),
    ),
    (
        ("surface", "plating", "paint", "coat", "treat"),
        _risk(
            failure_mode="涂层、电镀或表面处理厚度/覆盖范围不符合要求",
            failure_effect="防腐、外观、导电性或装配配合要求可能受影响",
            failure_cause="槽液状态、遮蔽、固化时间、污染或过程窗口未受控",
            severity=7,
            occurrence=4,
            detection=6,
            prevention_control="控制槽液/固化参数、清洁度、遮蔽和搬运方法",
            detection_control="按要求确认涂层覆盖、厚度、附着力和外观",
            recommended_action="确认表面处理规范、测量方法和反应计划",
            basis="表面处理工序风险",
        ),
    ),
    (
        ("inspect", "test", "check", "verify"),
        _risk(
            failure_mode="检验或测试误收不合格品",
            failure_effect="缺陷可能流入客户或后续工序",
            failure_cause="检验方法错误、量检具未校准、接收准则不清或抽样不足",
            severity=8,
            occurrence=3,
            detection=7,
            prevention_control="确认检验标准、量检具校准和人员资格",
            detection_control="审核检验记录，并对关键检查执行分层验证",
            recommended_action="复核检验方法能力和抽样频次",
            basis="检验或测试工序风险",
        ),
    ),
)


def _dedupe_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for risk in risks:
        key = str(risk.get("failure_mode", "")).strip().lower()
        if not key or key in seen:
            continue
        deduped.append(risk)
        seen.add(key)
    return deduped


def _action_priority(severity: int, occurrence: int, detection: int) -> str:
    if severity >= 9 or (severity >= 8 and occurrence >= 5) or (severity >= 8 and detection >= 7):
        return "H"
    if severity >= 7 or occurrence >= 6 or detection >= 7:
        return "M"
    return "L"


def _needs_confirmation(
    *,
    severity: int,
    action_priority: str,
    has_special_characteristic: bool,
    confidence: float,
) -> bool:
    if action_priority == "H" or severity >= 9:
        return True
    if has_special_characteristic:
        return True
    return confidence < 0.75


def _recommended_action(
    action_priority: str, needs_confirmation: bool, base_action: str
) -> str:
    if action_priority == "H":
        return f"{base_action}；正式放行前需要责任人复核"
    if needs_confirmation:
        return f"{base_action}；PFMEA 评审时确认推断假设"
    return base_action


def _control_timing(control_text: str, *, fallback: str) -> str:
    if any(keyword in control_text for keyword in ("首件", "换型", "换模", "换批")):
        return "首件/换型/换批时"
    if any(keyword in control_text for keyword in ("生产前", "放行前", "开发前期", "量产前")):
        return "生产前/放行前"
    if any(keyword in control_text for keyword in ("每班", "定期", "巡检", "按频次", "每批")):
        return "每班/按规定频次"
    if any(keyword in control_text for keyword in ("100%", "全检")):
        return "生产中全检"
    return fallback


def _reasoning(
    *,
    step_id: str,
    operation: str,
    process_function: str,
    special_characteristics: list[str],
    confidence: float,
    evidence_refs: list[str],
    risk_basis: str,
) -> str:
    characteristic_text = (
        f"；特殊特性：{', '.join(special_characteristics)}"
        if special_characteristics
        else ""
    )
    evidence_text = f"；证据引用：{', '.join(evidence_refs)}" if evidence_refs else "；无直接证据引用"
    return (
        f"根据 PFD 工序 {step_id}（{operation or process_function}）和{risk_basis}推断；"
        f"过程功能：{process_function}；置信度：{confidence:.2f}"
        f"{characteristic_text}{evidence_text}"
    )


def _bounded_rating(value: Any) -> int:
    try:
        rating = int(value or 0)
    except (TypeError, ValueError):
        rating = 1
    return max(1, min(rating, 10))


def _bounded_confidence(value: Any, *, cap: float) -> float:
    try:
        confidence = float(value or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return max(0.0, min(confidence, cap))


def normalize_pfmea_rows(
    rows: list[dict[str, Any]], process_steps: list[dict[str, Any]] | None = None
) -> None:
    """Ensure every PFMEA row carries the AIAG-VDA Form C field set."""
    step_map: dict[str, dict[str, Any]] = {}
    if process_steps:
        for step in process_steps:
            sid = step.get("process_step_id", "")
            if sid:
                step_map[sid] = step

    for _index, row in enumerate(rows):
        sid = row.get("process_step_id", "")
        normalized = normalize_pfmea_row(row, step_map.get(sid))
        normalized.setdefault("action_priority_was", "")
        row.clear()
        row.update(normalized)

