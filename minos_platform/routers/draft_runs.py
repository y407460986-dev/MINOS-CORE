"""POST /api/projects/{project_id}/draft-runs."""

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
from minos_platform.models import RunSummary

VALID_STATES = {"input_registered"}

router = APIRouter()


def _status_to_project_status(status: str) -> str:
    if status == "draft_ready":
        return "draft_ready"
    return "blocked"


@router.post("/projects/{project_id}/draft-runs", response_model=RunSummary, status_code=201)
async def trigger_draft_run(
    project_id: str,
    session: AsyncSession = Depends(db.get_session),
) -> RunSummary:
    """Trigger generate_draft for the project's input package."""
    result = await session.execute(select(db.Project).where(db.Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("project", project_id)
    if project.status not in VALID_STATES:
        raise InvalidStateError(project.status, "/".join(VALID_STATES))

    pkg_result = await session.execute(
        select(db.InputPackage)
        .where(db.InputPackage.project_id == project_id)
        .order_by(db.InputPackage.created_at.desc())
        .limit(1)
    )
    pkg = pkg_result.scalar_one_or_none()
    if pkg is None:
        raise NotFoundError("input_package", f"project={project_id}")

    artifacts_dir = config.get_artifacts_dir()
    project_artifacts = artifacts_dir / project_id
    run_id = str(uuid.uuid4())
    result_json_path = str(project_artifacts / f"draft_result_{run_id}.json")
    manifest_json_path = str(project_artifacts / f"draft_manifest_{run_id}.json")
    project_artifacts.mkdir(parents=True, exist_ok=True)

    run = db.Run(
        id=run_id,
        project_id=project_id,
        run_type="draft",
        status="created",
        result_json_path=result_json_path,
        manifest_json_path=manifest_json_path,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    session.add(run)

    try:
        def _generate() -> dict:
            from minos_core import generate_draft

            return generate_draft(
                evidence=pkg.package_path,
                output_path=result_json_path,
                manifest_output=manifest_json_path,
            )

        draft_result = await asyncio.to_thread(_generate)

        draft_json = json.loads(Path(result_json_path).read_text(encoding="utf-8"))
        artifact = db.Artifact(
            id=str(uuid.uuid4()),
            run_id=run_id,
            artifact_type="draft_result",
            file_path=result_json_path,
            sha256=draft_json.get("quality_gate", {}).get("run_id", "unknown"),
            created_at=datetime.now(timezone.utc).replace(microsecond=0),
        )
        session.add(artifact)

        project.status = _status_to_project_status(draft_result.get("status", "blocked"))
        if draft_result.get("status") != "draft_ready":
            run.status = "blocked"
            run.error_message = f"generate_draft returned status={draft_result.get('status')!r}"
        else:
            run.status = "draft_ready"

    except Exception as exc:  # noqa: BLE001
        run.status = "blocked"
        run.error_message = str(exc)
        project.status = "blocked"
        api_err = map_core_error(exc)
        raise HTTPException(status_code=api_err.status_code, detail=api_err.message) from exc

    await session.commit()
    await session.refresh(run)
    return RunSummary.model_validate(run)
