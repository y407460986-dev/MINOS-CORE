import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from minos_desktop.cli import main
from minos_desktop.preflight import run_desktop_preflight


class DesktopPreflightTests(unittest.TestCase):
    def test_missing_pyside6_is_warning_not_failed(self):
        real_import_module = __import__("importlib").import_module

        def fake_import_module(name, package=None):
            if name == "PySide6":
                raise ModuleNotFoundError("No module named 'PySide6'", name="PySide6")
            return real_import_module(name, package)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("importlib.import_module", side_effect=fake_import_module):
                report = run_desktop_preflight(
                    output_dir=Path(tmpdir) / "out",
                    db_path=Path(tmpdir) / "desktop.sqlite3",
                )

        self.assertNotEqual(report["status"], "failed")
        pyside6 = self._check(report, "pyside6")
        self.assertEqual(pyside6["status"], "warning")
        self.assertIn("PySide6", pyside6["message"])

    def test_sqlite_writable_check_passes_for_temp_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = run_desktop_preflight(
                output_dir=Path(tmpdir) / "out",
                db_path=Path(tmpdir) / "desktop.sqlite3",
            )

        sqlite_check = self._check(report, "sqlite_db_writable")
        self.assertEqual(sqlite_check["status"], "passed")

    def test_installed_pyside6_import_failure_becomes_failed_check(self):
        real_import_module = __import__("importlib").import_module

        def fake_import_module(name, package=None):
            if name == "PySide6":
                raise KeyError("PATH")
            return real_import_module(name, package)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("importlib.import_module", side_effect=fake_import_module):
                report = run_desktop_preflight(
                    output_dir=Path(tmpdir) / "out",
                    db_path=Path(tmpdir) / "desktop.sqlite3",
                )

        pyside6 = self._check(report, "pyside6")
        self.assertEqual(pyside6["status"], "failed")
        self.assertEqual(pyside6["failure"]["raw_error"], "'PATH'")

    def test_ai_config_details_never_expose_plain_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "MINOS_OPENAI_API_KEY": "secret-value",
                    "MINOS_OPENAI_MODEL": "gpt-test",
                    "MINOS_OPENAI_BASE_URL": "https://proxy.example/v1",
                    "MINOS_DISABLE_CODEX_CONFIG": "1",
                },
                clear=True,
            ):
                report = run_desktop_preflight(
                    output_dir=Path(tmpdir) / "out",
                    db_path=Path(tmpdir) / "desktop.sqlite3",
                )

        ai_config = self._check(report, "ai_config")
        self.assertEqual(ai_config["status"], "passed")
        self.assertTrue(ai_config["details"]["api_key_configured"])
        self.assertEqual(ai_config["details"]["api_key_source"], "environment")
        self.assertEqual(ai_config["details"]["api_key_env_name"], "MINOS_OPENAI_API_KEY")
        self.assertEqual(ai_config["details"]["responses_path"], "responses")
        self.assertNotIn("secret-value", json.dumps(report, ensure_ascii=False))

    def test_failure_payload_contains_abandon_task_option(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "missing_parent" / "desktop.sqlite3"
            with patch("sqlite3.connect", side_effect=PermissionError("Access is denied")):
                report = run_desktop_preflight(
                    output_dir=Path(tmpdir) / "out",
                    db_path=db_path,
                )

        sqlite_check = self._check(report, "sqlite_db_writable")
        self.assertEqual(sqlite_check["status"], "failed")
        self.assertEqual(sqlite_check["failure"]["raw_error"], "Access is denied")
        self.assertTrue(sqlite_check["failure"]["cause"])
        self.assertTrue(
            any("放弃任务" in option for option in sqlite_check["failure"]["options"])
        )

    def test_desktop_cli_smoke_prints_structured_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    [
                        "--smoke",
                        "--output-dir",
                        str(Path(tmpdir) / "out"),
                        "--db-path",
                        str(Path(tmpdir) / "desktop.sqlite3"),
                    ]
                )

        payload = json.loads(buffer.getvalue())
        self.assertIn(code, (0, 2))
        self.assertIn(payload["status"], ("ready", "warning", "failed"))
        self.assertIn("checks", payload)
        self.assertIn("warnings", payload)
        self.assertIn("recommendations", payload)

    def test_require_ai_config_failure_keeps_failure_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"MINOS_DISABLE_CODEX_CONFIG": "1"}, clear=True):
                report = run_desktop_preflight(
                    output_dir=Path(tmpdir) / "out",
                    db_path=Path(tmpdir) / "desktop.sqlite3",
                    require_ai_config=True,
                )

        ai_config = self._check(report, "ai_config")
        self.assertEqual(ai_config["status"], "failed")
        self.assertEqual(ai_config["failure"]["raw_error"], "AI API key 未配置；默认 smoke 不调用真实 AI 网络。")
        self.assertTrue(ai_config["failure"]["cause"])
        self.assertTrue(any("放弃任务" in option for option in ai_config["failure"]["options"]))

    def _check(self, report, name):
        for check in report["checks"]:
            if check["name"] == name:
                return check
        raise AssertionError(f"missing check: {name}")


if __name__ == "__main__":
    unittest.main()
