"""Pure helpers shared by desktop run responsibility services."""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from minos_core.knowledge_recommendation import DEFAULT_KNOWLEDGE_RULES

from ..app_state import (
    ChainStageStates,
    DesktopRunRecord,
    StageConfirmState,
)
from ..chain_state import (
    chain_stages_from_envelope,
    confirm_chain_table,
    failed_chain_stage,
    init_chain_stages,
    invalidate_chain_after_patch,
    pending_row_count,
    table_row_count,
    table_rows_for_chain,
)
from ..chain_state import dedupe_texts as _chain_dedupe_texts
from .sqlite_store import _to_json, _utc_now


def _project_context_value(context: dict[str, Any], key: str, default: str) -> str:
    value = str((context or {}).get(key) or default).strip()
    return value or default


def _sanitize_legacy_pfmea_placeholders(
    result: dict[str, Any], chain_stages: ChainStageStates | None, *, failure_message: str
) -> tuple[dict[str, Any], ChainStageStates | None]:
    pfmea_value = result.get("pfmea") if isinstance(result, dict) else None
    if not isinstance(pfmea_value, dict):
        return (result, chain_stages)
    pfmea = pfmea_value
    rows = pfmea.get("rows")
    if not isinstance(rows, list):
        return (result, chain_stages)
    kept_rows = [row for row in rows if not _is_legacy_pfmea_placeholder(row)]
    removed_count = len(rows) - len(kept_rows)
    if removed_count <= 0:
        return (result, chain_stages)
    pfmea["rows"] = kept_rows
    if not kept_rows and failure_message:
        result["status"] = "failed"
        result["blocked_stage"] = "pfmea"
        chain_stages = _mark_pfmea_stage_failed(chain_stages)
    return (result, chain_stages)


def _is_legacy_pfmea_placeholder(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    pfmea_id = str(row.get("pfmea_id") or "").strip()
    failure_mode = str(row.get("failure_mode") or "").strip()
    review_status = str(row.get("review_status") or "").strip()
    return pfmea_id.startswith("PFMEA-SYNC-") or (
        failure_mode == "待工程人员填写失效模式" and review_status == "联动新增"
    )


def _mark_pfmea_stage_failed(chain_stages: ChainStageStates | None) -> ChainStageStates | None:
    if chain_stages is None:
        return None
    return ChainStageStates(
        pfd=chain_stages.pfd,
        pfmea=StageConfirmState(
            status="failed",
            generated_at=chain_stages.pfmea.generated_at,
            confirmed_at=chain_stages.pfmea.confirmed_at,
            confirmed_by=chain_stages.pfmea.confirmed_by,
            row_count=0,
            pending_count=0,
        ),
        cp=chain_stages.cp,
        pipeline_mode=chain_stages.pipeline_mode,
    )


def _seed_knowledge_rules(connection: sqlite3.Connection) -> None:
    existing = connection.execute("SELECT COUNT(*) AS count FROM knowledge_rules").fetchone()
    if existing and int(existing["count"]) > 0:
        return
    now = _utc_now()
    for rule in DEFAULT_KNOWLEDGE_RULES:
        rule_id = str(rule.get("rule_id", ""))
        if not rule_id:
            continue
        connection.execute(
            """
            INSERT INTO knowledge_rules
                (rule_id, category, title, payload_json, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                rule_id,
                str(rule.get("recommendation_type", "知识库推荐")),
                str(rule.get("message", rule_id)),
                _to_json(rule),
                now,
                now,
            ),
        )


def _knowledge_rule_from_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        payload = json.loads(str(row["payload_json"] or "{}"))
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "rule_id": str(row["rule_id"]),
        "category": str(row["category"]),
        "title": str(row["title"]),
        "payload": payload,
        "enabled": bool(row["enabled"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _first_env_name(names: tuple[str, ...]) -> str:
    import os

    for name in names:
        if os.getenv(name):
            return name
    return ""


def _normalize_ai_base_url(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme == "https":
        return normalized
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return normalized
    raise ValueError("AI 服务地址必须使用 HTTPS；本机 127.0.0.1/localhost 代理可使用 HTTP。")


def _apply_edit_patch(result: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    try:
        from minos_core.edit_patch import apply_edit_patch
    except ModuleNotFoundError as exc:
        if exc.name not in {"minos_core.edit_patch", "edit_patch"}:
            raise
        return _apply_edit_patch_locally(result, patch)
    updated = apply_edit_patch(result, patch)
    return _apply_desktop_patch_marks(updated, patch)


def _export_edited_three_tables(result: dict[str, Any], output_dir: Path, export_mode: str) -> dict[str, Any]:
    try:
        from minos_core.edit_patch import export_edited_three_tables
    except ModuleNotFoundError as exc:
        if exc.name not in {"minos_core.edit_patch", "edit_patch"}:
            raise
        destination = _write_three_table_result(output_dir, result)
        return {"three_table_generation_result": str(destination)}
    exported = export_edited_three_tables(result, output_dir, export_mode=export_mode)
    return exported if isinstance(exported, dict) else {"export": str(exported)}


def _apply_edit_patch_locally(result: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(result, ensure_ascii=False))
    for item in patch.get("items", []):
        if not isinstance(item, dict):
            continue
        table = str(item.get("table") or "")
        action = str(item.get("action") or "")
        if action in {"accept_recommendation", "ignore_recommendation"}:
            _apply_recommendation_action_locally(updated, item)
            continue
        if action == "resolve_change_impact":
            _apply_change_impact_action_locally(updated, item)
            continue
        if action == "resolve_review_issue":
            _apply_review_issue_action_locally(updated, item)
            continue
        rows = _editable_rows(updated, table)
        row_id_field = _row_id_field(table)
        row_id = str(item.get("row_id") or item.get("target_id") or _target_id(str(item.get("target") or "")))
        if action == "add":
            row = item.get("row", {})
            if isinstance(row, dict):
                rows.append(dict(row))
        elif action == "update":
            row = _find_row(rows, row_id_field, row_id)
            if row is not None:
                changes = item.get("changes", {})
                if not isinstance(changes, dict):
                    changes = item.get("row", {})
                if isinstance(changes, dict):
                    row.update(changes)
        elif action == "soft_delete":
            row = _find_row(rows, row_id_field, row_id)
            if row is not None:
                row["deleted"] = True
                row["soft_deleted"] = True
        elif action == "confirm":
            row = _find_row(rows, row_id_field, row_id)
            if row is not None:
                row["needs_confirmation"] = False
                row["review_status"] = "已批量确认" if _is_automation_batch_confirm(item) else "已确认"
                row["ai_inferred"] = False
    updated = _apply_desktop_patch_marks(updated, patch)
    updated["edit_patch"] = patch
    updated["quality_gate"] = _evaluate_edit_export_gate_locally(updated)
    return updated


def _apply_desktop_patch_marks(result: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    for item in patch.get("items", []) if isinstance(patch, dict) else []:
        if not isinstance(item, dict) or item.get("action") != "confirm":
            continue
        if not _is_automation_batch_confirm(item):
            continue
        table = str(item.get("table") or "")
        row_id = str(item.get("row_id") or item.get("target_id") or _target_id(str(item.get("target") or "")))
        row = _find_row(_editable_rows(result, table), _row_id_field(table), row_id)
        if row is not None:
            row["review_status"] = "已批量确认"
            row["needs_confirmation"] = False
            row["ai_inferred"] = False
    return result


def _is_automation_batch_confirm(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        return (
            str(metadata.get("confirmation_mode", "")) == "ai_recommended_batch"
            and str(metadata.get("source", "")) == "automation_review"
        )
    return (
        str(item.get("confirmation_mode", "")) == "ai_recommended_batch"
        and str(item.get("source", "")) == "automation_review"
    )


def _can_apply_after_control_plan_automation_review(run: DesktopRunRecord) -> bool:
    chain_stages = _chain_stages_from_run(run)
    if chain_stages.cp.status != "confirmed":
        return False
    review = run.current_result.get("automation_review")
    if not isinstance(review, dict):
        return False
    return review.get("review_stage") == "after_control_plan" and review.get("human_decision_priority") is True


def _apply_recommendation_action_locally(result: dict[str, Any], item: dict[str, Any]) -> None:
    metadata = result.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        return
    items = metadata.setdefault("knowledge_recommendations", [])
    if not isinstance(items, list):
        return
    target_id = str(item.get("target_id", ""))
    target = _find_metadata_item(items, "recommendation_id", target_id)
    if target is None:
        target = {"recommendation_id": target_id}
        items.append(target)
    if item.get("action") == "accept_recommendation":
        target["status"] = "已采纳"
    else:
        target["status"] = "已忽略"
        target["ignore_reason"] = str(item.get("reason", ""))


def _apply_change_impact_action_locally(result: dict[str, Any], item: dict[str, Any]) -> None:
    metadata = result.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        return
    items = metadata.setdefault("change_impacts", [])
    if not isinstance(items, list):
        return
    target_id = str(item.get("target_id", ""))
    target = _find_metadata_item(items, "item_id", target_id)
    if target is None:
        target = {"item_id": target_id}
        items.append(target)
    changes = item.get("changes", {})
    target["status"] = changes.get("status", "已处理") if isinstance(changes, dict) else "已处理"
    if str(target.get("status", "")) == "已忽略":
        target["ignore_reason"] = str(item.get("reason", ""))


def _apply_review_issue_action_locally(result: dict[str, Any], item: dict[str, Any]) -> None:
    metadata = result.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        return
    items = metadata.setdefault("review_issues", [])
    if not isinstance(items, list):
        return
    target_id = str(item.get("target_id", ""))
    target = _find_metadata_item(items, "issue_id", target_id)
    if target is None:
        target = {"issue_id": target_id}
        items.append(target)
    changes = item.get("changes", {})
    target["status"] = changes.get("status", "已处理") if isinstance(changes, dict) else "已处理"
    if str(target.get("status", "")) == "已忽略":
        target["ignore_reason"] = str(item.get("reason", ""))


def _evaluate_edit_export_gate_locally(result: dict[str, Any]) -> dict[str, Any]:
    pending: list[str] = []
    for table in ("process_flow", "pfmea", "control_plan"):
        for row in _editable_rows(result, table):
            if row.get("soft_deleted") or row.get("deleted"):
                continue
            if row.get("needs_confirmation"):
                pending.append(f"{_target_prefix(table)}:{row.get(_row_id_field(table), '')}")
    return {"allow_final_export": not pending, "final_export_allowed": not pending, "needs_confirmation_items": pending}


def _editable_rows(result: dict[str, Any], table: str) -> list[dict[str, Any]]:
    document = result.setdefault(table, {})
    if not isinstance(document, dict):
        return []
    key = "steps" if table == "process_flow" else "rows"
    rows = document.setdefault(key, [])
    return rows if isinstance(rows, list) else []


def _row_id_field(table: str) -> str:
    return {"process_flow": "process_step_id", "pfmea": "pfmea_id", "control_plan": "control_plan_id"}.get(table, "id")


def _target_prefix(table: str) -> str:
    return {"process_flow": "process_step", "pfmea": "failure_mode", "control_plan": "control_item"}.get(table, table)


def _find_row(rows: list[dict[str, Any]], row_id_field: str, row_id: str) -> dict[str, Any] | None:
    for row in rows:
        if isinstance(row, dict) and str(row.get(row_id_field, "")) == row_id:
            return row
    return None


def _find_metadata_item(items: list[Any], key: str, value: str) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and str(item.get(key, "")).strip() == value:
            return item
    return None


def _target_id(target: str) -> str:
    return target.split(":", 1)[1] if ":" in target else target


def _write_three_table_result(output_dir: str | Path, result: dict[str, Any]) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / "three_table_generation_result.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def _from_json_list(value: str) -> list[Any]:
    data = json.loads(value or "[]")
    return data if isinstance(data, list) else []


def _init_chain_stages(pfd_status: str = "not_started", *, pfd_rows: int = 0, pfd_pending: int = 0) -> ChainStageStates:
    """创建初始的链式阶段状态。"""
    return init_chain_stages(pfd_status, pfd_rows=pfd_rows, pfd_pending=pfd_pending, now=_utc_now())


def _chain_stages_from_run(run: DesktopRunRecord) -> ChainStageStates:
    """从 DesktopRunRecord 提取链式阶段状态。"""
    if run.state.chain_stages is not None:
        return run.state.chain_stages
    return ChainStageStates(pipeline_mode="batch")


def _chain_stages_from_envelope(envelope: dict[str, Any]) -> ChainStageStates | None:
    """从存储 envelope 中解析链式阶段状态。"""
    return chain_stages_from_envelope(envelope)


def _chain_file_result(envelope: dict[str, Any]) -> dict[str, Any]:
    result = envelope.get("current_result", envelope)
    if not isinstance(result, dict):
        result = {}
    result = copy.deepcopy(result)
    chain_stages = envelope.get("chain_stages")
    if isinstance(chain_stages, dict):
        result["chain_stages"] = copy.deepcopy(chain_stages)
        result["pipeline_mode"] = chain_stages.get("pipeline_mode", "chain")
    return result


def _confirm_chain_table(result: dict[str, Any], table: str, *, confirmed_by: str = "") -> None:
    confirm_chain_table(result, table, confirmed_by=confirmed_by)


def _failed_chain_stage(chain_stages: ChainStageStates | None) -> str:
    return failed_chain_stage(chain_stages)


def _invalidate_chain_after_patch(
    result: dict[str, Any], patch: dict[str, Any], chain_stages: ChainStageStates | None
) -> tuple[dict[str, Any], ChainStageStates | None]:
    """Invalidate downstream staged outputs when an upstream table changes."""
    return invalidate_chain_after_patch(result, patch, chain_stages)


def _changed_chain_tables(patch: dict[str, Any]) -> set[str]:
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


def _table_row_count(result: dict[str, Any], table: str) -> int:
    return table_row_count(result, table)


def _pending_row_count(result: dict[str, Any], table: str) -> int:
    return pending_row_count(result, table)


def _table_rows_for_chain(result: dict[str, Any], table: str) -> list[Any]:
    return table_rows_for_chain(result, table)


def _dedupe_texts(values: list[Any]) -> list[str]:
    return _chain_dedupe_texts(values)
