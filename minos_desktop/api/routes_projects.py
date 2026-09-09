"""Project routes for the local desktop API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status

from minos_core.validation import (
    validate_drawing_input_file,
    validate_output_directory,
)
from minos_desktop.app_state import DesktopProjectState

from . import jobs
from .dependencies import ProjectStoreDep
from .schemas import CreateProjectRequest, project_to_dict, run_to_dict

router = APIRouter()


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: CreateProjectRequest, projects: ProjectStoreDep) -> dict[str, Any]:
    drawing_path = str(validate_drawing_input_file(payload.drawing_path))
    component_drawings = [
        str(validate_drawing_input_file(path)) for path in payload.component_drawings
    ]
    output_dir = (
        str(validate_output_directory(payload.output_dir))
        if payload.output_dir
        else payload.output_dir
    )
    context = dict(payload.context)
    analysis_mode = str(context.get("analysis_mode") or payload.analysis_mode or "hybrid").strip()
    ocr_engine = str(context.get("ocr_engine") or payload.ocr_engine or "mineru").strip()
    context["analysis_mode"] = analysis_mode or "hybrid"
    context["ocr_engine"] = ocr_engine or "mineru"
    record = projects.create_project(
        DesktopProjectState(
            project_name=payload.project_name,
            drawing_path=drawing_path,
            component_drawings=component_drawings,
            output_dir=output_dir,
            context=context,
        )
    )
    return project_to_dict(record)


@router.get("/projects/recent")
def recent_projects(projects: ProjectStoreDep, limit: int = 10) -> list[dict[str, Any]]:
    return [project_to_dict(record) for record in projects.list_recent_projects(limit)]


@router.get("/projects/{project_id}")
def get_project(project_id: int, projects: ProjectStoreDep) -> dict[str, Any]:
    record = projects.get_project(project_id)
    return project_to_dict(record)


@router.post("/projects/{project_id}/runs", status_code=status.HTTP_201_CREATED)
def create_project_run(
    project_id: int, request: Request
) -> dict[str, Any]:
    record = jobs.start_chain_run(request.app.state.db_path, project_id)
    return run_to_dict(record)


@router.post(
    "/projects/{project_id}/chain-runs", status_code=status.HTTP_201_CREATED
)
def create_chain_run(
    project_id: int, request: Request
) -> dict[str, Any]:
    """启动链式流程（仅生成 PFD，后续阶段需逐步骤确认）。"""
    record = jobs.start_chain_run(request.app.state.db_path, project_id)
    return run_to_dict(record)
