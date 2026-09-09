"""Map SQLite rows and stored envelopes to desktop run records."""

from __future__ import annotations

import copy
import json
import sqlite3
from typing import Any

from ..app_state import DesktopExportRecord, DesktopProjectRecord, DesktopRunRecord, DesktopRunState
from ..table_editor import EDIT_PATCH_VERSION
from .project_store import _from_json_object
from .run_chain import _status_display
from .run_edit_helpers import _normalize_three_table_result
from .run_shared import _chain_stages_from_envelope, _sanitize_legacy_pfmea_placeholders


def _stored_result_parts(stored: dict[str, Any]) -> dict[str, Any]:
    if stored.get("_desktop_storage_version") == 1:
        raw_result = stored.get("raw_result", {})
        current_result = stored.get("current_result", raw_result)
        edit_patch = stored.get("edit_patch", {})
        return {
            "raw_result": raw_result if isinstance(raw_result, dict) else {},
            "current_result": current_result if isinstance(current_result, dict) else {},
            "edit_patch": edit_patch if isinstance(edit_patch, dict) else {},
        }
    return {
        "raw_result": stored,
        "current_result": _normalize_three_table_result(stored),
        "edit_patch": {"edit_patch_version": EDIT_PATCH_VERSION, "items": []},
    }


def _project_from_row(row: sqlite3.Row) -> DesktopProjectRecord:
    return DesktopProjectRecord(
        id=int(row["id"]),
        project_name=str(row["project_name"]),
        drawing_path=str(row["drawing_path"]),
        output_dir=str(row["output_dir"]),
        context=_from_json_object(str(row["context_json"])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _run_from_row(row: sqlite3.Row) -> DesktopRunRecord:
    exports = _from_json_object(str(row["exports_json"]))
    manual_review_data = json.loads(str(row["manual_review_json"]) or "[]")
    manual_review_items = manual_review_data if isinstance(manual_review_data, list) else []
    raw_result = _from_json_object(str(row["raw_result_json"]))
    stored = _stored_result_parts(raw_result)
    current_result = copy.deepcopy(stored["current_result"])
    chain_stages = _chain_stages_from_envelope(raw_result)
    failure_message = str(row["failure_message"])
    current_result, chain_stages = _sanitize_legacy_pfmea_placeholders(
        current_result, chain_stages, failure_message=failure_message
    )
    if stored.get("edit_patch"):
        current_result["edit_patch"] = stored["edit_patch"]
    state_status = str(row["status"])
    state_blocked_stage = str(row["blocked_stage"])
    if (
        failure_message
        and str(current_result.get("status") or "") == "failed"
        and (str(current_result.get("blocked_stage") or "") == "pfmea")
    ):
        state_status = "failed"
        state_blocked_stage = "pfmea"
    state = DesktopRunState(
        status=state_status,
        status_display=_status_display(state_status),
        blocked_stage=state_blocked_stage,
        exports=tuple(
            sorted(
                (DesktopExportRecord(str(name), str(path)) for name, path in exports.items()),
                key=lambda item: item.name,
            )
        ),
        manifest_path=str(row["manifest_path"]),
        manifest_run_id=str(row["manifest_run_id"]),
        manual_review_required=bool(row["manual_review_required"]),
        manual_review_count=int(row["manual_review_count"]),
        manual_review_raw_count=int(row["manual_review_count"]),
        manual_review_items=tuple(manual_review_items),
        chain_stages=chain_stages,
    )
    return DesktopRunRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]) if row["project_id"] is not None else None,
        state=state,
        output_dir=str(row["output_dir"]),
        raw_result=current_result,
        failure_message=failure_message,
        created_at=str(row["created_at"]),
        original_result=stored["raw_result"],
        current_result=current_result,
        edit_patch=stored["edit_patch"],
    )
