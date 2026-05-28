"""Platform-level utility functions for file and artifact operations."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from minos_core.run_manifest import sha256_file

if TYPE_CHECKING:
    from minos_platform.errors import APIError


def safe_copy_input_file_or_dir(source_path: str, dest_dir: Path) -> Path:
    """Copy a file or directory to the destination directory.

    Returns the path of the copied content inside dest_dir.
    Raises FileNotFoundError if the source doesn't exist.
    Raises ValueError if source is a file and dest_dir is a file.
    """
    src = Path(source_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Source path does not exist: {source_path}")

    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        dest_path = dest_dir / src.name
        if dest_path.exists():
            shutil.rmtree(dest_path)
        shutil.copytree(src, dest_path)
    else:
        dest_path = dest_dir / src.name
        shutil.copy2(src, dest_path)

    return dest_path


def calculate_file_sha256(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    return sha256_file(file_path)


def calculate_json_sha256(data: dict) -> str:
    """Calculate SHA256 hash of a JSON-serializable dict."""
    from minos_core import sha256_json
    return sha256_json(data)


def parse_review_patch(file_path: Path) -> dict | None:
    """Parse a review patch JSON file and return the dict, or None if parsing fails."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def calculate_directory_sha256(dir_path: Path) -> str:
    """Calculate SHA256 of a directory by hashing all files in sorted order.

    SECURITY FIX v3.1.0: Use direct import instead of __import__.
    """
    import hashlib
    from minos_core import sha256_bytes
    files = sorted(dir_path.rglob("*"))
    hasher = hashlib.sha256()
    for f in files:
        if f.is_file():
            hasher.update(f.read_bytes())
    return hasher.hexdigest()


def verify_sha256(file_path: Path, expected: str) -> bool:
    """Verify that a file's SHA256 matches the expected value."""
    actual = calculate_file_sha256(file_path)
    return actual == expected


def resolve_project_artifact_dir(project_id: str, artifacts_dir: Path | None = None) -> Path:
    """Get the artifact directory for a project, creating it if needed."""
    from minos_platform import config
    base = artifacts_dir or config.get_artifacts_dir()
    project_dir = base / project_id / "inputs"
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def resolve_project_run_artifact_dir(project_id: str, run_id: str, artifacts_dir: Path | None = None) -> Path:
    """Get the artifact directory for a specific run, creating it if needed."""
    from minos_platform import config
    base = artifacts_dir or config.get_artifacts_dir()
    run_dir = base / project_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir