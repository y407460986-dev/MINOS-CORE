"""APQP Chinese workbook export."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .xlsx import WorkbookWriter


def export_apqp_workbook(
    chain: Any,
    path: str | Path,
    *,
    require_gate: bool = True,
    export_mode: str = "final",
    quality_gate: Any | None = None,
) -> Path:
    """Export an APQP chain into the fixed Chinese workbook.

    ``export_mode='final'`` is the customer-submission path and is protected by
    ``require_export_gate`` by default. ``export_mode='draft'`` writes an explicit
    draft-only workbook for engineering review without pretending to be released.
    """

    if export_mode not in {"final", "draft"}:
        raise ValueError(f"unsupported export_mode: {export_mode!r}")
    if export_mode == "final" and require_gate:
        from ..quality_gates import require_export_gate

        quality_gate = require_export_gate(chain)
    elif quality_gate is None:
        from ..quality_gates import evaluate_stage_gate

        quality_gate = evaluate_stage_gate(chain, stage="export")
    workbook = WorkbookWriter()
    if export_mode == "draft":
        workbook.add_sheet(
            "DRAFT_ONLY",
            _draft_notice_rows(quality_gate),
            column_widths={1: 30, 2: 90},
            auto_filter=False,
        )
    workbook.add_sheet(
        "摘要",
        _summary_rows(chain, export_mode),
        column_widths={1: 24, 2: 70},
    )
    workbook.add_sheet(
        "质量门状态",
        _quality_gate_rows(chain, quality_gate, export_mode),
        column_widths={1: 24, 2: 18, 3: 80},
    )
    workbook.add_sheet(
        "过程流程图", _process_flow_rows(chain), column_widths={1: 12, 2: 28, 3: 42}
    )
    workbook.add_sheet(
        "PFMEA",
        _pfmea_rows(chain),
        column_widths={1: 12, 2: 24, 3: 26, 4: 26, 5: 26, 6: 12, 7: 12, 8: 12},
    )
    workbook.add_sheet(
        "控制计划",
        _control_plan_rows(chain),
        column_widths={1: 12, 2: 24, 3: 24, 4: 24, 5: 24, 6: 24, 7: 24},
    )
    workbook.add_sheet(
        "三表追溯矩阵",
        _traceability_rows(chain),
        column_widths={1: 12, 2: 24, 3: 28, 4: 28, 5: 28},
    )
    workbook.add_sheet(
        "人工复核清单",
        _manual_review_rows(chain, quality_gate, export_mode),
        column_widths={1: 8, 2: 24, 3: 20, 4: 14, 5: 80},
    )
    return workbook.save(path)


def _draft_notice_rows(quality_gate: Any) -> list[list[Any]]:
    return [
        ["项目", "内容"],
        ["export_mode", "draft"],
        ["draft_only", "true"],
        ["requires_engineering_review", "true"],
        ["not for customer submission", "true"],
        ["中文提示", "仅限草案：需要工程/质量人工复核，不能提交客户"],
        ["quality_gate_stage", _first_value(quality_gate, "stage", default="export")],
        [
            "quality_gate_can_continue",
            _yes_no(_first_value(quality_gate, "can_continue", default=False)),
        ],
        [
            "quality_gate_allow_final_export",
            _yes_no(_first_value(quality_gate, "allow_user_export", default=False)),
        ],
        [
            "manual_review_required",
            _yes_no(_first_value(quality_gate, "needs_human_review", default=False)),
        ],
        [
            "needs_confirmation_items",
            _join(_first_value(quality_gate, "needs_confirmation_items", default=[])),
        ],
        ["pending_fields", _join(_first_value(quality_gate, "pending_fields", default=[]))],
        [
            "ai_inferred_items",
            _join(_first_value(quality_gate, "ai_inferred_items", default=[])),
        ],
    ]


def _summary_rows(chain: Any, export_mode: str = "final") -> list[list[Any]]:
    rows = [
        ["项目", "内容"],
    ]
    if export_mode == "draft":
        rows.extend(
            [
                ["export_mode", "draft"],
                ["draft_only", "true"],
                ["requires_engineering_review", "true"],
                ["not for customer submission", "true"],
                ["状态说明", "仅限草案：需要工程/质量人工复核，不能提交客户"],
            ]
        )
    else:
        rows.append(["export_mode", "final"])
    rows.extend(
        [
            [
                "产品",
                _first_value(
                    chain,
                    "display_name",
                    "primary_analysis_name",
                    "product_name",
                    "name",
                    default="",
                ),
            ],
            ["标识", _first_value(chain, "slug", "id", "part_number", default="")],
            ["阶段", _first_value(chain, "process_stage", "stage", default="")],
            [
                "关键特性",
                _join(_first_value(chain, "critical_characteristics", default=[])),
            ],
            ["过程数量", len(_process_steps(chain))],
            ["PFMEA 项数", len(_items(chain, "pfmea", "pfmea_items", "failure_modes"))],
            [
                "控制计划项数",
                len(_items(chain, "control_plan", "control_plan_items", "controls")),
            ],
        ]
    )
    return rows


def _quality_gate_rows(
    chain: Any,
    quality_gate: Any | None = None,
    export_mode: str = "final",
) -> list[list[Any]]:
    if quality_gate is None:
        from ..quality_gates import evaluate_stage_gate

        gate = evaluate_stage_gate(chain, stage="export")
    else:
        gate = quality_gate
    coverage = gate.evidence_coverage
    rows = [
        ["项目", "状态/数量", "说明"],
    ]
    if export_mode == "draft":
        rows.extend(
            [
                [
                    "export_mode",
                    "draft",
                    "draft_only；requires_engineering_review；not for customer submission",
                ],
                ["draft_only", "true", "仅限草案，不可提交客户"],
                ["requires_engineering_review", "true", "需要工程/质量人工复核"],
                ["not for customer submission", "true", "不能作为正式 PPAP/APQP 客户提交件"],
            ]
        )
    rows.extend(
        [
            ["阶段", gate.stage, ""],
            ["可继续", _yes_no(gate.can_continue), "validation 通过且证据充分"],
            ["允许用户导出", _yes_no(gate.allow_user_export), "可继续且无待补、待确认或 AI-only 项"],
            ["证据充分", _yes_no(gate.evidence_sufficient), ""],
            [
                "证据覆盖率",
                _coverage_ratio(coverage),
                f"{coverage.get('covered_items', 0)}/{coverage.get('required_items', 0)}",
            ],
            [
                "未覆盖证据对象数",
                len(gate.uncovered_evidence_items),
                _join(gate.uncovered_evidence_items),
            ],
            [
                "缺失证据引用数",
                len(gate.missing_evidence_refs),
                _join(gate.missing_evidence_refs),
            ],
            [
                "被引用 AI 推断证据数",
                len(coverage.get("ai_inferred_refs", [])),
                _join(coverage.get("ai_inferred_refs", [])),
            ],
            [
                "待确认证据数",
                len(gate.needs_confirmation_items),
                _join(gate.needs_confirmation_items),
            ],
            ["待补字段数", len(gate.pending_fields), _join(gate.pending_fields)],
            ["AI 推断项数", len(gate.ai_inferred_items), _join(gate.ai_inferred_items)],
            ["人工复核项数", len(gate.manual_review_items), ""],
            ["校验消息数", len(gate.validation.messages), _join(gate.validation.messages)],
            ["工序数", gate.audit.counts.get("process_steps", 0), ""],
            ["PFMEA 数", gate.audit.counts.get("failure_modes", 0), ""],
            ["控制计划数", gate.audit.counts.get("controls", 0), ""],
            ["机械链接数", gate.audit.counts.get("mechanical_links", 0), ""],
            ["弱链接数", gate.audit.counts.get("weak_links", 0), ""],
        ]
    )
    return rows


def _process_flow_rows(chain: Any) -> list[list[Any]]:
    rows = [["步骤", "过程名称", "说明"]]
    steps = _process_steps(chain)
    if not steps:
        aliases = _mapping(chain, "step_aliases")
        for step_no, names in aliases.items():
            rows.append([step_no, _join(names), ""])
        return rows
    for step in steps:
        rows.append(
            [
                _first_value(step, "step_no", "step", "operation_no", "id", default=""),
                _first_value(
                    step, "name", "process_name", "operation", "title", default=""
                ),
                _first_value(step, "description", "summary", "notes", default=""),
            ]
        )
    return rows


def _pfmea_rows(chain: Any) -> list[list[Any]]:
    rows = [
        ["步骤", "过程", "失效模式", "失效后果", "失效原因", "严重度", "频度", "探测度"]
    ]
    for item in _items(chain, "pfmea", "pfmea_items", "failure_modes"):
        rows.append(
            [
                _first_value(item, "step_no", "step", "operation_no", default=""),
                _first_value(item, "process_name", "process", "operation", default=""),
                _first_value(item, "failure_mode", "mode", "failure", default=""),
                _first_value(item, "effect", "failure_effect", "effects", default=""),
                _first_value(item, "cause", "failure_cause", "causes", default=""),
                _first_value(item, "severity", "s", default=""),
                _first_value(item, "occurrence", "o", default=""),
                _first_value(item, "detection", "d", default=""),
            ]
        )
    return rows


def _control_plan_rows(chain: Any) -> list[list[Any]]:
    rows = [
        [
            "步骤",
            "过程",
            "产品/过程特性",
            "规格/公差",
            "评价/测量方法",
            "控制方法",
            "反应计划",
        ]
    ]
    for item in _items(chain, "control_plan", "control_plan_items", "controls"):
        rows.append(
            [
                _first_value(item, "step_no", "step", "operation_no", default=""),
                _first_value(item, "process_name", "process", "operation", default=""),
                _first_value(
                    item,
                    "characteristic",
                    "feature",
                    "product_characteristic",
                    "process_characteristic",
                    default="",
                ),
                _first_value(item, "specification", "spec", "tolerance", default=""),
                _first_value(
                    item, "measurement", "evaluation_method", "method", default=""
                ),
                _first_value(item, "control_method", "control", default=""),
                _first_value(item, "reaction_plan", "reaction", default=""),
            ]
        )
    return rows


def _traceability_rows(chain: Any) -> list[list[Any]]:
    rows = [["步骤", "特性", "过程流程图", "PFMEA", "控制计划"]]
    for item in _items(chain, "traceability_matrix", "traceability", "matrix"):
        rows.append(
            [
                _first_value(item, "step_no", "step", "operation_no", default=""),
                _first_value(item, "characteristic", "feature", default=""),
                _first_value(
                    item, "process_flow_ref", "flow_ref", "process_flow", default=""
                ),
                _first_value(item, "pfmea_ref", "pfmea", default=""),
                _first_value(item, "control_plan_ref", "control_plan", default=""),
            ]
        )
    if len(rows) == 1:
        for characteristic in _first_value(
            chain, "critical_characteristics", default=[]
        ):
            rows.append(["", characteristic, "", "", ""])
    return rows


def _manual_review_rows(
    chain: Any,
    quality_gate: Any | None = None,
    export_mode: str = "final",
) -> list[list[Any]]:
    if quality_gate is None:
        from ..quality_gates import evaluate_stage_gate

        gate = evaluate_stage_gate(chain, stage="export")
    else:
        gate = quality_gate
    rows = [["序号", "对象ID", "类别", "严重度", "复核说明"]]
    if export_mode == "draft":
        rows.append(
            [
                0,
                "draft_only",
                "export_mode",
                "review",
                "requires_engineering_review；not for customer submission；仅限草案，不能提交客户",
            ]
        )
    for index, item in enumerate(gate.manual_review_items, start=1):
        rows.append(
            [
                index,
                _first_value(item, "item_id", default=""),
                _first_value(item, "category", default=""),
                _first_value(item, "severity", default="review"),
                _first_value(item, "message", default=""),
            ]
        )
    return rows


def _process_steps(chain: Any) -> list[Any]:
    return _items(chain, "process_flow", "process_steps", "steps", "operations")


def _items(source: Any, *names: str) -> list[Any]:
    value = _first_value(source, *names, default=[])
    if isinstance(value, Mapping):
        return list(value.values())
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _mapping(source: Any, name: str) -> Mapping[str, Any]:
    value = _first_value(source, name, default={})
    return value if isinstance(value, Mapping) else {}


def _first_value(source: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(source, Mapping) and name in source:
            return source[name]
        if hasattr(source, name):
            return getattr(source, name)
    if hasattr(source, "model_dump"):
        dumped = source.model_dump()
        for name in names:
            if name in dumped:
                return dumped[name]
    if hasattr(source, "dict"):
        dumped = source.dict()
        for name in names:
            if name in dumped:
                return dumped[name]
    return default


def _join(value: Any) -> str:
    if isinstance(value, Mapping):
        return "；".join(f"{key}: {_join(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return "；".join(str(item) for item in value)
    return "" if value is None else str(value)


def _yes_no(value: Any) -> str:
    return "是" if bool(value) else "否"


def _coverage_ratio(coverage: Mapping[str, Any]) -> str:
    ratio = coverage.get("coverage_ratio", 0)
    try:
        return f"{float(ratio):.0%}"
    except (TypeError, ValueError):
        return "0%"
