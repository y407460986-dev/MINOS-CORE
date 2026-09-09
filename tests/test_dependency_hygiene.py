from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
HYGIENE_SCRIPT = ROOT / "scripts" / "check_repo_hygiene.py"
SIDECAR_SCRIPT = ROOT / "scripts" / "build_sidecar.ps1"
CLEAN_SCRIPT = ROOT / "scripts" / "clean_workspace.ps1"
LOCKS = (
    ROOT / "requirements" / "locks" / "linux-py311.txt",
    ROOT / "requirements" / "locks" / "windows-py311.txt",
)


def test_pyproject_is_the_only_abstract_dependency_source() -> None:
    with PYPROJECT.open("rb") as stream:
        extras = tomllib.load(stream)["project"]["optional-dependencies"]

    assert extras["build"] == ["pip-tools>=7,<8", "pyinstaller>=6,<7"]
    for legacy_name in ("all.txt", "dev.txt", "minos-core.txt"):
        assert not (ROOT / "requirements" / legacy_name).exists()


def test_platform_locks_are_portable_and_exclude_unowned_apps() -> None:
    forbidden = ("-e ", "d:\\", "d:/", "pyside6", "streamlit", "shadowsocks")

    for lock in LOCKS:
        content = lock.read_text(encoding="utf-8").lower()
        assert "--extra" in content
        assert all(value not in content for value in forbidden)


def test_ci_installs_and_checks_linux_lock() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    runs = "\n".join(
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        if str(job.get("runs-on", "")).startswith("ubuntu")
        for step in job.get("steps", [])
    )

    assert "pip install -r requirements/locks/linux-py311.txt" in runs
    assert "pip install -e . --no-deps" in runs
    assert "uv pip compile pyproject.toml" in runs
    assert "git diff --exit-code -- requirements/locks/linux-py311.txt" in runs

    windows_job = workflow["jobs"]["windows-dependency-lock"]
    windows_runs = "\n".join(
        str(step.get("run", "")) for step in windows_job["steps"]
    )
    assert windows_job["runs-on"] == "windows-latest"
    assert "--python-platform windows" in windows_runs
    assert "git diff --exit-code -- requirements/locks/windows-py311.txt" in windows_runs


def test_sidecar_build_installs_windows_lock_without_resolving() -> None:
    script = SIDECAR_SCRIPT.read_text(encoding="utf-8")

    assert "requirements\\locks\\windows-py311.txt" in script
    assert "-m pip install -r $lockFile" in script
    assert "-m pip install -e $repo --no-deps" in script
    assert "[desktop-api,ocr]" not in script


def test_hygiene_covers_locks_and_runtime_artifacts() -> None:
    script = HYGIENE_SCRIPT.read_text(encoding="utf-8")

    assert '"test-results/*"' in script
    assert '"apps/*/src-tauri/binaries/*"' in script
    assert "absolute editable path" in script

    tracked = subprocess.check_output(
        ["git", "ls-files", "test-results", "apps/desktop-tauri/src-tauri/binaries"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    assert tracked == ["apps/desktop-tauri/src-tauri/binaries/.gitkeep"]


def test_clean_script_is_preview_only_and_uses_exact_canonical_allowlist() -> None:
    script = CLEAN_SCRIPT.read_text(encoding="utf-8")

    assert "[switch] $Apply" in script
    assert "$AllowedRelativePaths" in script
    assert "$candidatePath -notin $allowedPaths" in script
    assert "LinkType" in script
    assert "Remove-Item -LiteralPath $candidatePath -Recurse -Force" in script
