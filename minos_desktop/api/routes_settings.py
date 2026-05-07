"""Desktop settings routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from minos_desktop.services import DesktopSettingsStore

from .schemas import DefaultOutputDirRequest, settings_to_dict

router = APIRouter()


@router.get("/settings")
def get_settings(request: Request) -> dict:
    store = DesktopSettingsStore(request.app.state.db_path)
    return settings_to_dict(store.get_default_output_dir(), store.get_ai_config_state())


@router.patch("/settings/default-output-dir")
def set_default_output_dir(payload: DefaultOutputDirRequest, request: Request) -> dict:
    store = DesktopSettingsStore(request.app.state.db_path)
    value = store.set_default_output_dir(payload.output_dir)
    request.app.state.output_dir = value
    return settings_to_dict(value, store.get_ai_config_state())
