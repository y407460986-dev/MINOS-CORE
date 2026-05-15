import os
import tempfile
import unittest
from unittest.mock import patch

from minos_desktop.app_state import (
    ChainStageStates,
    DesktopProjectState,
    DesktopRunState,
    StageConfirmState,
    desktop_run_state_from_result,
    summarize_generation_result,
)
from minos_desktop.api.schemas import settings_to_dict
from minos_desktop.services import (
    DesktopKnowledgeStore,
    DesktopProjectStore,
    DesktopRunService,
    DesktopSettingsStore,
    format_desktop_failure,
)
from minos_desktop.table_editor import (
    ROW_STATUS_COLUMN,
    build_edit_patch,
    three_table_to_table_model,
)

# Shared fixtures can be added here
