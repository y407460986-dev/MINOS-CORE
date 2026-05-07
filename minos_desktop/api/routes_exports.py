"""Export routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status

from minos_desktop.services import DesktopRunService

from . import jobs
from .schemas import ExportRunRequest, default_export_dir

router = APIRouter()


@router.post("/runs/{run_id}/exports", status_code=status.HTTP_201_CREATED)
def export_run(run_id: int, payload: ExportRunRequest, request: Request) -> dict[str, Any]:
    output_dir = payload.output_dir
    if not output_dir:
        run = DesktopRunService(request.app.state.db_path).get_run(run_id)
        output_dir = default_export_dir(run.output_dir, run.id)
    return jobs.export_run(
        request.app.state.db_path,
        run_id,
        output_dir,
        payload.export_mode,
    )
