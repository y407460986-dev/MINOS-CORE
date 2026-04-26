"""POST /api/projects/{project_id}/input-packages."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from minos_platform import config, db
from minos_platform.errors import APIError, InvalidStateError, NotFoundError
from minos_platform.models import InputPackageSummary, RegisterInputPackageRequest
from minos_platform.utils import calculate_directory_sha256, calculate_file_sha256, safe_copy_input_file_or_dir

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
    """Register and copy an input_package into the platform artifact area."""
    result = await session.execute(select(db.Project).where(db.Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("project", project_id)
    if project.status not in VALID_STATES:
        raise InvalidStateError(project.status, "/".join(VALID_STATES))

    # Verify source exists
    src = Path(req.input_package_path)
    if not src.exists():
        raise APIError(
            f"Input package path does not exist: {req.input_package_path}",
            code="INPUT_PACKAGE_NOT_FOUND",
            status_code=404,
        )

    # Copy to platform artifact area
    project_artifact_dir = config.get_artifacts_dir() / project_id / "inputs"
    try:
        copied_path = safe_copy_input_file_or_dir(req.input_package_path, project_artifact_dir)
    except FileNotFoundError as e:
        raise APIError(str(e), code="INPUT_PACKAGE_NOT_FOUND", status_code=404) from e

    # Verify sha256 of the copy
    if src.is_file():
        actual_hash = calculate_file_sha256(copied_path)
    else:
        # For directories, compute hash of all files inside copied_path in sorted order
        actual_hash = calculate_directory_sha256(copied_path)

    if actual_hash != req.sha256:
        raise APIError(
            f"SHA256 mismatch: expected {req.sha256}, got {actual_hash}",
            code="SHA256_MISMATCH",
            status_code=422,
        )

    pkg = db.InputPackage(
        id=str(uuid.uuid4()),
        project_id=project_id,
        package_path=str(copied_path),
        sha256=actual_hash,
        redacted=req.redacted,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    session.add(pkg)
    project.status = "input_registered"
    await session.commit()
    await session.refresh(pkg)
    return InputPackageSummary.model_validate(pkg)