"""Small Pydantic schemas and serializers for the desktop sidecar API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from minos_desktop.app_state import DesktopProjectRecord, DesktopRunRecord
from minos_desktop.security.secret_str import SecretStr
from minos_desktop.services import format_desktop_failure


class APIError(HTTPException):
    def __init__(
        self,
        detail: str,
        code: str,
        status_code: int = 422,
        *,
        failure_message: str | None = None,
    ) -> None:
        self.code = code
        self.failure_message = failure_message or format_desktop_failure(detail)
        super().__init__(status_code=status_code, detail=detail)


class CreateProjectRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=256)
    drawing_path: str = ""
    component_drawings: list[str] = Field(default_factory=list)
    output_dir: str = ""
    analysis_mode: str = Field(default="hybrid", pattern="^(ocr_only|vision_only|hybrid)$")
    ocr_engine: str = Field(default="mineru", pattern="^(auto|pdf_text|rapidocr|mineru)$")
    context: dict[str, Any] = Field(default_factory=dict)


class DefaultOutputDirRequest(BaseModel):
    output_dir: str = Field(..., min_length=1)


class AIConfigUpdateRequest(BaseModel):
    base_url: str | None = None
    api_key: SecretStr | None = None
    model: str | None = None


class DataManagementClearRequest(BaseModel):
    scope: str = Field(..., pattern="^(workspace|factory_reset)$")
    delete_outputs: bool = False
    confirm_text: str = Field(..., min_length=1)


class EditPatchRequest(BaseModel):
    patch: dict[str, Any] = Field(default_factory=dict)


class ExportRunRequest(BaseModel):
    output_dir: str = ""
    export_mode: str = Field(default="draft", pattern="^(draft|final)$")


class IgnoreRequest(BaseModel):
    reason: str = ""


class ResolveActionRequest(BaseModel):
    changes: dict[str, Any] = Field(default_factory=lambda: {"status": "已处理"})
    reason: str = ""


class ResolveChangeImpactRequest(BaseModel):
    status: str = "已处理"
    reason: str = ""


class AutomationFixRequest(BaseModel):
    row: dict[str, Any] = Field(default_factory=dict)


class DrawingConfirmationsRequest(BaseModel):
    task_ids: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)
    reason: str = ""
    resolution_note: str = ""
    confirmed_by: str = ""
    manual_confirmation_event: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class PartFamilyRequest(BaseModel):
    part_family: str = ""
    task_id: str = ""
    family_key: str = ""
    family_name: str = ""
    confirmed: bool = True
    reason: str = ""
    resolution_note: str = ""


class ProcessFlowConfirmationsRequest(BaseModel):
    task_ids: list[str] = Field(default_factory=list)
    step_ids: list[str] = Field(default_factory=list)
    reason: str = ""
    resolution_note: str = ""
    confirmed_by: str = ""


class ChainConfirmRequest(BaseModel):
    """链式阶段确认请求。"""
    confirmed_by: str = ""
    reason: str = ""
    edit_patch: dict[str, Any] = Field(default_factory=dict)


class ClosureTaskResolveRequest(BaseModel):
    action: str = "resolve"
    status: str = "已处理"
    changes: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    resolution_note: str = ""
    owner: str = ""
    due_date: str = ""
    manual_confirmation_event: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class ClosureTasksBulkResolveRequest(ClosureTaskResolveRequest):
    task_type: str = Field(..., min_length=1)
    task_ids: list[str] = Field(default_factory=list)
    target_row_ids: list[str] = Field(default_factory=list)


class LinkageApplySyncRequest(BaseModel):
    edit_patch: dict[str, Any] = Field(default_factory=dict)
    selected_impact_ids: list[str] = Field(default_factory=list)
    suggestion_ids: list[str] = Field(default_factory=list)
    apply_all: bool = False
    reason: str = ""


class KnowledgeRuleRequest(BaseModel):
    rule_id: str = Field(..., min_length=1)
    category: str = "本地知识"
    title: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class KnowledgeImportSeedsRequest(BaseModel):
    seed_dirs: dict[str, str] = Field(default_factory=dict)
    output_dir: str = ""
    write_files: bool = True


def project_to_dict(record: DesktopProjectRecord) -> dict[str, Any]:
    analysis_mode = str(record.context.get("analysis_mode") or "hybrid")
    ocr_engine = str(record.context.get("ocr_engine") or "mineru")
    return {
        "id": record.id,
        "project_name": record.project_name,
        "drawing_path": record.drawing_path,
        "component_drawings": list(record.component_drawings),
        "output_dir": record.output_dir,
        "analysis_mode": analysis_mode,
        "ocr_engine": ocr_engine,
        "context": record.context,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def run_to_dict(record: DesktopRunRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "status": record.state.status,
        "status_display": record.state.status_display,
        "blocked_stage": record.state.blocked_stage,
        "exports": {item.name: item.path for item in record.state.exports},
        "manifest_path": record.state.manifest_path,
        "manifest_run_id": record.state.manifest_run_id,
        "manual_review_required": record.state.manual_review_required,
        "manual_review_count": record.state.manual_review_count,
        "manual_review_items": list(record.state.manual_review_items),
        "output_dir": record.output_dir,
        "raw_result": record.raw_result,
        "current_result": record.current_result,
        "edit_patch": record.edit_patch,
        "failure_message": record.failure_message,
        "created_at": record.created_at,
        "pipeline_mode": (
            record.state.chain_stages.pipeline_mode
            if record.state.chain_stages is not None
            else "batch"
        ),
        "chain_stages": (
            record.state.chain_stages.to_dict()
            if record.state.chain_stages is not None
            else None
        ),
    }


def settings_to_dict(default_output_dir: str, ai_config: Any) -> dict[str, Any]:
    return {
        "default_output_dir": default_output_dir,
        "ai_config": {
            "provider": ai_config.provider,
            "model": ai_config.model,
            "model_configured": ai_config.model_configured,
            "model_source": ai_config.model_source,
            "base_url": ai_config.base_url,
            "base_url_configured": ai_config.base_url_configured,
            "base_url_source": ai_config.base_url_source,
            "api_key_configured": ai_config.api_key_configured,
            "api_key_source": ai_config.api_key_source,
            "api_key_env_name": ai_config.api_key_env_name,
            "wire_api": ai_config.wire_api,
            "responses_path": ai_config.responses_path,
            "base_url_override": ai_config.base_url_override,
            "api_key_override_set": ai_config.api_key_override_set,
            "model_override": ai_config.model_override,
            "base_url_locked_by_env": ai_config.base_url_locked_by_env,
            "api_key_locked_by_env": ai_config.api_key_locked_by_env,
            "model_locked_by_env": ai_config.model_locked_by_env,
        },
    }


def table_rows(result: dict[str, Any], table_name: str) -> list[Any]:
    table = result.get(table_name, {})
    if not isinstance(table, dict):
        return []
    key = "steps" if table_name == "process_flow" else "rows"
    rows = table.get(key, [])
    return rows if isinstance(rows, list) else []


def failure_from_exception(exc: BaseException) -> APIError:
    if isinstance(exc, KeyError):
        return APIError(str(exc), "NOT_FOUND", 404)
    if isinstance(exc, ValueError):
        return APIError(str(exc), "VALUE_ERROR", 422)
    if isinstance(exc, TypeError):
        return APIError(str(exc), "TYPE_ERROR", 422)
    if isinstance(exc, OSError):
        return APIError(str(exc), "OS_ERROR", 422)
    return APIError(str(exc), "INTERNAL_ERROR", 500)


def default_export_dir(run_output_dir: str, run_id: int) -> str:
    base = Path(run_output_dir or "out/desktop")
    return str(base / f"run-{run_id}-exports")
