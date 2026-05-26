"""POST /api/projects/{project_id}/review-patches."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from minos_platform import config, db, utils
from minos_platform.errors import APIError, InvalidStateError, NotFoundError, map_core_error
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

    # Copy file to platform artifact area
    dest_dir = config.get_artifacts_dir() / project_id / "inputs"
    try:
        copied_path = utils.safe_copy_input_file_or_dir(req.patch_path, dest_dir)
    except FileNotFoundError:
        raise APIError(message="Patch file not found", code="REVIEW_PATCH_NOT_FOUND")

    # Reject patches that have template_status field
    parsed = utils.parse_review_patch(copied_path)
    if not isinstance(parsed, dict):
        raise APIError(
            message="Patch JSON must be a valid JSON object",
            code="INVALID_PATCH",
        )
    if "template_status" in parsed:
        raise APIError(message="Patch must not contain template_status field", code="INVALID_PATCH")

    # Calculate actual SHA256 of copied file
    from minos_core import sha256_json
    actual_hash = sha256_json(parsed)

    # Compare against client-provided hash
    if actual_hash != req.sha256:
        raise APIError(message="SHA256 mismatch", code="SHA256_MISMATCH", status_code=422)

    if run is None:
        raise NotFoundError("run", f"project={project_id},type=draft")
    draft_path = run.result_json_path
    if not draft_path or not Path(draft_path).exists():
        raise NotFoundError("draft_result", draft_path or "none")
    _validate_review_patch_semantics(draft_path, parsed)

    patch = db.ReviewPatch(
        id=str(uuid.uuid4()),
        run_id=run.id if run else None,
        project_id=project_id,
        patch_path=str(copied_path),
        sha256=actual_hash,
        submitted_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    session.add(patch)
    project.status = "review_patch_submitted"
    await session.commit()
    return {"id": patch.id, "project_id": project_id, "patch_path": patch.patch_path}


def _validate_review_patch_semantics(draft_path: str, patch: dict) -> None:
    try:
        from minos_core import apply_review as core_apply_review

        core_apply_review(draft_result_or_chain=draft_path, review_patch=patch)
    except (OSError, ValueError, TypeError, RuntimeError, KeyError, AttributeError) as exc:
        api_err = map_core_error(exc)
        raise APIError(
            message=api_err.message,
            code=api_err.code,
            status_code=api_err.status_code,
        ) from exc
