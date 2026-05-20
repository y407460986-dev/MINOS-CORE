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
    manual_review_items: list[Any] | None = None,
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
    if export_mode == "final":
        workbook.add_sheet(
            "正式导出审计",
            _final_audit_rows(chain, quality_gate, manual_review_items),
            column_widths={1: 18, 2: 24, 3: 30, 4: 88},
        )
    workbook.add_sheet(
        "知识推荐与行动闭环",
        _knowledge_action_audit_rows(chain),
        column_widths={1: 18, 2: 28, 3: 24},
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
        _manual_review_rows(chain, quality_gate, export_mode, manual_review_items),
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
            [
                "明细复核项数",
                len(gate.manual_review_items),
                "内部审计明细；用户优先查看人工复核清单中的中文摘要。",
            ],
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
    rows = [
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
        ]
    ]
    steps = [s for s in _process_steps(chain) if not _first_value(s, "deleted", default=False)]
    if not steps:
        aliases = _mapping(chain, "step_aliases")
        for step_no, names in aliases.items():
            rows.append([step_no, "", _join(names), "", "", "", "", "", ""])
        return rows
    for step in steps:
        rows.append(
            [
                _first_value(step, "sequence", "operation_no", "process_step_id", "step_no", "step", "id", default=""),
                _first_value(step, "flow_symbol", "flow_type_display", "flow_type", "operation_type", default=""),
                _first_value(
                    step, "name", "process_name", "operation", "title", default=""
                ),
                _first_value(step, "process_function", "description", "summary", "notes", default=""),
                _first_value(step, "equipment", "machine", "tooling", default=""),
                _join(_first_value(step, "product_characteristic", "product_characteristics", default=[])),
                _join(_first_value(step, "process_characteristic", "process_characteristics", default=[])),
                _join(_first_value(step, "special_characteristics", "special_characteristic", "classification", default=[])),
                _first_value(step, "owner", "responsibility", default=""),
            ]
        )
    return rows


def _pfmea_rows(chain: Any) -> list[list[Any]]:
    rows = [
        [
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
            "严重度 S",
            "失效原因",
            "原因过程参数",
            "预防控制",
            "预防控制对象",
            "预防控制时机",
            "频度 O",
            "探测控制",
            "探测对象",
            "探测时机",
            "探测度 D",
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
            "复核状态",
        ]
    ]
    for item in _items(chain, "pfmea", "pfmea_items", "failure_modes"):
        rows.append(
            [
                _first_value(item, "pfmea_id", "id", default=""),
                _first_value(
                    item, "process_step_id", "step_no", "step", "operation_no", default=""
                ),
                _first_value(item, "structure_process_item", "process_item", default=""),
                _first_value(
                    item,
                    "structure_process_step",
                    "process_step",
                    "process_step_name",
                    "process_step_operation",
                    "process_name",
                    "operation",
                    default="",
                ),
                _first_value(item, "structure_work_element", "process_work_element", default=""),
                _first_value(item, "function_process_item", default=""),
                _first_value(
                    item,
                    "function_process_step",
                    "function_requirement",
                    "process_function",
                    "process",
                    default="",
                ),
                _first_value(item, "function_work_element", default=""),
                _first_value(item, "failure_mode", "mode", "failure", default=""),
                _first_value(item, "effect", "failure_effect", "effects", default=""),
                _first_value(item, "severity", "s", "S", default=""),
                _first_value(item, "cause", "failure_cause", "causes", default=""),
                _first_value(item, "cause_process_parameter", default=""),
                _first_value(item, "prevention_control", default=""),
                _first_value(item, "prevention_control_target", default=""),
                _first_value(item, "prevention_control_timing", default=""),
                _first_value(item, "occurrence", "o", "O", default=""),
                _first_value(item, "detection_control", default=""),
                _first_value(item, "detection_control_target", default=""),
                _first_value(item, "detection_control_timing", default=""),
                _first_value(item, "detection", "d", "D", default=""),
                _first_value(item, "action_priority", "AP", default=""),
                _first_value(item, "control_logic_review", default=""),
                _join(_first_value(item, "special_characteristics", "special_characteristic", "special_characteristic_class", "classification", default=[])),
                _first_value(item, "optimization_action", "recommended_action", default=""),
                _first_value(item, "responsible_person", "responsibility", "owner", default=""),
                _first_value(item, "target_date", default=""),
                _first_value(item, "status", "action_status", default=""),
                _first_value(item, "actual_completion_date", "completion_date", default=""),
                _after_action_text(item),
                _join(_first_value(item, "evidence_refs", default=[])),
                _review_status_text(item),
            ]
        )
    return rows


def _control_plan_rows(chain: Any) -> list[list[Any]]:
    rows = [
        [
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
        ]
    ]
    for item in _items(chain, "control_plan", "control_plan_items", "controls"):
        rows.append(
            [
                _first_value(item, "control_plan_id", "id", default=""),
                _first_value(item, "process_name", "process", "operation", default=""),
                _first_value(item, "pfmea_id", "source_pfmea_id", default=""),
                _first_value(item, "equipment", "machine", default=""),
                _first_value(item, "characteristic_number", "characteristic_no", default=""),
                _first_value(item, "product_characteristic", "characteristic", "feature", default=""),
                _first_value(item, "process_characteristic", default=""),
                _first_value(item, "special_characteristic_class", "classification", default=""),
                _first_value(item, "specification_tolerance", "specification", "spec", "tolerance", default=""),
                _first_value(item, "process_parameter", default=""),
                _first_value(item, "parameter_specification", default=""),
                _first_value(item, "process_control_method", default=""),
                _first_value(item, "setup_verification", default=""),
                _first_value(item, "poka_yoke_device", default=""),
                _first_value(item, "poka_yoke_verification", default=""),
                _first_value(item, "process_record", "record_form", default=""),
                _first_value(item, "measurement_method", "measurement", "evaluation_method", "method", default=""),
                _first_value(item, "sample_size", default=""),
                _first_value(item, "sample_frequency", "frequency", default=""),
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
    display_items: list[Any] | None = None,
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
    items = display_items if display_items is not None else gate.manual_review_items
    for index, item in enumerate(items, start=1):
        rows.append(
            [
                index,
                _first_value(item, "item_id", default=""),
                _first_value(item, "category", default="人工复核"),
                _first_value(
                    item,
                    "severity_display",
                    "severity",
                    default="需复核",
                ),
                _manual_review_message(item),
            ]
        )
    return rows


def _final_audit_rows(
    chain: Any,
    quality_gate: Any | None = None,
    manual_review_items: list[Any] | None = None,
) -> list[list[Any]]:
    if quality_gate is None:
        from ..quality_gates import evaluate_stage_gate

        gate = evaluate_stage_gate(chain, stage="export")
    else:
        gate = quality_gate
    metadata = _metadata(chain)
    confirmations = _list_value(metadata.get("review_confirmations"))
    edit_history = _list_value(metadata.get("edit_history"))
    soft_deleted = _soft_deleted_summary(chain, metadata)
    manual_items = manual_review_items
    if manual_items is None:
        manual_items = _list_value(_first_value(gate, "manual_review_items", default=[]))

    rows = [
        ["类别", "项目", "状态/数量", "说明"],
        ["导出", "export_mode", "final", "正式导出审计页"],
        [
            "质量门",
            "allow_final_export",
            _yes_no(_first_value(gate, "allow_user_export", default=False)),
            "正式导出必须为“是”",
        ],
        [
            "质量门",
            "can_continue",
            _yes_no(_first_value(gate, "can_continue", default=False)),
            "",
        ],
        [
            "质量门",
            "evidence_sufficient",
            _yes_no(_first_value(gate, "evidence_sufficient", default=False)),
            "",
        ],
        [
            "质量门",
            "pending_fields",
            len(_list_value(_first_value(gate, "pending_fields", default=[]))),
            _join(_first_value(gate, "pending_fields", default=[])),
        ],
        [
            "质量门",
            "needs_confirmation_items",
            len(_list_value(_first_value(gate, "needs_confirmation_items", default=[]))),
            _join(_first_value(gate, "needs_confirmation_items", default=[])),
        ],
        [
            "质量门",
            "ai_inferred_items",
            len(_list_value(_first_value(gate, "ai_inferred_items", default=[]))),
            _join(_first_value(gate, "ai_inferred_items", default=[])),
        ],
        [
            "人工确认",
            "review_confirmations",
            len(confirmations),
            _confirmation_summary(confirmations),
        ],
        [
            "人工确认",
            "manual_review_items",
            len(manual_items),
            _manual_review_summary_text(manual_items),
        ],
        [
            "edit_patch",
            "edit_history",
            len(edit_history),
            _edit_history_summary(edit_history),
        ],
        [
            "软删除",
            "soft_deleted_items",
            len(soft_deleted),
            _join(soft_deleted),
        ],
        # --- v1.10_audit_summary ---
        [
            "v1.10_audit_summary",
            "sync_blocker_count",
            _sync_blocker_count(gate),
            "三表同步阻断项数量",
        ],
        [
            "v1.10_audit_summary",
            "open_action_count",
            _open_pfmea_action_count(chain),
            "未关闭 PFMEA 行动项数量",
        ],
        [
            "v1.10_audit_summary",
            "recommendation_blocker_count",
            _recommendation_blocker_count_from_gate(gate),
            "知识库推荐阻断项数量",
        ],
        [
            "v1.10_audit_summary",
            "linkage_gap_count",
            len(_list_value(_first_value(gate, "linkage_gaps", default=[]))),
            "三表联动缺口总数",
        ],
        [
            "v1.10_audit_summary",
            "soft_deleted_ids",
            len(soft_deleted),
            _soft_deleted_ids_text(chain, metadata),
        ],
    ]
    return rows


def _knowledge_action_audit_rows(source: dict) -> list[list[str]]:
    """生成知识推荐与行动闭环 sheet 的行数据。"""
    rows = []
    rows.append(["知识推荐与行动闭环", "", ""])
    rows.append(["类型", "编号", "状态"])

    # 知识推荐
    metadata = _first_value(source, "metadata", default={})
    recs = _list_value(metadata.get("knowledge_recommendations", []))
    for r in recs:
        rows.append([
            "知识推荐",
            _first_value(r, "recommendation_id", default=""),
            _first_value(r, "lifecycle_status", default="") or _first_value(r, "status", default=""),
        ])

    # 行动项
    actions = _list_value(metadata.get("action_items", []))
    for a in actions:
        rows.append([
            "行动项",
            _first_value(a, "action_id", default=""),
            _first_value(a, "status", default=""),
        ])

    return rows


def _manual_review_message(item: Any) -> str:
    message = str(_first_value(item, "message", default="")).strip()
    count = _first_value(item, "count", default=None)
    if count in {None, ""}:
        return message
    return f"{message}（涉及 {count} 条明细）"


def _after_action_text(item: Any) -> str:
    values = [
        _first_value(item, "after_severity", default=""),
        _first_value(item, "after_occurrence", default=""),
        _first_value(item, "after_detection", default=""),
        _first_value(item, "after_ap", default=""),
    ]
    return "/".join(str(value) for value in values if value not in {"", None})


def _review_status_text(item: Any) -> str:
    parts = []
    review_status = _first_value(item, "review_status", default="")
    if review_status:
        parts.append(str(review_status))
    if _first_value(item, "needs_confirmation", default=False):
        parts.append("需确认")
    if _first_value(item, "ai_inferred", default=False):
        parts.append("AI 草案")
    return "；".join(parts)


def _metadata(source: Any) -> Mapping[str, Any]:
    metadata = _first_value(source, "metadata", default={})
    return metadata if isinstance(metadata, Mapping) else {}


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return []


def _confirmation_summary(confirmations: list[Any]) -> str:
    values = []
    for item in confirmations[:20]:
        target = _first_value(item, "target", default="")
        confirmed_by = _first_value(item, "confirmed_by", default="")
        reason = _first_value(item, "reason", default="")
        values.append(
            " / ".join(str(part) for part in (target, confirmed_by, reason) if part)
        )
    return _join(values)


def _manual_review_summary_text(items: list[Any]) -> str:
    values = []
    for item in items[:20]:
        item_id = _first_value(item, "item_id", "target", default="")
        category = _first_value(item, "category", default="")
        message = _manual_review_message(item)
        values.append(
            " / ".join(str(part) for part in (item_id, category, message) if part)
        )
    return _join(values)


def _edit_history_summary(history: list[Any]) -> str:
    values = []
    for item in history[:20]:
        action = _first_value(item, "action", default="")
        table = _first_value(item, "table", default="")
        target_id = _first_value(item, "target_id", default="")
        edited_by = _first_value(item, "edited_by", default="")
        values.append(
            " / ".join(str(part) for part in (action, table, target_id, edited_by) if part)
        )
    return _join(values)


def _soft_deleted_summary(chain: Any, metadata: Mapping[str, Any]) -> list[str]:
    explicit = _list_value(metadata.get("soft_deleted_items"))
    values = [str(item) for item in explicit if str(item).strip()]
    values.extend(
        _deleted_row_labels(_items(chain, "process_flow", "process_steps", "steps"), "process_flow")
    )
    values.extend(_deleted_row_labels(_items(chain, "pfmea", "pfmea_items", "failure_modes"), "pfmea"))
    values.extend(
        _deleted_row_labels(
            _items(chain, "control_plan", "control_plan_items", "controls"),
            "control_plan",
        )
    )
    result = []
    seen = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _deleted_row_labels(rows: list[Any], table: str) -> list[str]:
    labels = []
    for row in rows:
        if not _first_value(row, "deleted", default=False):
            continue
        row_id = _first_value(
            row,
            "process_step_id",
            "pfmea_id",
            "control_plan_id",
            "id",
            default="",
        )
        labels.append(f"{table}:{row_id}" if row_id else table)
    return labels


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


def _sync_blocker_count(gate: Any) -> int:
    """Count sync_issues with blocker severity from the quality gate."""
    sync_issues = _list_value(_first_value(gate, "sync_issues", default=[]))
    return sum(1 for i in sync_issues if isinstance(i, dict) and i.get("severity") == "blocker")


def _open_pfmea_action_count(chain: Any) -> int:
    """Count PFMEA rows with open (not completed/closed) actions."""
    count = 0
    for row in _items(chain, "pfmea", "pfmea_items", "failure_modes"):
        status = str(_first_value(row, "status", "action_status", default="")).strip().lower()
        if status in {"", "open", "待处理", "进行中", "in_progress", "not started", "未开始"}:
            recommended = str(_first_value(row, "optimization_action", "recommended_action", default="")).strip()
            if recommended:
                count += 1
    return count


def _recommendation_blocker_count_from_gate(gate: Any) -> int:
    """Count recommendation blockers from the gate review_issues."""
    review_issues = _list_value(_first_value(gate, "review_issues", default=[]))
    return sum(
        1 for ri in review_issues
        if isinstance(ri, dict) and "recommendation" in str(ri.get("category", "")).lower()
    )


def _soft_deleted_ids_text(chain: Any, metadata: Mapping[str, Any]) -> str:
    """Return a compact list of soft-deleted row IDs from metadata and chain."""
    explicit = _list_value(metadata.get("soft_deleted_items"))
    ids = [str(item) for item in explicit if str(item).strip()]
    return "；".join(ids) if ids else "无"


def _coverage_ratio(coverage: Mapping[str, Any]) -> str:
    ratio = coverage.get("coverage_ratio", 0)
    try:
        return f"{float(ratio):.0%}"
    except (TypeError, ValueError):
        return "0%"
