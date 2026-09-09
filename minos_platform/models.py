"""Pydantic request/response models for minos_platform API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProjectStatus(StrEnum):
    CREATED = "created"
    INPUT_REGISTERED = "input_registered"
    DRAFT_READY = "draft_ready"
    REVIEW_TEMPLATE_READY = "review_template_ready"
    REVIEW_PATCH_SUBMITTED = "review_patch_submitted"
    REVIEW_APPLIED = "review_applied"
    FINAL_EXPORT_READY = "final_export_ready"
    BLOCKED = "blocked"


class RunType(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    EXPORT = "export"


class PPAPElementStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    MISSING = "missing"
    DRAFT_READY = "draft_ready"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    BLOCKED = "blocked"


class PPAPPackageStatus(StrEnum):
    DRAFT = "draft"
    READY_FOR_SUBMISSION = "ready_for_submission"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    project_code: str | None = Field(default=None, max_length=128)
    part_number: str | None = Field(default=None, max_length=128)


class RegisterInputPackageRequest(BaseModel):
    input_package_path: str = Field(...)
    redacted: str = Field(default="unknown", max_length=16)
    sha256: str = Field(..., min_length=64, max_length=64)


class SubmitReviewPatchRequest(BaseModel):
    patch_path: str = Field(...)
    sha256: str = Field(..., min_length=64, max_length=64)


class TriggerExportRequest(BaseModel):
    export_mode: str = Field(default="final", pattern="^(final|draft)$")


# ---------------------------------------------------------------------------
# PPAP Package / Element request models
# ---------------------------------------------------------------------------


class CreatePPAPPackageRequest(BaseModel):
    name: str = Field(default="PPAP Package 1", min_length=1, max_length=256)
    submission_level: str | None = Field(default=None, max_length=32)


class UpdatePPAPElementRequest(BaseModel):
    status: PPAPElementStatus | None = None
    notes: str | None = Field(default=None, max_length=2048)


class LinkArtifactToElementRequest(BaseModel):
    artifact_id: str = Field(...)
    notes: str | None = Field(default=None, max_length=1024)


class RefreshPackageRequest(BaseModel):
    pass


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ProjectSummary(BaseModel):
    id: str
    name: str
    project_code: str | None
    part_number: str | None
    status: ProjectStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class InputPackageSummary(BaseModel):
    id: str
    package_path: str
    sha256: str
    redacted: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectDetail(ProjectSummary):
    input_packages: list[InputPackageSummary] = Field(default_factory=list)
    latest_run_id: str | None = None


class RunSummary(BaseModel):
    id: str
    project_id: str
    run_type: RunType
    status: str
    result_json_path: str | None
    manifest_json_path: str | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactSummary(BaseModel):
    id: str
    run_id: str | None
    artifact_type: str
    file_path: str
    sha256: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ErrorDetail(BaseModel):
    detail: str
    code: str


class ReviewTemplateResponse(BaseModel):
    template_path: str
    run_id: str


class ApplyReviewResponse(BaseModel):
    review_result_path: str
    final_export_allowed: bool
    run_id: str


class ExportResponse(BaseModel):
    export_path: str
    run_id: str


# ---------------------------------------------------------------------------
# PPAP Package / Element response models
# ---------------------------------------------------------------------------


class PPAPElementSummary(BaseModel):
    id: str
    element_key: str
    display_name: str
    status: PPAPElementStatus
    notes: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class PPAPElementArtifactResponse(BaseModel):
    id: str
    artifact_id: str | None
    artifact_ref_path: str | None
    sha256: str | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PPAPElementDetail(PPAPElementSummary):
    artifacts: list[PPAPElementArtifactResponse] = Field(default_factory=list)


class PPAPPackageSummary(BaseModel):
    id: str
    project_id: str
    name: str
    submission_level: str | None
    status: PPAPPackageStatus
    total_elements: int = 0
    required_count: int = 0
    approved_count: int = 0
    missing_count: int = 0
    blocked_count: int = 0
    ready_for_submission: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class PPAPPackageDetail(PPAPPackageSummary):
    elements: list[PPAPElementDetail] = Field(default_factory=list)
