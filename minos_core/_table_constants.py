"""Shared table-structure constants for three-table operations.

Multiple modules (edit_patch, closure_tasks, live_linkage) previously
maintained their own copies of these mappings.  This module provides
the single source of truth.
"""

from __future__ import annotations

from typing import Any


TABLE_ROW_FIELDS: dict[str, tuple[str, ...]] = {
    "process_flow": ("steps", "process_steps"),
    "pfmea": ("rows", "failure_modes"),
    "control_plan": ("rows", "controls"),
}

TABLE_ID_FIELDS: dict[str, tuple[str, ...]] = {
    "process_flow": ("process_step_id", "id", "step_no"),
    "pfmea": ("pfmea_id", "id"),
    "control_plan": ("control_plan_id", "id"),
}


def row_id(table: str, row: dict[str, Any]) -> str:
    """Extract the primary ID from a three-table row."""
    for field_name in TABLE_ID_FIELDS.get(table, ()):
        value = str(row.get(field_name, "")).strip()
        if value:
            return value
    return ""
