"""PPAP Element management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from minos_platform import db
from minos_platform.errors import NotFoundError, InvalidStateError
from minos_platform.models import (
    PPAPElementDetail,
    PPAPElementArtifactResponse,
    PPAPElementSummary,
    UpdatePPAPElementRequest,
    LinkArtifactToElementRequest,
    PPAPElementStatus,
)

router = APIRouter()


def _build_element_detail_from_data(elem, artifacts) -> PPAPElementDetail:
    return PPAPElementDetail(
        id=elem.id,
        element_key=elem.element_key,
        display_name=elem.display_name,
        status=PPAPElementStatus(elem.status),
        notes=elem.notes,
        updated_at=elem.updated_at,
        artifacts=[
            PPAPElementArtifactResponse(
                id=a.id,
                artifact_id=a.artifact_id,
                artifact_ref_path=a.artifact_ref_path,
                sha256=a.sha256,
                notes=a.notes,
                created_at=a.created_at,
            )
            for a in artifacts
        ],
    )


def _build_element_summary(elem) -> PPAPElementSummary:
    return PPAPElementSummary(
        id=elem.id,
        element_key=elem.element_key,
        display_name=elem.display_name,
        status=PPAPElementStatus(elem.status),
        notes=elem.notes,
        updated_at=elem.updated_at,
    )


@router.get("/ppap-packages/{package_id}/elements")
async def list_elements(
    package_id: str,
    session: AsyncSession = Depends(db.get_session),
) -> list[PPAPElementSummary]:
    """List all elements in a PPAP package."""
    result = await session.execute(
        select(db.PPAPElement).where(db.PPAPElement.package_id == package_id)
    )
    elements = result.scalars().all()
    return [_build_element_summary(e) for e in elements]


@router.get("/ppap-packages/{package_id}/elements/{element_id}")
async def get_element(
    package_id: str,
    element_id: str,
    session: AsyncSession = Depends(db.get_session),
) -> PPAPElementDetail:
    """Get a single element with its artifact links."""
    result = await session.execute(
        select(db.PPAPElement).where(
            db.PPAPElement.id == element_id,
            db.PPAPElement.package_id == package_id,
        )
    )
    elem = result.scalar_one_or_none()
    if elem is None:
        raise NotFoundError("ppap_element", element_id)

    art_result = await session.execute(
        select(db.PPAPElementArtifact).where(db.PPAPElementArtifact.element_id == element_id)
    )
    artifacts = art_result.scalars().all()
    return _build_element_detail_from_data(elem, artifacts)


@router.patch("/ppap-packages/{package_id}/elements/{element_id}")
async def update_element(
    package_id: str,
    element_id: str,
    req: UpdatePPAPElementRequest,
    session: AsyncSession = Depends(db.get_session),
) -> PPAPElementSummary:
    """Update element status and/or notes."""
    result = await session.execute(
        select(db.PPAPElement).where(
            db.PPAPElement.id == element_id,
            db.PPAPElement.package_id == package_id,
        )
    )
    elem = result.scalar_one_or_none()
    if elem is None:
        raise NotFoundError("ppap_element", element_id)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    if req.status is not None:
        elem.status = req.status.value
    if req.notes is not None:
        elem.notes = req.notes
    elem.updated_at = now

    await session.commit()
    return _build_element_summary(elem)


@router.post("/ppap-packages/{package_id}/elements/{element_id}/artifacts", status_code=201)
async def link_artifact_to_element(
    package_id: str,
    element_id: str,
    req: LinkArtifactToElementRequest,
    session: AsyncSession = Depends(db.get_session),
) -> PPAPElementArtifactResponse:
    """Link a platform artifact to a PPAP element."""
    elem_result = await session.execute(
        select(db.PPAPElement).where(
            db.PPAPElement.id == element_id,
            db.PPAPElement.package_id == package_id,
        )
    )
    elem = elem_result.scalar_one_or_none()
    if elem is None:
        raise NotFoundError("ppap_element", element_id)

    artifact_result = await session.execute(
        select(db.Artifact).where(db.Artifact.id == req.artifact_id)
    )
    artifact = artifact_result.scalar_one_or_none()
    if artifact is None:
        raise NotFoundError("artifact", req.artifact_id)

    # Verify artifact belongs to a run in the same project
    run_result = await session.execute(
        select(db.Run).where(db.Run.id == artifact.run_id)
    )
    run = run_result.scalar_one_or_none()
    # Get package's project_id via the package
    pkg_result = await session.execute(
        select(db.PPAPPackage).where(db.PPAPPackage.id == elem.package_id)
    )
    pkg = pkg_result.scalar_one_or_none()
    # Cross-project check
    if run is None or pkg is None or run.project_id != pkg.project_id:
        raise InvalidStateError("cross_project_artifact", "same_project")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    link = db.PPAPElementArtifact(
        id=str(uuid.uuid4()),
        element_id=element_id,
        artifact_id=req.artifact_id,
        artifact_ref_path=artifact.file_path,
        sha256=artifact.sha256,
        notes=req.notes,
        created_at=now,
    )
    session.add(link)
    await session.commit()
    return PPAPElementArtifactResponse(
        id=link.id,
        artifact_id=link.artifact_id,
        artifact_ref_path=link.artifact_ref_path,
        sha256=link.sha256,
        notes=link.notes,
        created_at=link.created_at,
    )


@router.post("/ppap-packages/{package_id}/refresh-from-project")
async def refresh_package_from_project(
    package_id: str,
    session: AsyncSession = Depends(db.get_session),
) -> dict:
    """Auto-link project artifacts to PFD, PFMEA, and Control Plan elements.

    Searches the project's runs for artifacts of type pfmea_xlsx and final_xlsx,
    then links them to the corresponding elements.
    """
    pkg_result = await session.execute(
        select(db.PPAPPackage).where(db.PPAPPackage.id == package_id)
    )
    pkg = pkg_result.scalar_one_or_none()
    if pkg is None:
        raise NotFoundError("ppap_package", package_id)

    project_id = pkg.project_id

    # Find all relevant artifacts for this project
    runs_result = await session.execute(
        select(db.Run).where(db.Run.project_id == project_id)
    )
    runs = runs_result.scalars().all()

    artifact_map: dict[str, db.Artifact] = {}
    for run in runs:
        art_result = await session.execute(
            select(db.Artifact).where(db.Artifact.run_id == run.id)
        )
        for art in art_result.scalars().all():
            if art.artifact_type in ("pfmea_xlsx", "final_xlsx"):
                artifact_map[art.artifact_type] = art

    now = datetime.now(timezone.utc).replace(microsecond=0)
    linked = []

    pfmea_art = artifact_map.get("pfmea_xlsx")
    final_art = artifact_map.get("final_xlsx")

    elements_result = await session.execute(
        select(db.PPAPElement).where(db.PPAPElement.package_id == package_id)
    )
    elements = {e.element_key: e for e in elements_result.scalars().all()}

    for key, artifact in [
        ("process_flow_diagram", pfmea_art),
        ("pfmea", pfmea_art),
        ("control_plan", final_art),
    ]:
        if key not in elements or artifact is None:
            continue
        elem = elements[key]

        # Check if already linked to this artifact
        existing = await session.execute(
            select(db.PPAPElementArtifact).where(
                db.PPAPElementArtifact.element_id == elem.id,
                db.PPAPElementArtifact.artifact_id == artifact.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        link = db.PPAPElementArtifact(
            id=str(uuid.uuid4()),
            element_id=elem.id,
            artifact_id=artifact.id,
            artifact_ref_path=artifact.file_path,
            sha256=artifact.sha256,
            notes="Auto-linked via refresh-from-project",
            created_at=now,
        )
        session.add(link)
        linked.append({"element": key, "artifact_type": artifact.artifact_type})

        # Update element status to draft_ready
        if elem.status == PPAPElementStatus.MISSING.value:
            elem.status = PPAPElementStatus.DRAFT_READY.value
            elem.updated_at = now

    await session.commit()
    return {"linked_count": len(linked), "links": linked}
