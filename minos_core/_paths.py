"""Runtime path helpers for source and frozen desktop builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        return Path(meipass) if meipass else Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def configs_dir() -> Path:
    return Path(os.getenv("MINOS_CONFIGS_DIR") or (resource_root() / "configs"))


def user_data_dir() -> Path:
    if override := os.getenv("MINOS_DESKTOP_DATA_DIR"):
        return Path(override)
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "MINOS-CORE"
    return Path.home() / ".local" / "share" / "MINOS-CORE"
