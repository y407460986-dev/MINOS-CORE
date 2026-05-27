import json
import re
import tomllib
import unittest
from pathlib import Path

import minos_core
import minos_desktop
import minos_platform

REPO_ROOT = Path(__file__).resolve().parent.parent


class VersionConsistencyTests(unittest.TestCase):
    EXPECTED = "2.0.1"

    def test_pyproject_version(self):
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["version"], self.EXPECTED)

    def test_python_packages_expose_version(self):
        for module, name in (
            (minos_core, "minos_core"),
            (minos_desktop, "minos_desktop"),
            (minos_platform, "minos_platform"),
        ):
            with self.subTest(module=name):
                self.assertEqual(getattr(module, "__version__", None), self.EXPECTED)

    def test_tauri_metadata_versions(self):
        pkg = json.loads((REPO_ROOT / "apps/desktop-tauri/package.json").read_text(encoding="utf-8"))
        self.assertEqual(pkg["version"], self.EXPECTED)

        conf = json.loads((REPO_ROOT / "apps/desktop-tauri/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        self.assertEqual(conf["version"], self.EXPECTED)

        cargo = (REPO_ROOT / "apps/desktop-tauri/src-tauri/Cargo.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', cargo, flags=re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), self.EXPECTED)

    def test_desktop_runtime_version_uses_package_metadata(self):
        tauri_source = (
            REPO_ROOT / "apps/desktop-tauri/src-tauri/src/lib.rs"
        ).read_text(encoding="utf-8")
        app_source = (
            REPO_ROOT / "apps/desktop-tauri/src/App.tsx"
        ).read_text(encoding="utf-8")
        settings_source = (
            REPO_ROOT / "apps/desktop-tauri/src/pages/SettingsPage.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn('env!("CARGO_PKG_VERSION")', tauri_source)
        for source in (tauri_source, app_source, settings_source):
            self.assertNotIn("1.14.0", source)
            self.assertNotIn('"1.14"', source)


if __name__ == "__main__":
    unittest.main()
