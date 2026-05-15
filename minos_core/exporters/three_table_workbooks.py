"""Export unified and split PFD/PFMEA/CP workbooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .apqp_workbook import export_apqp_workbook
from .xlsx import WorkbookWriter


def export_three_table_workbook(
    chain: Any,
    path: str | Path,
    *,
    export_mode: str = "draft",
    require_gate: bool = False,
    quality_gate: Any | None = None,
    manual_review_items: list[Any] | None = None,
) -> Path:
    """Export the unified three-table workbook."""

    return export_apqp_workbook(
        chain,
        path,
        export_mode=export_mode,
        require_gate=require_gate,
        quality_gate=quality_gate,
        manual_review_items=manual_review_items,
    )


def export_split_three_table_workbooks(
    chain: Any,
    output_dir: str | Path,
    *,
    export_mode: str = "draft",
    require_gate: bool = False,
    quality_gate: Any | None = None,
) -> dict[str, Path]:
    """Export PFD, PFMEA and CP into three independent workbooks."""

    if export_mode not in {"draft", "final"}:
        raise ValueError(f"unsupported export_mode: {export_mode!r}")
    if export_mode == "final" and require_gate:
        from ..quality_gates import require_export_gate

        quality_gate = require_export_gate(chain)
    elif quality_gate is None:
        from ..quality_gates import evaluate_stage_gate

        quality_gate = evaluate_stage_gate(chain, stage="export")

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "process_flow": target_dir / "过程流程图.xlsx",
        "pfmea": target_dir / "PFMEA.xlsx",
        "control_plan": target_dir / "控制计划.xlsx",
    }
    _single_sheet_workbook(
        outputs["process_flow"],
        "过程流程图",
        _process_flow_rows(chain, export_mode, quality_gate),
    )
    _single_sheet_workbook(
        outputs["pfmea"], "PFMEA", _pfmea_rows(chain, export_mode, quality_gate)
    )
    _single_sheet_workbook(
        outputs["control_plan"],
        "控制计划",
        _control_plan_rows(chain, export_mode, quality_gate),
    )
    return outputs


def _single_sheet_workbook(path: Path, title: str, rows: list[list[Any]]) -> Path:
    workbook = WorkbookWriter()
    workbook.add_sheet(
        title,
        rows,
        column_widths={index: 24 for index in range(1, max((len(row) for row in rows), default=1) + 1)},
    )
    return workbook.save(path)


def _process_flow_rows(chain: Any, export_mode: str, quality_gate: Any | None = None) -> list[list[Any]]:
    rows = _mode_notice_rows(export_mode, quality_gate)
    rows.append(
        [
            "工序编号",
            "流程符号",
            "工序名称",
            "过程功能",
            "设备/工装",
            "产品特性",
            "过程特性",
            "特殊特性",
            "责任",
            "证据",
            "AI/复核",
        ]
    )
    for step in _items(chain, "process_steps", "steps"):
        rows.append(
            [
                _first(step, "sequence", "operation_no", "process_step_id", "step_no", default=""),
                _first(step, "flow_symbol", "flow_type_display", "flow_type", "operation_type", default=""),
                _first(step, "operation", "name", default=""),
                _first(step, "process_function", "description", default=""),
                _first(step, "equipment", "machine", "tooling", default=""),
                _join(_first(step, "product_characteristic", "product_characteristics", default=[])),
                _join(_first(step, "process_characteristic", "process_characteristics", default=[])),
                _join(_first(step, "special_characteristics", "special_characteristic", "classification", default=[])),
                _first(step, "owner", "responsibility", default=""),
                _join(_first(step, "evidence_refs", default=[])),
                _ai_review_text(step),
            ]
        )
    return rows


def _pfmea_rows(chain: Any, export_mode: str, quality_gate: Any | None = None) -> list[list[Any]]:
    rows = _mode_notice_rows(export_mode, quality_gate)
    rows.append(_pfmea_header())
    for row in _items(chain, "failure_modes", "rows"):
        rows.append(
            [
                _first(row, "pfmea_id", default=""),
                _first(row, "process_step_id", default=""),
                _first(row, "structure_process_item", "process_item", default=""),
                _first(row, "structure_process_step", "process_step", default=""),
                _first(row, "structure_work_element", "process_work_element", default=""),
                _first(row, "function_process_item", default=""),
                _first(row, "function_process_step", "function_requirement", "process_function", default=""),
                _first(row, "function_work_element", default=""),
                _first(row, "failure_mode", default=""),
                _first(row, "failure_effect", default=""),
                _first(row, "severity", default=""),
                _first(row, "failure_cause", default=""),
                _first(row, "cause_process_parameter", default=""),
                _first(row, "prevention_control", default=""),
                _first(row, "prevention_control_target", default=""),
                _first(row, "prevention_control_timing", default=""),
                _first(row, "occurrence", default=""),
                _first(row, "detection_control", default=""),
                _first(row, "detection_control_target", default=""),
                _first(row, "detection_control_timing", default=""),
                _first(row, "detection", default=""),
                _first(row, "action_priority", default=""),
                _first(row, "control_logic_review", default=""),
                _join(_first(row, "special_characteristics", "special_characteristic", "special_characteristic_class", "classification", default=[])),
                _first(row, "optimization_action", "recommended_action", default=""),
                _first(row, "responsible_person", "responsibility", default=""),
                _first(row, "target_date", default=""),
                _first(row, "status", "action_status", default=""),
                _first(row, "actual_completion_date", default=""),
                _after_action_text(row),
                _join(_first(row, "evidence_refs", default=[])),
                _ai_review_text(row),
            ]
        )
    return rows


def _control_plan_rows(chain: Any, export_mode: str, quality_gate: Any | None = None) -> list[list[Any]]:
    rows = _mode_notice_rows(export_mode, quality_gate)
    rows.append(_control_plan_header())
    for row in _items(chain, "controls", "rows"):
        rows.append(
            [
                _first(row, "control_plan_id", default=""),
                _first(row, "process_name", "process_step_id", default=""),
                _first(row, "pfmea_id", default=""),
                _first(row, "equipment", default=""),
                _first(row, "characteristic_number", default=""),
                _first(row, "product_characteristic", "product_process_characteristic", default=""),
                _first(row, "process_characteristic", default=""),
                _first(row, "special_characteristic_class", "classification", default=""),
                _first(row, "specification_tolerance", "specification", default=""),
                _first(row, "process_parameter", default=""),
                _first(row, "parameter_specification", default=""),
                _first(row, "process_control_method", default=""),
                _first(row, "setup_verification", default=""),
                _first(row, "poka_yoke_device", default=""),
                _first(row, "poka_yoke_verification", default=""),
                _first(row, "process_record", "record_form", default=""),
                _first(row, "measurement_method", default=""),
                _first(row, "sample_size", default=""),
                _first(row, "sample_frequency", default=""),
                _first(row, "control_method", default=""),
                _first(row, "reaction_plan", default=""),
                _join(_first(row, "evidence_refs", default=[])),
                _ai_review_text(row),
            ]
        )
    return rows


def _pfmea_header() -> list[str]:
    return [
        "PFMEA 编号",
        "工序编号",
        "结构过程项",
        "结构过程步骤",
        "结构工作要素",
        "功能过程项",
        "功能过程步骤",
        "功能工作要素",
        "失效模式",
        "失效后果",
        "S",
        "失效原因",
        "原因过程参数",
        "预防控制",
        "预防控制对象",
        "预防控制时机",
        "O",
        "探测控制",
        "探测对象",
        "探测时机",
        "D",
        "AP",
        "控制逻辑复核",
        "特殊特性",
        "优化措施",
        "责任人",
        "目标完成日期",
        "状态",
        "实际完成日期",
        "措施后 S/O/D/AP",
        "证据",
        "AI/复核",
    ]


def _control_plan_header() -> list[str]:
    return [
        "控制计划编号",
        "工序名称",
        "PFMEA 来源",
        "设备",
        "特性编号",
        "产品特性",
        "过程特性",
        "特殊特性分类",
        "规格和公差",
        "过程参数",
        "参数规格",
        "过程控制方法",
        "首件/换型确认",
        "防错装置",
        "防错验证",
        "过程记录",
        "测量方法",
        "样本容量",
        "检查频次",
        "控制方法",
        "反应计划",
        "证据",
        "AI/复核",
    ]


def _items(source: Any, *names: str) -> list[Any]:
    for name in names:
        value = _first(source, name, default=None)
        if isinstance(value, list):
            return value
    return []


def _first(source: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(source, dict) and name in source:
            return source[name]
        if hasattr(source, name):
            return getattr(source, name)
    return default


def _join(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return "" if value is None else str(value)


def _mode_notice_rows(export_mode: str, quality_gate: Any | None = None) -> list[list[Any]]:
    rows = [["导出模式", _export_mode_text(export_mode), ""]]
    if export_mode == "draft":
        rows.extend(
            [
                ["draft_only", "true", "仅限草案"],
                ["requires_engineering_review", "true", "需要工程/质量人工复核"],
                ["not for customer submission", "true", "不能提交客户"],
            ]
        )
    else:
        rows.append(
            [
                "quality_gate_allow_final_export",
                _yes_no(_first(quality_gate, "allow_user_export", default=False)),
                "正式导出质量门",
            ]
        )
    return rows


def _after_action_text(row: Any) -> str:
    values = [
        _first(row, "after_severity", default=""),
        _first(row, "after_occurrence", default=""),
        _first(row, "after_detection", default=""),
        _first(row, "after_ap", default=""),
    ]
    return "/".join(str(value) for value in values if value not in {"", None})


def _ai_review_text(row: Any) -> str:
    flags = []
    if _first(row, "ai_inferred", default=False):
        flags.append("AI")
    if _first(row, "needs_confirmation", default=False):
        flags.append("需复核")
    confidence = _first(row, "confidence", default="")
    if confidence not in {"", None}:
        flags.append(f"置信度={confidence}")
    return "; ".join(flags)


def _export_mode_text(export_mode: str) -> str:
    return {"draft": "草案", "final": "正式"}.get(export_mode, export_mode)


def _yes_no(value: Any) -> str:
    return "是" if bool(value) else "否"
