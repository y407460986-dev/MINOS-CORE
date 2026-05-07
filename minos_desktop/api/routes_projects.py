"""Project routes for the local desktop API."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import APIRouter, Request, status

from minos_desktop.app_state import DesktopProjectRecord, DesktopProjectState
from minos_desktop.services import DesktopProjectStore

from . import jobs
from .schemas import CreateProjectRequest, project_to_dict, run_to_dict

router = APIRouter()


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: CreateProjectRequest, request: Request) -> dict[str, Any]:
    context = dict(payload.context)
    analysis_mode = str(context.get("analysis_mode") or payload.analysis_mode or "hybrid").strip()
    ocr_engine = str(context.get("ocr_engine") or payload.ocr_engine or "auto").strip()
    context["analysis_mode"] = analysis_mode or "hybrid"
    context["ocr_engine"] = ocr_engine or "auto"
    record = DesktopProjectStore(request.app.state.db_path).create_project(
        DesktopProjectState(
            project_name=payload.project_name,
            drawing_path=payload.drawing_path,
            output_dir=payload.output_dir,
            context=context,
        )
    )
    return project_to_dict(record)


@router.get("/projects/recent")
def recent_projects(request: Request, limit: int = 10) -> list[dict[str, Any]]:
    db_path = request.app.state.db_path
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT * FROM projects
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    return [project_to_dict(_project_from_row(row)) for row in rows]


@router.get("/projects/{project_id}")
def get_project(project_id: int, request: Request) -> dict[str, Any]:
    record = DesktopProjectStore(request.app.state.db_path).get_project(project_id)
    return project_to_dict(record)


@router.post("/projects/{project_id}/runs", status_code=status.HTTP_201_CREATED)
def create_project_run(project_id: int, request: Request) -> dict[str, Any]:
    record = jobs.start_chain_run(request.app.state.db_path, project_id)
    return run_to_dict(record)


@router.post(
    "/projects/{project_id}/chain-runs", status_code=status.HTTP_201_CREATED
)
def create_chain_run(project_id: int, request: Request) -> dict[str, Any]:
    """启动链式流程（仅生成 PFD，后续阶段需逐步骤确认）。"""
    record = jobs.start_chain_run(request.app.state.db_path, project_id)
    return run_to_dict(record)


def _project_from_row(row: sqlite3.Row) -> DesktopProjectRecord:
    return DesktopProjectRecord(
        id=int(row["id"]),
        project_name=str(row["project_name"]),
        drawing_path=str(row["drawing_path"]),
        output_dir=str(row["output_dir"]),
        context=_json_object(str(row["context_json"])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _json_object(value: str) -> dict[str, Any]:
    data = json.loads(value or "{}")
    return data if isinstance(data, dict) else {}
