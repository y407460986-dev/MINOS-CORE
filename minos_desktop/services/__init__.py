"""Desktop services for MINOS-CORE application.

This package provides SQLite-backed services for the UI-neutral desktop business layer.
"""

from .sqlite_store import DesktopSQLiteStore, DEFAULT_DESKTOP_DB_PATH
from .knowledge_store import DesktopKnowledgeStore
from .data_management_service import DesktopDataManagementService, DEFAULT_DESKTOP_OUTPUT_DIR
from .settings_store import DesktopSettingsStore
from .project_store import DesktopProjectStore
from .run_service import DesktopRunService, format_desktop_failure

__all__ = [
    "DesktopSQLiteStore",
    "DesktopKnowledgeStore",
    "DesktopDataManagementService",
    "DesktopSettingsStore",
    "DesktopProjectStore",
    "DesktopRunService",
    "format_desktop_failure",
    "DEFAULT_DESKTOP_DB_PATH",
    "DEFAULT_DESKTOP_OUTPUT_DIR",
]
