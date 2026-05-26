import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class RuntimePathsTest(unittest.TestCase):
    def test_pyinstaller_spec_uses_package_entrypoint_launcher(self):
        spec_text = Path("minos-desktop-api.spec").read_text(encoding="utf-8")

        self.assertIn('"scripts/entrypoint_desktop_api.py"', spec_text)
        self.assertNotIn('"minos_desktop/api/cli.py"', spec_text)
        self.assertIn('pathex=[str(repo_root)]', spec_text)

    def test_pyinstaller_spec_collects_dynamic_business_submodules(self):
        spec_text = Path("minos-desktop-api.spec").read_text(encoding="utf-8")

        self.assertIn("collect_submodules", spec_text)
        self.assertIn('collect_submodules("minos_core")', spec_text)
        self.assertIn('collect_submodules("minos_desktop")', spec_text)
        self.assertNotIn('"minos_core.pipeline"', spec_text)
        self.assertNotIn('"minos_desktop.api.app"', spec_text)

    def test_sidecar_build_script_places_internal_next_to_root_exe(self):
        script_text = Path("scripts/build_sidecar.ps1").read_text(encoding="utf-8")

        self.assertIn('$destInternal = Join-Path $dest "_internal"', script_text)
        self.assertIn('Copy-Item -Recurse -Force $sourceInternal $destInternal', script_text)
        self.assertIn('python311.dll', script_text)

    def test_desktop_api_entrypoint_restores_missing_standard_streams(self):
        import scripts.entrypoint_desktop_api as entrypoint

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"LOCALAPPDATA": tmpdir}), patch.object(
                sys, "stdout", None
            ), patch.object(sys, "stderr", None):
                entrypoint._ensure_standard_streams()
                stdout_stream = sys.stdout
                stderr_stream = sys.stderr
                sys.stdout.write("stdout smoke\n")
                sys.stderr.write("stderr smoke\n")
                sys.stdout.flush()
                sys.stderr.flush()
                stdout_stream.close()
                if stderr_stream is not stdout_stream:
                    stderr_stream.close()

            log_path = Path(tmpdir) / "MINOS-CORE" / "logs" / "api-bootstrap.log"
            log_text = log_path.read_text(encoding="utf-8")

        self.assertIn("stdout smoke", log_text)
        self.assertIn("stderr smoke", log_text)

    def test_configs_dir_uses_env_override_lazily(self):
        import minos_core.config as sample_config
        import minos_core.knowledge_base as knowledge_base

        with tempfile.TemporaryDirectory() as tmpdir:
            configs = Path(tmpdir) / "configs"
            sample_dir = configs / "samples"
            knowledge_dir = configs / "knowledge"
            sample_dir.mkdir(parents=True)
            knowledge_dir.mkdir(parents=True)
            sample_path = sample_dir / "sample.json"
            sample_path.write_text(
                """
                {
                  "sample_id": "S-ENV",
                  "display_name": "Env Sample",
                  "product_family": "door_hinge",
                  "apqp_phase": "phase",
                  "language": "zh-CN",
                  "deliverable": {
                    "workbook_name": "env.xlsx",
                    "default_export_format": "xlsx"
                  }
                }
                """,
                encoding="utf-8",
            )
            rules_path = knowledge_dir / "fmea_rules.zh-CN.json"
            rules_path.write_text(
                '{"rules": [{"rule_id": "KR-ENV", "message": "env rule"}]}',
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"MINOS_CONFIGS_DIR": str(configs)}):
                samples = sample_config.list_samples()
                rules = knowledge_base.load_knowledge_base()

        self.assertEqual([item.sample_id for item in samples], ["S-ENV"])
        self.assertEqual([item["knowledge_id"] for item in rules], ["KR-ENV"])

    def test_resource_root_uses_frozen_executable_parent_without_meipass(self):
        import minos_core._paths as _paths

        with tempfile.TemporaryDirectory() as tmpdir:
            exe_path = Path(tmpdir) / "minos-desktop-api.exe"
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "executable", str(exe_path)
            ):
                if hasattr(sys, "_MEIPASS"):
                    with patch.object(sys, "_MEIPASS", None, create=True):
                        self.assertEqual(_paths.resource_root(), Path(tmpdir))
                else:
                    self.assertEqual(_paths.resource_root(), Path(tmpdir))

    def test_desktop_defaults_use_user_data_dir_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"MINOS_DESKTOP_DATA_DIR": tmpdir}):
                import minos_desktop.services as services

                reloaded = importlib.reload(services)
                self.assertEqual(
                    reloaded.DEFAULT_DESKTOP_DB_PATH,
                    Path(tmpdir) / "minos_desktop.sqlite3",
                )
                self.assertEqual(
                    reloaded.DEFAULT_DESKTOP_OUTPUT_DIR,
                    Path(tmpdir) / "out",
                )
        import minos_desktop.services as services
        importlib.reload(services)

    def test_part_family_index_uses_env_configs_dir(self):
        import minos_core.part_family_knowledge as part_family_knowledge

        with tempfile.TemporaryDirectory() as tmpdir:
            configs = Path(tmpdir) / "configs"
            part_family_dir = configs / "knowledge" / "part_families"
            part_family_dir.mkdir(parents=True)
            (part_family_dir / "demo.json").write_text(
                """
                {
                  "schema_version": "demo",
                  "family_key": "demo",
                  "family_name": "Demo",
                  "process_route_templates": [],
                  "pfmea_patterns": [],
                  "control_plan_patterns": [],
                  "special_characteristic_patterns": []
                }
                """,
                encoding="utf-8",
            )
            (part_family_dir / "index.json").write_text(
                """
                {
                  "schema_version": "index-demo",
                  "families": [
                    {
                      "family_key": "demo",
                      "family_name": "Demo",
                      "knowledge_path": "demo.json"
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"MINOS_CONFIGS_DIR": str(configs)}):
                index = part_family_knowledge.load_part_family_index()
                families = part_family_knowledge.load_part_family_knowledge(None)

        self.assertEqual(index["schema_version"], "index-demo")
        self.assertEqual([entry["family_key"] for entry in index["families"]], ["demo"])
        self.assertIn("demo", families)
        self.assertEqual(families["demo"]["family_key"], "demo")


if __name__ == "__main__":
    unittest.main()
