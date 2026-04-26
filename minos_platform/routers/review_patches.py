"""POST /api/projects/{project_id}/review-patches."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from minos_platform import db
from minos_platform.errors import InvalidStateError, NotFoundError
from minos_platform.models import SubmitReviewPatchRequest

VALID_STATES = {"review_template_ready"}

router = APIRouter()


@router.post(
    "/projects/{project_id}/review-patches",
    status_code=201,
)
async def submit_review_patch(
    project_id: str,
    req: SubmitReviewPatchRequest,
    session: AsyncSession = Depends(db.get_session),
) -> dict:
    """Record a submitted human-filled review patch against a project."""
    result = await session.execute(select(db.Project).where(db.Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("project", project_id)
    if project.status not in VALID_STATES:
        raise InvalidStateError(project.status, "/".join(VALID_STATES))

    run_result = await session.execute(
        select(db.Run)
        .where(db.Run.project_id == project_id, db.Run.run_type == "draft")
        .order_by(db.Run.created_at.desc())
        .limit(1)
    )
    run = run_result.scalar_one_or_none()

    patch = db.ReviewPatch(
        id=str(uuid.uuid4()),
        run_id=run.id if run else None,
        project_id=project_id,
        patch_path=req.patch_path,
        sha256=req.sha256,
        submitted_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    session.add(patch)
    project.status = "review_patch_submitted"
    await session.commit()
    return {"id": patch.id, "project_id": project_id, "patch_path": patch.patch_path}
