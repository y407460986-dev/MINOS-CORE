from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = "3.8.6"


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_release_metadata_versions_are_3_8_6() -> None:
    pyproject = tomllib.loads(_read("pyproject.toml"))
    package_json = json.loads(_read("apps/desktop-tauri/package.json"))
    package_lock = json.loads(_read("apps/desktop-tauri/package-lock.json"))
    tauri_config = json.loads(_read("apps/desktop-tauri/src-tauri/tauri.conf.json"))
    cargo_toml = tomllib.loads(_read("apps/desktop-tauri/src-tauri/Cargo.toml"))
    cargo_lock = _read("apps/desktop-tauri/src-tauri/Cargo.lock")

    assert pyproject["project"]["version"] == RELEASE_VERSION
    assert package_json["version"] == RELEASE_VERSION
    assert package_lock["version"] == RELEASE_VERSION
    assert package_lock["packages"][""]["version"] == RELEASE_VERSION
    assert tauri_config["version"] == RELEASE_VERSION
    assert cargo_toml["package"]["version"] == RELEASE_VERSION
    assert RELEASE_VERSION in cargo_toml["package"]["description"]
    assert f'name = "minos-core-desktop"\nversion = "{RELEASE_VERSION}"' in cargo_lock


def test_runtime_version_strings_are_3_8_6() -> None:
    checks = {
        "apps/desktop-tauri/src-tauri/src/lib.rs": [
            f'version: "{RELEASE_VERSION}".to_string()',
        ],
        "minos_desktop/api/app.py": [
            f'version="{RELEASE_VERSION}"',
        ],
        "minos_desktop/api/routes_health.py": [
            f'"version": "{RELEASE_VERSION}"',
        ],
        "apps/desktop-tauri/src/App.tsx": [
            f'bootstrap?.version ?? "{RELEASE_VERSION}"',
        ],
        "apps/desktop-tauri/src/pages/SettingsPage.tsx": [
            f'bootstrap?.version ?? "{RELEASE_VERSION}"',
        ],
    }

    for relative_path, expected_snippets in checks.items():
        content = _read(relative_path)
        for snippet in expected_snippets:
            assert snippet in content, f"{relative_path} missing {snippet}"


def test_release_owned_sources_do_not_expose_old_product_versions() -> None:
    release_owned_paths = [
        "pyproject.toml",
        "apps/desktop-tauri/package.json",
        "apps/desktop-tauri/src-tauri/Cargo.toml",
        "apps/desktop-tauri/src-tauri/tauri.conf.json",
        "apps/desktop-tauri/src-tauri/src/lib.rs",
        "minos_desktop/api/app.py",
        "minos_desktop/api/routes_health.py",
        "apps/desktop-tauri/src/App.tsx",
        "apps/desktop-tauri/src/pages/SettingsPage.tsx",
    ]

    old_product_version = re.compile(r"\b(?:1\.14\.0|3\.2\.0|3\.2\.1|3\.6\.0|3\.6\.5|3\.8\.0|3\.8\.5)\b")
    for relative_path in release_owned_paths:
        assert old_product_version.search(_read(relative_path)) is None, relative_path
