"""Export routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from minos_core.validation import validate_output_directory

from .dependencies import RunServiceDep
from .schemas import ExportRunRequest, default_export_dir

router = APIRouter()


@router.post("/runs/{run_id}/exports", status_code=status.HTTP_201_CREATED)
def export_run(run_id: int, payload: ExportRunRequest, service: RunServiceDep) -> dict[str, Any]:
    output_dir = payload.output_dir
    if not output_dir:
        run = service.get_run(run_id)
        output_dir = default_export_dir(run.output_dir, run.id)
    output_dir = str(validate_output_directory(output_dir))
    result = service.export_run(run_id, output_dir, payload.export_mode)
    if not isinstance(result, dict):
        raise RuntimeError("export job must return a mapping")
    return result
