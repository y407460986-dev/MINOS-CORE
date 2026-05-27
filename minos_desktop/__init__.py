"""MINOS desktop sidecar and business service package."""

__version__ = "2.0.1"

from .app_state import (
    DesktopAIConfigState,
    DesktopExportRecord,
    DesktopProjectRecord,
    DesktopProjectState,
    DesktopRunRecord,
    DesktopRunState,
    GenerationRunSummary,
)
from .services import DesktopProjectStore, DesktopRunService, DesktopSettingsStore

__all__ = [
    "DesktopAIConfigState",
    "DesktopExportRecord",
    "DesktopProjectRecord",
    "DesktopProjectState",
    "DesktopProjectStore",
    "DesktopRunRecord",
    "DesktopRunService",
    "DesktopRunState",
    "DesktopSettingsStore",
    "GenerationRunSummary",
]
