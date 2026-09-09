"""Desktop services for MINOS-CORE application.

This package provides SQLite-backed services for the UI-neutral desktop business layer.
"""

from minos_core._paths import user_data_dir
from minos_core.pipeline import analyze_drawing_for_three_table_chain

from .data_management_service import DesktopDataManagementService
from .history_store import DesktopHistoryStore
from .knowledge_store import DesktopKnowledgeStore
from .project_store import DesktopProjectStore
from .run_repository import RunRepository
from .run_service import DesktopRunService, format_desktop_failure
from .settings_store import DesktopSettingsStore
from .sqlite_store import DesktopSQLiteStore

DEFAULT_DESKTOP_DB_PATH = user_data_dir() / "minos_desktop.sqlite3"
DEFAULT_DESKTOP_OUTPUT_DIR = user_data_dir() / "out"

__all__ = [
    "DesktopSQLiteStore",
    "DesktopKnowledgeStore",
    "DesktopHistoryStore",
    "DesktopDataManagementService",
    "DesktopSettingsStore",
    "DesktopProjectStore",
    "RunRepository",
    "DesktopRunService",
    "format_desktop_failure",
    "DEFAULT_DESKTOP_DB_PATH",
    "DEFAULT_DESKTOP_OUTPUT_DIR",
    "analyze_drawing_for_three_table_chain",
]
