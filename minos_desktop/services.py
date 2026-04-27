"""SQLite-backed services for the UI-neutral desktop business layer."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from minos_core.ai_config import load_openai_responses_config
from minos_core.knowledge_recommendation import DEFAULT_KNOWLEDGE_RULES
from minos_core.pipeline import generate_three_tables_from_drawing

from .app_state import (
    DesktopAIConfigState,
    DesktopExportRecord,
    DesktopProjectRecord,
    DesktopProjectState,
    DesktopRunRecord,
    DesktopRunState,
    desktop_run_state_from_result,
)
from .table_editor import (
    EDIT_PATCH_VERSION,
    automation_batch_confirm_patch,
    automation_fix_suggestion_patch,
    build_edit_patch,
    change_impact_patch_item,
    recommendation_action_patch_item,
)

DEFAULT_DESKTOP_DB_PATH = Path("out/desktop/minos_desktop.sqlite3")
DEFAULT_DESKTOP_OUTPUT_DIR = Path("out/desktop")


class DesktopSQLiteStore:
    def __init__(self, db_path: str | Path = DEFAULT_DESKTOP_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT NOT NULL,
                    drawing_path TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER,
                    status TEXT NOT NULL,
                    blocked_stage TEXT NOT NULL,
                    exports_json TEXT NOT NULL,
                    manifest_path TEXT NOT NULL,
                    manifest_run_id TEXT NOT NULL,
                    manual_review_required INTEGER NOT NULL,
                    manual_review_count INTEGER NOT NULL,
                    manual_review_json TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    raw_result_json TEXT NOT NULL,
                    failure_message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS knowledge_rules (
                    rule_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            _seed_knowledge_rules(connection)


class DesktopSettingsStore:
    def __init__(self, db_path: str | Path = DEFAULT_DESKTOP_DB_PATH) -> None:
        self._store = DesktopSQLiteStore(db_path)

    def get_default_output_dir(self) -> str:
        value = self._get("default_output_dir")
        if value:
            return value
        return str(DEFAULT_DESKTOP_OUTPUT_DIR)

    def set_default_output_dir(self, output_dir: str | Path) -> str:
        value = str(Path(output_dir))
        self._set("default_output_dir", value)
        return value

    def get_ai_config_state(self) -> DesktopAIConfigState:
        config = load_openai_responses_config()
        model_env = _first_env_name(("MINOS_OPENAI_MODEL", "OPENAI_MODEL", "ARK_MODEL"))
        base_url_env = _first_env_name(
            ("MINOS_OPENAI_BASE_URL", "OPENAI_BASE_URL", "ARK_BASE_URL")
        )
        return DesktopAIConfigState(
            provider=config.provider,
            model=config.model,
            model_configured=bool(config.model),
            model_source=model_env or "default",
            base_url=config.base_url,
            base_url_configured=bool(config.base_url),
            base_url_source=base_url_env
            or ("codex_config" if config.codex_config_path else "default"),
            api_key_configured=config.api_key_configured,
            api_key_source=config.api_key_source,
            api_key_env_name=config.api_key_env_name,
            wire_api=config.wire_api,
            responses_path=config.responses_path,
        )

    def _get(self, key: str) -> str:
        with self._store.connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return str(row["value"]) if row else ""

    def _set(self, key: str, value: str) -> None:
        now = _utc_now()
        with self._store.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )


class DesktopProjectStore:
    def __init__(self, db_path: str | Path = DEFAULT_DESKTOP_DB_PATH) -> None:
        self._store = DesktopSQLiteStore(db_path)

    def create_project(self, state: DesktopProjectState) -> DesktopProjectRecord:
        now = _utc_now()
        output_dir = state.output_dir or DesktopSettingsStore(
            self._store.db_path
        ).get_default_output_dir()
        with self._store.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects
                    (project_name, drawing_path, output_dir, context_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    state.project_name,
                    state.drawing_path,
                    output_dir,
                    _to_json(state.context),
                    now,
                    now,
                ),
            )
            project_id = int(cursor.lastrowid)
        return self.get_project(project_id)

    def get_project(self, project_id: int) -> DesktopProjectRecord:
        with self._store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"desktop project not found: {project_id}")
        return _project_from_row(row)

    def update_project(
        self,
        project_id: int,
        *,
        project_name: str | None = None,
        drawing_path: str | None = None,
        output_dir: str | Path | None = None,
        context: dict[str, Any] | None = None,
    ) -> DesktopProjectRecord:
        current = self.get_project(project_id)
        with self._store.connect() as connection:
            connection.execute(
                """
                UPDATE projects
                SET project_name = ?,
                    drawing_path = ?,
                    output_dir = ?,
                    context_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    current.project_name if project_name is None else project_name,
                    current.drawing_path if drawing_path is None else drawing_path,
                    current.output_dir if output_dir is None else str(Path(output_dir)),
                    _to_json(current.context if context is None else context),
                    _utc_now(),
                    project_id,
                ),
            )
        return self.get_project(project_id)


class DesktopKnowledgeStore:
    def __init__(self, db_path: str | Path = DEFAULT_DESKTOP_DB_PATH) -> None:
        self._store = DesktopSQLiteStore(db_path)

    def list_rules(self, *, include_disabled: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM knowledge_rules"
        params: tuple[Any, ...] = ()
        if not include_disabled:
            query += " WHERE enabled = 1"
        query += " ORDER BY category, rule_id"
        with self._store.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_knowledge_rule_from_row(row) for row in rows]

    def add_rule(
        self,
        *,
        rule_id: str,
        category: str,
        title: str,
        payload: dict[str, Any],
        enabled: bool = True,
    ) -> dict[str, Any]:
        now = _utc_now()
        payload = dict(payload)
        payload.setdefault("rule_id", rule_id)
        with self._store.connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_rules
                    (rule_id, category, title, payload_json, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    category = excluded.category,
                    title = excluded.title,
                    payload_json = excluded.payload_json,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (rule_id, category, title, _to_json(payload), 1 if enabled else 0, now, now),
            )
        return self.get_rule(rule_id)

    def add_rule_from_recommendation(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        recommendation_id = str(recommendation.get("recommendation_id", "")).strip()
        rule_id = f"LOCAL-{recommendation_id}" if recommendation_id else f"LOCAL-{_utc_now()}"
        payload = {
            "rule_id": rule_id,
            "recommendation_type": recommendation.get("recommendation_type", "历史项目经验"),
            "message": recommendation.get("reason", ""),
            "suggested_fields": recommendation.get("suggested_fields", {}),
            "confidence": recommendation.get("confidence", 0.8),
        }
        return self.add_rule(
            rule_id=rule_id,
            category=str(recommendation.get("recommendation_type", "历史项目经验")),
            title=str(recommendation.get("reason", rule_id))[:120],
            payload=payload,
        )

    def disable_rule(self, rule_id: str) -> dict[str, Any]:
        with self._store.connect() as connection:
            connection.execute(
                "UPDATE knowledge_rules SET enabled = 0, updated_at = ? WHERE rule_id = ?",
                (_utc_now(), rule_id),
            )
        return self.get_rule(rule_id)

    def get_rule(self, rule_id: str) -> dict[str, Any]:
        with self._store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_rules WHERE rule_id = ?",
                (rule_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"knowledge rule not found: {rule_id}")
        return _knowledge_rule_from_row(row)


class DesktopRunService:
    def __init__(
        self,
        db_path: str | Path = DEFAULT_DESKTOP_DB_PATH,
        *,
        runner: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self._store = DesktopSQLiteStore(db_path)
        self._runner = runner or generate_three_tables_from_drawing

    def run_project(self, project: DesktopProjectRecord) -> DesktopRunRecord:
        try:
            result = self._runner(
                project.drawing_path,
                project.output_dir,
                context=project.context,
                export_mode="draft",
            )
        except Exception as exc:  # noqa: BLE001 - desktop service records exact failure text
            failure = format_desktop_failure(exc)
            state = DesktopRunState(
                status="failed",
                status_display="失败",
                blocked_stage="",
                exports=(),
                manifest_path="",
                manifest_run_id="",
                manual_review_required=False,
                manual_review_count=0,
                manual_review_raw_count=0,
            )
            return self.save_run(project.id, state, project.output_dir, {}, failure)
        return self.save_result(project.id, result, project.output_dir)

    def save_result(
        self,
        project_id: int | None,
        result: dict[str, Any],
        output_dir: str | Path = "",
    ) -> DesktopRunRecord:
        output_dir_text = str(output_dir)
        if output_dir_text:
            _write_three_table_result(output_dir_text, result)
        return self.save_run(
            project_id,
            desktop_run_state_from_result(result),
            output_dir_text,
            _desktop_result_envelope(result),
            "",
        )

    def save_run(
        self,
        project_id: int | None,
        state: DesktopRunState,
        output_dir: str | Path,
        raw_result: dict[str, Any],
        failure_message: str = "",
    ) -> DesktopRunRecord:
        now = _utc_now()
        exports = {record.name: record.path for record in state.exports}
        with self._store.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO runs (
                    project_id,
                    status,
                    blocked_stage,
                    exports_json,
                    manifest_path,
                    manifest_run_id,
                    manual_review_required,
                    manual_review_count,
                    manual_review_json,
                    output_dir,
                    raw_result_json,
                    failure_message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    state.status,
                    state.blocked_stage,
                    _to_json(exports),
                    state.manifest_path,
                    state.manifest_run_id,
                    1 if state.manual_review_required else 0,
                    state.manual_review_count,
                    _to_json(list(state.manual_review_items)),
                    str(output_dir),
                    _to_json(raw_result),
                    failure_message,
                    now,
                ),
            )
            run_id = int(cursor.lastrowid)
        return self.get_run(run_id)

    def get_run(self, run_id: int) -> DesktopRunRecord:
        with self._store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"desktop run not found: {run_id}")
        return _run_from_row(row)

    def list_recent_runs(self, limit: int = 10) -> list[DesktopRunRecord]:
        limit = max(1, int(limit))
        with self._store.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM runs
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_run_from_row(row) for row in rows]

    def restore_run(self, run_id: int) -> DesktopRunRecord:
        return self.get_run(run_id)

    def apply_edit_patch_to_run(
        self,
        run_id: int,
        patch: dict[str, Any],
    ) -> DesktopRunRecord:
        current = self.get_run(run_id)
        stored_payload = _stored_payload_for_run(self._store, run_id)
        stored = _stored_result_parts(stored_payload)
        edit_patch = _normalize_edit_patch(patch)
        updated_result = _apply_edit_patch(stored["current_result"], edit_patch)
        cumulative_patch = _merge_edit_patch(stored.get("edit_patch", {}), edit_patch)
        envelope = _desktop_result_envelope(
            stored["raw_result"],
            current_result=updated_result,
            edit_patch=cumulative_patch,
        )
        state = desktop_run_state_from_result(updated_result)
        exports = {record.name: record.path for record in state.exports}
        with self._store.connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET status = ?,
                    blocked_stage = ?,
                    exports_json = ?,
                    manifest_path = ?,
                    manifest_run_id = ?,
                    manual_review_required = ?,
                    manual_review_count = ?,
                    manual_review_json = ?,
                    raw_result_json = ?
                WHERE id = ?
                """,
                (
                    state.status,
                    state.blocked_stage,
                    _to_json(exports),
                    state.manifest_path,
                    state.manifest_run_id,
                    1 if state.manual_review_required else 0,
                    state.manual_review_count,
                    _to_json(list(state.manual_review_items)),
                    _to_json(envelope),
                    run_id,
                ),
            )
        if current.output_dir:
            _write_three_table_result(current.output_dir, updated_result)
        return self.get_run(run_id)

    def handle_recommendation(
        self,
        run_id: int,
        recommendation_id: str,
        *,
        accept: bool,
        reason: str = "",
    ) -> DesktopRunRecord:
        action = "accept_recommendation" if accept else "ignore_recommendation"
        item = recommendation_action_patch_item(recommendation_id, action, reason=reason)
        return self.apply_edit_patch_to_run(run_id, build_edit_patch([item]))

    def resolve_change_impact(
        self,
        run_id: int,
        item_id: str,
        *,
        status: str = "已处理",
        reason: str = "",
    ) -> DesktopRunRecord:
        item = change_impact_patch_item(item_id, status=status, reason=reason)
        return self.apply_edit_patch_to_run(run_id, build_edit_patch([item]))

    def batch_confirm_automation_review(self, run_id: int) -> DesktopRunRecord:
        current = self.get_run(run_id)
        patch = automation_batch_confirm_patch(current.current_result)
        if not patch.get("items"):
            return current
        return self.apply_edit_patch_to_run(run_id, patch)

    def accept_automation_fix_suggestion(
        self,
        run_id: int,
        row: dict[str, Any],
    ) -> DesktopRunRecord:
        patch = automation_fix_suggestion_patch(row)
        if not patch.get("items"):
            return self.get_run(run_id)
        return self.apply_edit_patch_to_run(run_id, patch)

    def export_run(
        self,
        run_id: int,
        output_dir: str | Path,
        export_mode: str = "draft",
    ) -> dict[str, Any]:
        if export_mode not in {"draft", "final"}:
            raise ValueError("export_mode must be 'draft' or 'final'")
        record = self.get_run(run_id)
        stored = _stored_result_parts(record.raw_result)
        result = stored["current_result"]
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        exported = _export_edited_three_tables(result, output_path, export_mode)
        return {
            "run_id": run_id,
            "export_mode": export_mode,
            "output_dir": str(output_path),
            "exports": exported.get("exports", exported)
            if isinstance(exported, dict)
            else {"export": str(exported)},
            "quality_gate": _evaluate_edit_export_gate(result),
            "export_result": exported,
        }


def format_desktop_failure(
    error: BaseException | str,
    *,
    reason: str | None = None,
    actions: list[str] | None = None,
) -> str:
    raw = str(error)
    reason_text = reason or _guess_failure_reason(raw)
    action_items = actions or [
        "检查图纸路径、输出目录权限和 AI 配置后重试。",
        "保留当前项目记录，修正输入后重新运行。",
        "放弃任务。",
    ]
    if not any("放弃任务" in item for item in action_items):
        action_items.append("放弃任务。")
    return "\n".join(
        [
            f"原始错误：{raw}",
            f"原因判断：{reason_text}",
            "处理方案：",
            *[f"{index}. {item}" for index, item in enumerate(action_items, start=1)],
        ]
    )


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
    manual_review_items = _from_json_list(str(row["manual_review_json"]))
    raw_result = _from_json_object(str(row["raw_result_json"]))
    stored = _stored_result_parts(raw_result)
    current_result = dict(stored["current_result"])
    if stored.get("edit_patch"):
        current_result["edit_patch"] = stored["edit_patch"]
    state = DesktopRunState(
        status=str(row["status"]),
        status_display=_status_display(str(row["status"])),
        blocked_stage=str(row["blocked_stage"]),
        exports=tuple(
            sorted(
                (
                    DesktopExportRecord(str(name), str(path))
                    for name, path in exports.items()
                ),
                key=lambda item: item.name,
            )
        ),
        manifest_path=str(row["manifest_path"]),
        manifest_run_id=str(row["manifest_run_id"]),
        manual_review_required=bool(row["manual_review_required"]),
        manual_review_count=int(row["manual_review_count"]),
        manual_review_raw_count=int(row["manual_review_count"]),
        manual_review_items=tuple(manual_review_items),
    )
    return DesktopRunRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]) if row["project_id"] is not None else None,
        state=state,
        output_dir=str(row["output_dir"]),
        raw_result=current_result,
        failure_message=str(row["failure_message"]),
        created_at=str(row["created_at"]),
        original_result=stored["raw_result"],
        current_result=current_result,
        edit_patch=stored["edit_patch"],
    )


def _stored_payload_for_run(store: DesktopSQLiteStore, run_id: int) -> dict[str, Any]:
    with store.connect() as connection:
        row = connection.execute(
            "SELECT raw_result_json FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"desktop run not found: {run_id}")
    return _from_json_object(str(row["raw_result_json"]))


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


def _guess_failure_reason(message: str) -> str:
    lowered = message.lower()
    if "references unknown evidence" in lowered or "unknown evidence" in lowered:
        return "AI 引用了不存在的图纸页面证据，通常是模型页码引用和实际渲染页数不一致。"
    if "api" in lowered or "key" in lowered:
        return "AI 配置可能缺失或不可用。"
    if "permission" in lowered or "access is denied" in lowered:
        return "输出目录或输入文件可能没有访问权限。"
    if "not found" in lowered or "no such file" in lowered:
        return "输入文件或运行依赖的路径可能不存在。"
    return "不确定。"


def _status_display(status: str) -> str:
    return {
        "draft_ready": "草案已就绪",
        "needs_review": "待人工复核",
        "blocked": "已阻断",
        "failed": "失败",
    }.get(status, status)


def _first_env_name(names: tuple[str, ...]) -> str:
    import os

    for name in names:
        if os.getenv(name):
            return name
    return ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _desktop_result_envelope(
    raw_result: dict[str, Any],
    *,
    current_result: dict[str, Any] | None = None,
    edit_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_raw = _normalize_three_table_result(raw_result)
    normalized_current = (
        _normalize_three_table_result(current_result)
        if current_result is not None
        else normalized_raw
    )
    return {
        "_desktop_storage_version": 1,
        "raw_result": normalized_raw,
        "current_result": normalized_current,
        "edit_patch": edit_patch
        if edit_patch is not None
        else {"edit_patch_version": EDIT_PATCH_VERSION, "items": []},
    }


def _merge_edit_patch(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = {"edit_patch_version": EDIT_PATCH_VERSION, "items": []}
    for source in (existing, patch):
        items = source.get("items", []) if isinstance(source, dict) else []
        if isinstance(items, list):
            merged["items"].extend(item for item in items if isinstance(item, dict))
    return merged


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


def _normalize_three_table_result(result: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(result or {})
    if any(key in normalized for key in ("process_flow", "pfmea", "control_plan")):
        normalized.setdefault("document_type", "three_table_generation_result")
        normalized.setdefault(
            "schema_version", "minos-core.three_table_generation_result.v1"
        )
        normalized.setdefault("status", "needs_review")
        normalized.setdefault("blocked_stage", None)
        normalized.setdefault("drawing_analysis", {"evidence": []})
        normalized.setdefault("process_flow", {"steps": []})
        normalized.setdefault("pfmea", {"rows": []})
        normalized.setdefault("control_plan", {"rows": []})
        normalized.setdefault("quality_gate", {})
        normalized.setdefault("quality_gates", {})
        normalized.setdefault("exports", {})
        normalized.setdefault("manifest", {})
        normalized.setdefault("manual_review", {"required": False, "items": []})
        normalized.setdefault("warnings", [])
    return normalized


def _normalize_edit_patch(patch: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(patch)
    normalized.setdefault("edit_patch_version", EDIT_PATCH_VERSION)
    items = normalized.get("items", [])
    if not isinstance(items, list):
        normalized["items"] = []
        return normalized
    normalized_items: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            normalized_items.append(item)
            continue
        normalized_item = dict(item)
        if not normalized_item.get("target_id"):
            normalized_item["target_id"] = str(
                normalized_item.get("row_id")
                or _target_id(str(normalized_item.get("target") or ""))
            ).strip()
        normalized_items.append(normalized_item)
    normalized["items"] = normalized_items
    return normalized


def _apply_edit_patch(result: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    try:
        from minos_core.edit_patch import apply_edit_patch
    except ModuleNotFoundError as exc:
        if exc.name not in {"minos_core.edit_patch", "edit_patch"}:
            raise
        return _apply_edit_patch_locally(result, patch)
    updated = apply_edit_patch(result, patch)
    return _apply_desktop_patch_marks(updated, patch)


def _evaluate_edit_export_gate(result: dict[str, Any]) -> dict[str, Any]:
    try:
        from minos_core.edit_patch import evaluate_edit_export_gate
    except ModuleNotFoundError as exc:
        if exc.name not in {"minos_core.edit_patch", "edit_patch"}:
            raise
        return _evaluate_edit_export_gate_locally(result)
    gate = evaluate_edit_export_gate(result)
    if isinstance(gate, dict):
        return gate
    if hasattr(gate, "model_dump"):
        return gate.model_dump()
    if hasattr(gate, "__dict__"):
        return dict(gate.__dict__)
    return {"allow_final_export": bool(gate)}


def _export_edited_three_tables(
    result: dict[str, Any],
    output_dir: Path,
    export_mode: str,
) -> dict[str, Any]:
    try:
        from minos_core.edit_patch import export_edited_three_tables
    except ModuleNotFoundError as exc:
        if exc.name not in {"minos_core.edit_patch", "edit_patch"}:
            raise
        destination = _write_three_table_result(output_dir, result)
        return {"three_table_generation_result": str(destination)}
    exported = export_edited_three_tables(result, output_dir, export_mode=export_mode)
    return exported if isinstance(exported, dict) else {"export": str(exported)}


def _apply_edit_patch_locally(
    result: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
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
        row_id = str(
            item.get("row_id")
            or item.get("target_id")
            or _target_id(str(item.get("target") or ""))
        )
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
                row["review_status"] = (
                    "已批量确认"
                    if _is_automation_batch_confirm(item)
                    else "已确认"
                )
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
    return (
        str(item.get("confirmation_mode", "")) == "ai_recommended_batch"
        and str(item.get("source", "")) == "automation_review"
    )


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
    return {
        "allow_final_export": not pending,
        "final_export_allowed": not pending,
        "needs_confirmation_items": pending,
    }


def _editable_rows(result: dict[str, Any], table: str) -> list[dict[str, Any]]:
    document = result.setdefault(table, {})
    if not isinstance(document, dict):
        return []
    key = "steps" if table == "process_flow" else "rows"
    rows = document.setdefault(key, [])
    return rows if isinstance(rows, list) else []


def _row_id_field(table: str) -> str:
    return {
        "process_flow": "process_step_id",
        "pfmea": "pfmea_id",
        "control_plan": "control_plan_id",
    }.get(table, "id")


def _target_prefix(table: str) -> str:
    return {
        "process_flow": "process_step",
        "pfmea": "failure_mode",
        "control_plan": "control_item",
    }.get(table, table)


def _find_row(
    rows: list[dict[str, Any]],
    row_id_field: str,
    row_id: str,
) -> dict[str, Any] | None:
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
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination


def _from_json_object(value: str) -> dict[str, Any]:
    data = json.loads(value or "{}")
    return data if isinstance(data, dict) else {}


def _from_json_list(value: str) -> list[Any]:
    data = json.loads(value or "[]")
    return data if isinstance(data, list) else []
