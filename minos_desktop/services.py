"""SQLite-backed services for the UI-neutral desktop business layer.

This module provides backward compatibility by re-exporting all services
from the services package. New code should import directly from the
services package submodules.
"""

from .services import (
    DesktopSQLiteStore,
    DesktopKnowledgeStore,
    DesktopDataManagementService,
    DesktopSettingsStore,
    DesktopProjectStore,
    DesktopRunService,
    DEFAULT_DESKTOP_DB_PATH,
    DEFAULT_DESKTOP_OUTPUT_DIR,
)

__all__ = [
    "DesktopSQLiteStore",
    "DesktopKnowledgeStore",
    "DesktopDataManagementService",
    "DesktopSettingsStore",
    "DesktopProjectStore",
    "DesktopRunService",
    "DEFAULT_DESKTOP_DB_PATH",
    "DEFAULT_DESKTOP_OUTPUT_DIR",
]
