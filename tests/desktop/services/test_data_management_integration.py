import os
import sqlite3
import tempfile
import unittest
import zipfile

from minos_core._paths import user_data_dir
from minos_desktop.app_state import DesktopProjectState
from minos_desktop.services import (
    DesktopDataManagementService,
    DesktopProjectStore,
    DesktopRunService,
    DesktopSettingsStore,
)


class TestDataManagementServiceIntegration(unittest.TestCase):
    def test_data_management_status_reports_paths_counts_and_sizes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "minos_desktop.sqlite3")
            output_dir = os.path.join(tmpdir, "out")
            log_dir = os.path.join(tmpdir, "logs")
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(output_dir, "artifact.txt"), "w", encoding="utf-8") as file:
                file.write("12345")
            DesktopSettingsStore(db_path).set_default_output_dir(output_dir)
            project = DesktopProjectStore(db_path).create_project(
                DesktopProjectState(
                    project_name="数据管理项目",
                    drawing_path="drawing.pdf",
                    output_dir=output_dir,
                )
            )
            DesktopRunService(db_path).save_result(
                project.id,
                {"status": "needs_review", "manual_review": {"required": False, "items": []}},
                output_dir,
            )

            status = DesktopDataManagementService(
                db_path,
                output_dir,
                log_dir=log_dir,
            ).get_status()

            self.assertEqual(status["data_dir"], tmpdir)
            self.assertEqual(status["db_path"], db_path)
            self.assertEqual(status["output_dir"], output_dir)
            self.assertEqual(status["log_dir"], log_dir)
            self.assertEqual(status["backup_dir"], os.path.join(tmpdir, "backups"))
            self.assertEqual(status["project_count"], 1)
            self.assertEqual(status["run_count"], 1)
            self.assertGreaterEqual(status["knowledge_rule_count"], 1)
            self.assertGreaterEqual(status["output_size_bytes"], 5)
            self.assertGreater(status["db_size_bytes"], 0)
            self.assertEqual(status["last_backup_path"], "")
            self.assertEqual(status["last_backup_created_at"], "")

    def test_data_management_backup_includes_database_outputs_logs_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "minos_desktop.sqlite3")
            output_dir = os.path.join(tmpdir, "out")
            log_dir = os.path.join(tmpdir, "logs")
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(output_dir, "artifact.txt"), "w", encoding="utf-8") as file:
                file.write("export")
            with open(os.path.join(log_dir, "api.log"), "w", encoding="utf-8") as file:
                file.write("log")
            project = DesktopProjectStore(db_path).create_project(
                DesktopProjectState(
                    project_name="备份项目",
                    drawing_path="drawing.pdf",
                    output_dir=output_dir,
                )
            )
            DesktopRunService(db_path).save_result(
                project.id,
                {"status": "needs_review", "manual_review": {"required": False, "items": []}},
                output_dir,
            )

            result = DesktopDataManagementService(
                db_path,
                output_dir,
                log_dir=log_dir,
            ).create_backup()

            self.assertTrue(os.path.exists(result["backup_path"]))
            self.assertGreater(result["size_bytes"], 0)
            with zipfile.ZipFile(result["backup_path"]) as archive:
                names = set(archive.namelist())
            self.assertIn("minos_desktop.sqlite3", names)
            self.assertIn("backup_manifest.json", names)
            self.assertIn("out/artifact.txt", names)
            self.assertIn("logs/api.log", names)

    def test_data_management_backup_captures_sqlite_wal_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "minos_desktop.sqlite3")
            output_dir = os.path.join(tmpdir, "out")
            service = DesktopDataManagementService(db_path, output_dir)
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(
                    """
                    INSERT INTO projects (
                        project_name, drawing_path, output_dir, context_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "WAL 项目",
                        "drawing.pdf",
                        output_dir,
                        "{}",
                        "2026-05-20T00:00:00+00:00",
                        "2026-05-20T00:00:00+00:00",
                    ),
                )
                connection.commit()
                self.assertTrue(os.path.exists(f"{db_path}-wal"))

                result = service.create_backup()
            finally:
                connection.close()

            extracted_db = os.path.join(tmpdir, "backup.sqlite3")
            with zipfile.ZipFile(result["backup_path"]) as archive:
                archive.extract("minos_desktop.sqlite3", tmpdir)
            os.replace(os.path.join(tmpdir, "minos_desktop.sqlite3"), extracted_db)
            connection = sqlite3.connect(extracted_db)
            try:
                row = connection.execute("SELECT project_name FROM projects").fetchone()
            finally:
                connection.close()

            self.assertEqual(row[0], "WAL 项目")

    def test_data_management_clear_workspace_preserves_settings_knowledge_and_backups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "minos_desktop.sqlite3")
            output_dir = os.path.join(tmpdir, "out")
            backup_dir = os.path.join(tmpdir, "backups")
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(backup_dir, exist_ok=True)
            with open(os.path.join(output_dir, "artifact.txt"), "w", encoding="utf-8") as file:
                file.write("export")
            with open(os.path.join(backup_dir, "keep.zip"), "w", encoding="utf-8") as file:
                file.write("backup")
            DesktopSettingsStore(db_path).set_default_output_dir(output_dir)
            project = DesktopProjectStore(db_path).create_project(
                DesktopProjectState(
                    project_name="清空项目",
                    drawing_path="drawing.pdf",
                    output_dir=output_dir,
                )
            )
            DesktopRunService(db_path).save_result(
                project.id,
                {"status": "needs_review", "manual_review": {"required": False, "items": []}},
                output_dir,
            )

            result = DesktopDataManagementService(db_path, output_dir).clear_data(
                scope="workspace",
                delete_outputs=True,
                confirm_text="清空项目",
            )

            self.assertEqual(result["project_count"], 0)
            self.assertEqual(result["run_count"], 0)
            self.assertGreaterEqual(result["knowledge_rule_count"], 1)
            self.assertEqual(DesktopSettingsStore(db_path).get_default_output_dir(), output_dir)
            self.assertFalse(os.path.exists(os.path.join(output_dir, "artifact.txt")))
            self.assertTrue(os.path.exists(os.path.join(backup_dir, "keep.zip")))

    def test_data_management_factory_reset_clears_settings_and_reseeds_knowledge(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "minos_desktop.sqlite3")
            output_dir = os.path.join(tmpdir, "out")
            DesktopSettingsStore(db_path).set_default_output_dir(output_dir)
            project = DesktopProjectStore(db_path).create_project(
                DesktopProjectState(
                    project_name="恢复项目",
                    drawing_path="drawing.pdf",
                    output_dir=output_dir,
                )
            )
            DesktopRunService(db_path).save_result(
                project.id,
                {"status": "needs_review", "manual_review": {"required": False, "items": []}},
                output_dir,
            )

            result = DesktopDataManagementService(db_path, output_dir).clear_data(
                scope="factory_reset",
                delete_outputs=False,
                confirm_text="恢复初始状态",
            )

            self.assertEqual(result["project_count"], 0)
            self.assertEqual(result["run_count"], 0)
            self.assertGreaterEqual(result["knowledge_rule_count"], 1)
            self.assertEqual(DesktopSettingsStore(db_path).get_default_output_dir(), str(user_data_dir() / "out"))

    def test_data_management_clear_rejects_wrong_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "minos_desktop.sqlite3")
            output_dir = os.path.join(tmpdir, "out")
            service = DesktopDataManagementService(db_path, output_dir)

            with self.assertRaises(ValueError):
                service.clear_data(
                    scope="workspace",
                    delete_outputs=False,
                    confirm_text="错误确认",
                )


if __name__ == "__main__":
    unittest.main()
