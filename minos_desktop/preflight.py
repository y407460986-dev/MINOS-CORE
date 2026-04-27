"""UI-neutral desktop delivery preflight checks."""

from __future__ import annotations

import importlib
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from .services import (
    DEFAULT_DESKTOP_DB_PATH,
    DEFAULT_DESKTOP_OUTPUT_DIR,
    DesktopSettingsStore,
    format_desktop_failure,
)


def run_desktop_preflight(
    *,
    output_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    require_ai_config: bool = False,
) -> dict[str, Any]:
    """Return a structured desktop delivery smoke report without network calls."""

    resolved_output_dir = Path(output_dir) if output_dir else DEFAULT_DESKTOP_OUTPUT_DIR
    resolved_db_path = Path(db_path) if db_path else DEFAULT_DESKTOP_DB_PATH
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    _record_pyside6_check(checks, warnings, recommendations)
    _record_ai_config_check(checks, warnings, recommendations, require_ai_config)
    _record_output_dir_check(checks, warnings, recommendations, resolved_output_dir)
    _record_sqlite_check(checks, warnings, recommendations, resolved_db_path)
    _record_desktop_entry_check(checks, warnings, recommendations)

    status = "ready"
    if any(check["status"] == "failed" for check in checks):
        status = "failed"
    elif warnings:
        status = "warning"
    return {
        "status": status,
        "checks": checks,
        "warnings": warnings,
        "recommendations": recommendations,
    }


def _record_pyside6_check(
    checks: list[dict[str, Any]],
    warnings: list[str],
    recommendations: list[str],
) -> None:
    try:
        importlib.import_module("PySide6")
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            message = "PySide6 未安装；无 Qt 环境下自检继续通过，桌面 UI 启动会被阻止。"
            warnings.append(message)
            recommendations.append('需要真实打开桌面时安装：pip install -e ".[desktop]"')
            checks.append(
                {
                    "name": "pyside6",
                    "status": "warning",
                    "message": message,
                }
            )
            return
        checks.append(_failed_check("pyside6", exc))
        recommendations.append("检查 Python 环境和 PySide6 依赖解析后重试。")
        return
    except Exception as exc:  # noqa: BLE001 - preflight should keep unexpected import failures visible
        checks.append(_failed_check("pyside6", exc))
        warnings.append("PySide6 已安装但当前环境无法正常导入，桌面 UI 启动会失败。")
        recommendations.append("检查 PATH、Qt 运行时依赖和 Python 环境后重试。")
        return
    checks.append(
        {
            "name": "pyside6",
            "status": "passed",
            "message": "PySide6 已安装。",
        }
    )


def _record_ai_config_check(
    checks: list[dict[str, Any]],
    warnings: list[str],
    recommendations: list[str],
    require_ai_config: bool,
) -> None:
    try:
        state = DesktopSettingsStore(":memory:").get_ai_config_state()
    except Exception as exc:  # noqa: BLE001 - preflight must report raw local error
        checks.append(_failed_check("ai_config", exc))
        recommendations.append("检查环境变量、Codex 配置文件格式和本机读取权限后重试。")
        return

    details = {
        "provider": state.provider,
        "model_configured": state.model_configured,
        "model_source": state.model_source,
        "base_url_configured": state.base_url_configured,
        "base_url_source": state.base_url_source,
        "api_key_configured": state.api_key_configured,
        "api_key_source": state.api_key_source,
        "api_key_env_name": state.api_key_env_name,
        "wire_api": state.wire_api,
        "responses_path": state.responses_path,
    }
    if not state.api_key_configured:
        message = "AI API key 未配置；默认 smoke 不调用真实 AI 网络。"
        warnings.append(message)
        recommendations.append("如需真实 AI 试跑，请配置 MINOS_OPENAI_API_KEY 或 OPENAI_API_KEY。")
        if require_ai_config:
            check = _failed_check("ai_config", RuntimeError(message), details)
            check["message"] = message
            checks.append(check)
        else:
            checks.append(
                {
                    "name": "ai_config",
                    "status": "warning",
                    "message": message,
                    "details": details,
                }
            )
        return
    checks.append(
        {
            "name": "ai_config",
            "status": "passed",
            "message": "AI 配置已找到；未进行网络调用。",
            "details": details,
        }
    )


def _record_output_dir_check(
    checks: list[dict[str, Any]],
    warnings: list[str],
    recommendations: list[str],
    output_dir: Path,
) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".minos_preflight_",
            suffix=".tmp",
            dir=output_dir,
            delete=False,
        ) as handle:
            handle.write("minos desktop preflight\n")
            temp_path = Path(handle.name)
        temp_path.unlink()
    except Exception as exc:  # noqa: BLE001 - exact local failure belongs in report
        checks.append(_failed_check("default_output_dir_writable", exc, {"path": str(output_dir)}))
        warnings.append("默认输出目录不可写，桌面导出会失败。")
        recommendations.append("换一个当前用户可写的输出目录后重试。")
        return
    checks.append(
        {
            "name": "default_output_dir_writable",
            "status": "passed",
            "message": "默认输出目录可写。",
            "details": {"path": str(output_dir)},
        }
    )


def _record_sqlite_check(
    checks: list[dict[str, Any]],
    warnings: list[str],
    recommendations: list[str],
    db_path: Path,
) -> None:
    connection = None
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS desktop_preflight_check "
            "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO desktop_preflight_check (value) VALUES (?)",
            ("ok",),
        )
        connection.execute("DELETE FROM desktop_preflight_check")
        connection.commit()
    except Exception as exc:  # noqa: BLE001 - exact SQLite failure belongs in report
        checks.append(_failed_check("sqlite_db_writable", exc, {"path": str(db_path)}))
        warnings.append("SQLite DB 不可写，桌面项目和运行记录无法保存。")
        recommendations.append("检查 DB 所在目录权限，或指定新的 --db-path。")
        return
    finally:
        if connection is not None:
            connection.close()
    checks.append(
        {
            "name": "sqlite_db_writable",
            "status": "passed",
            "message": "SQLite DB 可写。",
            "details": {"path": str(db_path)},
        }
    )


def _record_desktop_entry_check(
    checks: list[dict[str, Any]],
    warnings: list[str],
    recommendations: list[str],
) -> None:
    try:
        cli_module = importlib.import_module("minos_desktop.cli")
        qt_module = importlib.import_module("minos_desktop.qt_app")
        if not callable(getattr(cli_module, "main", None)):
            raise AttributeError("minos_desktop.cli.main is not callable")
        if not callable(getattr(qt_module, "run_desktop_app", None)):
            raise AttributeError("minos_desktop.qt_app.run_desktop_app is not callable")
    except Exception as exc:  # noqa: BLE001 - preflight should keep import failure visible
        checks.append(_failed_check("desktop_entry_importable", exc))
        warnings.append("桌面入口不可导入，minos-desktop 启动前置条件不满足。")
        recommendations.append("检查 minos_desktop 包安装状态和入口函数后重试。")
        return
    checks.append(
        {
            "name": "desktop_entry_importable",
            "status": "passed",
            "message": "桌面入口可导入，启动前置检查通过。",
        }
    )


def _failed_check(
    name: str,
    error: BaseException,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": "failed",
        "message": str(error),
        "failure": _failure_payload(error),
        "details": details or {},
    }


def _failure_payload(error: BaseException) -> dict[str, Any]:
    text = _redact_secrets(format_desktop_failure(error))
    return {
        "raw_error": _redact_secrets(str(error)),
        "cause": _extract_section(text, "原因判断：", "处理方案："),
        "options": _extract_options(text),
    }


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    if start_marker not in text:
        return "不确定。"
    tail = text.split(start_marker, 1)[1]
    if end_marker in tail:
        tail = tail.split(end_marker, 1)[0]
    return tail.strip() or "不确定。"


def _extract_options(text: str) -> list[str]:
    options = [
        line.split(". ", 1)[1].strip()
        for line in text.splitlines()
        if line[:2].strip().isdigit() and ". " in line
    ]
    if not any("放弃任务" in option for option in options):
        options.append("放弃任务。")
    return options


def _redact_secrets(value: str) -> str:
    redacted = value
    for name in ("MINOS_OPENAI_API_KEY", "OPENAI_API_KEY", "ARK_API_KEY"):
        secret = os.getenv(name, "")
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted
