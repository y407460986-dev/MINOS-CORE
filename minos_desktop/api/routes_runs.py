"""Run routes for restore and edit operations."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request

from . import jobs
from .dependencies import RunServiceDep
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
def recent_runs(service: RunServiceDep, limit: int = 10) -> list[dict[str, Any]]:
    records = service.list_recent_runs(limit)
    return [run_to_dict(record) for record in records]


@router.get("/runs/{run_id}")
def get_run(run_id: int, service: RunServiceDep) -> dict[str, Any]:
    try:
        return run_to_dict(service.get_run(run_id))
    except KeyError as exc:
        raise failure_from_exception(exc) from exc


@router.get("/runs/{run_id}/drawing-analysis")
def drawing_analysis(run_id: int, service: RunServiceDep) -> dict[str, Any]:
    try:
        record = service.get_run(run_id)
    except KeyError as exc:
        raise failure_from_exception(exc) from exc
    analysis = record.current_result.get("drawing_analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}
    return {"run_id": run_id, **analysis}


@router.post("/runs/{run_id}/restore")
def restore_run(run_id: int, service: RunServiceDep) -> dict[str, Any]:
    try:
        return run_to_dict(service.restore_run(run_id))
    except KeyError as exc:
        raise failure_from_exception(exc) from exc


@router.patch("/runs/{run_id}/edit-patch")
def edit_patch(run_id: int, payload: EditPatchRequest, service: RunServiceDep) -> dict[str, Any]:
    try:
        return run_to_dict(service.apply_edit_patch_to_run(run_id, payload.patch))
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.patch("/runs/{run_id}/drawing-confirmations")
def drawing_confirmations(
    run_id: int,
    payload: DrawingConfirmationsRequest,
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.resolve_closure_tasks_by_type(
                service,
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
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        return jobs.part_family_context(service, run_id)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.patch("/runs/{run_id}/part-family")
def update_part_family(
    run_id: int,
    payload: PartFamilyRequest,
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        family_key = payload.family_key or payload.part_family
        return jobs.update_part_family_context(
            service,
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
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        return run_to_dict(
            jobs.resolve_closure_tasks_by_type(
                service,
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
def chain_state(run_id: int, service: RunServiceDep) -> dict[str, Any]:
    try:
        return service.get_chain_state(run_id)
    except KeyError as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/chain/pfd-confirm")
async def chain_confirm_pfd(
    run_id: int,
    payload: ChainConfirmRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        from .sse import create_channel, get_channel, remove_channel
        record = service.confirm_pfd_stage(run_id, payload.confirmed_by, payload.edit_patch)
        channel = get_channel(run_id, "pfmea")
        if channel is None:
            channel = create_channel(run_id, "pfmea")
        channel.bind_loop(asyncio.get_running_loop())
        background_tasks.add_task(
            jobs.generate_pfmea_for_confirmed_pfd,
            request.app.state.db_path,
            run_id,
        )
        return run_to_dict(record)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        with contextlib.suppress(Exception):
            remove_channel(run_id, "pfmea")
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/chain/pfmea-regenerate")
async def chain_regenerate_pfmea(
    run_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        from .sse import create_channel, get_channel
        run = service.get_run(run_id)
        channel = get_channel(run_id, "pfmea")
        if channel is None:
            channel = create_channel(run_id, "pfmea")
        channel.bind_loop(asyncio.get_running_loop())
        background_tasks.add_task(
            jobs.regenerate_pfmea_stage, request.app.state.db_path, run_id
        )
        return run_to_dict(run)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/chain/pfmea-confirm")
async def chain_confirm_pfmea(
    run_id: int,
    payload: ChainConfirmRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        from .sse import create_channel, get_channel, remove_channel
        record = service.confirm_pfmea_stage(run_id, payload.confirmed_by, payload.edit_patch)
        channel = get_channel(run_id, "cp")
        if channel is None:
            channel = create_channel(run_id, "cp")
        channel.bind_loop(asyncio.get_running_loop())
        background_tasks.add_task(
            jobs.generate_cp_for_confirmed_pfmea,
            request.app.state.db_path,
            run_id,
        )
        return run_to_dict(record)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        with contextlib.suppress(Exception):
            remove_channel(run_id, "cp")
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/chain/cp-regenerate")
async def chain_regenerate_cp(
    run_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    service: RunServiceDep,
) -> dict[str, Any]:
    try:
        from .sse import create_channel, get_channel
        run = service.get_run(run_id)
        channel = get_channel(run_id, "cp")
        if channel is None:
            channel = create_channel(run_id, "cp")
        channel.bind_loop(asyncio.get_running_loop())
        background_tasks.add_task(
            jobs.regenerate_cp_stage, request.app.state.db_path, run_id
        )
        return run_to_dict(run)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/chain/cp-confirm")
def chain_confirm_cp(
    run_id: int, payload: ChainConfirmRequest, service: RunServiceDep
) -> dict[str, Any]:
    try:
        return run_to_dict(service.confirm_cp_stage(run_id, payload.confirmed_by, payload.edit_patch))
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/undo")
def undo_run(run_id: int, service: RunServiceDep) -> dict[str, Any]:
    try:
        record = service.undo_run(run_id)
        if record is None:
            raise ValueError("没有可以撤销的操作。")
        return run_to_dict(record)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/redo")
def redo_run(run_id: int, service: RunServiceDep) -> dict[str, Any]:
    try:
        record = service.redo_run(run_id)
        if record is None:
            raise ValueError("没有可以重做的操作。")
        return run_to_dict(record)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc
