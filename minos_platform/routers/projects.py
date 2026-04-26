"""POST /api/projects and GET /api/projects."""

from typing import List

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from minos_platform import db
from minos_platform.errors import NotFoundError
from minos_platform.models import (
    CreateProjectRequest,
    InputPackageSummary,
    ProjectDetail,
    ProjectSummary,
)

router = APIRouter()


@router.post("/projects", response_model=ProjectSummary, status_code=201)
async def create_project(
    req: CreateProjectRequest,
    session: AsyncSession = Depends(db.get_session),
) -> ProjectSummary:
    """Create a new PPAP project."""
    project = db.Project(
        id=str(uuid.uuid4()),
        name=req.name,
        project_code=req.project_code,
        part_number=req.part_number,
        status="created",
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return ProjectSummary.model_validate(project)


@router.get("/projects", response_model=List[ProjectSummary])
async def list_projects(
    session: AsyncSession = Depends(db.get_session),
) -> List[ProjectSummary]:
    """List all PPAP projects."""
    result = await session.execute(select(db.Project).order_by(db.Project.created_at.desc()))
    projects = result.scalars().all()
    return [ProjectSummary.model_validate(p) for p in projects]


@router.get("/projects/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(db.get_session),
) -> ProjectDetail:
    """Get a single PPAP project with its input packages and latest run."""
    result = await session.execute(select(db.Project).where(db.Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("project", project_id)
    pkgs_result = await session.execute(
        select(db.InputPackage)
        .where(db.InputPackage.project_id == project_id)
        .order_by(db.InputPackage.created_at.desc())
    )
    input_packages = pkgs_result.scalars().all()
    runs_result = await session.execute(
        select(db.Run)
        .where(db.Run.project_id == project_id)
        .order_by(db.Run.created_at.desc())
        .limit(1)
    )
    latest_run = runs_result.scalar_one_or_none()
    return ProjectDetail(
        id=project.id,
        name=project.name,
        project_code=project.project_code,
        part_number=project.part_number,
        status=project.status,
        created_at=project.created_at,
        input_packages=[InputPackageSummary.model_validate(p) for p in input_packages],
        latest_run_id=latest_run.id if latest_run else None,
    )
