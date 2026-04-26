"""Pydantic request/response models for minos_platform API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProjectStatus(str, Enum):
    CREATED = "created"
    INPUT_REGISTERED = "input_registered"
    DRAFT_READY = "draft_ready"
    REVIEW_TEMPLATE_READY = "review_template_ready"
    REVIEW_PATCH_SUBMITTED = "review_patch_submitted"
    REVIEW_APPLIED = "review_applied"
    FINAL_EXPORT_READY = "final_export_ready"
    BLOCKED = "blocked"


class RunType(str, Enum):
    DRAFT = "draft"
    REVIEW = "review"
    EXPORT = "export"


class PPAPElementStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    MISSING = "missing"
    DRAFT_READY = "draft_ready"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    BLOCKED = "blocked"


class PPAPPackageStatus(str, Enum):
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
    project_code: Optional[str] = Field(default=None, max_length=128)
    part_number: Optional[str] = Field(default=None, max_length=128)


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
    submission_level: Optional[str] = Field(default=None, max_length=32)


class UpdatePPAPElementRequest(BaseModel):
    status: Optional[PPAPElementStatus] = None
    notes: Optional[str] = Field(default=None, max_length=2048)


class LinkArtifactToElementRequest(BaseModel):
    artifact_id: str = Field(...)
    notes: Optional[str] = Field(default=None, max_length=1024)


class RefreshPackageRequest(BaseModel):
    pass


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ProjectSummary(BaseModel):
    id: str
    name: str
    project_code: Optional[str]
    part_number: Optional[str]
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
    input_packages: List[InputPackageSummary] = Field(default_factory=list)
    latest_run_id: Optional[str] = None


class RunSummary(BaseModel):
    id: str
    project_id: str
    run_type: RunType
    status: str
    result_json_path: Optional[str]
    manifest_json_path: Optional[str]
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactSummary(BaseModel):
    id: str
    run_id: Optional[str]
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
    notes: Optional[str]
    updated_at: datetime

    model_config = {"from_attributes": True}


class PPAPElementArtifactResponse(BaseModel):
    id: str
    artifact_id: Optional[str]
    artifact_ref_path: Optional[str]
    sha256: Optional[str]
    notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class PPAPElementDetail(PPAPElementSummary):
    artifacts: List[PPAPElementArtifactResponse] = Field(default_factory=list)


class PPAPPackageSummary(BaseModel):
    id: str
    project_id: str
    name: str
    submission_level: Optional[str]
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
    elements: List[PPAPElementDetail] = Field(default_factory=list)
