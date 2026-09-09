"""Read-only table routes for current run data."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .dependencies import RunServiceDep
from .schemas import table_rows

router = APIRouter()


@router.get("/runs/{run_id}/tables/{table_name}")
def get_table(run_id: int, table_name: str, service: RunServiceDep) -> dict[str, Any]:
    record = service.get_run(run_id)
    return {
        "run_id": run_id,
        "table": table_name,
        "rows": table_rows(record.current_result, table_name),
    }
