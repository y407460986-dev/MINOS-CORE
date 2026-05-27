"""Desktop settings routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from minos_desktop.services import DesktopDataManagementService, DesktopSettingsStore

from .schemas import (
    AIConfigUpdateRequest,
    DataManagementClearRequest,
    DefaultOutputDirRequest,
    ProcessBoundaryUpdateRequest,
    failure_from_exception,
    settings_to_dict,
)

router = APIRouter()


@router.get("/settings")
def get_settings(request: Request) -> dict:
    store = DesktopSettingsStore(request.app.state.db_path)
    return _settings_response(store)


@router.patch("/settings/default-output-dir")
def set_default_output_dir(payload: DefaultOutputDirRequest, request: Request) -> dict:
    store = DesktopSettingsStore(request.app.state.db_path)
    value = store.set_default_output_dir(payload.output_dir)
    request.app.state.output_dir = value
    return _settings_response(store)


@router.patch("/settings/ai-config")
def set_ai_config(payload: AIConfigUpdateRequest, request: Request) -> dict:
    store = DesktopSettingsStore(request.app.state.db_path)
    store.set_ai_overrides(
        base_url=payload.base_url,
        api_key=payload.api_key,
        model=payload.model,
    )
    return _settings_response(store)


@router.patch("/settings/process-boundary")
def set_process_boundary(payload: ProcessBoundaryUpdateRequest, request: Request) -> dict:
    store = DesktopSettingsStore(request.app.state.db_path)
    try:
        store.set_process_boundary_config(payload.model_dump())
    except ValueError as exc:
        raise failure_from_exception(exc) from exc
    return _settings_response(store)


@router.get("/settings/data-management")
def get_data_management_status(request: Request) -> dict:
    return _data_management_service(request).get_status()


@router.post("/settings/data-management/backup")
def backup_data_management(request: Request) -> dict:
    return _data_management_service(request).create_backup()


@router.post("/settings/data-management/clear")
def clear_data_management(payload: DataManagementClearRequest, request: Request) -> dict:
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


def _settings_response(store: DesktopSettingsStore) -> dict:
    return settings_to_dict(
        store.get_default_output_dir(),
        store.get_ai_config_state(),
        store.get_process_boundary_config(),
    )
