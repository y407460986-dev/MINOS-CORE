"""Run routes for restore and edit operations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request

from minos_desktop.services import DesktopRunService

from . import jobs
from .schemas import (
    ChainConfirmRequest,
    DrawingConfirmationsRequest,
    EditPatchRequest,
    PartFamilyRequest,
    ProcessFlowConfirmationsRequest,
    failure_from_exception,
    run_to_dict,
)

router = APIRouter()


@router.get("/runs/recent")
def recent_runs(request: Request, limit: int = 10) -> list[dict[str, Any]]:
    records = DesktopRunService(request.app.state.db_path).list_recent_runs(limit)
    return [run_to_dict(record) for record in records]


@router.get("/runs/{run_id}")
def get_run(run_id: int, request: Request) -> dict[str, Any]:
    try:
        return run_to_dict(DesktopRunService(request.app.state.db_path).get_run(run_id))
    except KeyError as exc:
        raise failure_from_exception(exc) from exc


@router.get("/runs/{run_id}/drawing-analysis")
def drawing_analysis(run_id: int, request: Request) -> dict[str, Any]:
    try:
        record = DesktopRunService(request.app.state.db_path).get_run(run_id)
    except KeyError as exc:
        raise failure_from_exception(exc) from exc
    analysis = record.current_result.get("drawing_analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}
    return {"run_id": run_id, **analysis}


@router.post("/runs/{run_id}/restore")
def restore_run(run_id: int, request: Request) -> dict[str, Any]:
    try:
        return run_to_dict(jobs.restore_run(request.app.state.db_path, run_id))
    except KeyError as exc:
        raise failure_from_exception(exc) from exc


@router.patch("/runs/{run_id}/edit-patch")
def edit_patch(run_id: int, payload: EditPatchRequest, request: Request) -> dict[str, Any]:
    try:
        return run_to_dict(jobs.apply_edit_patch(request.app.state.db_path, run_id, payload.patch))
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.patch("/runs/{run_id}/drawing-confirmations")
def drawing_confirmations(
    run_id: int,
    payload: DrawingConfirmationsRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.resolve_closure_tasks_by_type(
                request.app.state.db_path,
                run_id,
                "drawing_review",
                payload.model_dump(),
                task_ids=payload.task_ids,
                target_row_ids=payload.targets,
            )
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.get("/runs/{run_id}/part-family")
def part_family(
    run_id: int,
    request: Request,
) -> dict[str, Any]:
    try:
        return jobs.part_family_context(request.app.state.db_path, run_id)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.patch("/runs/{run_id}/part-family")
def update_part_family(
    run_id: int,
    payload: PartFamilyRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        family_key = payload.family_key or payload.part_family
        return jobs.update_part_family_context(
            request.app.state.db_path,
            run_id,
            family_key=family_key,
            family_name=payload.family_name,
            confirmed=payload.confirmed,
            reason=payload.reason or payload.resolution_note,
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.patch("/runs/{run_id}/process-flow-confirmations")
def process_flow_confirmations(
    run_id: int,
    payload: ProcessFlowConfirmationsRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.resolve_closure_tasks_by_type(
                request.app.state.db_path,
                run_id,
                "process_flow_confirmation",
                payload.model_dump(),
                task_ids=payload.task_ids,
                target_row_ids=payload.step_ids,
            )
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


# ---------------------------------------------------------------------------
# 链式确认流程 (Chain Pipeline)
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/chain/state")
def chain_state(run_id: int, request: Request) -> dict[str, Any]:
    try:
        return jobs.chain_state(request.app.state.db_path, run_id)
    except KeyError as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/chain/pfd-confirm")
def chain_confirm_pfd(
    run_id: int,
    payload: ChainConfirmRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    try:
        record = jobs.confirm_pfd_stage(
            request.app.state.db_path,
            run_id,
            payload.confirmed_by,
            payload.edit_patch,
        )
        background_tasks.add_task(
            jobs.generate_pfmea_for_confirmed_pfd,
            request.app.state.db_path,
            run_id,
        )
        return run_to_dict(record)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/chain/pfmea-regenerate")
def chain_regenerate_pfmea(run_id: int, request: Request) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.regenerate_pfmea_stage(request.app.state.db_path, run_id)
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/chain/pfmea-confirm")
def chain_confirm_pfmea(
    run_id: int,
    payload: ChainConfirmRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    try:
        record = jobs.confirm_pfmea_stage(
            request.app.state.db_path,
            run_id,
            payload.confirmed_by,
            payload.edit_patch,
        )
        background_tasks.add_task(
            jobs.generate_cp_for_confirmed_pfmea,
            request.app.state.db_path,
            run_id,
        )
        return run_to_dict(record)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/chain/cp-regenerate")
def chain_regenerate_cp(run_id: int, request: Request) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.regenerate_cp_stage(request.app.state.db_path, run_id)
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/chain/cp-confirm")
def chain_confirm_cp(
    run_id: int, payload: ChainConfirmRequest, request: Request
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.confirm_cp_stage(
                request.app.state.db_path,
                run_id,
                payload.confirmed_by,
                payload.edit_patch,
            )
        )
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc
