"""Review closure routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from . import jobs
from .schemas import (
    AutomationFixRequest,
    ClosureTaskResolveRequest,
    IgnoreRequest,
    LinkageApplySyncRequest,
    ResolveActionRequest,
    ResolveChangeImpactRequest,
    failure_from_exception,
    run_to_dict,
)

router = APIRouter()


@router.post("/runs/{run_id}/recommendations/{recommendation_id}/accept")
def accept_recommendation(run_id: int, recommendation_id: str, request: Request) -> dict[str, Any]:
    return run_to_dict(jobs.accept_recommendation(request.app.state.db_path, run_id, recommendation_id))


@router.post("/runs/{run_id}/recommendations/{recommendation_id}/ignore")
def ignore_recommendation(
    run_id: int,
    recommendation_id: str,
    payload: IgnoreRequest,
    request: Request,
) -> dict[str, Any]:
    return run_to_dict(
        jobs.ignore_recommendation(
            request.app.state.db_path,
            run_id,
            recommendation_id,
            payload.reason,
        )
    )


@router.post("/runs/{run_id}/actions/{action_id}/resolve")
def resolve_action(
    run_id: int,
    action_id: str,
    payload: ResolveActionRequest,
    request: Request,
) -> dict[str, Any]:
    record = jobs.resolve_action(
        request.app.state.db_path,
        run_id,
        action_id,
        payload.changes,
        payload.reason,
    )
    if record is None:
        return {"run_id": run_id, "action_id": action_id, "status": "unsupported"}
    return run_to_dict(record)


@router.post("/runs/{run_id}/change-impacts/{item_id}/resolve")
def resolve_change_impact(
    run_id: int,
    item_id: str,
    payload: ResolveChangeImpactRequest,
    request: Request,
) -> dict[str, Any]:
    return run_to_dict(
        jobs.resolve_change_impact(
            request.app.state.db_path,
            run_id,
            item_id,
            payload.status,
            payload.reason,
        )
    )


@router.post("/runs/{run_id}/automation-review/batch-confirm")
def batch_confirm_automation_review(run_id: int, request: Request) -> dict[str, Any]:
    return run_to_dict(jobs.batch_confirm_automation_review(request.app.state.db_path, run_id))


@router.post("/runs/{run_id}/automation-review/accept-fix")
def accept_automation_fix(
    run_id: int,
    payload: AutomationFixRequest,
    request: Request,
) -> dict[str, Any]:
    return run_to_dict(jobs.accept_automation_fix(request.app.state.db_path, run_id, payload.row))


@router.get("/runs/{run_id}/closure-tasks")
def closure_tasks(run_id: int, request: Request) -> dict[str, Any]:
    try:
        tasks = jobs.closure_tasks(request.app.state.db_path, run_id)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc
    return {"run_id": run_id, "tasks": tasks}


@router.post("/runs/{run_id}/closure-tasks/{task_id}/resolve")
def resolve_closure_task(
    run_id: int,
    task_id: str,
    payload: ClosureTaskResolveRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.resolve_closure_task(
                request.app.state.db_path,
                run_id,
                task_id,
                payload.model_dump(),
            )
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/linkage/apply-sync")
def apply_linkage_sync(
    run_id: int,
    payload: LinkageApplySyncRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.apply_linkage_sync(
                request.app.state.db_path,
                run_id,
                payload.edit_patch,
                payload.selected_impact_ids or payload.suggestion_ids,
                apply_all=payload.apply_all,
                reason=payload.reason,
            )
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc
