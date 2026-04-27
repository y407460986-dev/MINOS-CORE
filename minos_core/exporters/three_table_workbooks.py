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
    workbook.add_sheet(title, rows, column_widths={1: 14, 2: 26, 3: 32, 4: 36, 5: 36, 6: 24})
    return workbook.save(path)


def _process_flow_rows(chain: Any, export_mode: str, quality_gate: Any | None = None) -> list[list[Any]]:
    rows = _mode_notice_rows(export_mode, quality_gate)
    rows.append(["工序编号", "工序名称", "过程功能", "证据", "AI/复核"])
    for step in _items(chain, "process_steps", "steps"):
        rows.append(
            [
                _first(step, "process_step_id", "step_no", default=""),
                _first(step, "operation", "name", default=""),
                _first(step, "process_function", "description", default=""),
                _join(_first(step, "evidence_refs", default=[])),
                _ai_review_text(step),
            ]
        )
    return rows


def _pfmea_rows(chain: Any, export_mode: str, quality_gate: Any | None = None) -> list[list[Any]]:
    rows = _mode_notice_rows(export_mode, quality_gate)
    rows.append([
        "PFMEA 编号",
        "工序编号",
        "过程项",
        "过程步骤",
        "过程工作要素",
        "功能/要求",
        "失效模式",
        "失效后果",
        "S",
        "失效原因",
        "预防控制",
        "O",
        "探测控制",
        "D",
        "AP",
        "RPN",
        "推荐措施",
        "责任人",
        "目标完成日期",
        "措施状态",
        "实际完成日期",
        "措施后 S/O/D/AP/RPN",
        "证据",
        "AI/复核",
    ])
    for row in _items(chain, "failure_modes", "rows"):
        rows.append(
            [
                _first(row, "pfmea_id", default=""),
                _first(row, "process_step_id", default=""),
                _first(row, "process_item", default=""),
                _first(row, "process_step", default=""),
                _first(row, "process_work_element", default=""),
                _first(row, "function_requirement", "process_function", default=""),
                _first(row, "failure_mode", default=""),
                _first(row, "failure_effect", default=""),
                _first(row, "severity", default=""),
                _first(row, "failure_cause", default=""),
                _first(row, "prevention_control", default=""),
                _first(row, "occurrence", default=""),
                _first(row, "detection_control", default=""),
                _first(row, "detection", default=""),
                _first(row, "action_priority", default=""),
                _first(row, "rpn", default=""),
                _first(row, "recommended_action", default=""),
                _first(row, "responsibility", default=""),
                _first(row, "target_date", default=""),
                _first(row, "action_status", default=""),
                _first(row, "actual_completion_date", default=""),
                _after_action_text(row),
                _join(_first(row, "evidence_refs", default=[])),
                _ai_review_text(row),
            ]
        )
    return rows


def _control_plan_rows(chain: Any, export_mode: str, quality_gate: Any | None = None) -> list[list[Any]]:
    rows = _mode_notice_rows(export_mode, quality_gate)
    rows.append(["控制计划编号", "工序", "PFMEA 来源", "特性", "规格", "方法/频次", "反应计划", "证据", "AI/复核"])
    for row in _items(chain, "controls", "rows"):
        rows.append(
            [
                _first(row, "control_plan_id", default=""),
                _first(row, "process_step_id", default=""),
                _first(row, "pfmea_id", default=""),
                _first(row, "product_process_characteristic", default=""),
                _first(row, "specification", default=""),
                f"{_first(row, 'measurement_method', default='')} / {_first(row, 'sample_frequency', default='')}",
                _first(row, "reaction_plan", default=""),
                _join(_first(row, "evidence_refs", default=[])),
                _ai_review_text(row),
            ]
        )
    return rows


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
        _first(row, "after_rpn", default=""),
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
