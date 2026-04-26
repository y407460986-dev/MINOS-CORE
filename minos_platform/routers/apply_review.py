"""POST /api/projects/{project_id}/apply-review."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from minos_platform import config, db
from minos_platform.utils import calculate_file_sha256
from minos_platform.errors import InvalidStateError, NotFoundError, map_core_error
from minos_platform.models import ApplyReviewResponse

VALID_STATES = {"review_patch_submitted"}

router = APIRouter()


@router.post(
    "/projects/{project_id}/apply-review",
    response_model=ApplyReviewResponse,
    status_code=201,
)
async def apply_review(
    project_id: str,
    session: AsyncSession = Depends(db.get_session),
) -> ApplyReviewResponse:
    """Apply the latest review patch against the latest draft run."""
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
    if run is None:
        raise NotFoundError("run", f"project={project_id},type=draft")

    patch_result = await session.execute(
        select(db.ReviewPatch)
        .where(db.ReviewPatch.project_id == project_id)
        .order_by(db.ReviewPatch.submitted_at.desc())
        .limit(1)
    )
    patch = patch_result.scalar_one_or_none()
    if patch is None:
        raise NotFoundError("review_patch", f"project={project_id}")

    draft_path = run.result_json_path
    if not draft_path or not Path(draft_path).exists():
        raise NotFoundError("draft_result", draft_path or "none")

    artifacts_dir = config.get_artifacts_dir()
    project_artifacts = artifacts_dir / project_id
    apply_run_id = str(uuid.uuid4())
    review_result_path = str(project_artifacts / f"review_result_{apply_run_id}.json")
    manifest_path = str(project_artifacts / f"review_manifest_{apply_run_id}.json")
    project_artifacts.mkdir(parents=True, exist_ok=True)

    apply_run = db.Run(
        id=apply_run_id,
        project_id=project_id,
        run_type="review",
        status="created",
        result_json_path=review_result_path,
        manifest_json_path=manifest_path,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    session.add(apply_run)

    try:

        def _apply() -> dict:
            from minos_core import apply_review as core_apply_review
            return core_apply_review(
                draft_result_or_chain=draft_path,
                review_patch=patch.patch_path,
                output_path=review_result_path,
                manifest_output=manifest_path,
            )

        review_result = await asyncio.to_thread(_apply)

        result_sha256 = calculate_file_sha256(Path(review_result_path))
        artifact = db.Artifact(
            id=str(uuid.uuid4()),
            run_id=apply_run_id,
            artifact_type="review_result",
            file_path=review_result_path,
            sha256=result_sha256,
            created_at=datetime.now(timezone.utc).replace(microsecond=0),
        )
        session.add(artifact)

        if review_result.get("final_export_allowed"):
            project.status = "review_applied"
            apply_run.status = "review_applied"
        else:
            project.status = "blocked"
            apply_run.status = "blocked"
            apply_run.error_message = "Review applied but export gate did not clear"

    except Exception as exc:  # noqa: BLE001
        apply_run.status = "blocked"
        apply_run.error_message = str(exc)
        project.status = "blocked"
        api_err = map_core_error(exc)
        raise HTTPException(status_code=api_err.status_code, detail=api_err.message) from exc

    await session.commit()

    return ApplyReviewResponse(
        review_result_path=review_result_path,
        final_export_allowed=review_result.get("final_export_allowed", False),
        run_id=apply_run_id,
    )
