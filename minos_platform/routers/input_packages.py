"""POST /api/projects/{project_id}/input-packages."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from minos_platform import db
from minos_platform.errors import InvalidStateError, NotFoundError
from minos_platform.models import RegisterInputPackageRequest, InputPackageSummary

VALID_STATES = {"created"}

router = APIRouter()


@router.post(
    "/projects/{project_id}/input-packages",
    response_model=InputPackageSummary,
    status_code=201,
)
async def register_input_package(
    project_id: str,
    req: RegisterInputPackageRequest,
    session: AsyncSession = Depends(db.get_session),
) -> InputPackageSummary:
    """Register an input_package path against a project."""
    result = await session.execute(select(db.Project).where(db.Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("project", project_id)
    if project.status not in VALID_STATES:
        raise InvalidStateError(project.status, "/".join(VALID_STATES))

    pkg = db.InputPackage(
        id=str(uuid.uuid4()),
        project_id=project_id,
        package_path=req.input_package_path,
        sha256=req.sha256,
        redacted=req.redacted,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    session.add(pkg)
    project.status = "input_registered"
    await session.commit()
    await session.refresh(pkg)
    return InputPackageSummary.model_validate(pkg)
