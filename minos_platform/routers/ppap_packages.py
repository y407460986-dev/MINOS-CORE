"""PPAP Package management endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from minos_platform import db
from minos_platform.errors import NotFoundError
from minos_platform.models import (
    CreatePPAPPackageRequest,
    PPAPElementArtifactResponse,
    PPAPElementDetail,
    PPAPElementStatus,
    PPAPPackageDetail,
    PPAPPackageStatus,
    PPAPPackageSummary,
)

router = APIRouter()

# The 18 standard PPAP elements
PPAP_ELEMENT_DEFINITIONS = [
    ("design_records", "1. Design Records"),
    ("engineering_change_documents", "2. Authorized Engineering Change Documents"),
    ("engineering_approval", "3. Customer Engineering Approval"),
    ("dfmea", "4. DFMEA"),
    ("process_flow_diagram", "5. Process Flow Diagram"),
    ("pfmea", "6. PFMEA"),
    ("control_plan", "7. Control Plan"),
    ("msa_studies", "8. MSA Studies"),
    ("dimensional_results", "9. Dimensional Results"),
    ("material_test_results", "10. Material / Performance Test Results"),
    ("initial_process_studies", "11. Initial Process Studies"),
    ("laboratory_documentation", "12. Qualified Laboratory Documentation"),
    ("appearance_approval", "13. Appearance Approval Report"),
    ("sample_product", "14. Sample Product"),
    ("master_sample", "15. Master Sample"),
    ("checking_aids", "16. Checking Aids"),
    ("customer_specific_requirements", "17. Customer-Specific Requirements"),
    ("part_submission_warrant", "18. Part Submission Warrant"),
]


def _build_package_summary(pkg: db.PPAPPackage) -> PPAPPackageSummary:
    total = len(pkg.elements)
    required = sum(1 for e in pkg.elements if e.status == PPAPElementStatus.REQUIRED.value)
    approved = sum(1 for e in pkg.elements if e.status == PPAPElementStatus.APPROVED.value)
    missing = sum(1 for e in pkg.elements if e.status == PPAPElementStatus.MISSING.value)
    blocked = sum(1 for e in pkg.elements if e.status == PPAPElementStatus.BLOCKED.value)
    required_elements = [e for e in pkg.elements if e.status == PPAPElementStatus.REQUIRED.value]
    ready_for_submission = (
        all(e.status == PPAPElementStatus.APPROVED.value for e in required_elements)
        if required_elements
        else False
    )

    return PPAPPackageSummary(
        id=pkg.id,
        project_id=pkg.project_id,
        name=pkg.name,
        submission_level=pkg.submission_level,
        status=PPAPPackageStatus(pkg.status) if pkg.status else PPAPPackageStatus.DRAFT,
        total_elements=total,
        required_count=required,
        approved_count=approved,
        missing_count=missing,
        blocked_count=blocked,
        ready_for_submission=ready_for_submission,
        created_at=pkg.created_at,
    )


def _build_package_summary_from_elements(pkg, elements: list) -> PPAPPackageSummary:
    total = len(elements)
    required = sum(1 for e in elements if e.status == PPAPElementStatus.REQUIRED.value)
    approved = sum(1 for e in elements if e.status == PPAPElementStatus.APPROVED.value)
    missing = sum(1 for e in elements if e.status == PPAPElementStatus.MISSING.value)
    blocked = sum(1 for e in elements if e.status == PPAPElementStatus.BLOCKED.value)
    required_elements = [e for e in elements if e.status == PPAPElementStatus.REQUIRED.value]
    # Ready only when all required elements are approved (or none exist) AND at least one element is approved
    ready_for_submission = (
        (not required_elements or all(e.status == PPAPElementStatus.APPROVED.value for e in required_elements))
        and approved > 0
    )

    return PPAPPackageSummary(
        id=pkg.id,
        project_id=pkg.project_id,
        name=pkg.name,
        submission_level=pkg.submission_level,
        status=PPAPPackageStatus(pkg.status) if pkg.status else PPAPPackageStatus.DRAFT,
        total_elements=total,
        required_count=required,
        approved_count=approved,
        missing_count=missing,
        blocked_count=blocked,
        ready_for_submission=ready_for_submission,
        created_at=pkg.created_at,
    )


def _build_element_detail(elem) -> PPAPElementDetail:
    artifacts = [
        PPAPElementArtifactResponse(
            id=a.id,
            artifact_id=a.artifact_id,
            artifact_ref_path=a.artifact_ref_path,
            sha256=a.sha256,
            notes=a.notes,
            created_at=a.created_at,
        )
        for a in elem.artifacts
    ]
    return PPAPElementDetail(
        id=elem.id,
        element_key=elem.element_key,
        display_name=elem.display_name,
        status=PPAPElementStatus(elem.status),
        notes=elem.notes,
        updated_at=elem.updated_at,
        artifacts=artifacts,
    )


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


@router.post("/projects/{project_id}/ppap-packages", status_code=201)
async def create_ppap_package(
    project_id: str,
    req: CreatePPAPPackageRequest,
    session: AsyncSession = Depends(db.get_session),  # noqa: B008
) -> PPAPPackageSummary:
    """Create a new PPAP package for the project and initialize 18 element checklist."""
    result = await session.execute(select(db.Project).where(db.Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("project", project_id)

    package_id = str(uuid.uuid4())
    now = datetime.now(UTC).replace(microsecond=0)
    pkg = db.PPAPPackage(
        id=package_id,
        project_id=project_id,
        name=req.name,
        submission_level=req.submission_level,
        status="draft",
        created_at=now,
    )
    session.add(pkg)

    # Initialize 18 default elements
    created_elements = []
    for element_key, display_name in PPAP_ELEMENT_DEFINITIONS:
        elem = db.PPAPElement(
            id=str(uuid.uuid4()),
            package_id=package_id,
            element_key=element_key,
            display_name=display_name,
            status="missing",
            notes=None,
            updated_at=now,
        )
        session.add(elem)
        created_elements.append(elem)

    await session.commit()

    # Build summary from data we already have (no need to reload)
    total = len(created_elements)
    required = 0
    approved = 0
    missing = total
    blocked = 0

    return PPAPPackageSummary(
        id=package_id,
        project_id=project_id,
        name=req.name,
        submission_level=req.submission_level,
        status=PPAPPackageStatus.DRAFT,
        total_elements=total,
        required_count=required,
        approved_count=approved,
        missing_count=missing,
        blocked_count=blocked,
        ready_for_submission=False,
        created_at=now,
    )


@router.get("/projects/{project_id}/ppap-packages")
async def list_ppap_packages(
    project_id: str,
    session: AsyncSession = Depends(db.get_session),  # noqa: B008
) -> list[PPAPPackageSummary]:
    """List all PPAP packages for a project."""
    result = await session.execute(
        select(db.PPAPPackage)
        .where(db.PPAPPackage.project_id == project_id)
        .order_by(db.PPAPPackage.created_at.desc())
    )
    packages = result.scalars().all()

    summaries = []
    for pkg in packages:
        # Load elements for each package to compute counts
        elem_result = await session.execute(
            select(db.PPAPElement).where(db.PPAPElement.package_id == pkg.id)
        )
        elements = elem_result.scalars().all()
        summaries.append(_build_package_summary_from_elements(pkg, elements))
    return summaries


@router.get("/ppap-packages/{package_id}")
async def get_ppap_package(
    package_id: str,
    session: AsyncSession = Depends(db.get_session),  # noqa: B008
) -> PPAPPackageDetail:
    """Get detailed PPAP package with element checklist."""
    result = await session.execute(
        select(db.PPAPPackage).where(db.PPAPPackage.id == package_id)
    )
    pkg = result.scalar_one_or_none()
    if pkg is None:
        raise NotFoundError("ppap_package", package_id)

    # Load elements explicitly
    elem_result = await session.execute(
        select(db.PPAPElement).where(db.PPAPElement.package_id == package_id)
    )
    elements = elem_result.scalars().all()

    element_details = []
    for e in elements:
        art_result = await session.execute(
            select(db.PPAPElementArtifact).where(db.PPAPElementArtifact.element_id == e.id)
        )
        artifacts = art_result.scalars().all()
        element_details.append(_build_element_detail_from_data(e, artifacts))

    summary = _build_package_summary_from_elements(pkg, elements)
    return PPAPPackageDetail(
        id=summary.id,
        project_id=summary.project_id,
        name=summary.name,
        submission_level=summary.submission_level,
        status=summary.status,
        total_elements=summary.total_elements,
        required_count=summary.required_count,
        approved_count=summary.approved_count,
        missing_count=summary.missing_count,
        blocked_count=summary.blocked_count,
        ready_for_submission=summary.ready_for_submission,
        created_at=summary.created_at,
        elements=element_details,
    )
