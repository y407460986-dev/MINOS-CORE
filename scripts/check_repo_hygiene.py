"""Fail CI when generated or sensitive files are tracked by Git."""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

MAX_TRACKED_BINARY_BYTES = 20 * 1024 * 1024

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = (
    ".env",
    ".env.*",
    "secrets.json",
    "credentials.json",
    "auth.json",
    "*.credentials",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
)
SECRET_EXCEPTIONS = (".env.example",)

GENERATED_PATTERNS = (
    "dist/*",
    "build/*",
    "out/*",
    "output/*",
    "outputs/*",
    "reports/*",
    "tmp/*",
    "temp/*",
    "apps/*/dist/*",
    "apps/*/src-tauri/target/*",
    "apps/*/src-tauri/binaries/*",
    "apps/*/node_modules/*",
    "test-results/*",
)

RELEASE_PATTERNS = (
    "release/*.exe",
    "release/**/*.exe",
    "release/*.pdf",
    "release/**/*.pdf",
)

BINARY_SUFFIXES = {
    ".7z",
    ".bin",
    ".dll",
    ".dmg",
    ".exe",
    ".msi",
    ".pdf",
    ".pkg",
    ".so",
    ".zip",
}


def main() -> int:
    tracked = _tracked_files()
    violations: list[str] = []
    for path in tracked:
        normalized = path.replace("\\", "/")
        if normalized in {
            "release/.gitkeep",
            "apps/desktop-tauri/src-tauri/binaries/.gitkeep",
        }:
            continue
        if _matches(normalized, SECRET_PATTERNS) and not _matches(
            normalized, SECRET_EXCEPTIONS
        ):
            violations.append(f"tracked secret-like file: {path}")
        if _matches(normalized, GENERATED_PATTERNS):
            violations.append(f"tracked generated output: {path}")
        if _matches(normalized, RELEASE_PATTERNS):
            violations.append(f"tracked release artifact: {path}")
        size = _file_size(path)
        if size > MAX_TRACKED_BINARY_BYTES and Path(path).suffix.lower() in BINARY_SUFFIXES:
            violations.append(
                f"tracked large binary: {path} ({size / (1024 * 1024):.1f} MiB)"
            )

    tracked_locks = (
        ROOT / path
        for path in tracked
        if fnmatch.fnmatchcase(path.replace("\\", "/"), "requirements/locks/*.txt")
    )
    for lock_path in tracked_locks:
        for line_number, line in enumerate(
            lock_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if re.match(r"^-e\s+(?:[A-Za-z]:[\\/]|/)", line, flags=re.IGNORECASE):
                relative = lock_path.relative_to(ROOT).as_posix()
                violations.append(
                    f"absolute editable path in lock: {relative}:{line_number}"
                )

    if violations:
        print("Repository hygiene check failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("Repository hygiene check passed.")
    return 0


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    output = result.stdout.decode("utf-8", errors="replace")
    return [item for item in output.split("\0") if item]


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _file_size(path: str) -> int:
    try:
        return (ROOT / path).stat().st_size
    except OSError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
