"""Review closure routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from . import jobs
from .dependencies import RunServiceDep
from .schemas import (
    AutomationFixRequest,
    ClosureTaskResolveRequest,
    ClosureTasksBulkResolveRequest,
    IgnoreRequest,
    LinkageApplySyncRequest,
    ResolveActionRequest,
    ResolveChangeImpactRequest,
    failure_from_exception,
    run_to_dict,
)

router = APIRouter()


@router.post("/runs/{run_id}/recommendations/{recommendation_id}/accept")
def accept_recommendation(
    run_id: int, recommendation_id: str, service: RunServiceDep
) -> dict[str, Any]:
    try:
        return run_to_dict(jobs.accept_recommendation(service, run_id, recommendation_id))
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/recommendations/{recommendation_id}/ignore")
def ignore_recommendation(
    run_id: int,
    recommendation_id: str,
    payload: IgnoreRequest,
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.ignore_recommendation(
                service,
                run_id,
                recommendation_id,
                payload.reason,
            )
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/actions/{action_id}/resolve")
def resolve_action(
    run_id: int,
    action_id: str,
    payload: ResolveActionRequest,
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        record = jobs.resolve_action(
            service,
            run_id,
            action_id,
            payload.changes,
            payload.reason,
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc
    if record is None:
        return {"run_id": run_id, "action_id": action_id, "status": "unsupported"}
    return run_to_dict(record)


@router.post("/runs/{run_id}/change-impacts/{item_id}/resolve")
def resolve_change_impact(
    run_id: int,
    item_id: str,
    payload: ResolveChangeImpactRequest,
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.resolve_change_impact(
                service,
                run_id,
                item_id,
                payload.status,
                payload.reason,
            )
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/automation-review/batch-confirm")
def batch_confirm_automation_review(run_id: int, service: RunServiceDep) -> dict[str, Any]:
    return run_to_dict(jobs.batch_confirm_automation_review(service, run_id))


@router.post("/runs/{run_id}/automation-review/accept-fix")
def accept_automation_fix(
    run_id: int,
    payload: AutomationFixRequest,
    service: RunServiceDep,
) -> dict[str, Any]:
    return run_to_dict(jobs.accept_automation_fix(service, run_id, payload.row))


@router.get("/runs/{run_id}/closure-tasks")
def closure_tasks(run_id: int, service: RunServiceDep) -> dict[str, Any]:
    try:
        tasks = jobs.closure_tasks(service, run_id)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc
    return {"run_id": run_id, "tasks": tasks}


@router.post("/runs/{run_id}/closure-tasks/resolve-by-type")
def resolve_closure_tasks_by_type(
    run_id: int,
    payload: ClosureTasksBulkResolveRequest,
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.resolve_closure_tasks_by_type(
                service,
                run_id,
                payload.task_type,
                payload.model_dump(),
                task_ids=payload.task_ids,
                target_row_ids=payload.target_row_ids,
            )
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/closure-tasks/{task_id}/resolve")
def resolve_closure_task(
    run_id: int,
    task_id: str,
    payload: ClosureTaskResolveRequest,
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.resolve_closure_task(
                service,
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
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.apply_linkage_sync(
                service,
                run_id,
                payload.edit_patch,
                payload.selected_impact_ids or payload.suggestion_ids,
                apply_all=payload.apply_all,
                reason=payload.reason,
            )
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc
