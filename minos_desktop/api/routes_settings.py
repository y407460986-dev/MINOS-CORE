"""Desktop settings routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from minos_core.validation import validate_user_selected_directory
from minos_desktop.services import DesktopDataManagementService, DesktopSettingsStore

from .schemas import (
    AIConfigUpdateRequest,
    DataManagementClearRequest,
    DefaultOutputDirRequest,
    failure_from_exception,
    settings_to_dict,
)

router = APIRouter()


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    store = DesktopSettingsStore(request.app.state.db_path)
    return settings_to_dict(store.get_default_output_dir(), store.get_ai_config_state())


@router.patch("/settings/default-output-dir")
def set_default_output_dir(
    payload: DefaultOutputDirRequest, request: Request
) -> dict[str, Any]:
    store = DesktopSettingsStore(request.app.state.db_path)
    value = store.set_default_output_dir(validate_user_selected_directory(payload.output_dir))
    request.app.state.output_dir = value
    return settings_to_dict(value, store.get_ai_config_state())


@router.patch("/settings/ai-config")
def set_ai_config(
    payload: AIConfigUpdateRequest, request: Request
) -> dict[str, Any]:
    store = DesktopSettingsStore(request.app.state.db_path)
    store.set_ai_overrides(
        base_url=payload.base_url,
        api_key=payload.api_key,
        model=payload.model,
    )
    return settings_to_dict(store.get_default_output_dir(), store.get_ai_config_state())


@router.get("/settings/data-management")
def get_data_management_status(request: Request) -> dict[str, Any]:
    return _data_management_service(request).get_status()


@router.post("/settings/data-management/backup")
def backup_data_management(request: Request) -> dict[str, Any]:
    return _data_management_service(request).create_backup()


@router.post("/settings/data-management/clear")
def clear_data_management(
    payload: DataManagementClearRequest, request: Request
) -> dict[str, Any]:
    try:
        return _data_management_service(request).clear_data(
            scope=payload.scope,
            delete_outputs=payload.delete_outputs,
            confirm_text=payload.confirm_text,
        )
    except ValueError as exc:
        raise failure_from_exception(exc) from exc


def _data_management_service(request: Request) -> DesktopDataManagementService:
    return DesktopDataManagementService(
        request.app.state.db_path,
        request.app.state.output_dir,
    )
