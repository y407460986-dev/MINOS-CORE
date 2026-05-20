"""PyInstaller launcher for the MINOS desktop API sidecar."""

from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path


def _ensure_standard_streams() -> None:
    """Give windowed PyInstaller builds a writable stdout/stderr target."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_path = _bootstrap_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stream = log_path.open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def _bootstrap_log_path() -> Path:
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "MINOS-CORE" / "logs" / "api-bootstrap.log"
    return Path.home() / ".local" / "share" / "MINOS-CORE" / "logs" / "api-bootstrap.log"


if __name__ == "__main__":
    multiprocessing.freeze_support()
    _ensure_standard_streams()
    from minos_desktop.api.cli import main

    sys.exit(main())
