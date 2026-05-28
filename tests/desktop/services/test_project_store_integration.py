import os
import tempfile
import unittest

from minos_desktop.app_state import DesktopProjectState
from minos_desktop.services import DesktopProjectStore, DesktopSettingsStore


class TestProjectStoreIntegration(unittest.TestCase):
    def test_project_store_create_and_update(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            settings = DesktopSettingsStore(db_path)
            project_store = DesktopProjectStore(db_path)

            settings.set_default_output_dir(os.path.join(tmpdir, "out"))

            project = project_store.create_project(
                DesktopProjectState(
                    project_name="测试项目",
                    drawing_path="drawing.pdf",
                    context={"part_no": "A-001"},
                )
            )
            self.assertEqual(project.output_dir, os.path.join(tmpdir, "out"))

            updated = project_store.update_project(
                project.id,
                drawing_path="updated.pdf",
                context={"part_no": "A-002"},
            )
            self.assertEqual(updated.drawing_path, "updated.pdf")
            self.assertEqual(updated.context["part_no"], "A-002")


if __name__ == "__main__":
    unittest.main()
