"""GET /api/artifacts/{artifact_id} — serve artifact files. GET /api/artifacts — list artifacts."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from minos_platform import db
from minos_platform.errors import NotFoundError
from minos_platform.models import ArtifactSummary

router = APIRouter()


@router.get("/artifacts")
async def list_artifacts(
    session: AsyncSession = Depends(db.get_session),
) -> list[ArtifactSummary]:
    """List all artifacts."""
    result = await session.execute(select(db.Artifact))
    artifacts = result.scalars().all()
    return [ArtifactSummary.model_validate(a) for a in artifacts]


@router.get("/artifacts/{artifact_id}", response_class=FileResponse)
async def download_artifact(
    artifact_id: str,
    session: AsyncSession = Depends(db.get_session),
) -> FileResponse:
    """Download an artifact file by its id."""
    result = await session.execute(
        select(db.Artifact).where(db.Artifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise NotFoundError("artifact", artifact_id)

    path = Path(artifact.file_path)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Artifact file not found on disk: {artifact.file_path}",
        )
    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/octet-stream",
    )
