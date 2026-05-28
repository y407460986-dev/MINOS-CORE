"""Data management service for backup and cleanup operations."""

from __future__ import annotations

import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sqlite_store import (
    DesktopSQLiteStore,
    DEFAULT_DESKTOP_DB_PATH,
    _utc_now,
    _to_json,
    _seed_knowledge_rules,
)

from minos_core._paths import user_data_dir
from minos_core.validation import InputValidator

DEFAULT_DESKTOP_OUTPUT_DIR = user_data_dir() / "out"


class DesktopDataManagementService:
    def __init__(
        self,
        db_path: str | Path = DEFAULT_DESKTOP_DB_PATH,
        output_dir: str | Path = DEFAULT_DESKTOP_OUTPUT_DIR,
        *,
        log_dir: str | Path | None = None,
    ) -> None:
        self._store = DesktopSQLiteStore(db_path)
        self.db_path = self._store.db_path
        self.data_dir = self.db_path.parent
        self.output_dir = Path(output_dir)
        self.log_dir = Path(log_dir) if log_dir is not None else self.data_dir / "logs"
        self.backup_dir = self.data_dir / "backups"

    def get_status(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return {
            "data_dir": str(self.data_dir),
            "db_path": str(self.db_path),
            "output_dir": str(self.output_dir),
            "log_dir": str(self.log_dir),
            "backup_dir": str(self.backup_dir),
            "project_count": self._table_count("projects"),
            "run_count": self._table_count("runs"),
            "knowledge_rule_count": self._table_count("knowledge_rules"),
            "output_size_bytes": _directory_size(self.output_dir),
            "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
            **self._last_backup_fields(),
        }

    def create_backup(self) -> dict[str, Any]:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        created_at = _utc_now()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_path = self.backup_dir / f"MINOS-CORE-backup-{stamp}.zip"
        temp_db_path = self.backup_dir / f".{backup_path.stem}.sqlite3.tmp"
        source = sqlite3.connect(self.db_path)
        target = sqlite3.connect(temp_db_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        manifest = {
            "app": "MINOS-CORE",
            "created_at": created_at,
            "data_dir": str(self.data_dir),
            "db_path": str(self.db_path),
            "output_dir": str(self.output_dir),
            "log_dir": str(self.log_dir),
            "project_count": self._table_count("projects"),
            "run_count": self._table_count("runs"),
            "knowledge_rule_count": self._table_count("knowledge_rules"),
        }
        try:
            with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(temp_db_path, "minos_desktop.sqlite3")
                archive.writestr("backup_manifest.json", _to_json(manifest))
                _zip_directory(archive, self.output_dir, "out")
                _zip_directory(archive, self.log_dir, "logs")
        finally:
            temp_db_path.unlink(missing_ok=True)
        return {
            "backup_path": str(backup_path),
            "created_at": created_at,
            "size_bytes": backup_path.stat().st_size,
        }

    def clear_data(
        self,
        *,
        scope: str,
        delete_outputs: bool,
        confirm_text: str,
    ) -> dict[str, Any]:
        if scope not in {"workspace", "factory_reset"}:
            raise ValueError("unsupported data clear scope")
        expected = "清空项目" if scope == "workspace" else "恢复初始状态"
        if confirm_text != expected:
            raise ValueError(f"确认文字不匹配，请输入“{expected}”。")

        with self._store.connect() as connection:
            connection.execute("DELETE FROM runs")
            connection.execute("DELETE FROM projects")
            if scope == "factory_reset":
                connection.execute("DELETE FROM settings")
                connection.execute("DELETE FROM knowledge_rules")
                _seed_knowledge_rules(connection)

        if delete_outputs:
            _clear_directory_contents(self.output_dir, keep_names={"backups"})

        return self.get_status()

    def _table_count(self, table_name: str) -> int:
        """Count rows in a table. Only allows whitelisted table names.

        SECURITY FIX v3.1.0: Whitelist validation prevents SQL injection.
        """
        # Whitelist of allowed tables
        ALLOWED_TABLES = {"projects", "runs", "knowledge_rules", "settings"}

        if table_name not in ALLOWED_TABLES:
            raise ValueError(
                f"Invalid table name: {table_name}. Allowed: {ALLOWED_TABLES}"
            )

        with self._store.connect() as connection:
            # Safe to use f-string now that table_name is validated
            row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"]) if row else 0

    def _last_backup_fields(self) -> dict[str, str]:
        if not self.backup_dir.exists():
            return {"last_backup_path": "", "last_backup_created_at": ""}
        backups = sorted(
            self.backup_dir.glob("MINOS-CORE-backup-*.zip"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not backups:
            return {"last_backup_path": "", "last_backup_created_at": ""}
        latest = backups[0]
        created_at = datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        return {"last_backup_path": str(latest), "last_backup_created_at": created_at}

def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def _zip_directory(archive: zipfile.ZipFile, directory: Path, prefix: str) -> None:
    if not directory.exists():
        return
    for item in directory.rglob("*"):
        if not item.is_file():
            continue
        try:
            archive.write(item, str(Path(prefix) / item.relative_to(directory)))
        except OSError:
            continue


def _clear_directory_contents(path: Path, *, keep_names: set[str]) -> None:
    """Clear directory contents with path traversal protection.

    SECURITY FIX v3.1.0: Validates paths to prevent symlink attacks.
    """
    if not path.exists():
        return

    resolved_base = path.resolve()

    for item in path.iterdir():
        if item.name in keep_names:
            continue

        # Validate item is within base directory (防止符号链接攻击)
        try:
            InputValidator.validate_path_traversal(item, resolved_base)
        except Exception:
            # Skip items outside base directory
            continue

        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
