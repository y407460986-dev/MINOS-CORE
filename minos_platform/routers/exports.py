"""POST /api/projects/{project_id}/exports."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from minos_platform import config, db
from minos_platform.errors import InvalidStateError, NotFoundError, map_core_error
from minos_platform.models import ExportResponse, TriggerExportRequest

VALID_STATES_FINAL = {"review_applied"}
VALID_STATES_DRAFT = {"draft_ready", "review_applied", "review_template_ready", "review_patch_submitted"}

router = APIRouter()


@router.post("/projects/{project_id}/exports", response_model=ExportResponse, status_code=201)
async def trigger_export(
    project_id: str,
    req: TriggerExportRequest,
    session: AsyncSession = Depends(db.get_session),
) -> ExportResponse:
    """Export a final or draft workbook for the project."""
    result = await session.execute(select(db.Project).where(db.Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("project", project_id)

    export_mode = req.export_mode
    if export_mode == "final":
        valid = VALID_STATES_FINAL
    else:
        valid = VALID_STATES_DRAFT

    if project.status not in valid:
        raise InvalidStateError(project.status, "/".join(valid))

    run_result = await session.execute(
        select(db.Run)
        .where(db.Run.project_id == project_id)
        .order_by(db.Run.created_at.desc())
        .limit(1)
    )
    latest_run = run_result.scalar_one_or_none()
    if latest_run is None:
        raise NotFoundError("run", f"project={project_id}")

    if export_mode == "final":
        chain_input = latest_run.result_json_path
        if not chain_input or not Path(chain_input).exists():
            raise NotFoundError("chain_input", chain_input or "none")
    else:
        chain_input = latest_run.result_json_path
        if not chain_input or not Path(chain_input).exists():
            raise NotFoundError("chain_input", chain_input or "none")

    artifacts_dir = config.get_artifacts_dir()
    project_artifacts = artifacts_dir / project_id
    export_run_id = str(uuid.uuid4())
    ext = "xlsx"
    export_path = str(project_artifacts / f"export_{export_mode}_{export_run_id}.{ext}")
    manifest_path = str(project_artifacts / f"export_manifest_{export_run_id}.json")
    project_artifacts.mkdir(parents=True, exist_ok=True)

    export_run = db.Run(
        id=export_run_id,
        project_id=project_id,
        run_type="export",
        status="created",
        result_json_path=export_path,
        manifest_json_path=manifest_path,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    session.add(export_run)

    try:

        def _export() -> Path:
            from minos_core import export_draft_fixture, export_fixture
            if export_mode == "final":
                return export_fixture(
                    fixture=chain_input,
                    output_path=export_path,
                    manifest_output=manifest_path,
                )
            else:
                return export_draft_fixture(
                    fixture=chain_input,
                    output_path=export_path,
                    manifest_output=manifest_path,
                )

        exported = await asyncio.to_thread(_export)

        from minos_core.run_manifest import sha256_file
        file_hash = sha256_file(exported)

        artifact = db.Artifact(
            id=str(uuid.uuid4()),
            run_id=export_run_id,
            artifact_type=f"{export_mode}_xlsx",
            file_path=str(exported),
            sha256=file_hash,
            created_at=datetime.now(timezone.utc).replace(microsecond=0),
        )
        session.add(artifact)

        project.status = "final_export_ready"
        export_run.status = "final_export_ready"

    except Exception as exc:  # noqa: BLE001
        export_run.status = "blocked"
        export_run.error_message = str(exc)
        project.status = "blocked"
        api_err = map_core_error(exc)
        raise HTTPException(status_code=api_err.status_code, detail=api_err.message) from exc

    await session.commit()
    return ExportResponse(export_path=str(exported), run_id=export_run_id)
