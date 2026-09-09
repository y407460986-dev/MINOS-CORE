import os
import tempfile
import unittest

from minos_desktop.services import (
    DesktopKnowledgeStore,
)


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
