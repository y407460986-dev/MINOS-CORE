import os
import sqlite3
import tempfile
import unittest
import zipfile
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
    DesktopDataManagementService,
    DesktopKnowledgeStore,
    DesktopProjectStore,
    DesktopRunService,
    DesktopSQLiteStore,
    DesktopSettingsStore,
    format_desktop_failure,
)
from minos_desktop.table_editor import (
    ROW_STATUS_COLUMN,
    build_edit_patch,
    three_table_to_table_model,
)
from minos_core._paths import user_data_dir


class TestKnowledgeStoreIntegration(unittest.TestCase):
    def test_knowledge_store_seeds_adds_and_disables_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            store = DesktopKnowledgeStore(db_path)

            seeded = store.list_rules()
            added = store.add_rule(
                rule_id="LOCAL-1",
                category="失效模式库",
                title="压装不到位",
                payload={"rule_id": "LOCAL-1", "message": "考虑压装不到位"},
            )
            disabled = store.disable_rule("LOCAL-1")

        self.assertTrue(seeded)
        self.assertEqual(added["title"], "压装不到位")
        self.assertFalse(disabled["enabled"])




if __name__ == "__main__":
    unittest.main()
