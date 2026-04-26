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
