"""POST /api/projects/{project_id}/review-template."""

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
from minos_platform.errors import InvalidStateError, NotFoundError, map_core_error
from minos_platform.models import ReviewTemplateResponse

VALID_STATES = {"draft_ready"}

router = APIRouter()


@router.post(
    "/projects/{project_id}/review-template",
    response_model=ReviewTemplateResponse,
    status_code=201,
)
async def generate_review_template(
    project_id: str,
    session: AsyncSession = Depends(db.get_session),
) -> ReviewTemplateResponse:
    """Generate a human-fillable review template from the latest draft run."""
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

    draft_path = run.result_json_path
    if not draft_path or not Path(draft_path).exists():
        raise NotFoundError("draft_result", draft_path or "none")

    artifacts_dir = config.get_artifacts_dir()
    project_artifacts = artifacts_dir / project_id
    run_id = str(uuid.uuid4())
    template_path = str(project_artifacts / f"review_template_{run_id}.json")
    project_artifacts.mkdir(parents=True, exist_ok=True)

    try:

        def _build() -> dict:
            from minos_core import build_review_patch_template
            from minos_core.adapters.fixture_json import read_json_object
            return build_review_patch_template(read_json_object(Path(draft_path)))

        template = await asyncio.to_thread(_build)

        Path(template_path).write_text(
            json.dumps(template, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        artifact = db.Artifact(
            id=str(uuid.uuid4()),
            run_id=run.id,
            artifact_type="review_template",
            file_path=template_path,
            sha256="pending",
            created_at=datetime.now(timezone.utc).replace(microsecond=0),
        )
        session.add(artifact)

        project.status = "review_template_ready"
        await session.commit()

    except Exception as exc:  # noqa: BLE001
        api_err = map_core_error(exc)
        raise HTTPException(status_code=api_err.status_code, detail=api_err.message) from exc

    return ReviewTemplateResponse(template_path=template_path, run_id=run.id)
