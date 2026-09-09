"""Run-facing service wrappers kept separate for future background queues."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from minos_core.closure_tasks import apply_closure_action, build_closure_tasks
from minos_desktop.services import DesktopProjectStore, DesktopRunService
from minos_desktop.table_editor import build_edit_patch

RunServiceSource = DesktopRunService | str | Path


def _run_service(source: RunServiceSource) -> DesktopRunService:
    return source if isinstance(source, DesktopRunService) else DesktopRunService(source)


def start_chain_run(db_path: str | Path, project_id: int) -> Any:
    """Start a chain run through the replaceable background-job seam."""
    project = DesktopProjectStore(db_path).get_project(project_id)
    return DesktopRunService(db_path).start_chain_run(project)


def accept_recommendation(
    source: RunServiceSource, run_id: int, recommendation_id: str
) -> Any:
    return _run_service(source).apply_recommendation_to_run(run_id, recommendation_id)


def ignore_recommendation(
    source: RunServiceSource,
    run_id: int,
    recommendation_id: str,
    reason: str,
) -> Any:
    return _run_service(source).ignore_recommendation_in_run(
        run_id,
        recommendation_id,
        reason,
    )


def resolve_action(
    source: RunServiceSource,
    run_id: int,
    action_id: str,
    changes: dict[str, Any],
    reason: str,
) -> Any:
    return _run_service(source).resolve_action_in_run(run_id, action_id, changes, reason)


def resolve_change_impact(
    source: RunServiceSource,
    run_id: int,
    item_id: str,
    status: str,
    reason: str,
) -> Any:
    return _run_service(source).resolve_change_impact(
        run_id,
        item_id,
        status=status,
        reason=reason,
    )


def batch_confirm_automation_review(source: RunServiceSource, run_id: int) -> Any:
    return _run_service(source).batch_confirm_automation_review(run_id)


def accept_automation_fix(
    source: RunServiceSource, run_id: int, row: dict[str, Any]
) -> Any:
    return _run_service(source).accept_automation_fix_suggestion(run_id, row)


def closure_tasks(source: RunServiceSource, run_id: int) -> list[dict[str, Any]]:
    record = _run_service(source).get_run(run_id)
    return build_closure_tasks(record.current_result)


def part_family_context(source: RunServiceSource, run_id: int) -> dict[str, Any]:
    record = _run_service(source).get_run(run_id)
    context = _part_family_context(record.current_result)
    family_key = str(context.get("family_key") or context.get("key") or "").strip()
    return {
        "run_id": run_id,
        "part_family": family_key or "未设置",
        "confidence": context.get("confidence"),
        "source": "current_result",
        "candidates": _part_family_candidates(record.current_result, context),
        "context": context,
        "raw": context,
    }


def update_part_family_context(
    source: RunServiceSource,
    run_id: int,
    *,
    family_key: str,
    family_name: str = "",
    confirmed: bool = True,
    reason: str = "",
) -> dict[str, Any]:
    service = _run_service(source)
    record = service.get_run(run_id)
    key = str(family_key or "").strip()
    if not key:
        raise ValueError("part_family is required")
    result = copy.deepcopy(record.current_result)
    context = _part_family_context(result)
    context["family_key"] = key
    context["family_name"] = str(family_name or context.get("family_name") or key).strip()
    context["needs_confirmation"] = not confirmed
    context["confirmed_by_user"] = bool(confirmed)
    context["confirmation_reason"] = reason
    context.setdefault("source", "desktop_api")
    _write_part_family_context(result, context)
    service.save_with_undo(run_id, result)
    return {
        "run_id": run_id,
        "part_family": key,
        "confidence": context.get("confidence"),
        "source": "desktop_api",
        "candidates": _part_family_candidates(result, context),
        "context": context,
        "raw": context,
    }


def resolve_closure_task(
    source: RunServiceSource,
    run_id: int,
    task_id: str,
    action: dict[str, Any],
) -> Any:
    service = _run_service(source)
    record = service.get_run(run_id)
    patch = apply_closure_action(record.current_result, task_id, action)
    return service.apply_edit_patch_to_run(run_id, patch)


def resolve_closure_tasks_by_type(
    source: RunServiceSource,
    run_id: int,
    task_type: str,
    action: dict[str, Any],
    *,
    task_ids: list[str] | None = None,
    target_row_ids: list[str] | None = None,
) -> Any:
    service = _run_service(source)
    record = service.get_run(run_id)
    tasks = [
        task
        for task in build_closure_tasks(record.current_result)
        if task.get("task_type") == task_type and task.get("status") == "open"
    ]
    if task_ids:
        selected = set(task_ids)
        tasks = [task for task in tasks if task.get("task_id") in selected]
    if target_row_ids:
        selected_targets = set(target_row_ids)
        tasks = [task for task in tasks if task.get("target_row_id") in selected_targets]
    if not tasks:
        return service.refresh_run_result(run_id)

    items: list[dict[str, Any]] = []
    for task in tasks:
        patch = apply_closure_action(record.current_result, task["task_id"], action)
        items.extend(item for item in patch.get("items", []) if isinstance(item, dict))
    if not items:
        return record
    return service.apply_edit_patch_to_run(run_id, build_edit_patch(items))


def apply_linkage_sync(
    source: RunServiceSource,
    run_id: int,
    edit_patch: dict[str, Any],
    selected_impact_ids: list[str],
    *,
    apply_all: bool = False,
    reason: str = "",
) -> Any:
    service = _run_service(source)
    if not isinstance(edit_patch.get("items"), list) or not edit_patch.get("items"):
        if not apply_all and not selected_impact_ids:
            return service.get_run(run_id)
        edit_patch = _sync_suggestions_patch(
            service.get_run(run_id).current_result,
            selected_impact_ids,
            reason=reason,
        )
        if not edit_patch.get("items"):
            return service.get_run(run_id)
    return service.apply_live_edit_to_run(
        run_id,
        edit_patch,
        selected_impact_ids,
    )


def _part_family_context(result: dict[str, Any]) -> dict[str, Any]:
    for candidate in (
        ((result.get("process_flow") or {}).get("metadata") if isinstance(result.get("process_flow"), dict) else {}),
        result.get("metadata"),
        ((result.get("chain") or {}).get("metadata") if isinstance(result.get("chain"), dict) else {}),
        result.get("part_family"),
    ):
        if not isinstance(candidate, dict):
            continue
        context = candidate.get("family_context", candidate)
        if isinstance(context, dict) and (context.get("family_key") or context.get("key")):
            return copy.deepcopy(context)
    return {}


def _write_part_family_context(result: dict[str, Any], context: dict[str, Any]) -> None:
    metadata = result.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["family_context"] = copy.deepcopy(context)
        metadata["part_family"] = context.get("family_key", "")
    process_flow = result.setdefault("process_flow", {})
    if isinstance(process_flow, dict):
        process_metadata = process_flow.setdefault("metadata", {})
        if isinstance(process_metadata, dict):
            process_metadata["family_context"] = copy.deepcopy(context)
    chain = result.get("chain")
    if isinstance(chain, dict):
        chain_metadata = chain.setdefault("metadata", {})
        if isinstance(chain_metadata, dict):
            chain_metadata["family_context"] = copy.deepcopy(context)
            chain_metadata["part_family"] = context.get("family_key", "")
    result["part_family"] = {
        "part_family": context.get("family_key", ""),
        "context": copy.deepcopy(context),
    }


def _part_family_candidates(result: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = context.get("alternative_families", [])
    rows = [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []
    if context.get("family_key"):
        rows.insert(
            0,
            {
                "value": context.get("family_key", ""),
                "label": context.get("family_name", context.get("family_key", "")),
                "confidence": context.get("confidence"),
                "reason": "当前零件族",
            },
        )
    return rows


def _sync_suggestions_patch(
    result: dict[str, Any],
    selected_ids: list[str],
    *,
    reason: str = "",
) -> dict[str, Any]:
    selected = {str(item).strip() for item in selected_ids if str(item).strip()}
    suggestions = _sync_suggestions(result)
    items: list[dict[str, Any]] = []
    for suggestion in suggestions:
        suggestion_id = str(suggestion.get("suggestion_id", "")).strip()
        if selected and suggestion_id not in selected:
            continue
        table = str(suggestion.get("target_table", "")).strip()
        if table not in {"pfmea", "control_plan"}:
            continue
        if str(suggestion.get("suggested_action", "add")).strip() != "add":
            continue
        row = _row_from_sync_suggestion(result, suggestion, table)
        if not row:
            continue
        items.append(
            {
                "action": "add",
                "table": table,
                "target_id": _row_id_for_table(row, table),
                "row": row,
                "reason": reason or "应用三表联动同步建议",
                "metadata": {
                    "source": "live_linkage",
                    "linkage_suggestion_id": suggestion_id,
                },
            }
        )
    return build_edit_patch(items)


def _sync_suggestions(result: dict[str, Any]) -> list[dict[str, Any]]:
    report = result.get("linkage_report")
    if isinstance(report, dict) and isinstance(report.get("sync_suggestions"), list):
        return [item for item in report["sync_suggestions"] if isinstance(item, dict)]
    try:
        from minos_core.three_table_linkage import evaluate_three_table_linkage
    except ImportError:
        return []
    report = evaluate_three_table_linkage(result)
    suggestions = report.get("sync_suggestions", [])
    return [item for item in suggestions if isinstance(item, dict)] if isinstance(suggestions, list) else []


def _row_from_sync_suggestion(
    result: dict[str, Any],
    suggestion: dict[str, Any],
    table: str,
) -> dict[str, Any]:
    fields = copy.deepcopy(suggestion.get("suggested_fields", {}))
    if not isinstance(fields, dict):
        fields = {}
    if table == "pfmea":
        return {}
    pfmea_id = str(fields.get("pfmea_id") or _source_id(suggestion, "pfmea")).strip()
    if not pfmea_id:
        return {}
    pfmea_row = _find_row(result, "pfmea", pfmea_id)
    step_id = str(fields.get("process_step_id") or (pfmea_row or {}).get("process_step_id", "")).strip()
    row_id = f"CP-SYNC-{pfmea_id}"
    return {
        "control_plan_id": row_id,
        "process_step_id": step_id,
        "pfmea_id": pfmea_id,
        "product_process_characteristic": fields.get("product_process_characteristic", "按 PFMEA 风险定义控制特性"),
        "measurement_method": fields.get("measurement_method", "按 PFMEA 风险定义测量方法"),
        "sample_frequency": fields.get("sample_frequency", "首件和巡检"),
        "reaction_plan": fields.get("reaction_plan", "隔离并通知质量工程师"),
        "needs_confirmation": True,
        "ai_inferred": False,
    }


def _source_id(suggestion: dict[str, Any], prefix: str) -> str:
    source = str(suggestion.get("source", "")).strip()
    marker = f"{prefix}:"
    return source[len(marker):] if source.startswith(marker) else ""


def _find_row(result: dict[str, Any], table: str, row_id: str) -> dict[str, Any] | None:
    document_key = "control_plan" if table == "control_plan" else table
    rows_key = "steps" if table == "process_flow" else "rows"
    document = result.get(document_key)
    rows = document.get(rows_key, []) if isinstance(document, dict) else []
    id_key = {"process_flow": "process_step_id", "pfmea": "pfmea_id", "control_plan": "control_plan_id"}[table]
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and str(row.get(id_key, "")).strip() == row_id:
            return row
    return None


def _row_id_for_table(row: dict[str, Any], table: str) -> str:
    return str(row[{"pfmea": "pfmea_id", "control_plan": "control_plan_id"}[table]]).strip()


# ---------------------------------------------------------------------------
# 链式确认流程 jobs
# ---------------------------------------------------------------------------

def chain_state(source: RunServiceSource, run_id: int) -> dict[str, Any]:
    """获取链式阶段状态。"""
    return _run_service(source).get_chain_state(run_id)


def confirm_pfd_stage(
    source: RunServiceSource,
    run_id: int,
    confirmed_by: str = "",
    edit_patch: dict[str, Any] | None = None,
) -> Any:
    """确认 PFD，自动生成 PFMEA。"""
    return _run_service(source).confirm_pfd_stage(
        run_id, confirmed_by, edit_patch
    )


def generate_pfmea_for_confirmed_pfd(db_path: str | Path, run_id: int) -> Any:
    """后台为已确认 PFD 生成 PFMEA。"""
    return DesktopRunService(db_path).generate_pfmea_for_confirmed_pfd(run_id)


def regenerate_pfmea_stage(db_path: str | Path, run_id: int) -> Any:
    """重新生成 PFMEA。"""
    return DesktopRunService(db_path).regenerate_pfmea_stage(run_id)


def confirm_pfmea_stage(
    source: RunServiceSource,
    run_id: int,
    confirmed_by: str = "",
    edit_patch: dict[str, Any] | None = None,
) -> Any:
    """确认 PFMEA，自动生成 CP。"""
    return _run_service(source).confirm_pfmea_stage(
        run_id, confirmed_by, edit_patch
    )


def generate_cp_for_confirmed_pfmea(db_path: str | Path, run_id: int) -> Any:
    """后台为已确认 PFMEA 生成 CP。"""
    return DesktopRunService(db_path).generate_cp_for_confirmed_pfmea(run_id)


def regenerate_cp_stage(db_path: str | Path, run_id: int) -> Any:
    """重新生成 CP。"""
    return DesktopRunService(db_path).regenerate_cp_stage(run_id)


def confirm_cp_stage(
    source: RunServiceSource,
    run_id: int,
    confirmed_by: str = "",
    edit_patch: dict[str, Any] | None = None,
) -> Any:
    """确认 CP，完成链式流程。"""
    return _run_service(source).confirm_cp_stage(run_id, confirmed_by, edit_patch)
