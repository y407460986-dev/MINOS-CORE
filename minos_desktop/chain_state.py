"""Chain-stage state transitions for the desktop three-table workflow."""

from __future__ import annotations

import copy
from typing import Any

from .app_state import ChainStageStates, StageConfirmState


def init_chain_stages(
    pfd_status: str = "not_started",
    *,
    pfd_rows: int = 0,
    pfd_pending: int = 0,
    now: str = "",
) -> ChainStageStates:
    generated_at = now if pfd_status not in ("not_started", "failed") else ""
    return ChainStageStates(
        pfd=StageConfirmState(
            status=pfd_status,
            generated_at=generated_at,
            row_count=pfd_rows,
            pending_count=pfd_pending,
        ),
        pfmea=StageConfirmState(
            status="running" if pfd_status == "confirmed" else "not_started"
        ),
        cp=StageConfirmState(status="not_started"),
        pipeline_mode="chain",
    )


def chain_stages_from_envelope(envelope: dict[str, Any]) -> ChainStageStates | None:
    data = envelope.get("chain_stages")
    if data and isinstance(data, dict):
        return ChainStageStates.from_dict(data)
    return None


def confirm_chain_table(
    result: dict[str, Any],
    table: str,
    *,
    confirmed_by: str = "",
) -> None:
    for row in table_rows_for_chain(result, table):
        if not isinstance(row, dict):
            continue
        row["needs_confirmation"] = False
        row["ai_inferred"] = False
        row["review_status"] = "已确认"
        if confirmed_by:
            row["confirmed_by"] = confirmed_by


def failed_chain_stage(chain_stages: ChainStageStates | None) -> str:
    if chain_stages is None:
        return ""
    for stage_name in ("pfd", "pfmea", "cp"):
        stage = getattr(chain_stages, stage_name)
        if stage.status == "failed":
            return stage_name
    return ""


def invalidate_chain_after_patch(
    result: dict[str, Any],
    patch: dict[str, Any],
    chain_stages: ChainStageStates | None,
) -> tuple[dict[str, Any], ChainStageStates | None]:
    if chain_stages is None or chain_stages.pipeline_mode != "chain":
        return result, chain_stages
    changed_tables = changed_chain_tables(patch)
    if not changed_tables:
        return result, chain_stages

    updated = copy.deepcopy(result)
    metadata = updated.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        updated["metadata"] = metadata
    invalidated = list(metadata.get("chain_invalidated_stages", []))

    if "process_flow" in changed_tables:
        updated["pfmea"] = {"rows": []}
        updated["control_plan"] = {"rows": []}
        invalidated = dedupe_texts(invalidated + ["pfmea", "control_plan"])
        chain_stages = ChainStageStates(
            pfd=StageConfirmState(
                status="generated",
                generated_at=chain_stages.pfd.generated_at,
                confirmed_at="",
                confirmed_by="",
                row_count=table_row_count(updated, "process_flow"),
                pending_count=pending_row_count(updated, "process_flow"),
            ),
            pfmea=StageConfirmState(status="not_started"),
            cp=StageConfirmState(status="not_started"),
            pipeline_mode="chain",
        )
    elif "pfmea" in changed_tables:
        updated["control_plan"] = {"rows": []}
        invalidated = dedupe_texts(invalidated + ["control_plan"])
        chain_stages = ChainStageStates(
            pfd=chain_stages.pfd,
            pfmea=StageConfirmState(
                status="generated",
                generated_at=chain_stages.pfmea.generated_at,
                confirmed_at="",
                confirmed_by="",
                row_count=table_row_count(updated, "pfmea"),
                pending_count=pending_row_count(updated, "pfmea"),
            ),
            cp=StageConfirmState(status="not_started"),
            pipeline_mode="chain",
        )

    metadata["chain_invalidated_stages"] = invalidated
    updated["status"] = "needs_review"
    return updated, chain_stages


def changed_chain_tables(patch: dict[str, Any]) -> set[str]:
    tables: set[str] = set()
    items = patch.get("items", [])
    if not isinstance(items, list):
        return tables
    for item in items:
        if not isinstance(item, dict):
            continue
        table = str(item.get("table") or "").strip()
        action = str(item.get("action") or "").strip()
        if table not in {"process_flow", "pfmea", "control_plan"}:
            continue
        if action in {"add", "update", "soft_delete"}:
            tables.add(table)
    return tables


def table_row_count(result: dict[str, Any], table: str) -> int:
    return len(table_rows_for_chain(result, table))


def pending_row_count(result: dict[str, Any], table: str) -> int:
    return sum(
        1
        for row in table_rows_for_chain(result, table)
        if isinstance(row, dict) and bool(row.get("needs_confirmation", False))
    )


def table_rows_for_chain(result: dict[str, Any], table: str) -> list[Any]:
    document = result.get(table)
    if not isinstance(document, dict):
        return []
    key = "steps" if table == "process_flow" else "rows"
    rows = document.get(key, [])
    return rows if isinstance(rows, list) else []


def dedupe_texts(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
