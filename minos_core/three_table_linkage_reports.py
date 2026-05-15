"""Report projections for three-table linkage analysis."""

from __future__ import annotations

from typing import Any

from minos_core._text_utils import text


def build_sync_snapshot(linkage_map: dict[str, Any]) -> dict[str, Any]:
    """Build a sync snapshot from the linkage map gaps."""

    summary = linkage_map.get("summary", {})
    gaps = linkage_map.get("gaps", [])
    return {
        "process_step_count": summary.get("process_step_count", 0),
        "pfmea_row_count": summary.get("pfmea_row_count", 0),
        "control_plan_row_count": summary.get("control_plan_row_count", 0),
        "pfd_steps_without_pfmea": [
            gap["source"] for gap in gaps if gap.get("category_key") == "pfd_pfmea_coverage"
        ],
        "pfmea_without_pfd": [
            gap["source"] for gap in gaps if gap.get("category_key") in ("orphan_pfmea",)
        ],
        "pfmea_without_cp": [
            gap["source"] for gap in gaps if gap.get("category_key") == "pfmea_cp_coverage"
        ],
        "cp_without_pfmea": [
            gap["source"] for gap in gaps if gap.get("category_key") in ("orphan_cp", "orphan_cp_step")
        ],
        "special_characteristics_missing_in_pfmea": [
            gap["source"] for gap in gaps if gap.get("category_key") == "special_char_step"
        ],
        "special_characteristics_missing_in_cp": [
            gap["source"] for gap in gaps if gap.get("category_key") == "special_char_cp"
        ],
        "cp_execution_gaps": [
            gap["source"]
            for gap in gaps
            if gap.get("category_key") in (
                "cp_missing_measurement",
                "cp_missing_frequency",
                "cp_missing_reaction_plan",
            )
        ],
    }


def build_sync_issues(linkage_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert gaps into a UI-friendly sync issue list."""

    gaps = linkage_map.get("gaps", [])
    return [
        {
            "issue_id": gap["gap_id"],
            "category": "三表同步",
            "category_key": gap.get("category_key", ""),
            "severity": gap["severity"],
            "source": gap["source"],
            "target": gap.get("target", ""),
            "message": gap["message"],
            "recommended_action": gap.get("recommended_action", ""),
            "status": "待处理",
        }
        for gap in gaps
    ]


def build_sync_suggestions(linkage_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate actionable sync suggestions for blocker gaps."""

    suggestions: list[dict[str, Any]] = []
    gaps = linkage_map.get("gaps", [])
    pfmea_rows = {
        str(row.get("pfmea_id", "")).strip(): row
        for row in linkage_map.get("pfmea_rows", [])
        if isinstance(row, dict) and str(row.get("pfmea_id", "")).strip()
    }
    for gap in gaps:
        if gap.get("severity") != "blocker":
            continue
        category_key = gap.get("category_key", "")
        if category_key == "pfmea_cp_coverage":
            pfmea_id = gap["source"].replace("pfmea:", "")
            pfmea_row = pfmea_rows.get(pfmea_id, {})
            process_parameter = text(
                pfmea_row.get("cause_process_parameter"),
                pfmea_row.get("process_parameter"),
                pfmea_row.get("process_characteristic"),
                pfmea_row.get("process_characteristics"),
                pfmea_row.get("function_work_element"),
                "按 PFMEA 原因定义过程参数",
            )
            prevention_control = text(
                pfmea_row.get("prevention_control"),
                "按 PFMEA 失效原因定义过程控制",
            )
            suggestions.append(
                {
                    "suggestion_id": f"SYNC-SUGG-ADD-CP-{pfmea_id}",
                    "source_issue_id": gap["gap_id"],
                    "target_table": "control_plan",
                    "target_id": "NEW",
                    "suggested_action": "add",
                    "suggested_fields": {
                        "pfmea_id": pfmea_id,
                        "process_parameter": process_parameter,
                        "parameter_specification": text(
                            pfmea_row.get("failure_cause"),
                            "按 PFMEA 失效原因确认参数规格",
                        ),
                        "process_control_method": prevention_control,
                        "setup_verification": "首件/换型后确认过程参数和工装状态",
                        "poka_yoke_device": "按 PFMEA 原因设置防错或权限控制",
                        "poka_yoke_verification": "每班/换型后验证防错有效",
                        "process_record": "过程参数点检/首件确认记录",
                        "measurement_method": "按 PFMEA 风险定义测量方法",
                        "sample_frequency": "首件和巡检",
                        "reaction_plan": "隔离并通知质量工程师",
                    },
                    "status": "待确认",
                }
            )
    return suggestions
